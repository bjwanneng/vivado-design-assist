"""
合规评分器

评分规则:
- CRITICAL: -15 分/条
- FAIL: -10 分/条
- WARN: -3 分/条
- INFO: 不扣分
"""

from vivado_ai.models.issue import Issue, Severity


class ComplianceScorer:

    PENALTY = {
        Severity.CRITICAL: 15,
        Severity.FAIL: 10,
        Severity.WARN: 3,
        Severity.INFO: 0,
    }

    def score(self, issues: list[Issue]) -> int:
        penalty = sum(self.PENALTY.get(i.severity, 0) for i in issues)
        return max(0, 100 - penalty)
