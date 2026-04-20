"""
Group H: 布线 Log 规则 (ROUTE-*)

分析布线阶段的 unrouted nets、拥塞、hold violation 等。
"""

from vivado_ai.core.rules.base import Rule, RuleResult
from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.models.finding import Findings
from vivado_ai.models.issue import Severity


@RuleRegistry.register
class UnroutedNets(Rule):
    """ROUTE-001: 未布线网络"""
    id = "ROUTE-001"
    name = "Unrouted Nets"
    group = "H"
    severity = Severity.CRITICAL
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.route_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.route_log.messages:
            if msg.code == "Route 35-139" or "unrouted" in msg.text.lower():
                issues.append(self._create_issue(
                    message=f"Unrouted nets: {msg.text}",
                    detail=f"Code: {msg.code}",
                    fix_suggestion=(
                        "Unrouted nets indicate incomplete routing.\n"
                        "1. Check for over-constrained design\n"
                        "2. Try route_design -directive NoTimingRelaxation\n"
                        "3. Review congestion reports"
                    ),
                    severity=Severity.CRITICAL,
                    message_code=msg.code,
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class RouterCongestion(Rule):
    """ROUTE-002: 布线拥塞"""
    id = "ROUTE-002"
    name = "Router Congestion"
    group = "H"
    severity = Severity.FAIL
    ug949_ref = "UG1292: Reducing Congestion"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.route_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.route_log.messages:
            if msg.code == "Route 35-243" or "congestion" in msg.text.lower():
                issues.append(self._create_issue(
                    message=f"Router congestion: {msg.text}",
                    detail=f"Code: {msg.code}",
                    fix_suggestion=(
                        "1. Review placement congestion\n"
                        "2. Try route_design -directive HigherRouterEffort\n"
                        "3. Add Pblock constraints\n"
                        "4. Consider restructuring RTL to reduce fanout"
                    ),
                    message_code=msg.code,
                ))

        # 检查拥塞报告
        for congestion in findings.route_log.congestion_reports:
            if congestion.level >= 4:
                issues.append(self._create_issue(
                    message=f"Severe routing congestion level {congestion.level}",
                    detail=f"Region: {congestion.region}",
                    fix_suggestion=(
                        "1. Redesign high-fanout logic\n"
                        "2. Use pipeline registers to distribute load\n"
                        "3. Consider physical constraints (Pblock)"
                    ),
                    severity=Severity.CRITICAL,
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class HoldViolation(Rule):
    """ROUTE-006: Hold Violation"""
    id = "ROUTE-006"
    name = "Hold Violation After Routing"
    group = "H"
    severity = Severity.FAIL
    ug949_ref = "UG1292: Hold Violation"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []

        # 检查 route log 中的 hold violation 消息
        if findings.route_log:
            for msg in findings.route_log.messages:
                if "hold" in msg.text.lower() and "violation" in msg.text.lower():
                    issues.append(self._create_issue(
                        message=f"Hold violation: {msg.text}",
                        fix_suggestion=(
                            "1. Check for multi-cycle path constraints\n"
                            "2. Verify clock skew is within spec\n"
                            "3. Run phys_opt_design with hold fix\n"
                            "4. Review false_path constraints"
                        ),
                    ))

        return RuleResult(rule_id=self.id, issues=issues)
