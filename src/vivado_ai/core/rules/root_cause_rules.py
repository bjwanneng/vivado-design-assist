"""
Group D: 时序根因分析规则 (ROOT-*)

当 WNS < 0 时，分析时序违例的根因类型。
基于 UG1292 决策树。
"""

from vivado_ai.core.rules.base import Rule, RuleResult
from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.models.finding import Findings
from vivado_ai.models.issue import Severity


@RuleRegistry.register
class LogicDelayDominant(Rule):
    """ROOT-001: 逻辑延迟占比 > 50%"""
    id = "ROOT-001"
    name = "Logic Delay Dominant"
    group = "D"
    severity = Severity.FAIL
    ug949_ref = "UG1292: Reducing Logic Delay"
    applicable_modes = ["check", "analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.timing_paths:
            return RuleResult(rule_id=self.id)

        for path in findings.timing_paths:
            if path.slack >= 0:
                continue

            datapath_delay = path.datapath_delay
            if datapath_delay <= 0:
                continue

            logic_ratio = path.logic_delay / datapath_delay

            if logic_ratio > 0.5:
                issues.append(self._create_issue(
                    message=(
                        f"Logic delay dominant on critical path: "
                        f"{path.logic_delay:.3f}ns / "
                        f"{datapath_delay:.3f}ns "
                        f"({logic_ratio:.0%})"
                    ),
                    detail=(
                        f"Path: {path.start_point} -> {path.end_point}\n"
                        f"Logic levels: {path.logic_levels}\n"
                        f"Slack: {path.slack:.3f} ns"
                    ),
                    fix_suggestion=(
                        "1. Add pipeline registers to reduce logic levels\n"
                        "2. Run: opt_design -remap to combine small LUTs\n"
                        "3. Remove DONT_TOUCH on critical modules\n"
                        "4. Use synth_design -retiming\n"
                        "5. Check for single CARRY chains in critical paths"
                    ),
                    location=f"{path.start_point} -> {path.end_point}",
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class NetDelayDominant(Rule):
    """ROOT-002: 布线延迟占比 > 60%"""
    id = "ROOT-002"
    name = "Net Delay Dominant (High Fanout)"
    group = "D"
    severity = Severity.FAIL
    ug949_ref = "UG1292: Reducing Net Delay"
    applicable_modes = ["check", "analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.timing_paths:
            return RuleResult(rule_id=self.id)

        for path in findings.timing_paths:
            if path.slack >= 0:
                continue

            datapath_delay = path.datapath_delay
            if datapath_delay <= 0:
                continue

            net_ratio = path.net_delay / datapath_delay

            if net_ratio > 0.6:
                issues.append(self._create_issue(
                    message=(
                        f"Net delay dominant: "
                        f"{path.net_delay:.3f}ns / "
                        f"{datapath_delay:.3f}ns "
                        f"({net_ratio:.0%})"
                    ),
                    detail=(
                        f"Path: {path.start_point} -> {path.end_point}\n"
                        f"Slack: {path.slack:.3f} ns"
                    ),
                    fix_suggestion=(
                        "1. Replicate high-fanout drivers\n"
                        "2. Add pipeline registers\n"
                        "3. Use physical constraints (Pblock)\n"
                        "4. Check for cross-SLR paths in SSI devices"
                    ),
                    location=f"{path.start_point} -> {path.end_point}",
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class NegativeSetupSlack(Rule):
    """ROOT-004: WNS < 0 汇总"""
    id = "ROOT-004"
    name = "Negative Setup Slack"
    group = "D"
    severity = Severity.FAIL
    ug949_ref = "UG1292: Timing Closure"
    applicable_modes = ["check", "analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []

        if findings.timing_summary and findings.timing_summary.wns < 0:
            ts = findings.timing_summary
            issues.append(self._create_issue(
                message=(
                    f"Timing not met: WNS = {ts.wns:.3f} ns, "
                    f"TNS = {ts.tns:.3f} ns"
                ),
                detail=(
                    f"Failing endpoints: {ts.failing_endpoints} / "
                    f"{ts.total_endpoints}"
                ),
                fix_suggestion=(
                    "Follow UG1292 decision tree:\n"
                    "1. If logic delay > 50%: reduce logic levels\n"
                    "2. If net delay > 60%: reduce fanout, add pipeline\n"
                    "3. If clock skew large: check clock tree\n"
                    "4. If WNS < -1ns: likely needs RTL changes\n"
                    "5. If WNS > -0.5ns: try implementation directives"
                ),
            ))

        return RuleResult(rule_id=self.id, issues=issues)
