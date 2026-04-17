"""Tests for rules and engine"""

import pytest
from pathlib import Path

from vivado_ai.core.rules.base import RuleResult
from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.core.engine import MethodologyEngine, CheckConfig, CheckMode
from vivado_ai.core.scorer import ComplianceScorer
from vivado_ai.models.finding import (
    Findings, StageLogData, LogMessage, CongestionReport,
    TimingSummary, TimingPath, ClockInteraction,
)
from vivado_ai.models.issue import Issue, Severity

# Ensure rules are registered
import vivado_ai.core.rules.constraint_rules   # noqa: F401
import vivado_ai.core.rules.synth_rules         # noqa: F401
import vivado_ai.core.rules.place_rules         # noqa: F401
import vivado_ai.core.rules.route_rules         # noqa: F401
import vivado_ai.core.rules.root_cause_rules    # noqa: F401


FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestUnintendedLatch:
    def test_latch_detected(self):
        from vivado_ai.core.rules.synth_rules import UnintendedLatch
        rule = UnintendedLatch()
        findings = Findings()
        findings.synth_log = StageLogData(
            stage="synthesis",
            messages=[
                LogMessage(level="WARNING", code="Synth 8-327",
                           text="inferred latch for signal tmp"),
                LogMessage(level="WARNING", code="Synth 8-327",
                           text="inferred latch for signal next_state"),
            ],
        )

        result = rule.check(findings)
        assert len(result.issues) == 2
        assert all(i.rule_id == "SYNTH-002" for i in result.issues)

    def test_no_latch(self):
        from vivado_ai.core.rules.synth_rules import UnintendedLatch
        rule = UnintendedLatch()
        findings = Findings()
        findings.synth_log = StageLogData(stage="synthesis", messages=[])

        result = rule.check(findings)
        assert len(result.issues) == 0


class TestNonDedicatedClockRoute:
    def test_clock_route_detected(self):
        from vivado_ai.core.rules.synth_rules import NonDedicatedClockRoute
        rule = NonDedicatedClockRoute()
        findings = Findings()
        findings.synth_log = StageLogData(
            stage="synthesis",
            messages=[
                LogMessage(level="CRITICAL WARNING", code="Synth 8-524",
                           text="non-dedicated clock route for net clk_div"),
            ],
        )

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.FAIL


class TestPlacementCongestion:
    def test_high_congestion(self):
        from vivado_ai.core.rules.place_rules import PlacementCongestion
        rule = PlacementCongestion()
        findings = Findings()
        findings.place_log = StageLogData(
            stage="place",
            congestion_reports=[
                CongestionReport(level=4, region="X12Y5:W16xH16"),
                CongestionReport(level=2, region="X5Y10:W8xH8"),
            ],
        )

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.CRITICAL

    def test_low_congestion_ignored(self):
        from vivado_ai.core.rules.place_rules import PlacementCongestion
        rule = PlacementCongestion()
        findings = Findings()
        findings.place_log = StageLogData(
            stage="place",
            congestion_reports=[
                CongestionReport(level=2, region="X5Y10:W8xH8"),
            ],
        )

        result = rule.check(findings)
        assert len(result.issues) == 0


class TestLogicDelayDominant:
    def test_logic_delay_dominant(self):
        from vivado_ai.core.rules.root_cause_rules import LogicDelayDominant
        rule = LogicDelayDominant()
        findings = Findings()
        findings.timing_paths = [
            TimingPath(
                slack=-0.5, start_point="a", end_point="b",
                datapath_delay=4.0, logic_delay=3.0, net_delay=1.0,
                logic_levels=8,
            ),
        ]

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert result.issues[0].rule_id == "ROOT-001"

    def test_net_delay_dominant(self):
        from vivado_ai.core.rules.root_cause_rules import LogicDelayDominant
        rule = LogicDelayDominant()
        findings = Findings()
        findings.timing_paths = [
            TimingPath(
                slack=-0.5, start_point="a", end_point="b",
                datapath_delay=4.0, logic_delay=1.0, net_delay=3.0,
                logic_levels=2,
            ),
        ]

        result = rule.check(findings)
        assert len(result.issues) == 0


class TestClockInteractionConstraint:
    def test_unsafe_interaction(self):
        from vivado_ai.core.rules.constraint_rules import ClockInteractionConstraint
        rule = ClockInteractionConstraint()
        findings = Findings()
        findings.clock_interactions = [
            ClockInteraction(from_clock="clk1", to_clock="clk2",
                             inter_class="unsafe", wns=-0.1),
            ClockInteraction(from_clock="clk1", to_clock="clk1",
                             inter_class="safe"),
        ]

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert "unsafe" in result.issues[0].message


class TestScorer:
    def test_perfect_score(self):
        scorer = ComplianceScorer()
        from vivado_ai.models.issue import Issue
        score = scorer.score([])
        assert score == 100

    def test_penalties(self):
        scorer = ComplianceScorer()
        issues = [
            Issue(rule_id="T1", rule_name="", severity=Severity.CRITICAL, message=""),
            Issue(rule_id="T2", rule_name="", severity=Severity.FAIL, message=""),
            Issue(rule_id="T3", rule_name="", severity=Severity.WARN, message=""),
        ]
        score = scorer.score(issues)
        assert score == 100 - 15 - 10 - 3  # 72

    def test_minimum_zero(self):
        scorer = ComplianceScorer()
        issues = [Issue(rule_id=f"T{i}", rule_name="", severity=Severity.CRITICAL, message="") for i in range(10)]
        score = scorer.score(issues)
        assert score == 0


class TestEngine:
    def test_lint_mode_missing_clock(self):
        config = CheckConfig(
            mode=CheckMode.LINT,
            xdc_files=[FIXTURES / "xdc" / "missing_clock.xdc"],
            enable_ai=False,
        )
        engine = MethodologyEngine(config)
        result = engine.run()

        rule_ids = [i.rule_id for i in result.issues]
        assert "CONST-001" in rule_ids

    def test_lint_mode_complete(self):
        config = CheckConfig(
            mode=CheckMode.LINT,
            xdc_files=[FIXTURES / "xdc" / "complete_constraints.xdc"],
            enable_ai=False,
        )
        engine = MethodologyEngine(config)
        result = engine.run()

        # Complete constraints should have fewer issues
        const001 = [i for i in result.issues if i.rule_id == "CONST-001"]
        assert len(const001) == 0
