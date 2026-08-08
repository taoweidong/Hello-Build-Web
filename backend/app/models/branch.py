from sqlalchemy import String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..database import Base

class Branch(Base):
    __tablename__ = "branch"
    __table_args__ = (UniqueConstraint("version_id", "name", name="uq_branch_version_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("version.id"))
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    version: Mapped["Version"] = relationship(back_populates="branches")
    strategies: Mapped[list["Strategy"]] = relationship(back_populates="branch")