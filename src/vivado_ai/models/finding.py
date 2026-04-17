"""
解析器产出的结构化数据模型

Findings 是所有解析结果的汇总容器，作为规则引擎的输入。
"""

from dataclasses import dataclass, field
from typing import List, Optional


# ─── 报告解析辅助类型 ─────────────────────────────────────

@dataclass
class TimingPath:
    """时序路径"""
    slack: float
    start_point: str
    end_point: str
    path_type: str = "setup"   # "setup" | "hold"
    requirement: float = 0.0
    datapath_delay: float = 0.0
    logic_delay: float = 0.0
    net_delay: float = 0.0
    clock_skew: float = 0.0
    logic_levels: int = 0


@dataclass
class TimingSummary:
    """时序汇总"""
    wns: float = 0.0
    tns: float = 0.0
    whs: float = 0.0
    ths: float = 0.0
    failing_endpoints: int = 0
    total_endpoints: int = 0


@dataclass
class MethodologyCheck:
    """report_methodology 单条检查"""
    check_id: str       # e.g. "TIMING-14"
    severity: str       # "CRITICAL WARNING" | "WARNING" | "INFO"
    message: str
    details: List[str] = field(default_factory=list)


@dataclass
class ClockInteraction:
    """时钟域交互"""
    from_clock: str
    to_clock: str
    inter_class: str   # "safe" | "no" | "unsafe"
    wns: Optional[float] = None


@dataclass
class ClockNetwork:
    """时钟网络"""
    name: str
    source_port: str = ""
    endpoint_count: int = 0


# ─── Log 解析辅助类型 ─────────────────────────────────────

@dataclass
class LogMessage:
    """Log 中的单条消息"""
    level: str           # "ERROR" | "CRITICAL WARNING" | "WARNING" | "INFO"
    code: str            # e.g. "Synth 8-327", "Place 30-487"
    text: str
    source: str = ""
    timestamp: str = ""


@dataclass
class CongestionReport:
    """拥塞报告"""
    level: int            # 1-5
    region: str           # e.g. "X12Y5:W16xH16"
    top_modules: List[str] = field(default_factory=list)


@dataclass
class StageLogData:
    """单阶段 log 数据"""
    stage: str            # "synthesis" | "opt" | "place" | "route"
    messages: List[LogMessage] = field(default_factory=list)
    congestion_reports: List[CongestionReport] = field(default_factory=list)
    wns_before_phys_opt: Optional[float] = None
    wns_after_phys_opt: Optional[float] = None
    duration_seconds: Optional[float] = None


# ─── XDC 解析辅助类型 ─────────────────────────────────────

@dataclass
class XDCCommand:
    """XDC 命令"""
    type: str           # "create_clock", "set_input_delay", etc.
    args: dict = field(default_factory=dict)
    line: int = 0
    file_path: str = ""
    raw: str = ""


@dataclass
class XDCData:
    """XDC 文件解析结果"""
    commands: List[XDCCommand] = field(default_factory=list)
    file_path: str = ""


# ─── 汇总容器 ─────────────────────────────────────────────

@dataclass
class Findings:
    """
    所有解析结果的汇总容器

    各解析器将数据填充到对应字段，规则引擎读取需要的字段进行判断。
    """
    # Mode 1: Lint 数据
    xdc_data: Optional[XDCData] = None

    # Mode 2: Check 数据（报告文件解析）
    timing_summary: Optional[TimingSummary] = None
    timing_paths: List[TimingPath] = field(default_factory=list)
    methodology_checks: List[MethodologyCheck] = field(default_factory=list)
    clock_interactions: List[ClockInteraction] = field(default_factory=list)
    clock_networks: List[ClockNetwork] = field(default_factory=list)
    failfast_data: Optional[dict] = None
    utilization: Optional[dict] = None

    # Mode 3: Analyze 数据（Log 文件解析）
    synth_log: Optional[StageLogData] = None
    opt_log: Optional[StageLogData] = None
    place_log: Optional[StageLogData] = None
    route_log: Optional[StageLogData] = None
