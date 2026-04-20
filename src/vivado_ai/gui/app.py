"""
VMC GUI 后端 — 浮窗应用核心逻辑

编排: 自动安装 → 探测 Vivado → 连接 → 注入 Hook → 监控 → 分析
暴露给 pywebview 前端的 JavaScript API。
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Callable

import psutil
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from vivado_ai.core.engine import MethodologyEngine, CheckConfig, CheckMode
from vivado_ai.gui.installer import VivadoAutoInstaller
from vivado_ai.gui.tcl_client import VivadoTclClient
from vivado_ai.gui.hooks import HookScriptGenerator

logger = logging.getLogger(__name__)


class VivadoProbe:
    """探测本机运行的 Vivado 进程"""

    VIVADO_NAMES = ["vivado", "vivado.bat", "vivado64", "vivado.exe"]

    def scan(self) -> Optional[dict]:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info["name"] or "").lower()
                if any(vn in name for vn in self.VIVADO_NAMES):
                    return {"pid": proc.info["pid"], "name": proc.info["name"]}
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None


class BuildWatchdogHandler(FileSystemEventHandler):
    """监控 DONE 标记文件"""

    def __init__(self, callback: Callable[[str], None]):
        self.callback = callback
        self._processed: set[str] = set()

    def on_created(self, event):
        path = Path(event.src_path)
        name = path.name
        if name.startswith("vm_") and name.endswith("_done"):
            if name not in self._processed:
                self._processed.add(name)
                stage = name[3:-5]  # vm_synth_done -> synth
                self.callback(stage)


class Backend:
    """
    VMC 浮窗后端

    暴露给 pywebview 的 JavaScript 前端调用。
    状态机: init -> waiting -> ready -> analyzing -> results
    """

    def __init__(self):
        self.installer = VivadoAutoInstaller()
        self.probe = VivadoProbe()
        self.tcl_client: Optional[VivadoTclClient] = None
        self.hooks: Optional[HookScriptGenerator] = None

        self._state = "init"
        self._project_info: dict = {}
        self._analysis_result: Optional[dict] = None
        self._observer: Optional[Observer] = None
        self._window = None
        self._polling = True

    # ── 前端可读属性 ──

    @property
    def state(self) -> str:
        return self._state

    @property
    def project_info(self) -> dict:
        return self._project_info

    @property
    def analysis_result(self) -> Optional[dict]:
        return self._analysis_result

    # ── 初始化 ──

    def initialize(self) -> dict:
        """应用启动时调用"""
        was_installed = self.installer.is_installed
        self.installer.install()
        self._set_state("waiting")
        self._start_polling()
        return {"installed": True, "need_restart": not was_installed}

    # ── 后台轮询 ──

    def _start_polling(self):
        def poll_loop():
            while self._polling:
                self._try_connect()
                time.sleep(5)

        thread = threading.Thread(target=poll_loop, daemon=True)
        thread.start()

    def _try_connect(self):
        if self.tcl_client and self.tcl_client.is_connected:
            return

        proc = self.probe.scan()
        if not proc:
            if self._state == "ready":
                self._set_state("waiting")
            return

        client = VivadoTclClient()
        if client.connect():
            self.tcl_client = client
            self._on_connected()

    def _on_connected(self):
        self._project_info = self.tcl_client.get_project_info()

        hooks_dir = self._get_hooks_dir()
        self.hooks = HookScriptGenerator(hooks_dir)
        self.hooks.generate_all()

        self.tcl_client.inject_hooks(self.hooks.scripts_dir)
        self._start_watching()
        self._set_state("ready")

    def _get_hooks_dir(self) -> str:
        if self._project_info.get("runs_dir"):
            return str(Path(self._project_info["runs_dir"]) / "vmc_hooks")
        return str(Path.home() / ".vmc" / "hooks")

    # ── 文件监控 ──

    def _start_watching(self):
        if not self.hooks:
            return

        handler = BuildWatchdogHandler(self._on_stage_done)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.hooks.reports_dir), recursive=False)
        self._observer.start()

    def _on_stage_done(self, stage: str):
        logger.info("Stage %s completed", stage)
        self._set_state("analyzing")

        thread = threading.Thread(target=self._run_analysis, args=(stage,), daemon=True)
        thread.start()

    # ── 分析 ──

    def _run_analysis(self, stage: str):
        try:
            reports_dir = self.hooks.reports_dir if self.hooks else None
            if not reports_dir:
                return

            config = CheckConfig(
                mode=CheckMode.CHECK,
                reports_dir=reports_dir,
                enable_ai=False,  # GUI 模式先不用 AI，保持响应快
            )
            engine = MethodologyEngine(config)
            result = engine.run()

            self._analysis_result = {
                "stage": stage,
                "score": result.score,
                "total_issues": len(result.issues),
                "root_cause_summary": result.root_cause_summary,
                "issues": [
                    {
                        "rule_id": i.rule_id,
                        "rule_name": i.rule_name,
                        "severity": i.severity.value,
                        "message": i.message,
                        "detail": i.detail,
                        "fix_suggestion": i.fix_suggestion,
                        "location": i.location,
                        "message_code": i.message_code,
                        "forum_url": i.forum_url,
                        "ug949_ref": i.ug949_ref,
                        "ai_explanation": i.ai_explanation,
                    }
                    for i in result.issues
                ],
            }

            self._set_state("results")

        except Exception as e:
            logger.error("Analysis failed: %s", e, exc_info=True)
            self._analysis_result = {"error": str(e)}
            self._set_state("results")

    # ── 手动触发 ──

    def run_now(self) -> dict:
        """前端按钮调用"""
        if not self.tcl_client or not self.tcl_client.is_connected:
            return {"error": "Not connected to Vivado"}

        self._set_state("analyzing")
        reports_dir = str(self.hooks.reports_dir) if self.hooks else ""

        success = self.tcl_client.run_reports_now(reports_dir)
        if success:
            self._run_analysis("manual")

        return {"success": success}

    # ── 卸载 ──

    def uninstall(self) -> dict:
        self.installer.uninstall()
        self._polling = False
        if self._observer:
            self._observer.stop()
        if self.tcl_client:
            self.tcl_client.disconnect()
        return {"uninstalled": True}

    # ── 状态管理 ──

    def _set_state(self, new_state: str):
        self._state = new_state
        if self._window:
            try:
                self._window.evaluate_js(
                    f"window.dispatchEvent(new CustomEvent('vmc-state',"
                    f"{{detail:'{new_state}'}}));"
                )
            except Exception:
                pass


def start_gui():
    """启动 VMC 浮窗"""
    import webview

    backend = Backend()
    frontend_path = Path(__file__).parent / "frontend" / "index.html"

    window = webview.create_window(
        title="VMC - Vivado Methodology Checker",
        url=str(frontend_path),
        js_api=backend,
        width=420,
        height=680,
        resizable=True,
    )

    backend._window = window
    webview.start(backend.initialize, debug=False)
