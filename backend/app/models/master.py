from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import String, Integer, BigInteger, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.models.base import Base
from backend.app.core.time import business_day, local_now

class Hostel(Base):
    __tablename__ = "Hostels"
    __table_args__ = {"schema": "master"}

    HostelId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    HostelName: Mapped[str] = mapped_column(String(100), nullable=False)
    HostelCode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    UpdatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    devices: Mapped[List["Device"]] = relationship("Device", back_populates="hostel")
    students: Mapped[List["Student"]] = relationship("Student", back_populates="hostel")

class Device(Base):
    __tablename__ = "Devices"
    __table_args__ = {"schema": "master"}

    DeviceId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False) # Matches IT hardware DeviceId
    DeviceName: Mapped[str] = mapped_column(String(100), nullable=False)
    HostelId: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("master.Hostels.HostelId"), nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    UpdatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    hostel: Mapped[Optional["Hostel"]] = relationship("Hostel", back_populates="devices")

class Student(Base):
    __tablename__ = "Students"
    __table_args__ = {"schema": "master"}

    StudentId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    UserId: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    StudentName: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    HostelId: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("master.Hostels.HostelId"), nullable=True)
    RoomNo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    RegistrationDate: Mapped[date] = mapped_column(Date, default=lambda: business_day(local_now()), nullable=False)
    RegistrationStatus: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False) # ACTIVE, INACTIVE
    EnrolledAt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    DeactivatedAt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    DeactivationReason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    UpdatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    hostel: Mapped[Optional["Hostel"]] = relationship("Hostel", back_populates="students")
    hostel_history: Mapped[List["StudentHostelHistory"]] = relationship("StudentHostelHistory", back_populates="student")
    current_status: Mapped[Optional["StudentCurrentStatus"]] = relationship("StudentCurrentStatus", back_populates="student", uselist=False)

class StudentHostelHistory(Base):
    __tablename__ = "StudentHostelHistory"
    __table_args__ = {"schema": "master"}

    HistoryId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    StudentId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("master.Students.StudentId"), nullable=False)
    HostelId: Mapped[int] = mapped_column(Integer, ForeignKey("master.Hostels.HostelId"), nullable=False)
    RoomNo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    FromDate: Mapped[date] = mapped_column(Date, nullable=False)
    ToDate: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    student: Mapped["Student"] = relationship("Student", back_populates="hostel_history")
    hostel: Mapped["Hostel"] = relationship("Hostel")


class StudentStateHistory(Base):
    __tablename__ = 'StudentStateHistory'
    __table_args__ = {'schema': 'master'}
    StateId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    StudentId: Mapped[int] = mapped_column(BigInteger, ForeignKey('master.Students.StudentId'), index=True)
    HostelId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    RoomNo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    RegistrationStatus: Mapped[str] = mapped_column(String(20))
    EffectiveFrom: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    EffectiveTo: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class DeviceStateHistory(Base):
    __tablename__ = 'DeviceStateHistory'
    __table_args__ = {'schema': 'master'}
    StateId: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True, autoincrement=True)
    DeviceId: Mapped[int] = mapped_column(Integer, ForeignKey('master.Devices.DeviceId'), index=True)
    HostelId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean)
    EffectiveFrom: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    EffectiveTo: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
