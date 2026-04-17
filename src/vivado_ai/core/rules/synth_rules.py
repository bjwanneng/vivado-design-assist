"""
Group E: 综合 Log 规则 (SYNTH-*)

分析综合阶段 log 中的消息，检测方法论违规。
"""

from vivado_ai.core.rules.base import Rule, RuleResult
from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.models.finding import Findings
from vivado_ai.models.issue import Severity


@RuleRegistry.register
class RAMNotBlockRAM(Rule):
    """SYNTH-001: RAM 未使用 Block RAM"""
    id = "SYNTH-001"
    name = "RAM Not Using Block RAM"
    group = "E"
    severity = Severity.WARN
    ug949_ref = "Ch3: Inferring RAM/DSP"
    applicable_modes = ["analyze"]

    TARGET_CODES = ["Synth 8-3936", "Synth 8-5537"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if msg.code in self.TARGET_CODES:
                issues.append(self._create_issue(
                    message=f"RAM not using dedicated resource: {msg.text}",
                    detail=f"Code: {msg.code}",
                    fix_suggestion=(
                        "1. Review RAM inference coding style in UG901\n"
                        "2. Ensure synchronous read with registered output\n"
                        "3. Check RAM pragma/attribute settings\n"
                        "4. Verify write-first/read-first behavior matches"
                    ),
                    location=msg.source,
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class UnintendedLatch(Rule):
    """SYNTH-002: 意外 Latch 生成"""
    id = "SYNTH-002"
    name = "Unintended Latch Generation"
    group = "E"
    severity = Severity.FAIL
    ug949_ref = "Ch3: Latch"
    applicable_modes = ["analyze"]

    TARGET_CODES = ["Synth 8-327"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if msg.code in self.TARGET_CODES:
                issues.append(self._create_issue(
                    message=f"Latch inferred: {msg.text}",
                    detail=(
                        "Incomplete if/case statement causes unintended latch. "
                        "Latches are problematic for timing analysis."
                    ),
                    fix_suggestion=(
                        "Add 'default' to case statement, "
                        "or 'else' clause to if statement. "
                        "Ensure all signal assignments in all branches."
                    ),
                    location=msg.source,
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class MultiDrivenSignal(Rule):
    """SYNTH-003: 多驱动信号"""
    id = "SYNTH-003"
    name = "Multi-Driven Signal"
    group = "E"
    severity = Severity.FAIL
    ug949_ref = "Ch3: RTL Coding"
    applicable_modes = ["analyze"]

    TARGET_CODES = ["Synth 8-3352"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if msg.code in self.TARGET_CODES:
                issues.append(self._create_issue(
                    message=f"Multi-driven signal: {msg.text}",
                    detail=f"Code: {msg.code}",
                    fix_suggestion=(
                        "Ensure each signal is driven by exactly one process.\n"
                        "Check for accidental multiple assignments."
                    ),
                    location=msg.source,
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class UnconnectedPorts(Rule):
    """SYNTH-005: 未连接端口"""
    id = "SYNTH-005"
    name = "Unconnected Ports"
    group = "E"
    severity = Severity.WARN
    ug949_ref = "Ch3: RTL Coding"
    applicable_modes = ["analyze"]

    TARGET_CODES = ["Synth 8-6014", "Synth 8-3331"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if msg.code in self.TARGET_CODES:
                issues.append(self._create_issue(
                    message=f"Unconnected port: {msg.text}",
                    detail=f"Code: {msg.code}",
                    fix_suggestion="Check module instantiation for missing connections.",
                    location=msg.source,
                    severity=Severity.WARN,
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class NonDedicatedClockRoute(Rule):
    """SYNTH-006: 非专用时钟布线"""
    id = "SYNTH-006"
    name = "Non-Dedicated Clock Route"
    group = "E"
    severity = Severity.FAIL
    ug949_ref = "Ch3: CLOCK_DEDICATED_ROUTE"
    applicable_modes = ["analyze"]

    TARGET_CODES = [
        "Synth 8-524",
        "Vivado 12-4737",
        "DRC RTSTAT-1",
    ]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if msg.code in self.TARGET_CODES:
                issues.append(self._create_issue(
                    message=f"Non-dedicated clock route: {msg.text}",
                    detail=f"Code: {msg.code}",
                    fix_suggestion=(
                        "1. Use GCIO (Global Clock I/O) pins\n"
                        "2. Add: set_property CLOCK_DEDICATED_ROUTE "
                        "TRUE [get_nets <clk_net>]\n"
                        "3. Ensure clock goes through MMCM/PLL/BUFG"
                    ),
                    location=msg.source,
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class GatedClock(Rule):
    """SYNTH-012: 门控时钟"""
    id = "SYNTH-012"
    name = "Gated Clock Detected"
    group = "E"
    severity = Severity.WARN
    ug949_ref = "Ch3: Clocking"
    applicable_modes = ["analyze"]

    TARGET_CODES = ["Synth 8-5543"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if msg.code in self.TARGET_CODES:
                issues.append(self._create_issue(
                    message=f"Gated clock: {msg.text}",
                    detail=f"Code: {msg.code}",
                    fix_suggestion=(
                        "Use clock enable (CE) instead of gated clock.\n"
                        "If gating is necessary, use BUFGCE or clock mux."
                    ),
                    location=msg.source,
                    severity=Severity.WARN,
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class DontTouchBlocking(Rule):
    """SYNTH-008: DONT_TOUCH 阻止优化"""
    id = "SYNTH-008"
    name = "DONT_TOUCH Blocking Optimization"
    group = "E"
    severity = Severity.WARN
    ug949_ref = "Ch4: DONT_TOUCH Guidelines"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        dt_count = sum(
            1 for m in findings.synth_log.messages
            if "DONT_TOUCH" in m.text
            and m.level in ("WARNING", "CRITICAL WARNING")
        )
        if dt_count > 5:
            issues.append(self._create_issue(
                message=f"High DONT_TOUCH usage: {dt_count} instances",
                detail=(
                    "Excessive DONT_TOUCH prevents optimization "
                    "(retiming, LUT combining, replication)"
                ),
                fix_suggestion=(
                    "UG949 Ch4: Only use DONT_TOUCH when necessary.\n"
                    "- Remove DONT_TOUCH on non-timing-critical modules\n"
                    "- Use KEEP_HIERARCHY instead when possible\n"
                    "- Review each DONT_TOUCH with the team"
                ),
            ))

        return RuleResult(rule_id=self.id, issues=issues)
