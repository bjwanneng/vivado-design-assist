"""
方法论检查结果模型

Issue 代表一条规则检查的结果（违规或通过）。
"""

from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    CRITICAL = "CRITICAL"
    FAIL = "FAIL"
    WARN = "WARN"
    INFO = "INFO"
    PASS = "PASS"


@dataclass
class Issue:
    """方法论检查结果"""
    # 规则信息
    rule_id: str               # e.g. "CONST-001"
    rule_name: str             # e.g. "Clock Period Constraints"
    severity: Severity         # FAIL / WARN / INFO / PASS

    # 问题描述
    message: str               # 简短描述
    detail: str = ""           # 详细说明

    # 修复建议
    fix_suggestion: str = ""

    # 定位信息
    location: str = ""         # 文件名:行号 或 实例路径

    # 参考文档
    ug949_ref: str = ""        # UG949 章节引用
    ug1292_ref: str = ""       # UG1292 引用 (可选)

    # AI 解读 (由 ai_interpreter.py 填充)
    ai_explanation: str = ""
