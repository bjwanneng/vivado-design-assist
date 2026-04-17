"""
Group A: 约束方法论规则 (CONST-*)

检查 XDC 约束的完整性和正确性。
"""

from vivado_ai.core.rules.base import Rule, RuleResult
from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.models.finding import Findings
from vivado_ai.models.issue import Severity


@RuleRegistry.register
class ClockPeriodConstraint(Rule):
    """CONST-001: 检查所有时钟是否有周期约束"""
    id = "CONST-001"
    name = "Clock Period Constraints"
    group = "A"
    severity = Severity.FAIL
    ug949_ref = "Ch5: Establishing a Baseline"
    applicable_modes = ["lint", "check"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []

        # 从 XDC 数据中提取已约束的时钟
        constrained_clocks = set()
        if findings.xdc_data:
            for cmd in findings.xdc_data.commands:
                if cmd.type == "create_clock" and "name" in cmd.args:
                    constrained_clocks.add(cmd.args["name"])
                elif cmd.type == "create_clock" and "port" in cmd.args:
                    constrained_clocks.add(cmd.args["port"])

        # 从 report_clock_networks 中提取所有时钟网络
        if findings.clock_networks:
            for net in findings.clock_networks:
                if net.name not in constrained_clocks:
                    issues.append(self._create_issue(
                        message=f"Clock '{net.name}' has no period constraint",
                        detail=f"{net.endpoint_count} endpoints driven by "
                               f"unconstrained clock",
                        fix_suggestion=(
                            f"create_clock -period <period> -name {net.name} "
                            f"[get_ports {net.source_port}]"
                        ),
                        location=net.source_port,
                    ))

        # Lint 模式: 检查 XDC 文件中的时钟端口覆盖
        if findings.xdc_data and not findings.clock_networks:
            for cmd in findings.xdc_data.commands:
                if cmd.type == "create_clock":
                    continue
            # 如果没有 create_clock 命令，报告
            has_create_clock = any(
                c.type == "create_clock" for c in findings.xdc_data.commands
            )
            if not has_create_clock:
                issues.append(self._create_issue(
                    message="No create_clock constraint found in XDC",
                    detail="XDC file contains no clock period constraints",
                    fix_suggestion=(
                        "Add create_clock for each clock port:\n"
                        "create_clock -period <ns> -name clk "
                        "[get_ports clk]"
                    ),
                    location=findings.xdc_data.file_path,
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class ClockInteractionConstraint(Rule):
    """CONST-004: 检查时钟域交互是否声明"""
    id = "CONST-004"
    name = "Clock Domain Interaction Constraints"
    group = "A"
    severity = Severity.FAIL
    ug949_ref = "Ch5: CDC Constraints"
    applicable_modes = ["lint", "check"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []

        if findings.clock_interactions:
            for interaction in findings.clock_interactions:
                if interaction.inter_class in ("unsafe", "no"):
                    issues.append(self._create_issue(
                        message=(
                            f"Unsafe clock interaction: "
                            f"{interaction.from_clock} -> "
                            f"{interaction.to_clock} "
                            f"(class: {interaction.inter_class})"
                        ),
                        detail=(
                            f"WNS: {interaction.wns}" if interaction.wns else ""
                        ),
                        fix_suggestion=(
                            f"set_clock_groups -asynchronous "
                            f"-group [get_clocks {interaction.from_clock}] "
                            f"-group [get_clocks {interaction.to_clock}]"
                        ),
                    ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class UnconstrainedPaths(Rule):
    """CONST-006: 检查无约束路径"""
    id = "CONST-006"
    name = "Unconstrained Paths"
    group = "A"
    severity = Severity.FAIL
    ug949_ref = "Ch5: Constraining All Paths"
    applicable_modes = ["check"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []

        if findings.methodology_checks:
            for check in findings.methodology_checks:
                if check.check_id == "TIMING-14":
                    issues.append(self._create_issue(
                        message=f"Unconstrained paths: {check.message}",
                        detail="\n".join(check.details) if check.details else "",
                        fix_suggestion=(
                            "Ensure all paths have timing constraints.\n"
                            "Common causes: missing create_clock, "
                            "missing set_input_delay/set_output_delay"
                        ),
                    ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class ExcessiveFalsePaths(Rule):
    """CONST-008: 过多 false path"""
    id = "CONST-008"
    name = "Excessive False Paths"
    group = "A"
    severity = Severity.WARN
    ug949_ref = "Ch5: False Path Guidelines"
    applicable_modes = ["lint"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []

        if findings.xdc_data:
            fp_count = sum(
                1 for c in findings.xdc_data.commands
                if c.type == "set_false_path"
            )
            total_cmds = len(findings.xdc_data.commands)
            if total_cmds > 0 and fp_count / total_cmds > 0.3:
                issues.append(self._create_issue(
                    message=f"Excessive false paths: {fp_count}/{total_cmds} "
                            f"constraints are false_path",
                    detail="Too many false paths may mask real timing issues",
                    fix_suggestion=(
                        "Review each set_false_path to ensure it's necessary.\n"
                        "Consider using set_clock_groups instead of "
                        "individual set_false_path commands."
                    ),
                ))

        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class MissingIODelay(Rule):
    """CONST-009: 缺少 I/O 延迟约束"""
    id = "CONST-009"
    name = "Missing I/O Delay Constraints"
    group = "A"
    severity = Severity.WARN
    ug949_ref = "Ch5: I/O Constraints"
    applicable_modes = ["lint", "check"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []

        if findings.xdc_data:
            has_input_delay = any(
                c.type == "set_input_delay" for c in findings.xdc_data.commands
            )
            has_output_delay = any(
                c.type == "set_output_delay" for c in findings.xdc_data.commands
            )

            msgs = []
            if not has_input_delay:
                msgs.append("No set_input_delay found")
            if not has_output_delay:
                msgs.append("No set_output_delay found")

            if msgs:
                issues.append(self._create_issue(
                    message="; ".join(msgs),
                    detail="I/O delays are needed for accurate timing analysis",
                    fix_suggestion=(
                        "set_input_delay -clock [get_clocks <clk>] "
                        "<delay> [get_ports <port>]\n"
                        "set_output_delay -clock [get_clocks <clk>] "
                        "<delay> [get_ports <port>]"
                    ),
                    severity=Severity.WARN,
                ))

        return RuleResult(rule_id=self.id, issues=issues)
