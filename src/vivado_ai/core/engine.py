"""
方法论检查引擎

编排 解析器 → 规则引擎 → AI 解读 → 评分 的完整流程。
"""

import urllib.parse
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
    root_cause_summary: str = ""


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
        self._ai_interpreter = None  # lazy init

    def run(self) -> CheckResult:
        """执行完整检查流程"""
        # Step 0: 输入验证
        self._validate_config()

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

        # Step 3: 附加 Forum 搜索链接
        self._attach_forum_links(issues)

        # Step 4: AI 增强解读 (可选)
        root_cause_summary = ""
        if self.config.enable_ai:
            root_cause_summary = self._run_ai_enhancements(issues)

        # Step 5: 评分
        score = self.scorer.score(issues)

        return CheckResult(
            issues=issues,
            score=score,
            summary=self._build_summary(issues, score),
            root_cause_summary=root_cause_summary,
        )

    def _validate_config(self):
        """验证配置中的必填输入"""
        mode = self.config.mode
        if mode == CheckMode.LINT and not self.config.xdc_files:
            raise ValueError("Lint mode requires at least one --xdc file")
        if mode == CheckMode.CHECK and not self.config.reports_dir:
            raise ValueError("Check mode requires --reports-dir")
        if mode == CheckMode.ANALYZE and not self.config.log_dir:
            raise ValueError("Analyze mode requires --log-dir")

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

    def _attach_forum_links(self, issues: List[Issue]):
        """为非 PASS 的 issue 生成 Xilinx Forum 搜索链接"""
        for issue in issues:
            if issue.severity == Severity.PASS:
                continue
            query = issue.message_code or issue.rule_name
            if query:
                issue.forum_url = (
                    "https://support.xilinx.com/s/search?q="
                    + urllib.parse.quote(query)
                )

    def _run_ai_enhancements(self, issues: List[Issue]) -> str:
        """AI 增强解读：单 issue 解释 + 跨 issue 根因分析"""
        try:
            from vivado_ai.core.ai_interpreter import AIInterpreter
            if self._ai_interpreter is None:
                self._ai_interpreter = AIInterpreter()

            # 单 issue 解释
            explanations = self._ai_interpreter.explain_batch(issues)
            for idx, issue in enumerate(issues):
                if idx in explanations:
                    issue.ai_explanation = explanations[idx]

            # 跨 issue 根因分析
            return self._ai_interpreter.analyze_root_cause(issues)
        except Exception as e:
            return f"[AI enhancement unavailable: {e}]"
