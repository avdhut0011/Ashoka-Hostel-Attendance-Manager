from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.models.base import Base

class User(Base):
    __tablename__ = "Users"
    __table_args__ = {"schema": "security"}

    SystemUserId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    Username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    PasswordHash: Mapped[str] = mapped_column(String(500), nullable=False)
    Role: Mapped[str] = mapped_column(String(30), nullable=False) # ADMIN, WARDEN, IT_ADMIN, MANAGEMENT
    HostelId: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("master.Hostels.HostelId"), nullable=True) # Scoped Hostel for WARDEN
    IsActive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    UpdatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    TokenVersion: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)

    hostel = relationship("Hostel")

class SystemEvent(Base):
    __tablename__ = "SystemEvents"
    __table_args__ = {"schema": "system"}

    EventId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    EventType: Mapped[str] = mapped_column(String(100), nullable=False)
    Description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    CreatedBy: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
