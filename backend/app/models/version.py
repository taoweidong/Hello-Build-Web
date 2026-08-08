from sqlalchemy import String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..database import Base

class Version(Base):
    __tablename__ = "version"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    pm_user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/archived
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    branches: Mapped[list["Branch"]] = relationship(back_populates="version")