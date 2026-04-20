"""
规则注册表

管理所有可用规则，支持按模式和规则组过滤。
"""

import logging
from typing import List, Dict, Type

from vivado_ai.core.rules.base import Rule

logger = logging.getLogger(__name__)


class RuleRegistry:
    """规则注册表"""

    _rules: Dict[str, Type[Rule]] = {}

    @classmethod
    def register(cls, rule_class: Type[Rule]) -> Type[Rule]:
        """注册规则（用作装饰器）"""
        if rule_class.id in cls._rules:
            logger.warning(
                "Duplicate rule_id '%s': overwriting %s with %s",
                rule_class.id,
                cls._rules[rule_class.id].__name__,
                rule_class.__name__,
            )
        cls._rules[rule_class.id] = rule_class
        return rule_class

    def get_rules(
        self,
        mode: str = "all",
        groups: List[str] = None,
    ) -> List[Rule]:
        """获取适用于当前模式的规则实例"""
        rules = []
        for rule_cls in self._rules.values():
            rule = rule_cls()
            # 过滤模式
            if mode != "all" and mode not in rule.applicable_modes:
                continue
            # 过滤规则组
            if groups and "all" not in groups:
                if rule.group not in groups:
                    continue
            rules.append(rule)
        return rules

    def list_rules(self) -> List[dict]:
        """列出所有已注册规则"""
        return [
            {
                "id": cls.id,
                "name": cls.name,
                "group": cls.group,
                "severity": cls.severity.value,
                "modes": cls.applicable_modes,
            }
            for cls in self._rules.values()
        ]
