"""
Vivado 编译日志解析器

解析 .log 文件，提取各阶段的消息、拥塞报告、WNS 演变。
支持: 综合日志、布局日志、布线日志、完整编译日志
"""

import re
from pathlib import Path
from typing import Optional

from vivado_ai.models.finding import (
    Findings, LogMessage, CongestionReport, StageLogData,
)


class LogParser:
    """解析 Vivado 编译日志"""

    # Vivado 消息级别正则
    MESSAGE_PATTERN = re.compile(
        r"(ERROR|CRITICAL WARNING|WARNING|INFO)\s*:\s*"
        r"(?:\[([^\]]+?)\]\s*)?"  # 消息码, e.g. [Synth 8-327]
        r"(.*?)\s*$",
        re.MULTILINE,
    )

    # 阶段标识符
    STAGE_MARKERS = {
        "synthesis": [
            "Starting Synthesis",
            "synth_design",
            "Running synth_design",
        ],
        "opt": [
            "Starting opt_design",
            "Running opt_design",
        ],
        "place": [
            "Starting Placement",
            "Running place_design",
        ],
        "phys_opt": [
            "Starting Physical Optimization",
            "Running phys_opt_design",
        ],
        "route": [
            "Starting Routing",
            "Running route_design",
        ],
    }

    # WNS 提取
    TIMING_PATTERN = re.compile(
        r"WNS\s*=\s*([-\d.]+)",
    )

    # 拥塞报告
    CONGESTION_PATTERN = re.compile(
        r"Congestion\s*(?:level|Level)\s*(\d+)"
        r"(?:\s+in\s+)?(?:Region|Window)\s*[:=]?\s*(\S+)",
    )

    def parse_dir(self, log_dir: Path) -> Findings:
        """解析目录下的所有 log 文件"""
        findings = Findings()
        log_dir = Path(log_dir)
        log_files = list(log_dir.glob("**/*.log"))

        for log_file in log_files:
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            name_lower = log_file.name.lower()

            if "synth" in name_lower:
                findings.synth_log = self._parse_stage(content, "synthesis")
            elif "opt" in name_lower and "place" not in name_lower:
                findings.opt_log = self._parse_stage(content, "opt")
            elif "place" in name_lower:
                findings.place_log = self._parse_stage(content, "place")
            elif "route" in name_lower:
                findings.route_log = self._parse_stage(content, "route")
            else:
                # 可能是完整编译 log
                self._parse_full_log(content, findings)

        return findings

    def parse_file(self, log_file: Path) -> Findings:
        """解析单个 log 文件"""
        findings = Findings()
        content = log_file.read_text(encoding="utf-8", errors="ignore")
        name_lower = log_file.name.lower()

        if "synth" in name_lower:
            findings.synth_log = self._parse_stage(content, "synthesis")
        elif "place" in name_lower:
            findings.place_log = self._parse_stage(content, "place")
        elif "route" in name_lower:
            findings.route_log = self._parse_stage(content, "route")
        else:
            self._parse_full_log(content, findings)

        return findings

    # ─── 单阶段解析 ────────────────────────────────────

    def _parse_stage(self, content: str, stage: str) -> StageLogData:
        """解析单个阶段的 log"""
        messages = self._extract_messages(content)
        congestion = self._extract_congestion(content)
        wns_values = self._extract_all_wns(content)
        duration = self._extract_duration(content)

        wns_before = None
        wns_after = None
        if len(wns_values) >= 2:
            wns_before = wns_values[0]
            wns_after = wns_values[-1]
        elif len(wns_values) == 1:
            wns_after = wns_values[0]

        return StageLogData(
            stage=stage,
            messages=messages,
            congestion_reports=congestion,
            wns_before_phys_opt=wns_before,
            wns_after_phys_opt=wns_after,
            duration_seconds=duration,
        )

    # ─── 完整日志拆分 ──────────────────────────────────

    def _parse_full_log(self, content: str, findings: Findings):
        """解析包含多个阶段的完整 log"""
        sections = self._split_by_stage(content)

        for stage_name, section_content in sections.items():
            stage_log = self._parse_stage(section_content, stage_name)
            if stage_name == "synthesis":
                findings.synth_log = stage_log
            elif stage_name == "opt":
                findings.opt_log = stage_log
            elif stage_name == "place":
                findings.place_log = stage_log
            elif stage_name == "route":
                findings.route_log = stage_log

    def _split_by_stage(self, content: str) -> dict:
        """按阶段标识符拆分完整 log"""
        sections = {}
        positions = []

        for stage, markers in self.STAGE_MARKERS.items():
            for marker in markers:
                for m in re.finditer(re.escape(marker), content):
                    positions.append((m.start(), stage))

        positions.sort()

        for i, (pos, stage) in enumerate(positions):
            end = positions[i + 1][0] if i + 1 < len(positions) else len(content)
            # 只保留每个阶段的第一个区段
            if stage not in sections:
                sections[stage] = content[pos:end]

        return sections

    # ─── 提取方法 ───────────────────────────────────────

    def _extract_messages(self, content: str) -> list[LogMessage]:
        """提取所有 ERROR/CRITICAL WARNING/WARNING"""
        messages = []
        for m in self.MESSAGE_PATTERN.finditer(content):
            level = m.group(1)
            # 只保留有价值的消息（过滤 INFO 噪音）
            if level in ("ERROR", "CRITICAL WARNING", "WARNING"):
                messages.append(LogMessage(
                    level=level,
                    code=m.group(2) or "",
                    text=m.group(3).strip(),
                ))
        return messages

    def _extract_congestion(self, content: str) -> list[CongestionReport]:
        """提取拥塞报告"""
        reports = []
        for m in self.CONGESTION_PATTERN.finditer(content):
            reports.append(CongestionReport(
                level=int(m.group(1)),
                region=m.group(2),
            ))
        return reports

    def _extract_all_wns(self, content: str) -> list[float]:
        """提取所有 WNS 值（按出现顺序）"""
        return [float(m.group(1)) for m in self.TIMING_PATTERN.finditer(content)]

    def _extract_duration(self, content: str) -> Optional[float]:
        """提取运行时间"""
        time_pattern = re.search(
            r"(?:real|elapsed|Time)\s*[:=]?\s*(\d+):(\d+)(?::(\d+))?",
            content, re.IGNORECASE,
        )
        if time_pattern:
            minutes = int(time_pattern.group(1))
            seconds = int(time_pattern.group(2))
            return minutes * 60 + seconds
        return None
