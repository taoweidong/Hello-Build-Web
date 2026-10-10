"""数据模型包：按领域拆分文件，统一从此处导出，保持既有导入方式不变。

- report.py：验证报告领域（报告主表 + 修改记录表，不与其他表建立外键）
- others.py：其余业务模型（用户/版本/分支/策略/执行/日志等）
"""
from .others import (
    AdminOpLog,
    Branch,
    ExecutionLog,
    ExecutionRound,
    SecurityLog,
    Strategy,
    StrategyChangeLog,
    StrategyTemplate,
    User,
    Version,
)
from .report import ReportRevisionLog, VerificationReport
from .branch_config import (
    BranchPermission,
    BranchProject,
    Instance,
    Project,
    StartupConfig,
)
from .slot_booking import SlotBooking, SlotTemplate

__all__ = [
    "AdminOpLog",
    "Branch",
    "BranchPermission",
    "BranchProject",
    "ExecutionLog",
    "ExecutionRound",
    "Instance",
    "Project",
    "ReportRevisionLog",
    "SecurityLog",
    "SlotBooking",
    "SlotTemplate",
    "StartupConfig",
    "Strategy",
    "StrategyChangeLog",
    "StrategyTemplate",
    "User",
    "VerificationReport",
    "Version",
]