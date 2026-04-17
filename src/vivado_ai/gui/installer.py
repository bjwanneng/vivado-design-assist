"""
Vivado 自动安装器

通过修改 ~/.Xilinx/Vivado/init.tcl 注入 Tcl Socket Server，
使 VMC GUI 能自动连接 Vivado 并注入 Hook 脚本。
"""

import os
import platform
from pathlib import Path


class VivadoAutoInstaller:
    """Vivado 自动安装器 — 修改 init.tcl 注入 Tcl Socket Server"""

    DEFAULT_PORT = 19876
    MARKER_START = "# >>> VMC_AUTO_START >>>"
    MARKER_END = "# <<< VMC_AUTO_END <<<"

    def __init__(self):
        self.init_tcl_path = self._find_init_tcl()

    def _find_init_tcl(self) -> Path:
        if platform.system() == "Windows":
            base = Path(os.environ.get("USERPROFILE", Path.home()))
        else:
            base = Path.home()
        return base / ".Xilinx" / "Vivado" / "init.tcl"

    @property
    def is_installed(self) -> bool:
        if not self.init_tcl_path.exists():
            return False
        content = self.init_tcl_path.read_text(encoding="utf-8", errors="ignore")
        return self.MARKER_START in content

    def install(self, port: int = DEFAULT_PORT) -> bool:
        """安装 Tcl Server 到 init.tcl"""
        self.init_tcl_path.parent.mkdir(parents=True, exist_ok=True)

        existing = ""
        if self.init_tcl_path.exists():
            existing = self.init_tcl_path.read_text(encoding="utf-8", errors="ignore")

        if self.MARKER_START in existing:
            existing = self._strip_injection(existing)

        tcl_payload = self._generate_tcl_server(port)
        new_content = existing.rstrip() + "\n\n" + tcl_payload + "\n"

        self.init_tcl_path.write_text(new_content, encoding="utf-8")
        return True

    def uninstall(self) -> bool:
        """卸载：恢复原始 init.tcl"""
        if not self.init_tcl_path.exists():
            return True

        content = self.init_tcl_path.read_text(encoding="utf-8", errors="ignore")
        cleaned = self._strip_injection(content).strip()

        if cleaned:
            self.init_tcl_path.write_text(cleaned + "\n", encoding="utf-8")
        else:
            self.init_tcl_path.unlink()
        return True

    def _strip_injection(self, content: str) -> str:
        start_idx = content.find(self.MARKER_START)
        if start_idx == -1:
            return content
        end_idx = content.find(self.MARKER_END)
        if end_idx == -1:
            return content
        return content[:start_idx] + content[end_idx + len(self.MARKER_END):]

    def _generate_tcl_server(self, port: int) -> str:
        return f"""{self.MARKER_START}
# Vivado Methodology Checker (VMC) - Auto-injected Tcl Server
# To remove: run 'vivado-ai gui --uninstall'

namespace eval vmc {{
    variable port {port}
    variable clients {{}}

    proc start {{}} {{
        catch {{
            set ::vmc::server [socket -server ::vmc::accept $::vmc::port]
        }}
    }}

    proc accept {{sock addr p}} {{
        fconfigure $sock -buffering line -translation auto
        lappend ::vmc::clients $sock
        fileevent $sock readable [list ::vmc::handle $sock]
    }}

    proc handle {{sock}} {{
        if {{[eof $sock] || [catch {{gets $sock line}} err]}} {{
            close $sock
            set idx [lsearch $::vmc::clients $sock]
            set ::vmc::clients [lreplace $::vmc::clients $idx $idx]
            return
        }}
        if {{$line eq ""}} return

        if {{[catch {{set result [uplevel #0 $line]}} err]}} {{
            puts $sock "ERROR:$err"
        }} else {{
            puts $sock "OK:$result"
        }}
        flush $sock
    }}
}}

after 3000 ::vmc::start
{self.MARKER_END}"""
