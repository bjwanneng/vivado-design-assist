"""
Group C: 实现流程方法论规则 (IMPL-*)

检查 Vivado 实现流程是否符合 UG949 Ch4 + UG1292 的方法论建议。
"""

from vivado_ai.core.rules.base import Rule, RuleResult
from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.models.finding import Findings
from vivado_ai.models.issue import Severity


@RuleRegistry.register
class PostSynthBaselineCheck(Rule):
    """IMPL-001: 综合后约束基线检查"""
    id = "IMPL-001"
    name = "Post-Synth Constraint Baseline Check"
    group = "C"
    severity = Severity.WARN
    ug949_ref = "Ch5: Baseline"
    applicable_modes = ["check"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        # UG949: 综合后应先建立约束基线再进行实现
        # 检查: 是否有 methodology_checks 但没有 timing_summary
        if (findings.methodology_checks and not findings.timing_summary):
            issues.append(self._create_issue(
                message="Methodology checks found but no timing summary — "
                        "constraint baseline may be incomplete",
                detail="UG949 Ch5: Run report_timing_summary after synthesis "
                       "to establish a baseline before implementation.",
                fix_suggestion=(
                    "After synthesis, run:\n"
                    "1. report_timing_summary -max_paths 10\n"
                    "2. report_methodology\n"
                    "3. Review and fix all issues before proceeding to implementation"
                ),
            ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class ReportMethodologyExecution(Rule):
    """IMPL-002: report_methodology 是否执行"""
    id = "IMPL-002"
    name = "report_methodology Execution"
    group = "C"
    severity = Severity.WARN
    ug949_ref = "Ch4: DRC"
    applicable_modes = ["check"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        # 如果有 timing_summary 但没有 methodology_checks，
        # 可能没有运行 report_methodology
        if (findings.timing_summary is not None
                and not findings.methodology_checks):
            issues.append(self._create_issue(
                message="Timing report found but no methodology checks — "
                        "report_methodology may not have been run",
                detail="UG949 Ch4 recommends running report_methodology at "
                       "each implementation stage.",
                fix_suggestion="Run: report_methodology -file methodology.rpt",
            ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class MultiplePlaceDirectives(Rule):
    """IMPL-003: 多 place_design 指令探索"""
    id = "IMPL-003"
    name = "Multiple place_design Directives"
    group = "C"
    severity = Severity.INFO
    ug949_ref = "Ch4: Implementation"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        # 如果 WNS < 0 且没有尝试多个 directive，给出建议
        if findings.place_log:
            wns = findings.place_log.wns_after_phys_opt
            if wns is not None and wns < 0:
                issues.append(self._create_issue(
                    message=f"WNS = {wns:.3f} ns after placement — "
                            f"consider exploring multiple directives",
                    detail="UG949 Ch4 recommends trying different "
                           "place_design directives when timing is not met.",
                    fix_suggestion=(
                        "Try these directives in order:\n"
                        "1. place_design -directive Default\n"
                        "2. place_design -directive AltSpreadLogic_medium\n"
                        "3. place_design -directive AltSpreadLogic_high\n"
                        "4. place_design -directive ExtraNetDelay_high\n"
                        "5. place_design -directive ExtraPostOpt"
                    ),
                    severity=Severity.INFO,
                ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class SevereCongestion(Rule):
    """IMPL-004: 严重拥塞"""
    id = "IMPL-004"
    name = "Severe Congestion"
    group = "C"
    severity = Severity.FAIL
    ug949_ref = "UG1292: Congestion"
    applicable_modes = ["check", "analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        # 检查所有阶段的拥塞报告
        for stage_log in [
            findings.place_log, findings.route_log,
        ]:
            if not stage_log:
                continue
            for congestion in stage_log.congestion_reports:
                if congestion.level >= 4:
                    issues.append(self._create_issue(
                        message=(
                            f"Severe congestion level {congestion.level} "
                            f"in {stage_log.stage} stage, region {congestion.region}"
                        ),
                        fix_suggestion=(
                            "1. Add Pblock constraints to separate modules\n"
                            "2. Use place_design -directive AltSpreadLogic_high\n"
                            "3. Reduce routing complexity in RTL\n"
                            "4. Consider larger device or floorplanning"
                        ),
                    ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class SLRUtilizationImbalance(Rule):
    """IMPL-005: SLR 利用率不均衡"""
    id = "IMPL-005"
    name = "SLR Utilization Imbalance"
    group = "C"
    severity = Severity.WARN
    ug949_ref = "UG1292: SSI"
    applicable_modes = ["check", "analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        # 检查 utilization 中的 SLR 信息（如果 report_failfast 提供了）
        if findings.utilization:
            # 简化检查：如果利用率 > 70% 给出警告
            for site_type, data in findings.utilization.items():
                if isinstance(data, dict):
                    util_str = str(data.get("utilization", "0"))
                    try:
                        util_val = float(util_str.rstrip("%"))
                        if util_val > 70:
                            issues.append(self._create_issue(
                                message=f"High utilization: {site_type} at {util_val:.0f}%",
                                detail=f"Used: {data.get('used')}, Available: {data.get('available')}",
                                fix_suggestion=(
                                    "1. Optimize RTL to reduce resource usage\n"
                                    "2. Consider larger device\n"
                                    "3. Use resource sharing where possible\n"
                                    "4. For SSI devices, balance utilization across SLRs"
                                ),
                                severity=Severity.WARN,
                            ))
                    except (ValueError, TypeError):
                        pass
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class HighControlSetRatio(Rule):
    """IMPL-006: 高控制集比例"""
    id = "IMPL-006"
    name = "High Control Set Ratio"
    group = "C"
    severity = Severity.WARN
    ug949_ref = "UG1292"
    applicable_modes = ["check"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        # 检查 failfast_data 中的控制集信息
        if findings.failfast_data:
            control_set_ratio = findings.failfast_data.get(
                "control_set_ratio", None
            )
            if control_set_ratio is not None and control_set_ratio > 0.075:
                issues.append(self._create_issue(
                    message=f"High control set ratio: {control_set_ratio:.1%}",
                    detail="UG1292 recommends control set ratio < 7.5%",
                    fix_suggestion=(
                        "1. Use opt_design -control_set_merge\n"
                        "2. Reduce unique reset/enable signals in RTL\n"
                        "3. Use synchronous resets instead of asynchronous\n"
                        "4. Share control signals across registers"
                    ),
                ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class IncrementalCompileUsage(Rule):
    """IMPL-007: 增量编译使用"""
    id = "IMPL-007"
    name = "Incremental Compile Usage"
    group = "C"
    severity = Severity.INFO
    ug949_ref = "UG949: Incremental"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        # 简化检查：如果编译多次且有相似 WNS，建议增量编译
        wns_values = []
        for stage_log in [
            findings.synth_log, findings.place_log, findings.route_log,
        ]:
            if stage_log and stage_log.wns_after_phys_opt is not None:
                wns_values.append(stage_log.wns_after_phys_opt)

        # 如果有多个阶段的 WNS 数据且差异很小，建议增量编译
        if len(wns_values) >= 2:
            wns_range = max(wns_values) - min(wns_values)
            if wns_range < 0.1 and all(w < 0 for w in wns_values):
                issues.append(self._create_issue(
                    message="Timing is close to meeting — incremental "
                            "compile may help",
                    detail=(
                        f"WNS range: {min(wns_values):.3f} to "
                        f"{max(wns_values):.3f} ns"
                    ),
                    fix_suggestion=(
                        "1. Use incremental implementation:\n"
                        "   set_property incremental_compile 1 "
                        "[get_runs impl_1]\n"
                        "2. Or: vivado -mode batch -source run.tcl "
                        "-tclargs incremental"
                    ),
                    severity=Severity.INFO,
                ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class ReportQoRSuggestionsExecution(Rule):
    """IMPL-008: report_qor_suggestions 是否执行"""
    id = "IMPL-008"
    name = "report_qor_suggestions Execution"
    group = "C"
    severity = Severity.INFO
    ug949_ref = "Ch4: QoR"
    applicable_modes = ["check"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        # 如果有时序违例，建议运行 report_qor_suggestions
        if (findings.timing_summary
                and findings.timing_summary.wns < 0):
            issues.append(self._create_issue(
                message="Timing not met — run report_qor_suggestions "
                        "for optimization advice",
                detail=f"WNS = {findings.timing_summary.wns:.3f} ns",
                fix_suggestion="Run: report_qor_suggestions -file qor_suggestions.rpt",
                severity=Severity.INFO,
            ))
        return RuleResult(rule_id=self.id, issues=issues)
