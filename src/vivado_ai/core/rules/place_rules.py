"""
Group G: 布局 Log 规则 (PLACE-*)

分析布局阶段的拥塞和物理优化效果。
"""

from vivado_ai.core.rules.base import Rule, RuleResult
from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.models.finding import Findings
from vivado_ai.models.issue import Severity


@RuleRegistry.register
class PlacementCongestion(Rule):
    """PLACE-001: 布局拥塞检测"""
    id = "PLACE-001"
    name = "Placement Congestion"
    group = "G"
    severity = Severity.FAIL
    ug949_ref = "UG1292: Reducing Congestion"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.place_log:
            return RuleResult(rule_id=self.id)

        for congestion in findings.place_log.congestion_reports:
            if congestion.level >= 4:
                sev = Severity.CRITICAL
            elif congestion.level >= 3:
                sev = Severity.FAIL
            else:
                continue

            issues.append(self._create_issue(
                message=(
                    f"Congestion Level {congestion.level} in region "
                    f"{congestion.region}"
                ),
                detail=(
                    f"Top contributors: {', '.join(congestion.top_modules)}"
                    if congestion.top_modules else ""
                ),
                fix_suggestion=(
                    "1. Add Pblock constraints to separate "
                    "overlapping modules\n"
                    "2. Try place_design -directive AltSpreadLogic_medium\n"
                    "3. Consider RTL changes to reduce routing complexity\n"
                    "4. Run: report_design_analysis -congestion"
                ),
                severity=sev,
            ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class PlacementFailed(Rule):
    """PLACE-002: 布局失败"""
    id = "PLACE-002"
    name = "Placement Failed"
    group = "G"
    severity = Severity.CRITICAL
    ug949_ref = "UG1292: Congestion"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.place_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.place_log.messages:
            if msg.code == "Place 30-494" or "failed" in msg.text.lower():
                issues.append(self._create_issue(
                    message=f"Placement failed: {msg.text}",
                    detail=f"Code: {msg.code}",
                    fix_suggestion=(
                        "1. Reduce congestion with Pblock constraints\n"
                        "2. Try different placement directives\n"
                        "3. Consider reducing design size or increasing part"
                    ),
                    severity=Severity.CRITICAL,
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class PhysOptEffectiveness(Rule):
    """PLACE-005: 物理优化效果"""
    id = "PLACE-005"
    name = "Physical Optimization Effectiveness"
    group = "G"
    severity = Severity.WARN
    ug949_ref = "UG1292: Post-Place Physical Optimization"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.place_log:
            return RuleResult(rule_id=self.id)

        wns_before = findings.place_log.wns_before_phys_opt
        wns_after = findings.place_log.wns_after_phys_opt

        if wns_before is not None and wns_after is not None:
            improvement = wns_after - wns_before
            if wns_after < 0 and improvement < 0.1:
                issues.append(self._create_issue(
                    message=(
                        f"phys_opt_design WNS improvement minimal: "
                        f"{wns_before:.3f} -> {wns_after:.3f} "
                        f"(+{improvement:.3f} ns)"
                    ),
                    fix_suggestion=(
                        "1. Try phys_opt_design -directive AggressiveExplore\n"
                        "2. Try phys_opt_design -directive "
                        "AlternateFlowWithRetiming\n"
                        "3. Consider over-constraining with "
                        "set_clock_uncertainty before placement\n"
                        "4. If WNS < -1ns, likely needs RTL changes"
                    ),
                    severity=Severity.WARN,
                ))

        return RuleResult(rule_id=self.id, issues=issues)
