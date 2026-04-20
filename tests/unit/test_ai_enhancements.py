"""Tests for AI enhancements: forum links, root cause summary, new fields"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from vivado_ai.models.issue import Issue, Severity
from vivado_ai.models.report import CheckReport
from vivado_ai.core.engine import MethodologyEngine, CheckConfig, CheckMode


class TestIssueNewFields:
    def test_message_code_default(self):
        issue = Issue(rule_id="T", rule_name="T", severity=Severity.WARN, message="x")
        assert issue.message_code == ""
        assert issue.forum_url == ""

    def test_message_code_set(self):
        issue = Issue(
            rule_id="SYNTH-002", rule_name="Latch", severity=Severity.FAIL,
            message="Latch inferred", message_code="Synth 8-327",
        )
        assert issue.message_code == "Synth 8-327"


class TestForumLinkGeneration:
    def test_attach_forum_links_skips_pass(self):
        engine = MethodologyEngine(CheckConfig(
            mode=CheckMode.LINT,
            xdc_files=[Path("dummy")],
            enable_ai=False,
        ))
        issues = [
            Issue(rule_id="T", rule_name="T", severity=Severity.PASS, message="ok"),
        ]
        engine._attach_forum_links(issues)
        assert issues[0].forum_url == ""

    def test_attach_forum_links_with_code(self):
        engine = MethodologyEngine(CheckConfig(
            mode=CheckMode.ANALYZE,
            log_dir=Path("dummy"),
            enable_ai=False,
        ))
        issues = [
            Issue(
                rule_id="SYNTH-002", rule_name="Latch", severity=Severity.FAIL,
                message="test", message_code="Synth 8-327",
            ),
        ]
        engine._attach_forum_links(issues)
        assert "support.xilinx.com" in issues[0].forum_url
        assert "Synth" in issues[0].forum_url
        assert "8-327" in issues[0].forum_url

    def test_attach_forum_links_without_code(self):
        engine = MethodologyEngine(CheckConfig(
            mode=CheckMode.LINT,
            xdc_files=[Path("dummy")],
            enable_ai=False,
        ))
        issues = [
            Issue(
                rule_id="CONST-001", rule_name="Clock Period Constraints",
                severity=Severity.WARN, message="test",
            ),
        ]
        engine._attach_forum_links(issues)
        assert "support.xilinx.com" in issues[0].forum_url
        assert "Clock" in issues[0].forum_url
        assert "Period" in issues[0].forum_url

    def test_forum_link_on_real_lint(self):
        """Test that lint mode actually produces forum links"""
        config = CheckConfig(
            mode=CheckMode.LINT,
            xdc_files=[Path("tests/fixtures/xdc/missing_clock.xdc")],
            enable_ai=False,
        )
        engine = MethodologyEngine(config)
        result = engine.run()

        for issue in result.issues:
            assert issue.forum_url != "", f"No forum URL for {issue.rule_id}"
            assert "support.xilinx.com" in issue.forum_url

    def test_forum_link_on_real_analyze(self):
        """Test that analyze mode produces forum links with message codes"""
        config = CheckConfig(
            mode=CheckMode.ANALYZE,
            log_dir=Path("tests/fixtures/logs"),
            enable_ai=False,
        )
        engine = MethodologyEngine(config)
        result = engine.run()

        for issue in result.issues:
            assert issue.forum_url != "", f"No forum URL for {issue.rule_id}"


class TestReportRootCause:
    def test_root_cause_in_markdown(self):
        report = CheckReport(
            mode="analyze",
            total_rules=0,
            total_issues=0,
            score=100,
            root_cause_summary="All issues stem from missing clock constraints.",
        )
        md = report.to_markdown()
        assert "Root Cause Analysis" in md
        assert "missing clock constraints" in md

    def test_root_cause_in_json(self):
        report = CheckReport(
            mode="check",
            total_rules=0,
            total_issues=0,
            score=80,
            root_cause_summary="Test summary",
        )
        j = report.to_json()
        assert '"root_cause_summary": "Test summary"' in j

    def test_empty_root_cause_omitted_in_markdown(self):
        report = CheckReport(
            mode="check",
            total_rules=0,
            total_issues=0,
            score=100,
        )
        md = report.to_markdown()
        assert "Root Cause Analysis" not in md

    def test_forum_url_in_markdown(self):
        report = CheckReport(
            mode="analyze",
            total_rules=0,
            total_issues=1,
            score=90,
            issues=[
                Issue(
                    rule_id="SYNTH-002", rule_name="Latch", severity=Severity.FAIL,
                    message="test", forum_url="https://support.xilinx.com/s/search?q=Synth+8-327",
                ),
            ],
        )
        md = report.to_markdown()
        assert "support.xilinx.com" in md

    def test_forum_url_in_json(self):
        report = CheckReport(
            mode="analyze",
            total_rules=0,
            total_issues=1,
            score=90,
            issues=[
                Issue(
                    rule_id="SYNTH-002", rule_name="Latch", severity=Severity.FAIL,
                    message="test", message_code="Synth 8-327",
                    forum_url="https://support.xilinx.com/s/search?q=Synth+8-327",
                ),
            ],
        )
        j = report.to_json()
        assert "forum_url" in j
        assert "message_code" in j


class TestAIInterpreterRootCause:
    def test_analyze_root_cause_no_issues(self):
        """Empty issue list returns empty string without calling LLM"""
        with patch("vivado_ai.core.ai_interpreter.create_llm") as mock_create:
            mock_llm = MagicMock()
            mock_create.return_value = mock_llm
            from vivado_ai.core.ai_interpreter import AIInterpreter
            ai = AIInterpreter()
            result = ai.analyze_root_cause([])
            assert result == ""
            mock_llm.chat.assert_not_called()

    def test_analyze_root_cause_with_issues(self):
        """Root cause analysis calls LLM and returns response"""
        with patch("vivado_ai.core.ai_interpreter.create_llm") as mock_create:
            mock_llm = MagicMock()
            mock_llm.chat.return_value = MagicMock(text="Common root cause: clock issues")
            mock_create.return_value = mock_llm
            from vivado_ai.core.ai_interpreter import AIInterpreter
            ai = AIInterpreter()
            issues = [
                Issue(
                    rule_id="SYNTH-002", rule_name="Latch", severity=Severity.FAIL,
                    message="Latch inferred", message_code="Synth 8-327",
                ),
            ]
            result = ai.analyze_root_cause(issues)
            assert "clock issues" in result
            mock_llm.chat.assert_called_once()

    def test_analyze_root_cause_handles_error(self):
        """Root cause analysis returns error message on failure"""
        with patch("vivado_ai.core.ai_interpreter.create_llm") as mock_create:
            mock_llm = MagicMock()
            mock_llm.chat.side_effect = Exception("API error")
            mock_create.return_value = mock_llm
            from vivado_ai.core.ai_interpreter import AIInterpreter
            ai = AIInterpreter()
            issues = [
                Issue(
                    rule_id="SYNTH-002", rule_name="Latch", severity=Severity.FAIL,
                    message="test",
                ),
            ]
            result = ai.analyze_root_cause(issues)
            assert "unavailable" in result


class TestEngineRootCauseResult:
    def test_engine_without_ai_no_root_cause(self):
        config = CheckConfig(
            mode=CheckMode.LINT,
            xdc_files=[Path("tests/fixtures/xdc/missing_clock.xdc")],
            enable_ai=False,
        )
        engine = MethodologyEngine(config)
        result = engine.run()
        assert result.root_cause_summary == ""
