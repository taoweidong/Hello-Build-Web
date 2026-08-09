from datetime import UTC, datetime

from sqlalchemy import DateTime, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    """与历史数据格式保持一致的 naive UTC 时间"""
    return datetime.now(UTC).replace(tzinfo=None)


# ------------------------------- 表模型 -------------------------------


class User(SQLModel, table=True):
    __tablename__ = "user"
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=64)
    password_hash: str = Field(max_length=255)
    display_name: str = Field(max_length=64)
    role: str = Field(max_length=20)  # admin/pm/builder/tester/integrator
    is_active: bool = True
    created_at: datetime = Field(default_factory=get_datetime_utc)


class Version(SQLModel, table=True):
    __tablename__ = "version"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, max_length=32)
    pm_user_id: int | None = Field(default=None, foreign_key="user.id", unique=True)
    status: str = Field(default="active", max_length=20)  # active/archived
    created_at: datetime = Field(default_factory=get_datetime_utc)
    branches: list["Branch"] = Relationship(back_populates="version")


class Branch(SQLModel, table=True):
    __tablename__ = "branch"
    __table_args__ = (
        UniqueConstraint("version_id", "name", name="uq_branch_version_name"),
    )
    id: int | None = Field(default=None, primary_key=True)
    version_id: int = Field(foreign_key="version.id")
    name: str = Field(max_length=64)
    created_at: datetime = Field(default_factory=get_datetime_utc)
    version: Version | None = Relationship(back_populates="branches")
    strategies: list["Strategy"] = Relationship(back_populates="branch")


class StrategyTemplate(SQLModel, table=True):
    __tablename__ = "strategy_template"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=64)
    smoke_minutes: int
    analysis_minutes: int
    description: str | None = Field(default=None, max_length=255)
    created_by: int | None = Field(default=None, foreign_key="user.id")
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime,  # type: ignore
        sa_column_kwargs={"onupdate": get_datetime_utc},
    )


class Strategy(SQLModel, table=True):
    __tablename__ = "strategy"
    id: int | None = Field(default=None, primary_key=True)
    branch_id: int = Field(foreign_key="branch.id")
    template_id: int = Field(foreign_key="strategy_template.id")
    name: str = Field(max_length=64)
    build_start_time: str = Field(max_length=5)  # "HH:MM" 每日循环
    push_mode: str = Field(default="normal", max_length=10)  # normal/sync
    enabled: bool = True
    created_by: int | None = Field(default=None, foreign_key="user.id")
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime,  # type: ignore
        sa_column_kwargs={"onupdate": get_datetime_utc},
    )
    branch: Branch | None = Relationship(back_populates="strategies")
    template: StrategyTemplate | None = Relationship()


class ExecutionRound(SQLModel, table=True):
    __tablename__ = "execution_round"
    __table_args__ = (
        UniqueConstraint("strategy_id", "exec_date", name="uq_round_strategy_date"),
    )
    id: int | None = Field(default=None, primary_key=True)
    strategy_id: int = Field(foreign_key="strategy.id")
    exec_date: str = Field(max_length=10)  # "YYYY-MM-DD"
    # 各阶段绝对时间（可跨天）
    push_start: datetime | None = None
    push_end: datetime | None = None
    build_start: datetime
    build_end: datetime
    smoke_start: datetime
    smoke_end: datetime
    analysis_start: datetime
    analysis_end: datetime
    conclusion: str = Field(default="pending", max_length=10)  # pending/pass/fail
    conclusion_by: int | None = Field(default=None, foreign_key="user.id")
    conclusion_at: datetime | None = None
    conclusion_note: str | None = Field(default=None, max_length=500)
    push_status: str = Field(default="not_triggered", max_length=10)  # not_triggered/pending/success/failed
    release_approved: bool | None = None  # sync 模式标记
    strategy: Strategy | None = Relationship()


class ExecutionLog(SQLModel, table=True):
    __tablename__ = "execution_log"
    id: int | None = Field(default=None, primary_key=True)
    round_id: int = Field(foreign_key="execution_round.id")
    stage: str = Field(max_length=32)
    event: str = Field(max_length=64)
    detail: str | None = Field(default=None, sa_type=Text)  # type: ignore
    at: datetime = Field(default_factory=get_datetime_utc)


class StrategyChangeLog(SQLModel, table=True):
    __tablename__ = "strategy_change_log"
    id: int | None = Field(default=None, primary_key=True)
    strategy_id: int = Field(foreign_key="strategy.id")
    operator: int = Field(foreign_key="user.id")
    field: str = Field(max_length=32)
    old_value: str | None = Field(default=None, max_length=255)
    new_value: str | None = Field(default=None, max_length=255)
    at: datetime = Field(default_factory=get_datetime_utc)


class AdminOpLog(SQLModel, table=True):
    __tablename__ = "admin_op_log"
    id: int | None = Field(default=None, primary_key=True)
    operator: int = Field(foreign_key="user.id")
    action: str = Field(max_length=64)
    target_type: str = Field(max_length=32)
    target_id: int | None = None
    detail: str | None = Field(default=None, sa_type=Text)  # type: ignore
    at: datetime = Field(default_factory=get_datetime_utc)


class SecurityLog(SQLModel, table=True):
    __tablename__ = "security_log"
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="user.id")
    event: str = Field(max_length=32)  # login/logout/login_failed
    ip: str | None = Field(default=None, max_length=64)
    at: datetime = Field(default_factory=get_datetime_utc)


# ------------------------------- API Schema -------------------------------


# JSON 载荷：登录请求（前端契约：{username, password}）
class LoginReq(SQLModel):
    username: str
    password: str


# JWT token 内容
class TokenPayload(SQLModel):
    sub: str | None = None


# 策略创建/更新请求
class StrategyCreate(SQLModel):
    branch_id: int
    template_id: int
    name: str
    build_start_time: str  # "HH:MM"
    push_mode: str  # normal/sync
    enabled: bool = True


# 版本创建/更新请求
class VersionCreate(SQLModel):
    name: str
    pm_user_id: int | None = None
    status: str = "active"


# 用户创建/更新请求
class UserCreate(SQLModel):
    username: str
    password: str = ""
    display_name: str
    role: str
    is_active: bool = True


# 模板创建/更新请求
class TemplateCreate(SQLModel):
    name: str
    smoke_minutes: int
    analysis_minutes: int
    description: str = ""


# 全局关键配置
class ConfigUpdate(SQLModel):
    build_minutes: int
    push_minutes: int
    sync_buffer_minutes: int


# 结论录入请求
class ConclusionCreate(SQLModel):
    conclusion: str  # pass/fail
    note: str = ""
