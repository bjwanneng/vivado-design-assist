"""
规则基类

每条规则对应 UG949/UG1292 中的一个检查项。
规则只做确定性判断，不做 AI 推理。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

from vivado_ai.models.finding import Findings
from vivado_ai.models.issue import Issue, Severity


@dataclass
class RuleResult:
    """规则执行结果"""
    rule_id: str
    issues: List[Issue] = field(default_factory=list)


class Rule(ABC):
    """
    方法论检查规则基类

    子类必须定义:
    - id: 规则ID，e.g. "CONST-001"
    - name: 规则名称
    - group: 规则组，e.g. "A" (约束), "E" (综合Log)
    - severity: 默认严重性
    - applicable_modes: 适用模式列表
    """

    id: str = ""
    name: str = ""
    group: str = ""
    severity: Severity = Severity.FAIL
    ug949_ref: str = ""
    ug1292_ref: str = ""
    applicable_modes: List[str] = field(default_factory=lambda: ["check"])

    @abstractmethod
    def check(self, findings: Findings) -> RuleResult:
        """
        执行检查

        Args:
            findings: 解析器提取的结构化数据

        Returns:
            RuleResult: 包含发现的问题列表（空列表 = PASS）
        """
        pass

    def _create_issue(
        self,
        message: str,
        detail: str = "",
        fix_suggestion: str = "",
        location: str = "",
        severity: Severity = None,
        message_code: str = "",
    ) -> Issue:
        return Issue(
            rule_id=self.id,
            rule_name=self.name,
            severity=severity or self.severity,
            message=message,
            detail=detail,
            fix_suggestion=fix_suggestion,
            location=location,
            message_code=message_code,
            ug949_ref=self.ug949_ref,
            ug1292_ref=self.ug1292_ref,
        )
