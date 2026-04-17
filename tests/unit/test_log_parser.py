"""Tests for log_parser.py"""

import pytest
from pathlib import Path

from vivado_ai.core.parsers.log_parser import LogParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestSynthLogParser:
    def test_parse_latch_warning(self):
        content = (FIXTURES / "logs" / "synth_with_latch.log").read_text()
        parser = LogParser()
        stage_log = parser._parse_stage(content, "synthesis")

        latch_msgs = [m for m in stage_log.messages if m.code == "Synth 8-327"]
        assert len(latch_msgs) == 3

    def test_parse_clock_route(self):
        content = (FIXTURES / "logs" / "synth_with_latch.log").read_text()
        parser = LogParser()
        stage_log = parser._parse_stage(content, "synthesis")

        clock_msgs = [
            m for m in stage_log.messages
            if "clock" in m.text.lower() and m.level == "CRITICAL WARNING"
        ]
        assert len(clock_msgs) >= 1

    def test_parse_ram_warning(self):
        content = (FIXTURES / "logs" / "synth_with_latch.log").read_text()
        parser = LogParser()
        stage_log = parser._parse_stage(content, "synthesis")

        ram_msgs = [m for m in stage_log.messages if m.code == "Synth 8-3936"]
        assert len(ram_msgs) == 1


class TestPlaceLogParser:
    def test_parse_congestion(self):
        content = (FIXTURES / "logs" / "place_congestion.log").read_text()
        parser = LogParser()
        stage_log = parser._parse_stage(content, "place")

        assert len(stage_log.congestion_reports) >= 1
        levels = [c.level for c in stage_log.congestion_reports]
        assert 4 in levels

    def test_parse_wns(self):
        content = (FIXTURES / "logs" / "place_congestion.log").read_text()
        parser = LogParser()
        stage_log = parser._parse_stage(content, "place")

        assert stage_log.wns_before_phys_opt is not None
        assert stage_log.wns_after_phys_opt is not None


class TestRouteLogParser:
    def test_parse_unrouted(self):
        content = (FIXTURES / "logs" / "route_unrouted.log").read_text()
        parser = LogParser()
        stage_log = parser._parse_stage(content, "route")

        unrouted = [m for m in stage_log.messages if "unrouted" in m.text.lower()]
        assert len(unrouted) >= 1


class TestParseDir:
    def test_parse_log_directory(self, tmp_path):
        # Copy fixture log files
        logs_src = FIXTURES / "logs"
        for f in logs_src.glob("*.log"):
            (tmp_path / f.name).write_text(f.read_text())

        parser = LogParser()
        findings = parser.parse_dir(tmp_path)

        assert findings.synth_log is not None
        assert findings.place_log is not None
        assert findings.route_log is not None
