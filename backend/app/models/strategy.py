from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..database import Base

class StrategyTemplate(Base):
    __tablename__ = "strategy_template"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    smoke_minutes: Mapped[int] = mapped_column(Integer)
    analysis_minutes: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Strategy(Base):
    __tablename__ = "strategy"
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id"))
    template_id: Mapped[int] = mapped_column(ForeignKey("strategy_template.id"))
    name: Mapped[str] = mapped_column(String(64))
    build_start_time: Mapped[str] = mapped_column(String(5))  # "HH:MM" 每日循环
    push_mode: Mapped[str] = mapped_column(String(10), default="normal")  # normal/sync
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    branch: Mapped["Branch"] = relationship(back_populates="strategies")
    template: Mapped["StrategyTemplate"] = relationship()