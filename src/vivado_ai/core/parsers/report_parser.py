"""
Vivado 报告文件解析器

解析 .rpt 文件，提取结构化数据填充到 Findings。
支持: timing_summary, methodology, clock_interaction, clock_networks,
      utilization, failfast
"""

import logging
import re
from pathlib import Path
from typing import Optional

from vivado_ai.models.finding import (
    Findings, TimingPath, TimingSummary,
    MethodologyCheck, ClockInteraction, ClockNetwork,
)

logger = logging.getLogger(__name__)


class ReportParser:
    """解析 Vivado 报告文件 (.rpt)"""

    def parse_dir(self, reports_dir: Path) -> Findings:
        """解析报告目录下的所有 .rpt 文件"""
        findings = Findings()
        reports_dir = Path(reports_dir)
        rpt_files = list(reports_dir.glob("**/*.rpt"))

        for rpt_file in rpt_files:
            try:
                content = rpt_file.read_text(encoding="utf-8", errors="ignore")
            except (OSError, PermissionError) as e:
                logger.warning("Cannot read report file %s: %s", rpt_file, e)
                continue
            name_lower = rpt_file.name.lower()

            if "timing_summary" in name_lower or (
                "timing" in name_lower and "summary" in name_lower
            ):
                findings.timing_summary = self._parse_timing_summary(content)
                findings.timing_paths = self._parse_timing_paths(content)
            elif "methodology" in name_lower:
                findings.methodology_checks = self._parse_methodology(content)
            elif "clock_interaction" in name_lower:
                findings.clock_interactions = self._parse_clock_interaction(content)
            elif "clock_network" in name_lower:
                findings.clock_networks = self._parse_clock_networks(content)
            elif "utilization" in name_lower:
                findings.utilization = self._parse_utilization(content)

        return findings

    def parse_file(self, rpt_file: Path) -> Findings:
        """解析单个 .rpt 文件"""
        findings = Findings()
        try:
            content = rpt_file.read_text(encoding="utf-8", errors="ignore")
        except (OSError, PermissionError) as e:
            logger.warning("Cannot read report file %s: %s", rpt_file, e)
            return findings
        name_lower = rpt_file.name.lower()

        if "timing_summary" in name_lower:
            findings.timing_summary = self._parse_timing_summary(content)
            findings.timing_paths = self._parse_timing_paths(content)
        elif "methodology" in name_lower:
            findings.methodology_checks = self._parse_methodology(content)
        elif "clock_interaction" in name_lower:
            findings.clock_interactions = self._parse_clock_interaction(content)
        elif "clock_network" in name_lower:
            findings.clock_networks = self._parse_clock_networks(content)
        elif "utilization" in name_lower:
            findings.utilization = self._parse_utilization(content)

        return findings

    # ─── Timing Summary ────────────────────────────────

    def _parse_timing_summary(self, content: str) -> TimingSummary:
        wns = _extract_float(r"WNS\s*:\s*([-\d.]+)", content)
        tns = _extract_float(r"TNS\s*:\s*([-\d.]+)", content)
        whs = _extract_float(r"WHS\s*:\s*([-\d.]+)", content)
        ths = _extract_float(r"THS\s*:\s*([-\d.]+)", content)
        failing = _extract_int(r"Failing Endpoints\s*:\s*(\d+)", content)
        total = _extract_int(r"Total Endpoints\s*:\s*(\d+)", content)

        return TimingSummary(
            wns=wns if wns is not None else 0,
            tns=tns if tns is not None else 0,
            whs=whs if whs is not None else 0,
            ths=ths if ths is not None else 0,
            failing_endpoints=failing if failing is not None else 0,
            total_endpoints=total if total is not None else 0,
        )

    def _parse_timing_paths(self, content: str) -> list[TimingPath]:
        """解析关键时序路径"""
        paths = []
        path_pattern = re.compile(
            r"Slack\s*\((?:setup|hold)\)\s*:\s*([-\d.]+)\s*ns.*?"
            r"Source:\s*(\S+).*?"
            r"Destination:\s*(\S+).*?"
            r"Requirement:\s*([-\d.]+)\s*ns.*?"
            r"Data Path Delay:\s*([-\d.]+)\s*ns.*?"
            r"Logic Delay:\s*([-\d.]+)\s*ns.*?"
            r"(?:Net Delay|Net Delay \(interconnect\)|Interconnect):\s*([-\d.]+)\s*ns.*?"
            r"Clock\s+(?:Path\s+)?Skew:\s*([-\d.]+)\s*ns",
            re.DOTALL,
        )
        for m in path_pattern.finditer(content):
            paths.append(TimingPath(
                slack=float(m.group(1)),
                start_point=m.group(2),
                end_point=m.group(3),
                requirement=float(m.group(4)),
                datapath_delay=float(m.group(5)),
                logic_delay=float(m.group(6)),
                net_delay=float(m.group(7)),
                clock_skew=float(m.group(8)),
            ))
        return paths

    # ─── Methodology ───────────────────────────────────

    def _parse_methodology(self, content: str) -> list[MethodologyCheck]:
        checks = []
        line_pattern = re.compile(
            r"\|\s*(TIMING-\d+|XDC\w*-\d+|UTIL-\d+|PWR-\d+|CFGBVS-\d+|"
            r"AUTO-USR-\d+|NETLIST-\d+|PDRC-\d+|DRC-\d+|PS-\d+)"
            r"\s*\|\s*"
            r"(CRITICAL WARNING|WARNING|INFO)"
            r"\s*\|\s*"
            r"(.*?)\s*\|?\s*$"
        )
        for line in content.splitlines():
            m = line_pattern.match(line)
            if m:
                checks.append(MethodologyCheck(
                    check_id=m.group(1),
                    severity=m.group(2),
                    message=m.group(3).strip(),
                ))
        return checks

    # ─── Clock Interaction ─────────────────────────────

    def _parse_clock_interaction(self, content: str) -> list[ClockInteraction]:
        interactions = []
        # 匹配表格式: | clkA | clkB | safe/unsafe/no | WNS |
        inter_pattern = re.compile(
            r"\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(\w+)\s*\|"
            r"(?:\s*([-\d.]+)\s*\|)?",
        )
        for m in inter_pattern.finditer(content):
            from_clk = m.group(1)
            to_clk = m.group(2)
            cls = m.group(3)
            # 跳过表头
            if from_clk in ("From", "Clock", "---"):
                continue
            interactions.append(ClockInteraction(
                from_clock=from_clk,
                to_clock=to_clk,
                inter_class=cls,
                wns=float(m.group(4)) if m.group(4) else None,
            ))
        return interactions

    # ─── Clock Networks ────────────────────────────────

    def _parse_clock_networks(self, content: str) -> list[ClockNetwork]:
        networks = []
        # 匹配: | clock_name | driver | endpoints |
        net_pattern = re.compile(
            r"\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(\d+)\s*\|"
        )
        for m in net_pattern.finditer(content):
            name = m.group(1)
            if name in ("Clock", "Net", "---"):
                continue
            networks.append(ClockNetwork(
                name=name,
                source_port=m.group(2),
                endpoint_count=int(m.group(3)),
            ))
        return networks

    # ─── Utilization ───────────────────────────────────

    def _parse_utilization(self, content: str) -> dict:
        util = {}
        # 匹配: | Site Type | Used | Available | Util% |
        util_pattern = re.compile(
            r"\|\s*(\S[\w\s]*?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|"
            r"\s*([-\d.]+%?)\s*\|"
        )
        for m in util_pattern.finditer(content):
            site_type = m.group(1).strip()
            if site_type in ("Site Type", "---"):
                continue
            util[site_type] = {
                "used": int(m.group(2)),
                "available": int(m.group(3)),
                "utilization": m.group(4),
            }
        return util


# ─── 工具函数 ───────────────────────────────────────────

def _extract_float(pattern: str, text: str) -> Optional[float]:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def _extract_int(pattern: str, text: str) -> Optional[int]:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None
