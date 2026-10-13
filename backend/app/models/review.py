"""New tables only: review data never replaces imported punches or profiles."""
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, BigInteger, Integer, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.models.base import Base


class RecoveryScan(Base):
    __tablename__ = 'RecoveryScans'
    __table_args__ = {'schema': 'integration'}
    ScanId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    StartDate: Mapped[date] = mapped_column(Date)
    EndDate: Mapped[date] = mapped_column(Date)
    SourceWatermark: Mapped[int] = mapped_column(BigInteger)
    LastScannedSourceId: Mapped[int] = mapped_column(BigInteger, default=0)
    ScannedCount: Mapped[int] = mapped_column(Integer, default=0)
    CandidateCount: Mapped[int] = mapped_column(Integer, default=0)
    UnknownStudentCount: Mapped[int] = mapped_column(Integer, default=0)
    Status: Mapped[str] = mapped_column(String(20), default='PENDING')
    RequestedBy: Mapped[str] = mapped_column(String(100))
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    CompletedAt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RecoveryPunch(Base):
    __tablename__ = 'RecoveryPunches'
    __table_args__ = {'schema': 'integration'}
    RecoveryId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    ScanId: Mapped[int] = mapped_column(BigInteger, ForeignKey('integration.RecoveryScans.ScanId'), index=True)
    SourceDeviceLogId: Mapped[int] = mapped_column(BigInteger, unique=True)
    StudentId: Mapped[int] = mapped_column(BigInteger, ForeignKey('master.Students.StudentId'), index=True)
    UserId: Mapped[str] = mapped_column(String(50))
    DeviceId: Mapped[int] = mapped_column(Integer)
    LogDate: Mapped[datetime] = mapped_column(DateTime)
    DownloadDate: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ReviewStatus: Mapped[str] = mapped_column(String(20), default='PENDING')
    Reason: Mapped[str] = mapped_column(String(500))
    CapturedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ReviewedBy: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ReviewedAt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ReviewNote: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class VerifiedRoomChange(Base):
    __tablename__ = 'VerifiedRoomChanges'
    __table_args__ = (UniqueConstraint('StudentId', 'ChangeDate', name='UQ_VerifiedRoomChanges_Student_Date'), {'schema': 'master'})
    ChangeId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    StudentId: Mapped[int] = mapped_column(BigInteger, ForeignKey('master.Students.StudentId'), index=True)
    OldRoomNo: Mapped[str] = mapped_column(String(50))
    NewRoomNo: Mapped[str] = mapped_column(String(50))
    ChangeDate: Mapped[date] = mapped_column(Date)
    EffectiveAt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    Evidence: Mapped[str] = mapped_column(String(1000))
    RecordedBy: Mapped[str] = mapped_column(String(100))
    RecordedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AttendanceChange(Base):
    __tablename__ = 'AttendanceChanges'
    __table_args__ = {'schema': 'system'}
    ChangeId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
