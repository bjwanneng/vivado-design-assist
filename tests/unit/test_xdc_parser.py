"""Tests for xdc_parser.py"""

import pytest
from pathlib import Path

from vivado_ai.core.parsers.xdc_parser import XDCParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestXDCParser:
    def test_parse_complete_constraints(self):
        parser = XDCParser()
        data = parser.parse(FIXTURES / "xdc" / "complete_constraints.xdc")

        cmd_types = [c.type for c in data.commands]
        assert "create_clock" in cmd_types
        assert "set_clock_groups" in cmd_types
        assert "set_input_delay" in cmd_types
        assert "set_output_delay" in cmd_types

    def test_parse_clock_names(self):
        parser = XDCParser()
        data = parser.parse(FIXTURES / "xdc" / "complete_constraints.xdc")

        clocks = [c for c in data.commands if c.type == "create_clock"]
        assert len(clocks) == 2
        clock_names = [c.args.get("name", "") for c in clocks]
        assert "clk_sys" in clock_names
        assert "clk_ext" in clock_names

    def test_parse_missing_clock(self):
        parser = XDCParser()
        data = parser.parse(FIXTURES / "xdc" / "missing_clock.xdc")

        has_create_clock = any(c.type == "create_clock" for c in data.commands)
        assert not has_create_clock

        false_paths = [c for c in data.commands if c.type == "set_false_path"]
        assert len(false_paths) == 4

    def test_parse_string(self):
        parser = XDCParser()
        data = parser.parse_string(
            'create_clock -period 5.0 -name clk [get_ports clk_in]\n'
            'set_input_delay -clock [get_clocks clk] 2.0 [get_ports data]\n'
        )

        assert len(data.commands) == 2
        assert data.commands[0].args["period"] == pytest.approx(5.0)
        assert data.commands[0].args["name"] == "clk"
