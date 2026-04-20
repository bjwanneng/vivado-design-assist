"""
输出报告模型

CheckReport 封装检查结果，支持 Markdown 和 JSON 导出。
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict

from vivado_ai.models.issue import Issue, Severity


@dataclass
class CheckReport:
    """检查报告"""
    mode: str              # "lint" | "check" | "analyze"
    total_rules: int       # 执行的规则总数
    total_issues: int      # 发现的问题总数

    # 分类统计
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_group: Dict[str, List[Issue]] = field(default_factory=dict)

    # 评分
    score: int = 100       # 合规评分 0-100

    # 问题列表
    issues: List[Issue] = field(default_factory=list)

    # 优先修复建议
    priority_actions: List[str] = field(default_factory=list)

    # AI 跨 issue 根因分析
    root_cause_summary: str = ""

    def to_markdown(self) -> str:
        """生成 Markdown 格式报告"""
        lines = [
            "# Vivado Methodology Check Report",
            f"\n**Mode**: {self.mode}",
            f"**Score**: {self.score}/100",
            f"**Total Issues**: {self.total_issues}",
            "",
            "## Summary",
            "",
        ]
        for sev, count in self.by_severity.items():
            lines.append(f"- {sev}: {count}")

        if self.root_cause_summary:
            lines.append("\n## Root Cause Analysis\n")
            lines.append(self.root_cause_summary)

        if self.priority_actions:
            lines.append("\n## Priority Actions\n")
            for action in self.priority_actions:
                lines.append(f"- {action}")

        lines.append("\n## Issues\n")
        for issue in self.issues:
            if issue.severity == Severity.PASS:
                continue
            lines.append(
                f"### [{issue.severity.value}] "
                f"{issue.rule_id}: {issue.rule_name}"
            )
            lines.append(f"\n{issue.message}")
            if issue.detail:
                lines.append(f"\n**Detail**: {issue.detail}")
            if issue.fix_suggestion:
                lines.append(f"\n**Fix**: {issue.fix_suggestion}")
            if issue.forum_url:
                lines.append(f"\n**Forum**: {issue.forum_url}")
            if issue.ai_explanation:
                lines.append(f"\n**AI Analysis**: {issue.ai_explanation}")
            if issue.ug949_ref:
                lines.append(f"\n**Ref**: UG949 {issue.ug949_ref}")
            lines.append("\n---\n")

        return "\n".join(lines)

    def to_json(self) -> str:
        """生成 JSON 格式"""
        data = {
            "mode": self.mode,
            "score": self.score,
            "total_issues": self.total_issues,
            "by_severity": self.by_severity,
            "root_cause_summary": self.root_cause_summary,
            "priority_actions": self.priority_actions,
            "issues": [
                {
                    "rule_id": i.rule_id,
                    "rule_name": i.rule_name,
                    "severity": i.severity.value,
                    "message": i.message,
                    "detail": i.detail,
                    "fix": i.fix_suggestion,
                    "location": i.location,
                    "message_code": i.message_code,
                    "forum_url": i.forum_url,
                    "ref": i.ug949_ref,
                    "ug1292_ref": i.ug1292_ref,
                    "ai_explanation": i.ai_explanation,
                }
                for i in self.issues
            ],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)
