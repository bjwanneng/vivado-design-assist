"""
Group I: 全流程 Log 汇总分析规则 (FLOW-*)

跨阶段汇总分析：CRITICAL WARNING 趋势、WNS 演变、资源变化、问题重复、编译时间。
"""

from vivado_ai.core.rules.base import Rule, RuleResult
from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.models.finding import Findings, StageLogData
from vivado_ai.models.issue import Severity


@RuleRegistry.register
class PerStageCriticalWarnings(Rule):
    """FLOW-001: 各阶段 CRITICAL WARNING 统计及趋势"""
    id = "FLOW-001"
    name = "Per-Stage CRITICAL WARNING Stats"
    group = "I"
    severity = Severity.WARN
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        stages = _get_stages(findings)

        total_crit = 0
        crit_by_stage = {}
        for name, log in stages:
            count = sum(1 for m in log.messages if m.level == "CRITICAL WARNING")
            crit_by_stage[name] = count
            total_crit += count

        if total_crit > 0:
            detail_parts = [
                f"{name}: {count}" for name, count in crit_by_stage.items() if count > 0
            ]
            issues.append(self._create_issue(
                message=f"{total_crit} CRITICAL WARNINGs across build stages",
                detail=" | ".join(detail_parts),
                fix_suggestion=(
                    "CRITICAL WARNINGs indicate potential design issues.\n"
                    "Review each one before sign-off:\n"
                    "1. Check synthesis CRITICAL WARNINGs first\n"
                    "2. Then placement, then routing\n"
                    "3. Some may be benign — document waivers"
                ),
            ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class WNSEvolutionTrend(Rule):
    """FLOW-002: 各阶段 WNS 演变趋势"""
    id = "FLOW-002"
    name = "WNS Evolution Trend"
    group = "I"
    severity = Severity.INFO
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        stages = _get_stages(findings)

        wns_evolution = []
        for name, log in stages:
            if log.wns_after_phys_opt is not None:
                wns_evolution.append((name, log.wns_after_phys_opt))
            elif log.wns_before_phys_opt is not None:
                wns_evolution.append((name, log.wns_before_phys_opt))

        if len(wns_evolution) >= 2:
            trend = " -> ".join(
                f"{name}: {wns:.3f}" for name, wns in wns_evolution
            )

            # 如果 WNS 在恶化
            first_wns = wns_evolution[0][1]
            last_wns = wns_evolution[-1][1]
            severity = Severity.INFO
            msg_detail = trend

            if last_wns < first_wns:
                severity = Severity.WARN
                msg_detail += "\nWARNING: WNS is getting worse across stages!"

            issues.append(self._create_issue(
                message=f"WNS evolution: {len(wns_evolution)} stages tracked",
                detail=msg_detail,
                fix_suggestion=(
                    "WNS should improve (become less negative) through stages.\n"
                    "If WNS worsens, check:\n"
                    "1. Are constraints correct?\n"
                    "2. Is there excessive clock skew?\n"
                    "3. Are physical constraints (Pblock) interfering?"
                ),
                severity=severity,
            ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class ResourceUtilizationTrend(Rule):
    """FLOW-003: 各阶段资源利用率变化"""
    id = "FLOW-003"
    name = "Resource Utilization Changes"
    group = "I"
    severity = Severity.INFO
    applicable_modes = ["check", "analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.utilization:
            return RuleResult(rule_id=self.id)

        # 检查高利用率资源
        high_util = []
        for site_type, data in findings.utilization.items():
            if isinstance(data, dict):
                util_str = str(data.get("utilization", "0"))
                try:
                    util_val = float(util_str.rstrip("%"))
                    if util_val > 50:
                        high_util.append(
                            f"{site_type}: {util_val:.0f}% "
                            f"({data.get('used')}/{data.get('available')})"
                        )
                except (ValueError, TypeError):
                    pass

        if high_util:
            issues.append(self._create_issue(
                message=f"Resource utilization report: {len(high_util)} "
                        f"resource types above 50%",
                detail="\n".join(high_util),
                fix_suggestion=(
                    "Monitor resource utilization across build stages.\n"
                    "Sudden increases may indicate:\n"
                    "1. Synthesis inferring non-optimal structures\n"
                    "2. Missing optimization constraints\n"
                    "3. Design growth exceeding expectations"
                ),
                severity=Severity.INFO,
            ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class RepeatedIssuesAcrossStages(Rule):
    """FLOW-004: 多阶段重复报告的问题"""
    id = "FLOW-004"
    name = "Issues Repeated Across Stages"
    group = "I"
    severity = Severity.WARN
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        stages = _get_stages(findings)

        # 按消息码统计跨阶段出现次数
        code_stages: dict[str, list[str]] = {}
        for name, log in stages:
            for msg in log.messages:
                if msg.code:
                    code_stages.setdefault(msg.code, []).append(name)

        # 出现在 2+ 阶段的码
        repeated = {
            code: stage_names
            for code, stage_names in code_stages.items()
            if len(set(stage_names)) >= 2
        }

        if repeated:
            detail_parts = [
                f"{code}: {', '.join(set(stages_list))}"
                for code, stages_list in sorted(repeated.items())
            ]
            issues.append(self._create_issue(
                message=f"{len(repeated)} issue(s) appearing in multiple stages",
                detail="\n".join(detail_parts[:10]),
                fix_suggestion=(
                    "Issues appearing in multiple stages often indicate "
                    "root-cause problems that should be fixed early:\n"
                    "1. Fix in RTL or XDC before re-running\n"
                    "2. Don't rely on implementation to work around them"
                ),
            ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class CompileTimeBreakdown(Rule):
    """FLOW-005: 总编译时间及各阶段占比"""
    id = "FLOW-005"
    name = "Compile Time Breakdown"
    group = "I"
    severity = Severity.INFO
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        stages = _get_stages(findings)

        time_parts = []
        total_time = 0.0
        bottleneck = None
        bottleneck_time = 0.0

        for name, log in stages:
            if log.duration_seconds is not None:
                mins = int(log.duration_seconds // 60)
                secs = int(log.duration_seconds % 60)
                time_parts.append(f"{name}: {mins}m{secs}s")
                total_time += log.duration_seconds
                if log.duration_seconds > bottleneck_time:
                    bottleneck_time = log.duration_seconds
                    bottleneck = name

        if time_parts:
            total_mins = int(total_time // 60)
            total_secs = int(total_time % 60)
            detail = f"Total: {total_mins}m{total_secs}s\n" + "\n".join(time_parts)
            if bottleneck and bottleneck_time > total_time * 0.5:
                detail += f"\nBottleneck: {bottleneck} ({bottleneck_time/total_time:.0%} of total)"

            issues.append(self._create_issue(
                message=f"Build completed in {total_mins}m{total_secs}s",
                detail=detail,
                fix_suggestion=(
                    "To reduce build time:\n"
                    "1. Use -jobs option for parallel compilation\n"
                    "2. Enable incremental builds for small changes\n"
                    "3. Profile bottleneck stage and optimize"
                ),
                severity=Severity.INFO,
            ))
        return RuleResult(rule_id=self.id, issues=issues)

    @staticmethod
    def _get_stages(findings: Findings) -> list[tuple[str, StageLogData]]:
        """获取所有非 None 的阶段日志"""
        stages = []
        for name, log in [
            ("synthesis", findings.synth_log),
            ("opt", findings.opt_log),
            ("place", findings.place_log),
            ("route", findings.route_log),
        ]:
            if log is not None:
                stages.append((name, log))
        return stages


# 共享辅助函数（避免重复）
def _get_stages(findings: Findings) -> list[tuple[str, StageLogData]]:
    """获取所有非 None 的阶段日志"""
    stages = []
    for name, log in [
        ("synthesis", findings.synth_log),
        ("opt", findings.opt_log),
        ("place", findings.place_log),
        ("route", findings.route_log),
    ]:
        if log is not None:
            stages.append((name, log))
    return stages
