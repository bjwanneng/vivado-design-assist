"""Tests for Phase 2 rules (IMPL, OPT, FLOW, RTL)"""

import pytest
from pathlib import Path

from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.core.engine import MethodologyEngine, CheckConfig, CheckMode
from vivado_ai.models.finding import (
    Findings, StageLogData, LogMessage, CongestionReport,
    TimingSummary, TimingPath, ClockInteraction, MethodologyCheck,
)
from vivado_ai.models.issue import Severity

# Register all rules
import vivado_ai.core.rules.constraint_rules   # noqa: F401
import vivado_ai.core.rules.synth_rules         # noqa: F401
import vivado_ai.core.rules.place_rules         # noqa: F401
import vivado_ai.core.rules.route_rules         # noqa: F401
import vivado_ai.core.rules.root_cause_rules    # noqa: F401
import vivado_ai.core.rules.impl_rules          # noqa: F401
import vivado_ai.core.rules.opt_rules           # noqa: F401
import vivado_ai.core.rules.flow_rules          # noqa: F401
import vivado_ai.core.rules.rtl_rules           # noqa: F401

from vivado_ai.core.parsers.log_parser import LogParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ─── IMPL Rules ────────────────────────────────────────

class TestReportMethodologyExecution:
    def test_warns_when_no_methodology(self):
        from vivado_ai.core.rules.impl_rules import ReportMethodologyExecution
        rule = ReportMethodologyExecution()
        findings = Findings()
        findings.timing_summary = TimingSummary(wns=-0.1)
        findings.methodology_checks = []  # empty = not run

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert result.issues[0].rule_id == "IMPL-002"


class TestReportQoRSuggestions:
    def test_suggests_when_timing_fails(self):
        from vivado_ai.core.rules.impl_rules import ReportQoRSuggestionsExecution
        rule = ReportQoRSuggestionsExecution()
        findings = Findings()
        findings.timing_summary = TimingSummary(wns=-0.5)

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert "qor_suggestions" in result.issues[0].fix_suggestion.lower()


# ─── OPT Rules ─────────────────────────────────────────

class TestDontTouchBlocking:
    def test_detects_dont_touch(self):
        from vivado_ai.core.rules.opt_rules import OptimizationBlockedByDontTouch
        rule = OptimizationBlockedByDontTouch()
        findings = Findings()
        findings.opt_log = StageLogData(
            stage="opt",
            messages=[
                LogMessage(level="WARNING", code="Opt 31-68",
                           text="DONT_TOUCH property on module prevented optimization"),
                LogMessage(level="WARNING", code="Opt 31-68",
                           text="DONT_TOUCH property on ila prevented optimization"),
            ],
        )

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert "DONT_TOUCH" in result.issues[0].message


# ─── FLOW Rules ────────────────────────────────────────

class TestPerStageCriticalWarnings:
    def test_counts_crit_warnings(self):
        from vivado_ai.core.rules.flow_rules import PerStageCriticalWarnings
        rule = PerStageCriticalWarnings()
        findings = Findings()
        findings.synth_log = StageLogData(
            stage="synthesis",
            messages=[
                LogMessage(level="CRITICAL WARNING", code="Synth 8-524",
                           text="clock route issue"),
                LogMessage(level="WARNING", code="Synth 8-327",
                           text="latch"),
            ],
        )
        findings.place_log = StageLogData(
            stage="place",
            messages=[
                LogMessage(level="CRITICAL WARNING", code="Place 30-494",
                           text="placement failed"),
            ],
        )

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert "2" in result.issues[0].message  # 2 CRITICAL WARNINGs


class TestWNSEvolutionTrend:
    def test_tracks_wns_evolution(self):
        from vivado_ai.core.rules.flow_rules import WNSEvolutionTrend
        rule = WNSEvolutionTrend()
        findings = Findings()
        findings.synth_log = StageLogData(stage="synthesis", wns_after_phys_opt=-0.5)
        findings.place_log = StageLogData(stage="place", wns_after_phys_opt=-0.3)
        findings.route_log = StageLogData(stage="route", wns_after_phys_opt=-0.1)

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert "3 stages" in result.issues[0].message


class TestRepeatedIssuesAcrossStages:
    def test_finds_repeated_codes(self):
        from vivado_ai.core.rules.flow_rules import RepeatedIssuesAcrossStages
        rule = RepeatedIssuesAcrossStages()
        findings = Findings()
        findings.synth_log = StageLogData(
            stage="synthesis",
            messages=[LogMessage(level="WARNING", code="Synth 8-6416",
                                 text="DONT_TOUCH blocking")],
        )
        findings.place_log = StageLogData(
            stage="place",
            messages=[LogMessage(level="WARNING", code="Synth 8-6416",
                                 text="DONT_TOUCH still blocking")],
        )

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert "multiple stages" in result.issues[0].message.lower()


class TestCompileTimeBreakdown:
    def test_reports_time(self):
        from vivado_ai.core.rules.flow_rules import CompileTimeBreakdown
        rule = CompileTimeBreakdown()
        findings = Findings()
        findings.synth_log = StageLogData(stage="synthesis", duration_seconds=120)
        findings.place_log = StageLogData(stage="place", duration_seconds=300)

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert "7m0s" in result.issues[0].message  # 120+300=420s=7m0s


# ─── RTL Rules ─────────────────────────────────────────

class TestCDCNoSynchronizer:
    def test_detects_unsafe_interaction(self):
        from vivado_ai.core.rules.rtl_rules import CDCNoSynchronizer
        rule = CDCNoSynchronizer()
        findings = Findings()
        findings.clock_interactions = [
            ClockInteraction(from_clock="clk1", to_clock="clk2",
                             inter_class="unsafe"),
        ]

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert result.issues[0].rule_id == "RTL-003"


class TestNotUsingXPM:
    def test_suggests_xpm_for_manual_ram(self):
        from vivado_ai.core.rules.rtl_rules import NotUsingXPM
        rule = NotUsingXPM()
        findings = Findings()
        findings.synth_log = StageLogData(
            stage="synthesis",
            messages=[
                LogMessage(level="WARNING", code="Synth 8-3936",
                           text="ram_inst is not inferred as dedicated Block RAM"),
            ],
        )

        result = rule.check(findings)
        assert len(result.issues) == 1
        assert "XPM" in result.issues[0].fix_suggestion


# ─── Engine integration ───────────────────────────────

class TestEnginePhase2:
    def test_analyze_with_full_log(self):
        """Test analyze mode with full build log fixture"""
        config = CheckConfig(
            mode=CheckMode.ANALYZE,
            log_dir=FIXTURES / "logs",
            enable_ai=False,
        )
        engine = MethodologyEngine(config)
        result = engine.run()

        # Should have issues from SYNTH, PLACE, ROUTE, FLOW rules
        rule_ids = [i.rule_id for i in result.issues]
        # At minimum SYNTH-002 (latch) and FLOW rules
        assert any("SYNTH" in rid for rid in rule_ids)

    def test_analyze_opt_fixture(self):
        config = CheckConfig(
            mode=CheckMode.ANALYZE,
            log_dir=FIXTURES / "logs",
            enable_ai=False,
        )
        engine = MethodologyEngine(config)
        result = engine.run()

        # Should find OPT-001 from opt_dont_touch.log
        rule_ids = [i.rule_id for i in result.issues]
        assert "OPT-001" in rule_ids
