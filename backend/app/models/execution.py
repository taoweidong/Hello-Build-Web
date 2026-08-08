from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..database import Base

class ExecutionRound(Base):
    __tablename__ = "execution_round"
    __table_args__ = (UniqueConstraint("strategy_id", "exec_date", name="uq_round_strategy_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategy.id"))
    exec_date: Mapped[str] = mapped_column(String(10))  # "YYYY-MM-DD"
    # 各阶段绝对时间（可跨天）
    push_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    push_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    build_start: Mapped[datetime] = mapped_column(DateTime)
    build_end: Mapped[datetime] = mapped_column(DateTime)
    smoke_start: Mapped[datetime] = mapped_column(DateTime)
    smoke_end: Mapped[datetime] = mapped_column(DateTime)
    analysis_start: Mapped[datetime] = mapped_column(DateTime)
    analysis_end: Mapped[datetime] = mapped_column(DateTime)
    conclusion: Mapped[str] = mapped_column(String(10), default="pending")  # pending/pass/fail
    conclusion_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    conclusion_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    conclusion_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    push_status: Mapped[str] = mapped_column(String(10), default="not_triggered")  # not_triggered/pending/success/failed
    release_approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # sync 模式标记
    strategy: Mapped["Strategy"] = relationship()