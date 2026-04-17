"""
Group F: 优化 Log 分析规则 (OPT-*)

分析 opt_design / power_opt_design 阶段的 log 输出。
"""

from vivado_ai.core.rules.base import Rule, RuleResult
from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.models.finding import Findings
from vivado_ai.models.issue import Severity


@RuleRegistry.register
class OptimizationBlockedByDontTouch(Rule):
    """OPT-001: DONT_TOUCH 阻止的优化"""
    id = "OPT-001"
    name = "Optimization Blocked by DONT_TOUCH"
    group = "F"
    severity = Severity.WARN
    ug949_ref = "Ch4: DONT_TOUCH"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.opt_log:
            return RuleResult(rule_id=self.id)

        dt_msgs = [
            m for m in findings.opt_log.messages
            if "DONT_TOUCH" in m.text
            or "MARK_DEBUG" in m.text
        ]
        if dt_msgs:
            issues.append(self._create_issue(
                message=f"DONT_TOUCH/MARK_DEBUG blocked {len(dt_msgs)} "
                        f"optimizations in opt_design",
                detail="\n".join(m.text[:100] for m in dt_msgs[:5]),
                fix_suggestion=(
                    "1. Review each DONT_TOUCH — remove if not needed\n"
                    "2. Use KEEP_HIERARCHY instead of DONT_TOUCH\n"
                    "3. MARK_DEBUG should only be on debug signals"
                ),
            ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class ControlSetOptNotRun(Rule):
    """OPT-002: 控制集优化未执行"""
    id = "OPT-002"
    name = "Control Set Optimization Not Run"
    group = "F"
    severity = Severity.INFO
    ug949_ref = "Ch4: Implementation"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.opt_log:
            return RuleResult(rule_id=self.id)

        # 检查 opt_design 日志中是否有控制集合并信息
        has_control_set_merge = any(
            "control_set" in m.text.lower() or "control set" in m.text.lower()
            for m in findings.opt_log.messages
        )
        # 如果没有找到控制集优化记录，建议添加
        if not has_control_set_merge and findings.opt_log.messages:
            issues.append(self._create_issue(
                message="No control set optimization detected in opt_design",
                fix_suggestion=(
                    "Consider running:\n"
                    "opt_design -control_set_merge\n"
                    "to reduce control set count"
                ),
                severity=Severity.INFO,
            ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class HighFanoutNotBUFGBuffered(Rule):
    """OPT-003: 高扇出网络未被 BUFG 缓冲"""
    id = "OPT-003"
    name = "High Fanout Not BUFG Buffered"
    group = "F"
    severity = Severity.WARN
    ug949_ref = "Ch3: CLOCK_BUFFER_TYPE"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.opt_log:
            return RuleResult(rule_id=self.id)

        fanout_msgs = [
            m for m in findings.opt_log.messages
            if "fanout" in m.text.lower() and (
                "high" in m.text.lower() or "limit" in m.text.lower()
            )
        ]
        if fanout_msgs:
            issues.append(self._create_issue(
                message=f"High fanout networks detected: {len(fanout_msgs)} instances",
                detail="\n".join(m.text[:100] for m in fanout_msgs[:3]),
                fix_suggestion=(
                    "1. Add MAX_FANOUT attribute to high-fanout signals:\n"
                    "   (* MAX_FANOUT = 32 *)\n"
                    "2. Use BUFG for clock-like high-fanout signals\n"
                    "3. Replicate logic to reduce fanout"
                ),
            ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class LUTMergingCongestion(Rule):
    """OPT-004: LUT 合并导致拥塞"""
    id = "OPT-004"
    name = "LUT Merging May Cause Congestion"
    group = "F"
    severity = Severity.INFO
    ug949_ref = "Ch3: LUT Usage"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        # 如果 opt 阶段后还有拥塞，且使用了 LUT 合并，给出建议
        has_congestion = False
        for stage_log in [findings.place_log, findings.route_log]:
            if stage_log:
                has_congestion = any(
                    c.level >= 3 for c in stage_log.congestion_reports
                )
                if has_congestion:
                    break

        if has_congestion:
            issues.append(self._create_issue(
                message="Congestion detected — LUT merging may be a factor",
                fix_suggestion=(
                    "If congestion is caused by dense LUT packing:\n"
                    "1. Try opt_design -no_lc to disable LUT combining\n"
                    "2. Use place_design -directive SpreadLogic\n"
                    "3. Review floorplan for better module placement"
                ),
                severity=Severity.INFO,
            ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class PowerOptNotRun(Rule):
    """OPT-005: power_opt_design 未执行"""
    id = "OPT-005"
    name = "power_opt_design Not Run"
    group = "F"
    severity = Severity.INFO
    ug949_ref = "Ch4: Recommended Flow"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        # 检查是否有 power_opt 相关的日志
        has_power_opt = False
        for stage_log in [findings.opt_log, findings.place_log]:
            if stage_log:
                has_power_opt = any(
                    "power_opt" in m.text.lower()
                    for m in stage_log.messages
                )
                if has_power_opt:
                    break

        # 如果有布线结果但没有 power_opt，建议运行
        if findings.route_log and not has_power_opt:
            issues.append(self._create_issue(
                message="power_opt_design not detected in build flow",
                detail="UG949 Ch4 recommends running power_opt_design "
                       "for dynamic power reduction.",
                fix_suggestion=(
                    "Add to implementation flow:\n"
                    "power_opt_design\n"
                    "(typically after place_design)"
                ),
                severity=Severity.INFO,
            ))
        return RuleResult(rule_id=self.id, issues=issues)
