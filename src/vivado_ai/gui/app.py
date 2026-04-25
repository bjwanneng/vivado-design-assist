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

    def scan_all(self) -> list[dict]:
        """扫描所有 Vivado 进程，提取项目名称，返回列表"""
        results = []
        seen_pids = set()
        for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
            try:
                name = (proc.info["name"] or "").lower()
                if any(vn in name for vn in self.VIVADO_NAMES):
                    pid = proc.info["pid"]
                    if pid not in seen_pids:
                        seen_pids.add(pid)
                        cmdline = proc.info.get("cmdline") or []
                        cmdline_str = " ".join(cmdline)[:200] if cmdline else ""

                        project_name = ""
                        project_path = ""
                        for arg in cmdline:
                            if arg.endswith(".xpr"):
                                project_path = arg
                                project_name = Path(arg).stem
                                break

                        results.append({
                            "pid": pid,
                            "name": proc.info["name"],
                            "cmdline": cmdline_str,
                            "project_name": project_name,
                            "project_path": project_path,
                            "create_time": proc.info.get("create_time", 0),
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        results.sort(key=lambda x: x.get("create_time", 0) or 0)
        return results

    def probe_tcl_servers(self, base_port: int = 19876, max_port: int = 19900) -> list[dict]:
        """探测端口上可用的 Tcl Server，获取项目信息（短超时快速扫描）"""
        servers = []
        for port in range(base_port, max_port):
            client = VivadoTclClient(port=port)
            try:
                if client.connect(timeout=1):
                    proj_name = ""
                    part = ""
                    try:
                        proj_name = client.execute("get_property NAME [current_project]")
                    except Exception:
                        pass
                    try:
                        part = client.execute("get_property PART [current_project]")
                    except Exception:
                        pass
                    servers.append({
                        "port": port,
                        "project_name": proj_name or "未知项目",
                        "part": part or "",
                    })
                    client.disconnect()
            except Exception:
                pass
        return servers


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

        self._lock = threading.Lock()
        self._state = "init"
        self._project_info: dict = {}
        self._analysis_result: Optional[dict] = None
        self._observer: Optional[Observer] = None
        self._window = None
        self._polling = True
        self._analyzing = False
        self._state_callbacks: list[Callable[[str], None]] = []
        self._vivado_instances: list[dict] = []
        self._selected_port: int = 0

    # ── 前端可读属性 ──

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def project_info(self) -> dict:
        with self._lock:
            return self._project_info

    @property
    def vivado_instances(self) -> list[dict]:
        return self._vivado_instances

    def select_vivado(self, index: int):
        """用户选择连接某个 Vivado 实例"""
        instances = self._vivado_instances
        if 0 <= index < len(instances):
            self._selected_port = instances[index]["port"]
            logger.info("User selected Vivado instance %d (port %d)", index, self._selected_port)

    @property
    def analysis_result(self) -> Optional[dict]:
        with self._lock:
            return self._analysis_result

    @property
    def run_status(self) -> dict:
        if self._analyzing:
            return {}
        with self._lock:
            return self.tcl_client.get_run_status() if self.tcl_client else {}

    def add_state_callback(self, cb: Callable[[str], None]):
        """注册状态变化回调（供 web server SSE 使用）"""
        with self._lock:
            self._state_callbacks.append(cb)

    # ── 初始化 ──

    def initialize(self) -> dict:
        """应用启动时调用"""
        was_installed = self.installer.is_installed
        install_ok = self.installer.install()
        self._set_state("waiting")
        self._start_polling()
        return {"installed": install_ok, "need_restart": install_ok and not was_installed}

    # ── 后台轮询 ──

    def _start_polling(self):
        def poll_loop():
            while self._polling:
                self._try_connect()
                time.sleep(5)

        thread = threading.Thread(target=poll_loop, daemon=True)
        thread.start()

    def _try_connect(self):
        with self._lock:
            if self.tcl_client and self.tcl_client.is_connected:
                return

        instances = self.probe.scan_all()

        if not instances:
            self._vivado_instances = []
            if self.state not in ("waiting", "select_vivado"):
                self._set_state("waiting")
            return

        if self._selected_port > 0:
            self._do_connect()
            return

        tcl_servers = self.probe.probe_tcl_servers()
        self._vivado_instances = tcl_servers

        if len(tcl_servers) == 0:
            if self.state not in ("waiting", "select_vivado"):
                self._set_state("waiting")
        elif len(tcl_servers) == 1:
            self._selected_port = tcl_servers[0]["port"]
            self._do_connect()
        else:
            if self.state != "select_vivado":
                self._set_state("select_vivado")

    def _do_connect(self):
        port = self._selected_port
        logger.info("Connecting to Vivado Tcl Server on port %d...", port)
        client = VivadoTclClient(port=port)
        if client.connect():
            with self._lock:
                if self.tcl_client:
                    self.tcl_client.disconnect()
                if self._observer:
                    self._observer.stop()
                    self._observer = None

                self.tcl_client = client
            self._on_connected()
        else:
            logger.warning(
                "Vivado process found but Tcl Server not responding on port %d.",
                port,
            )

    def _on_connected(self):
        with self._lock:
            self._project_info = self.tcl_client.get_project_info()

        hooks_dir = self._get_hooks_dir()
        try:
            self.hooks = HookScriptGenerator(hooks_dir)
            self.hooks.generate_all()
            self.tcl_client.inject_hooks(self.hooks.scripts_dir)
            self._start_watching()
        except OSError:
            logger.warning("Cannot write hook scripts (read-only filesystem)")

        self._set_state("ready")

    def _get_hooks_dir(self) -> str:
        with self._lock:
            pi = self._project_info
        if pi.get("runs_dir"):
            return str(Path(pi["runs_dir"]) / "vmc_hooks")
        return str(Path.home() / ".vmc" / "hooks")

    # ── 文件监控 ──

    def _start_watching(self):
        if not self.hooks:
            return

        handler = BuildWatchdogHandler(self._on_stage_done)
        with self._lock:
            self._observer = Observer()
            self._observer.schedule(handler, str(self.hooks.reports_dir), recursive=False)
            self._observer.start()

    def _on_stage_done(self, stage: str):
        logger.info("Stage %s completed", stage)
        self._set_state("analyzing")

        thread = threading.Thread(target=self._run_analysis, args=(stage,), daemon=True)
        thread.start()

    # ── 分析 ──

    def _run_analysis(self, stage: str, stage_dir: str):
        try:
            if not Path(stage_dir).exists():
                return

            config = CheckConfig(
                mode=CheckMode.CHECK,
                reports_dir=Path(stage_dir),
                enable_ai=False,
            )
            engine = MethodologyEngine(config)
            result = engine.run()

            all_reports = self._collect_all_reports(stage_dir)

            ai_summary = ""
            if all_reports:
                ai_summary = self._run_ai_summary(stage, result, all_reports)

            analysis_result = {
                "stage": stage,
                "score": result.score,
                "total_issues": len(result.issues),
                "root_cause_summary": result.root_cause_summary,
                "ai_summary": ai_summary,
                "reports_dir": str(Path(stage_dir).parent),
                "stage_dir": stage_dir,
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

            with self._lock:
                self._analysis_result = analysis_result

            self._highlight_issues(result.issues)

            self._set_state("results")

        except Exception as e:
            logger.error("Analysis failed: %s", e, exc_info=True)
            with self._lock:
                self._analysis_result = {"error": str(e)}
            self._set_state("results")

    @staticmethod
    def _extract_report_content(rpt_file: Path) -> dict:
        """按报告类型差异化提取摘要和详情

        不同 Vivado 报告结构差异很大：
        - timing_summary: 表头在前面，关键路径在后面
        - methodology: 表格式，每行一个检查
        - utilization: 表头 + 资源表格
        - clock_interaction: 矩阵表
        - drc/cdc: 逐条列举
        - fail_fast: 摘要在前，详情在后
        - high_fanout: 表格
        - congestion: 热图数据
        - logic_level: 分布表
        - power: 分模块功耗
        """
        try:
            content = rpt_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return {"filename": rpt_file.name, "summary": "", "detail": "", "has_issue": False}

        name = rpt_file.name.lower()
        lines = content.splitlines()

        info = {
            "filename": rpt_file.name,
            "size": len(content),
            "has_issue": False,
            "summary": "",
            "detail": "",
        }

        if "timing" in name and "summary" in name:
            wns, whs, failing = "", "", ""
            for line in lines:
                if "WNS" in line and ":" in line:
                    wns = line.strip()
                if "WHS" in line and ":" in line:
                    whs = line.strip()
                if "Failing Endpoints" in line:
                    failing = line.strip()

            info["summary"] = f"{wns}\n{whs}\n{failing}"

            has_negative = False
            try:
                wns_val = float(wns.split(":")[-1].strip())
                if wns_val < 0:
                    has_negative = True
            except (ValueError, IndexError):
                pass
            try:
                whs_val = float(whs.split(":")[-1].strip())
                if whs_val < 0:
                    has_negative = True
            except (ValueError, IndexError):
                pass

            if has_negative:
                info["has_issue"] = True
                path_section = []
                in_path = False
                for line in lines:
                    if "Slack" in line and ("setup" in line.lower() or "hold" in line.lower()):
                        in_path = True
                    if in_path:
                        path_section.append(line)
                        if len(path_section) > 60:
                            break
                info["detail"] = "\n".join(path_section[:60])

        elif "methodology" in name:
            checks = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("|") and ("WARNING" in stripped or "CRITICAL" in stripped or "INFO" in stripped):
                    checks.append(stripped)
            info["summary"] = f"共 {len(checks)} 条检查结果"
            if any("CRITICAL WARNING" in c or "WARNING" in c for c in checks):
                info["has_issue"] = True
                info["detail"] = "\n".join(checks[:30])

        elif "utilization" in name:
            info["summary"] = "\n".join(lines[:30])
            for line in lines:
                parts = line.split("|")
                if len(parts) >= 4:
                    try:
                        util_str = parts[-2].strip().replace("%", "")
                        if float(util_str) > 70:
                            info["has_issue"] = True
                            if line.strip() not in info["detail"]:
                                info["detail"] += line.strip() + "\n"
                    except (ValueError, IndexError):
                        pass

        elif "clock_interaction" in name:
            info["summary"] = "\n".join(lines[:10])
            for line in lines:
                lower = line.lower()
                if "unsafe" in lower or "no-clock" in lower or "partial" in lower:
                    info["has_issue"] = True
                    info["detail"] += line.strip() + "\n"

        elif "cdc" in name:
            info["summary"] = "\n".join(lines[:15])
            for line in lines:
                lower = line.lower()
                if "warning" in lower or "error" in lower or "violation" in lower:
                    info["has_issue"] = True
                    info["detail"] += line.strip() + "\n"

        elif "drc" in name:
            info["summary"] = "\n".join(lines[:10])
            for line in lines:
                lower = line.lower()
                if ("error" in lower or "critical warning" in lower) and "|" in line:
                    info["has_issue"] = True
                    info["detail"] += line.strip() + "\n"

        elif "fail_fast" in name:
            info["summary"] = "\n".join(lines[:30])
            if "violation" in content.lower() or "failing" in content.lower():
                info["has_issue"] = True
                info["detail"] = "\n".join(lines[30:90])

        elif "control_set" in name:
            info["summary"] = "\n".join(lines[:20])
            if "high" in content.lower() or "exceed" in content.lower():
                info["has_issue"] = True
                for line in lines:
                    if "high" in line.lower() or "exceed" in line.lower():
                        info["detail"] += line.strip() + "\n"

        elif "high_fanout" in name:
            info["summary"] = "\n".join(lines[:10])
            info["detail"] = "\n".join(lines[5:35])

        elif "congestion" in name:
            info["summary"] = "\n".join(lines[:20])
            if "high" in content.lower() or "congested" in content.lower():
                info["has_issue"] = True
                info["detail"] = "\n".join(lines[20:60])

        elif "logic_level" in name:
            info["summary"] = "\n".join(lines[:30])
            if "high" in content.lower() or "exceed" in content.lower():
                info["has_issue"] = True
                info["detail"] = "\n".join(lines[10:40])

        elif "ram_utilization" in name or "dsp_utilization" in name:
            info["summary"] = "\n".join(lines[:25])

        elif "power" in name:
            info["summary"] = "\n".join(lines[:30])
            total_power = ""
            for line in lines:
                if "Total On-Chip Power" in line:
                    total_power = line.strip()
            if total_power:
                info["summary"] = total_power + "\n" + info["summary"]

        elif "clock_network" in name:
            info["summary"] = "\n".join(lines[:20])

        else:
            info["summary"] = "\n".join(lines[:30])
            lower_content = content[:5000].lower()
            if any(kw in lower_content for kw in ["error", "violation", "failing", "unsafe"]):
                info["has_issue"] = True
                for i, line in enumerate(lines):
                    lower = line.lower()
                    if any(kw in lower for kw in ["error", "violation", "failing", "unsafe"]):
                        start = max(0, i - 1)
                        end = min(len(lines), i + 4)
                        info["detail"] += "\n".join(lines[start:end]) + "\n---\n"
                        if len(info["detail"]) > 2000:
                            break

        info["summary"] = info["summary"][:1000]
        info["detail"] = info["detail"][:3000]

        return info

    def _collect_all_reports(self, stage_dir: str) -> dict:
        """收集阶段目录下所有报告的摘要和详情"""
        reports = {}
        report_dir = Path(stage_dir)
        if not report_dir.is_dir():
            return reports

        for rpt_file in sorted(report_dir.glob("*.rpt")):
            reports[rpt_file.name] = self._extract_report_content(rpt_file)

        return reports

    def _run_ai_summary(self, stage: str, result, all_reports: dict) -> str:
        """用 AI 逐报告分析，总结所有报告"""
        try:
            from vivado_ai.core.llm_provider import create_llm, LLMConfig
            from vivado_ai.utils.config import get_config

            cfg = get_config()
            llm_cfg = cfg.llm

            llm = create_llm(LLMConfig(
                provider=llm_cfg.provider,
                model=llm_cfg.model,
                api_key=llm_cfg.api_key,
                base_url=llm_cfg.base_url,
                max_tokens=llm_cfg.max_tokens,
                temperature=llm_cfg.temperature,
            ))

            stage_names = {"opt": "OPT 后", "place": "布局后", "route": "布线后"}
            stage_label = stage_names.get(stage, stage)

            issues_summary = ""
            for issue in result.issues[:20]:
                issues_summary += (
                    f"- [{issue.severity.value}] {issue.rule_id}: {issue.message}\n"
                )
                if issue.detail:
                    issues_summary += f"  详情: {issue.detail[:100]}\n"

            reports_text = ""
            problem_reports = []
            clean_reports = []

            for fname, info in all_reports.items():
                if info["has_issue"]:
                    problem_reports.append(fname)
                    reports_text += f"\n### [有问题] {fname}\n"
                    reports_text += f"摘要:\n{info['summary']}\n\n"
                    if info.get("detail"):
                        reports_text += f"问题详情:\n{info['detail']}\n"
                else:
                    clean_reports.append(fname)
                    reports_text += f"\n### [正常] {fname}\n"
                    reports_text += f"摘要:\n{info['summary'][:300]}\n"

            problem_list = ", ".join(problem_reports) if problem_reports else "无"
            clean_list = ", ".join(clean_reports) if clean_reports else "无"

            user_msg = (
                f"## {stage_label}阶段分析\n\n"
                f"评分: {result.score}/100\n"
                f"问题总数: {len(result.issues)}\n"
                f"有问题的报告: {problem_list}\n"
                f"正常的报告: {clean_list}\n\n"
                f"### 规则引擎发现的问题:\n{issues_summary}\n\n"
                f"### 各报告详细内容:\n{reports_text}\n\n"
                f"请用中文做一份简洁的分析总结：\n"
                f"1. 主要问题概述（3-5 条），指出来自哪个报告\n"
                f"2. 根因分析\n"
                f"3. 修复建议（按优先级排序，附具体 Tcl/XDC 代码）\n"
            )

            response = llm.chat(
                system_prompt=(
                    "你是 Vivado FPGA 设计方法学专家。根据报告和规则引擎的分析结果，"
                    "用简洁的中文总结主要问题、根因和修复建议。\n"
                    "要求：\n"
                    "- 对有问题的报告重点分析，指出具体数值（如 WNS、利用率百分比）\n"
                    "- 对正常的报告简要确认\n"
                    "- 修复建议必须包含具体可执行的 Tcl/XDC 代码\n"
                    "- 回答控制在 800 字以内"
                ),
                user_message=user_msg,
            )
            return response.text
        except Exception as e:
            logger.warning("AI summary failed: %s", e)
            return f"[AI 总结不可用: {e}]"

    def _highlight_issues(self, issues):
        """在 Vivado 中高亮显示问题对象"""
        with self._lock:
            client = self.tcl_client
        if not client:
            return
        fail_issues = [i for i in issues if i.severity.value in ("CRITICAL", "FAIL")][:20]
        if not fail_issues:
            return
        locations = [i.location for i in fail_issues if i.location]
        if locations:
            count = client.show_objects(locations)
            logger.info("Highlighted %d objects in Vivado", count)

    # ── 手动触发 ──

    def _get_reports_dir(self) -> str:
        """获取报告目录，支持项目目录只读时回退到用户数据目录"""
        # 优先使用 hooks 配置的目录
        if self.hooks:
            hooks_dir = Path(self.hooks.reports_dir)
            if self._is_writable(hooks_dir):
                return str(hooks_dir)

        # 尝试项目 runs 目录
        runs_dir = self._project_info.get("runs_dir", "")
        if runs_dir:
            project_reports = Path(runs_dir) / "vmc_reports"
            if self._is_writable(project_reports):
                return str(project_reports)

        # 回退到用户数据目录
        from vivado_ai.utils.config import _get_config_dir
        user_reports = _get_config_dir() / "reports"
        user_reports.mkdir(parents=True, exist_ok=True)
        return str(user_reports)

    @staticmethod
    def _is_writable(path: Path) -> bool:
        """检查目录是否可写"""
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".write_test"
            test_file.write_text("1")
            test_file.unlink()
            return True
        except OSError:
            return False

    def analyze_stage(self, stage: str) -> dict:
        """TUI 按键触发：生成报告并分析指定阶段"""
        with self._lock:
            if self._analyzing:
                return {"error": "分析正在进行中，请等待完成"}
            if not self.tcl_client or not self.tcl_client.is_connected:
                return {"error": "Not connected to Vivado"}

        self._set_state("analyzing")
        self._analyzing = True

        def _do():
            base_dir = self._get_reports_dir()
            stage_dir = str(Path(base_dir) / stage)
            Path(stage_dir).mkdir(parents=True, exist_ok=True)

            success = False
            try:
                success = self.tcl_client.run_reports_now(stage, stage_dir)
            except Exception as e:
                logger.error("Report generation failed: %s", e)

            if success:
                self._run_analysis(stage, stage_dir)
            else:
                with self._lock:
                    self._analysis_result = {
                        "error": "报告生成失败，请检查 Vivado 状态",
                        "reports_dir": base_dir,
                        "stage_dir": stage_dir,
                    }
                self._set_state("results")

            self._analyzing = False

        thread = threading.Thread(target=_do, daemon=True)
        thread.start()
        return {"success": True}

    def run_now(self) -> dict:
        """前端按钮调用"""
        return self.analyze_stage("manual")

    def clear_stage_reports(self, stage: str = "all"):
        """清理指定阶段的报告文件"""
        base_dir = Path(self._get_reports_dir())
        if not base_dir.exists():
            return

        import shutil
        if stage == "all":
            for d in base_dir.iterdir():
                if d.is_dir():
                    shutil.rmtree(d, ignore_errors=True)
            for f in base_dir.glob("vm_*.rpt"):
                f.unlink(missing_ok=True)
        else:
            stage_dir = base_dir / stage
            if stage_dir.is_dir():
                shutil.rmtree(stage_dir, ignore_errors=True)

        with self._lock:
            self._analysis_result = None
        self._set_state("ready")

    # ── 卸载 / 关闭 ──

    def shutdown(self):
        self._polling = False
        with self._lock:
            if self._observer:
                self._observer.stop()
                self._observer = None
            if self.tcl_client:
                self.tcl_client.disconnect()
                self.tcl_client = None

    def uninstall(self) -> dict:
        self.installer.uninstall()
        self.shutdown()
        return {"uninstalled": True}

    # ── 状态管理 ──

    def _set_state(self, new_state: str):
        with self._lock:
            self._state = new_state
            callbacks = list(self._state_callbacks)

        if self._window:
            try:
                self._window.evaluate_js(
                    f"window.dispatchEvent(new CustomEvent('vmc-state',"
                    f"{{detail:'{new_state}'}}));"
                )
            except Exception:
                pass
        for cb in callbacks:
            try:
                cb(new_state)
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
