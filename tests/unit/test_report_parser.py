"""Tests for report_parser.py"""

import pytest
from pathlib import Path

from vivado_ai.core.parsers.report_parser import ReportParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestTimingSummaryParser:
    def test_parse_pass(self):
        content = (FIXTURES / "reports" / "timing_summary_pass.rpt").read_text()
        parser = ReportParser()
        summary = parser._parse_timing_summary(content)

        assert summary.wns == pytest.approx(0.245)
        assert summary.whs == pytest.approx(0.089)
        assert summary.failing_endpoints == 0
        assert summary.total_endpoints == 2450

    def test_parse_fail(self):
        content = (FIXTURES / "reports" / "timing_summary_fail.rpt").read_text()
        parser = ReportParser()
        summary = parser._parse_timing_summary(content)

        assert summary.wns == pytest.approx(-0.342)
        assert summary.tns == pytest.approx(-1.856)
        assert summary.failing_endpoints == 12
        assert summary.total_endpoints == 1580

    def test_parse_timing_paths(self):
        content = (FIXTURES / "reports" / "timing_summary_fail.rpt").read_text()
        parser = ReportParser()
        paths = parser._parse_timing_paths(content)

        assert len(paths) >= 1
        assert paths[0].slack == pytest.approx(-0.342)
        assert paths[0].logic_delay == pytest.approx(2.856)
        assert paths[0].net_delay == pytest.approx(1.486)


class TestMethodologyParser:
    def test_parse_violations(self):
        content = (FIXTURES / "reports" / "methodology_violations.rpt").read_text()
        parser = ReportParser()
        checks = parser._parse_methodology(content)

        assert len(checks) >= 2
        check_ids = [c.check_id for c in checks]
        assert "TIMING-14" in check_ids
        assert "TIMING-6" in check_ids


class TestClockInteractionParser:
    def test_parse_unsafe(self):
        content = (FIXTURES / "reports" / "clock_interaction_unsafe.rpt").read_text()
        parser = ReportParser()
        interactions = parser._parse_clock_interaction(content)

        assert len(interactions) >= 3
        unsafe = [i for i in interactions if i.inter_class == "unsafe"]
        assert len(unsafe) == 1
        assert unsafe[0].from_clock == "clk_sys"
        assert unsafe[0].to_clock == "clk_ext"


class TestParseDir:
    def test_parse_directory(self, tmp_path):
        # Copy only the fail report to avoid naming collision
        reports_src = FIXTURES / "reports"
        (tmp_path / "timing_summary_fail.rpt").write_text(
            (reports_src / "timing_summary_fail.rpt").read_text()
        )

        parser = ReportParser()
        findings = parser.parse_dir(tmp_path)

        assert findings.timing_summary is not None
        assert findings.timing_summary.wns == pytest.approx(-0.342)
