"""
XDC 约束文件解析器

提取 XDC 文件中的约束命令，用于 Lint 模式的静态检查。
"""

import re
from pathlib import Path

from vivado_ai.models.finding import XDCCommand, XDCData


class XDCParser:
    """
    解析 XDC 约束文件

    提取:
    - create_clock / create_generated_clock
    - set_input_delay / set_output_delay
    - set_clock_groups / set_false_path
    - set_max_delay / set_min_delay
    - set_multicycle_path
    - set_case_analysis / set_disable_timing
    - set_clock_uncertainty
    - set_property (物理约束)
    - set_bus_skew
    """

    COMMAND_TYPES = [
        "create_clock",
        "create_generated_clock",
        "set_input_delay",
        "set_output_delay",
        "set_clock_groups",
        "set_false_path",
        "set_max_delay",
        "set_min_delay",
        "set_multicycle_path",
        "set_case_analysis",
        "set_disable_timing",
        "set_clock_uncertainty",
        "set_property",
        "set_bus_skew",
    ]

    def parse(self, file_path: Path) -> XDCData:
        """解析 XDC 文件"""
        file_path = Path(file_path)
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        commands = []

        for line_no, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            for cmd_type in self.COMMAND_TYPES:
                if stripped.startswith(cmd_type):
                    commands.append(XDCCommand(
                        type=cmd_type,
                        args=self._parse_args(stripped),
                        line=line_no,
                        file_path=str(file_path),
                        raw=stripped,
                    ))
                    break

        return XDCData(
            commands=commands,
            file_path=str(file_path),
        )

    def parse_string(self, content: str) -> XDCData:
        """解析 XDC 字符串"""
        commands = []
        for line_no, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for cmd_type in self.COMMAND_TYPES:
                if stripped.startswith(cmd_type):
                    commands.append(XDCCommand(
                        type=cmd_type,
                        args=self._parse_args(stripped),
                        line=line_no,
                        raw=stripped,
                    ))
                    break
        return XDCData(commands=commands)

    def _parse_args(self, line: str) -> dict:
        """简化的 XDC 参数解析"""
        args = {}

        # -name
        name_match = re.search(r'-name\s+(\S+)', line)
        if name_match:
            args["name"] = name_match.group(1).strip('"')

        # -period
        period_match = re.search(r'-period\s+([\d.]+)', line)
        if period_match:
            args["period"] = float(period_match.group(1))

        # -clock
        clock_match = re.search(r'-clock\s+(?:\[(.*?)\]|(\S+))', line)
        if clock_match:
            args["clock"] = (
                clock_match.group(1) or clock_match.group(2)
            ).strip('"')

        # get_ports target
        port_match = re.search(
            r'get_ports\s+(?:-of_objects\s+\S+\s+)?\[(\S+)\]|'
            r'get_ports\s+(\[\S+\]|\S+)',
            line,
        )
        if port_match:
            args["port"] = (port_match.group(1) or port_match.group(2)).strip('[]')

        # Boolean flags
        for flag in ("asynchronous", "logically_exclusive",
                     "physically_exclusive", "datapath_only"):
            if f"-{flag}" in line:
                args[flag] = True

        # -group (multiple)
        groups = re.findall(r'-group\s+(?:\[(.*?)\]|(\S+))', line)
        if groups:
            args["groups"] = [g[0] or g[1] for g in groups]

        # -max / -min for delay
        max_match = re.search(r'-max\s+([-\d.]+)', line)
        if max_match:
            args["max_delay"] = float(max_match.group(1))
        min_match = re.search(r'-min\s+([-\d.]+)', line)
        if min_match:
            args["min_delay"] = float(min_match.group(1))

        return args
