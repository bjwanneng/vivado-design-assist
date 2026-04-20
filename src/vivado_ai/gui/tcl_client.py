"""
Vivado Tcl 客户端

通过 TCP 连接 Vivado 内嵌的 Tcl Server，发送命令并接收结果。
"""

import socket
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class VivadoTclClient:
    """Vivado Tcl Server 客户端"""

    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 19876
    TIMEOUT = 60  # report 命令可能耗时

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._socket: Optional[socket.socket] = None

    @property
    def is_connected(self) -> bool:
        return self._socket is not None

    def connect(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.host, self.port))
            sock.settimeout(self.TIMEOUT)
            self._socket = sock
            logger.info("Connected to Vivado at %s:%d", self.host, self.port)
            return True
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            logger.debug("Cannot connect to Vivado: %s", e)
            self._socket = None
            return False

    def disconnect(self):
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def execute(self, command: str) -> str:
        if not self._socket:
            raise ConnectionError("Not connected to Vivado")

        self._socket.sendall((command + "\n").encode("utf-8"))

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

        if line.startswith("OK:"):
            return line[3:]
        elif line.startswith("ERROR:"):
            raise RuntimeError(f"Vivado Tcl error: {line[6:]}")
        else:
            return line

    def get_project_info(self) -> dict:
        try:
            return {
                "name": self._safe_exec("get_property NAME [current_project]"),
                "directory": self._safe_exec("file dirname [current_project_dir]"),
                "part": self._safe_exec("get_property PART [current_design]"),
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

    def run_reports_now(self, output_dir: str) -> bool:
        try:
            safe_dir = output_dir.replace("\\", "/").replace('"', '\\"')
            reports = [
                ("report_timing_summary", f"-max_paths 10 -file \"{safe_dir}/vm_timing_summary.rpt\""),
                ("report_methodology", f"-file \"{safe_dir}/vm_methodology.rpt\""),
                ("report_clock_interaction", f"-file \"{safe_dir}/vm_clock_interaction.rpt\""),
                ("report_utilization", f"-file \"{safe_dir}/vm_utilization.rpt\""),
            ]

            for cmd_name, args in reports:
                try:
                    self.execute(f"{cmd_name} {args}")
                except RuntimeError as e:
                    logger.warning("Report %s failed: %s", cmd_name, e)

            return True
        except Exception as e:
            logger.warning("Cannot run reports: %s", e)
            return False

    def _safe_exec(self, command: str) -> str:
        try:
            return self.execute(f"catch {{{command}}} result; return $result")
        except Exception:
            return ""
