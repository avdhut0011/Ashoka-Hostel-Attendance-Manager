from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, Boolean, Date, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.models.base import Base

class ProcessedPunch(Base):
    __tablename__ = "ProcessedPunches"
    __table_args__ = (Index('UX_ProcessedPunches_RawPunchId', 'RawPunchId', unique=True),
                      Index('IX_ProcessedPunches_StudentId_LogDate', 'StudentId', 'LogDate'),
                      Index('IX_ProcessedPunches_LogDate', 'LogDate'),
                      Index('IX_Punches_Hostel_Time_Id', 'HostelIdSnapshot', 'LogDate', 'PunchId',
                            mssql_include=['StudentId', 'UserId', 'ProcessingStatus', 'PunchType', 'DeviceId']),
                      Index('IX_Punches_Student_Time_Id', 'StudentId', 'LogDate', 'PunchId',
                            mssql_include=['ProcessingStatus', 'PunchType', 'RawPunchId']),
                      {'schema': 'attendance'})

    PunchId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    RawPunchId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("integration.RawPunches.RawPunchId"), nullable=False)
    StudentId: Mapped[Optional[int]] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("master.Students.StudentId"), nullable=True)
    UserId: Mapped[str] = mapped_column(String(50), nullable=False)
    DeviceId: Mapped[int] = mapped_column(Integer, nullable=False)
    LogDate: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    PunchType: Mapped[Optional[str]] = mapped_column(String(20), nullable=True) # REGISTRATION, IN, OUT
    ProcessingStatus: Mapped[str] = mapped_column(String(30), nullable=False) # VALID, DUPLICATE, INACTIVE_STUDENT, INVALID_DEVICE
    IsFirstEverPunch: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    IsFirstValidPunchOfDay: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    PreviousStatus: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    Reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ProcessedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    HostelIdSnapshot: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    RoomNoSnapshot: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    raw_punch = relationship("RawPunch")
    student = relationship("Student")

class StudentCurrentStatus(Base):
    __tablename__ = "StudentCurrentStatus"
    __table_args__ = (Index('IX_CurrentStatus_Status_Time', 'CurrentStatus', 'LastPunchTime', 'StudentId'), {"schema": "attendance"})

    StudentId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("master.Students.StudentId"), primary_key=True)
    CurrentStatus: Mapped[str] = mapped_column(String(20), default="NOT_STARTED", nullable=False) # NOT_STARTED, IN, OUT
    LastPunchId: Mapped[Optional[int]] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("attendance.ProcessedPunches.PunchId"), nullable=True)
    LastPunchTime: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    LastPunchType: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    LastValidAttendanceDate: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    CounterDate: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    TodayInCount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    TodayOutCount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    TodayValidPunchCount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    TodayDuplicatePunchCount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    UpdatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    student = relationship("Student", back_populates="current_status")
    last_punch = relationship("ProcessedPunch")


class AttendanceOverride(Base):
    __tablename__ = 'AttendanceOverrides'
    __table_args__ = (Index('IX_AttendanceOverrides_Student_Time', 'StudentId', 'EffectiveAt'), {'schema': 'attendance'})
    OverrideId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    StudentId: Mapped[int] = mapped_column(BigInteger, ForeignKey('master.Students.StudentId'))
    PreviousStatus: Mapped[str] = mapped_column(String(20))
    CurrentStatus: Mapped[str] = mapped_column(String(20))
    EffectiveAt: Mapped[datetime] = mapped_column(DateTime)
    Reason: Mapped[str] = mapped_column(String(500))
    CreatedBy: Mapped[str] = mapped_column(String(100))
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    HostelIdSnapshot: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    RoomNoSnapshot: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
