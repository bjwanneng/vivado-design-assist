"""
Vivado Tcl 客户端

通过 TCP 连接 Vivado 内嵌的 Tcl Server，发送命令并接收结果。
"""

import socket
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VivadoTclClient:
    """Vivado Tcl Server 客户端"""

    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 19876
    TIMEOUT = 60
    LONG_TIMEOUT = 300

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._socket: Optional[socket.socket] = None
        self._socket_lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._socket is not None

    def connect(self, timeout: float = 5) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((self.host, self.port))
            sock.settimeout(self.TIMEOUT)
            self._socket = sock
            logger.info("Connected to Vivado at %s:%d", self.host, self.port)
            return True
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            logger.info("Cannot connect to Vivado Tcl Server at %s:%d: %s", self.host, self.port, e)
            self._socket = None
            return False

    def disconnect(self):
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _recv_response(self) -> str:
        """可靠地读取一行 Tcl Server 响应。

        Tcl Server 对每条命令只输出一行 'OK:...' 或 'ERROR:...'。
        但 open_checkpoint 等命令在 Vivado 内部会产生大量日志，
        这些日志不会写入 socket，所以 socket 上只有一行响应。
        """
        response = b""
        while True:
            chunk = self._socket.recv(65536)
            if not chunk:
                self._socket = None
                raise ConnectionError("Connection lost")
            response += chunk
            if b"\n" in response:
                break

        line = response.decode("utf-8", errors="ignore").strip()
        return line

    def execute(self, command: str, timeout: Optional[int] = None) -> str:
        if not self._socket:
            raise ConnectionError("Not connected to Vivado")

        with self._socket_lock:
            old_timeout = self._socket.gettimeout()
            # None 表示永久阻塞（覆盖任何现有超时）
            # 其他值表示设置指定超时
            if timeout is not None or old_timeout is not None:
                self._socket.settimeout(timeout)

            try:
                self._socket.sendall((command + "\n").encode("utf-8"))
                line = self._recv_response()
            finally:
                self._socket.settimeout(old_timeout)

        if line.startswith("OK:"):
            return line[3:]
        elif line.startswith("ERROR:"):
            raise RuntimeError(line[6:])
        else:
            return line

    def get_project_info(self) -> dict:
        try:
            return {
                "name": self._safe_exec("get_property NAME [current_project]"),
                "directory": self._safe_exec("file dirname [current_project_dir]"),
                "part": self._safe_exec("get_property PART [current_project]"),
                "runs_dir": self._safe_exec("get_property DIRECTORY [current_run]"),
            }
        except Exception as e:
            logger.warning("Cannot get project info: %s", e)
            return {}

    def inject_hooks(self, scripts_dir: str) -> bool:
        try:
            scripts = {
                "SYNTHESIS": f"{scripts_dir}/vm_post_synth.tcl",
                "PLACEMENT": f"{scripts_dir}/vm_post_place.tcl",
                "ROUTING":   f"{scripts_dir}/vm_post_route.tcl",
            }

            for step, script_path in scripts.items():
                cmd = (
                    f"set_property STEPS.{step}.TCL.POST "
                    f"[file normalize {{{script_path}}}] "
                    f"[get_runs [current_run]]"
                )
                self.execute(cmd)

            logger.info("Hook scripts injected")
            return True
        except Exception as e:
            logger.warning("Cannot inject hooks: %s", e)
            return False

    def find_dcp(self, stage: str) -> str:
        """查找指定阶段的 DCP 文件路径

        Vivado DCP 命名规则：
          synth:  <synth_1_dir>/<top>.dcp
          opt:    <impl_1_dir>/<top>_opt.dcp
          place:  <impl_1_dir>/<top>_placed.dcp
          route:  <impl_1_dir>/<top>_routed.dcp
        """
        run_map = {
            "synth": "synth_1",
            "opt": "impl_1",
            "place": "impl_1",
            "route": "impl_1",
            "current": "",
        }
        run_name = run_map.get(stage, "impl_1")

        if stage == "current":
            dcp_dir = self._safe_exec("get_property DIRECTORY [current_run]")
        else:
            dcp_dir = self._safe_exec(f"get_property DIRECTORY [get_runs {run_name}]")

        if not dcp_dir:
            return ""

        dcp_pattern_map = {
            "synth": "*_synth.dcp *_synth_*.dcp",
            "opt": "*_opt.dcp",
            "place": "*_placed.dcp",
            "route": "*_routed.dcp",
            "current": "*.dcp",
        }

        patterns = dcp_pattern_map.get(stage, "*.dcp")

        for pattern in patterns.split():
            dcp_files = self._safe_exec(
                f"glob -nocomplain -directory {{{dcp_dir}}} {pattern}"
            )
            if dcp_files:
                return dcp_files.split()[0]

        # synth 可能只有一个 .dcp（不带 _synth 后缀）
        if stage == "synth":
            dcp_files = self._safe_exec(
                f"glob -nocomplain -directory {{{dcp_dir}}} *.dcp"
            )
            if dcp_files:
                files = dcp_files.split()
                for f in files:
                    if "_opt" not in f and "_placed" not in f and "_routed" not in f and "_physopt" not in f:
                        return f
                return files[0]

        return ""

    def open_checkpoint_for_stage(self, stage: str) -> bool:
        """打开指定阶段的 DCP 检查点"""
        import time

        current = self._safe_exec("current_design")
        if current:
            logger.info("Design already open: %s", current)
            return True

        dcp = self.find_dcp(stage)
        if not dcp:
            logger.warning("No DCP found for stage %s", stage)
            return False

        # 确保旧设计已关闭
        self._safe_exec("close_design -quiet")
        time.sleep(1)

        logger.info("Opening checkpoint: %s", dcp)
        try:
            self.execute(f"open_checkpoint {dcp}", timeout=self.LONG_TIMEOUT)
        except RuntimeError as e:
            logger.error("Failed to open checkpoint: %s", e)
            return False

        # 等待设计真正加载完成
        for attempt in range(30):
            time.sleep(1)
            current = self._safe_exec("current_design")
            if current:
                logger.info("Design loaded: %s", current)
                return True
            logger.info("Waiting for design to load... (%d)", attempt + 1)

        logger.error("Design did not load after open_checkpoint")
        return False

    def show_objects(self, locations: list[str]) -> int:
        """在 Vivado 中高亮显示问题对象，返回成功数"""
        count = 0
        for loc in locations:
            if not loc:
                continue
            try:
                cells = self._safe_exec(
                    f"get_cells -quiet -hierarchical -filter {{NAME =~ \"*{loc}*\"}}"
                )
                if cells:
                    for c in cells.split():
                        self.execute(f"select_objects [get_cells {c}]")
                        count += 1
                    continue
                pins = self._safe_exec(
                    f"get_pins -quiet -hierarchical -filter {{NAME =~ \"*{loc}*\"}}"
                )
                if pins:
                    for p in pins.split():
                        self.execute(f"select_objects [get_pins {p}]")
                        count += 1
                    continue
                nets = self._safe_exec(
                    f"get_nets -quiet -hierarchical -filter {{NAME =~ \"*{loc}*\"}}"
                )
                if nets:
                    for n in nets.split():
                        self.execute(f"select_objects [get_nets {n}]")
                        count += 1
            except Exception:
                pass
        return count

    def run_reports_now(self, stage: str, output_dir: str) -> bool:
        try:
            if not self.open_checkpoint_for_stage(stage):
                logger.error("Cannot open design for stage %s", stage)
                return False

            safe_dir = output_dir.replace("\\", "/").replace('"', '\\"')
            Path(safe_dir).mkdir(parents=True, exist_ok=True)

            STAGE_REPORTS = {
                "opt": [
                    ("report_timing_summary", f"-max_paths 10 -file \"{safe_dir}/vm_timing_opt.rpt\""),
                    ("report_methodology", f"-file \"{safe_dir}/vm_methodology_opt.rpt\""),
                    ("report_utilization", f"-hierarchical -file \"{safe_dir}/vm_utilization_opt.rpt\""),
                    ("report_clock_interaction", f"-file \"{safe_dir}/vm_clock_interaction_opt.rpt\""),
                    ("report_clock_networks", f"-file \"{safe_dir}/vm_clock_networks_opt.rpt\""),
                    ("report_cdc", f"-file \"{safe_dir}/vm_cdc_opt.rpt\""),
                    ("report_drc", f"-file \"{safe_dir}/vm_drc_opt.rpt\""),
                    ("xilinx::designutils::report_failfast", f"-file \"{safe_dir}/vm_fail_fast_opt.rpt\""),
                    ("report_control_sets", f"-verbose -file \"{safe_dir}/vm_control_sets_opt.rpt\""),
                    ("report_high_fanout_nets", f"-timing -max_nets 20 -file \"{safe_dir}/vm_high_fanout_opt.rpt\""),
                    ("report_design_analysis", f"-congestion -file \"{safe_dir}/vm_congestion_opt.rpt\""),
                    ("report_design_analysis", f"-logic_level_distribution -file \"{safe_dir}/vm_logic_level_opt.rpt\""),
                    ("report_ram_utilization", f"-file \"{safe_dir}/vm_ram_utilization_opt.rpt\""),
                    ("report_DSP_utilization", f"-file \"{safe_dir}/vm_dsp_utilization_opt.rpt\""),
                ],
                "place": [
                    ("report_timing_summary", f"-max_paths 10 -file \"{safe_dir}/vm_timing_place.rpt\""),
                    ("report_methodology", f"-file \"{safe_dir}/vm_methodology_place.rpt\""),
                    ("report_utilization", f"-hierarchical -file \"{safe_dir}/vm_utilization_place.rpt\""),
                    ("report_clock_interaction", f"-file \"{safe_dir}/vm_clock_interaction_place.rpt\""),
                    ("report_high_fanout_nets", f"-timing -max_nets 20 -file \"{safe_dir}/vm_high_fanout_place.rpt\""),
                    ("report_design_analysis", f"-congestion -file \"{safe_dir}/vm_congestion_place.rpt\""),
                ],
                "route": [
                    ("report_timing_summary", f"-max_paths 10 -file \"{safe_dir}/vm_timing_route.rpt\""),
                    ("report_methodology", f"-file \"{safe_dir}/vm_methodology_route.rpt\""),
                    ("report_utilization", f"-hierarchical -file \"{safe_dir}/vm_utilization_route.rpt\""),
                    ("report_clock_interaction", f"-file \"{safe_dir}/vm_clock_interaction_route.rpt\""),
                    ("report_drc", f"-file \"{safe_dir}/vm_drc_route.rpt\""),
                    ("report_power", f"-file \"{safe_dir}/vm_power.rpt\""),
                    ("report_high_fanout_nets", f"-timing -max_nets 20 -file \"{safe_dir}/vm_high_fanout_route.rpt\""),
                ],
            }

            reports = STAGE_REPORTS.get(stage, STAGE_REPORTS["opt"])

            for cmd_name, args in reports:
                try:
                    self.execute(f"{cmd_name} {args}", timeout=None)
                    logger.info("Report %s generated", cmd_name)
                except RuntimeError as e:
                    logger.warning("Report %s failed: %s", cmd_name, e)

            return True
        except Exception as e:
            logger.error("Cannot run reports: %s", e)
            return False

    def get_run_status(self) -> dict:
        try:
            synth_status = self._safe_exec("get_property STATUS [get_runs synth_1]")
            synth_progress = self._safe_exec("get_property PROGRESS [get_runs synth_1]")
            impl_status = self._safe_exec("get_property STATUS [get_runs impl_1]")
            impl_progress = self._safe_exec("get_property PROGRESS [get_runs impl_1]")
            impl_step = self._safe_exec("get_property CURRENT_STEP [get_runs impl_1]")

            def stage_of(s: str) -> str:
                if "Complete" in s:
                    return "complete"
                if "Running" in s or "In Progress" in s:
                    return "running"
                if "Error" in s or "Failed" in s:
                    return "failed"
                return "not_started"

            synth_stage = stage_of(synth_status)
            impl_stage = stage_of(impl_status)

            # 推断四个阶段状态：综合, OPT, 布局, 布线
            STEPS = ["opt_design", "place_design", "phys_opt_design", "route_design"]
            step_idx = STEPS.index(impl_step) if impl_step in STEPS else -1

            phases = {
                "synth": {"status": synth_status, "progress": synth_progress, "stage": synth_stage},
                "opt":   {"status": "", "progress": "", "stage": "not_started"},
                "place": {"status": "", "progress": "", "stage": "not_started"},
                "route": {"status": "", "progress": "", "stage": "not_started"},
            }

            if impl_stage == "complete":
                for k in ["opt", "place", "route"]:
                    phases[k]["stage"] = "complete"
            elif impl_stage == "running" and step_idx >= 0:
                for i, k in enumerate(["opt", "place", "route"]):
                    if i < step_idx:
                        phases[k]["stage"] = "complete"
                    elif i == step_idx:
                        phases[k]["stage"] = "running"
                        phases[k]["progress"] = impl_progress

            phases["synth"] = {"status": synth_status, "progress": synth_progress, "stage": synth_stage}
            phases["impl_overall"] = {"status": impl_status, "progress": impl_progress, "stage": impl_stage}
            phases["current_step"] = impl_step

            return phases
        except Exception as e:
            logger.warning("Cannot get run status: %s", e)
            return {}

    def _safe_exec(self, command: str) -> str:
        try:
            return self.execute(command)
        except Exception:
            return ""
