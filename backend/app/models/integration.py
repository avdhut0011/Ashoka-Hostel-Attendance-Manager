from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.models.base import Base

class RawPunch(Base):
    __tablename__ = "RawPunches"
    __table_args__ = (Index('IX_RawPunches_UserId_LogDate', 'UserId', 'LogDate'), {'schema': 'integration'})

    RawPunchId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    SourceDeviceLogId: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    DeviceId: Mapped[int] = mapped_column(Integer, nullable=False)
    UserId: Mapped[str] = mapped_column(String(50), nullable=False)
    LogDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    DownloadDate: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ReceivedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class SyncCheckpoint(Base):
    __tablename__ = "SyncCheckpoint"
    __table_args__ = {"schema": "integration"}

    SyncId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    SourceName: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    LastSourceDeviceLogId: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    LastSyncStartedAt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    LastSyncCompletedAt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    LastSyncStatus: Mapped[Optional[str]] = mapped_column(String(20), nullable=True) # SUCCESS, PARTIAL_SUCCESS, FAILED, RUNNING
    LastError: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    UpdatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class QuarantinedPunch(Base):
    __tablename__ = "QuarantinedPunches"
    __table_args__ = {"schema": "integration"}

    QuarantineId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    SourceDeviceLogId: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    DeviceId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    UserId: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    LogDate: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    DownloadDate: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    RawPayload: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    ErrorType: Mapped[str] = mapped_column(String(50), default="DATA_CORRUPTION", nullable=False) # DATA_CORRUPTION, VALIDATION_FAILURE
    ErrorMessage: Mapped[str] = mapped_column(String(2000), nullable=False)
    QuarantinedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    ResolvedStatus: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False) # PENDING, RESOLVED, IGNORED
    ResolvedAt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ResolvedBy: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class PunchCorrection(Base):
    __tablename__ = 'PunchCorrections'
    __table_args__ = {'schema': 'integration'}
    CorrectionId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    RawPunchId: Mapped[int] = mapped_column(BigInteger, ForeignKey('integration.RawPunches.RawPunchId'), index=True)
    UserId: Mapped[str] = mapped_column(String(50))
    DeviceId: Mapped[int] = mapped_column(Integer)
    LogDate: Mapped[datetime] = mapped_column(DateTime)
    Reason: Mapped[str] = mapped_column(String(500))
    CreatedBy: Mapped[str] = mapped_column(String(100))
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

