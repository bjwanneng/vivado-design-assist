"""
方法论检查引擎

编排 解析器 → 规则引擎 → AI 解读 → 评分 的完整流程。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from pathlib import Path

from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.core.parsers.report_parser import ReportParser
from vivado_ai.core.parsers.log_parser import LogParser
from vivado_ai.core.parsers.xdc_parser import XDCParser
from vivado_ai.core.scorer import ComplianceScorer
from vivado_ai.models.finding import Findings
from vivado_ai.models.issue import Issue, Severity


# 确保所有规则被导入和注册
import vivado_ai.core.rules.constraint_rules   # noqa: F401
import vivado_ai.core.rules.synth_rules         # noqa: F401
import vivado_ai.core.rules.place_rules         # noqa: F401
import vivado_ai.core.rules.route_rules         # noqa: F401
import vivado_ai.core.rules.root_cause_rules    # noqa: F401
import vivado_ai.core.rules.impl_rules          # noqa: F401
import vivado_ai.core.rules.opt_rules           # noqa: F401
import vivado_ai.core.rules.flow_rules          # noqa: F401
import vivado_ai.core.rules.rtl_rules           # noqa: F401


class CheckMode(Enum):
    LINT = "lint"
    CHECK = "check"
    ANALYZE = "analyze"


@dataclass
class CheckConfig:
    mode: CheckMode
    rtl_dir: Optional[Path] = None
    xdc_files: List[Path] = field(default_factory=list)
    reports_dir: Optional[Path] = None
    log_dir: Optional[Path] = None
    part: Optional[str] = None
    enable_ai: bool = True
    rule_groups: List[str] = field(default_factory=lambda: ["all"])


@dataclass
class CheckResult:
    issues: List[Issue]
    score: int  # 0-100
    summary: dict


class MethodologyEngine:
    """
    Vivado Methodology 检查引擎

    工作流程:
    1. 解析输入数据 -> Findings
    2. 加载规则 -> 匹配 Findings -> Issues
    3. 汇总评分
    4. (可选) AI 解读
    """

    def __init__(self, config: CheckConfig):
        self.config = config
        self.registry = RuleRegistry()
        self.scorer = ComplianceScorer()
        self.report_parser = ReportParser()
        self.log_parser = LogParser()
        self.xdc_parser = XDCParser()

    def run(self) -> CheckResult:
        """执行完整检查流程"""
        # Step 1: 收集数据
        findings = self._collect_findings()

        # Step 2: 加载并执行规则
        rules = self.registry.get_rules(
            mode=self.config.mode.value,
            groups=self.config.rule_groups,
        )
        issues = []
        for rule in rules:
            result = rule.check(findings)
            issues.extend(result.issues)

        # Step 3: 评分
        score = self.scorer.score(issues)

        return CheckResult(
            issues=issues,
            score=score,
            summary=self._build_summary(issues, score),
        )

    def _collect_findings(self) -> Findings:
        """根据模式收集数据"""
        findings = Findings()

        if self.config.mode == CheckMode.LINT:
            for xdc in self.config.xdc_files:
                parsed = self.xdc_parser.parse(xdc)
                # 合并多个 XDC 的命令
                if findings.xdc_data is None:
                    findings.xdc_data = parsed
                else:
                    findings.xdc_data.commands.extend(parsed.commands)

        elif self.config.mode == CheckMode.CHECK:
            if self.config.reports_dir:
                findings = self.report_parser.parse_dir(self.config.reports_dir)

        elif self.config.mode == CheckMode.ANALYZE:
            if self.config.log_dir:
                findings = self.log_parser.parse_dir(self.config.log_dir)

        return findings

    def _build_summary(self, issues: List[Issue], score: int) -> dict:
        by_severity = {}
        for issue in issues:
            by_severity[issue.severity.value] = (
                by_severity.get(issue.severity.value, 0) + 1
            )
        return {
            "total_issues": len(issues),
            "by_severity": by_severity,
            "score": score,
        }
