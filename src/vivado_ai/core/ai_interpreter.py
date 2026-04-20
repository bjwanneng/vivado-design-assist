"""
AI 增强解读

为规则引擎产出的 Issue 提供 AI 生成的人类可读解释和修复建议。
AI 只做解释，不做判断。
"""

from typing import List

from vivado_ai.models.issue import Issue, Severity
from vivado_ai.core.llm_provider import create_llm, LLMConfig


SYSTEM_PROMPT = """You are a Vivado FPGA design methodology expert.
You explain UG949 UltraFast Design Methodology violations in clear,
concise Chinese.

Your job:
1. Explain WHY this is a problem (technical root cause)
2. Explain WHAT impact it has on the design
3. Give a SPECIFIC fix for THIS particular case

Rules:
- Be concise (max 200 words per explanation)
- Always reference UG949 chapter/section when possible
- Include specific TCL/XDC code in fix suggestions
- Do NOT make judgments about pass/fail (that's done by rule engine)
- If you're unsure, say so explicitly
"""


class AIInterpreter:
    """AI 增强解读"""

    def __init__(self, llm_config: LLMConfig = None):
        if llm_config is None:
            llm_config = LLMConfig(
                provider="claude",
                model="claude-haiku-4-20250514",
                max_tokens=512,
                temperature=0.2,
            )
        self.llm = create_llm(llm_config)

    def explain(self, issue: Issue) -> str:
        """为单个 Issue 生成 AI 解读"""
        user_message = (
            f"Rule: {issue.rule_id} ({issue.rule_name})\n"
            f"Severity: {issue.severity.value}\n"
            f"Message: {issue.message}\n"
            f"Detail: {issue.detail}\n"
            f"Location: {issue.location}\n"
            f"UG949 Ref: {issue.ug949_ref}\n"
            f"UG1292 Ref: {issue.ug1292_ref}\n\n"
            f"Please explain this methodology violation "
            f"in Chinese, including:\n"
            f"1. Why this is a problem\n"
            f"2. What's the impact\n"
            f"3. Specific fix suggestion with code"
        )

        try:
            response = self.llm.chat(
                system_prompt=SYSTEM_PROMPT,
                user_message=user_message,
            )
            return response.text
        except Exception as e:
            return f"[AI explanation unavailable: {e}]"

    def explain_batch(self, issues: list[Issue]) -> dict[int, str]:
        """批量生成解读（只对 FAIL/CRITICAL 级别）"""
        results = {}
        for idx, issue in enumerate(issues):
            if issue.severity in (Severity.FAIL, Severity.CRITICAL):
                results[idx] = self.explain(issue)
        return results

    def analyze_root_cause(self, issues: List[Issue]) -> str:
        """跨 issue 根因分析 — 归纳所有 FAIL/CRITICAL 的共同根因"""
        critical_issues = [
            i for i in issues
            if i.severity in (Severity.FAIL, Severity.CRITICAL)
        ]
        if not critical_issues:
            return ""

        issue_summary = "\n".join(
            f"- [{i.severity.value}] {i.rule_id}: {i.message}"
            + (f" (code: {i.message_code})" if i.message_code else "")
            for i in critical_issues
        )

        user_message = (
            f"The following {len(critical_issues)} methodology violations were found:\n\n"
            f"{issue_summary}\n\n"
            f"Please analyze the root cause in Chinese:\n"
            f"1. What is the common root cause (if any)?\n"
            f"2. What is the priority fix order?\n"
            f"3. One-sentence executive summary.\n"
            f"Keep it under 300 words."
        )

        try:
            response = self.llm.chat(
                system_prompt=SYSTEM_PROMPT,
                user_message=user_message,
            )
            return response.text
        except Exception as e:
            return f"[AI root cause analysis unavailable: {e}]"
