from datetime import datetime, date
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from zoneinfo import ZoneInfo
from backend.app.core.config import settings


def timestamp_json(value, source=False):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(settings.SOURCE_TIMEZONE if source else 'UTC'))
    return value.isoformat()

# --- Auth Schemas ---
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str
    hostel_id: Optional[int] = None

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    SystemUserId: int
    Username: str
    Role: str
    HostelId: Optional[int] = None
    IsActive: bool

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)

# --- Hostel Schemas ---
class HostelCreate(BaseModel):
    HostelName: str = Field(min_length=1, max_length=100)
    HostelCode: Optional[str] = Field(None, max_length=50)
    IsActive: bool = True

class HostelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    HostelId: int
    HostelName: str
    HostelCode: Optional[str] = None
    IsActive: bool
    CreatedAt: datetime

    @field_serializer('CreatedAt', when_used='json')
    def serialize_created_time(self, value):
        return timestamp_json(value)

# --- Device Schemas ---
class DeviceCreate(BaseModel):
    DeviceId: int = Field(gt=0)
    DeviceName: str = Field(min_length=1, max_length=100)
    HostelId: Optional[int] = Field(None, gt=0)
    IsActive: bool = True

class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    DeviceId: int
    DeviceName: str
    HostelId: Optional[int] = None
    HostelName: Optional[str] = None
    IsActive: bool
    CreatedAt: datetime

    @field_serializer('CreatedAt', when_used='json')
    def serialize_created_time(self, value):
        return timestamp_json(value)

# --- Student Schemas ---
class StudentCreate(BaseModel):
    UserId: str = Field(min_length=1, max_length=50, pattern=r'\S')
    StudentName: Optional[str] = Field(None, max_length=150)
    HostelId: Optional[int] = Field(None, gt=0)
    RoomNo: Optional[str] = Field(None, max_length=50)
    RegistrationStatus: Literal['ACTIVE', 'PENDING_ENROLLMENT'] = 'ACTIVE'

class StudentUpdate(BaseModel):
    StudentName: Optional[str] = Field(None, min_length=1, max_length=150, pattern=r'\S')
    HostelId: Optional[int] = Field(None, gt=0)
    RoomNo: Optional[str] = Field(None, max_length=50)

class StudentStatusUpdate(BaseModel):
    RegistrationStatus: Literal['ACTIVE', 'INACTIVE']
    DeactivationReason: Optional[str] = Field(None, max_length=500)

class StudentAttendanceStatusUpdate(BaseModel):
    CurrentStatus: Literal['IN', 'OUT', 'REGISTRATION', 'NOT_STARTED']
    Reason: str = Field(default='Manual status override by Admin', min_length=1, max_length=500, pattern=r'\S')

class StudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    StudentId: int
    UserId: str
    StudentName: Optional[str] = None
    HostelId: Optional[int] = None
    HostelName: Optional[str] = None
    RoomNo: Optional[str] = None
    RegistrationDate: date
    RegistrationStatus: str
    DeactivatedAt: Optional[datetime] = None
    DeactivationReason: Optional[str] = None
    CurrentStatus: Optional[str] = "REGISTRATION"
    LastPunchTime: Optional[datetime] = None
    TodayInCount: int = 0
    TodayOutCount: int = 0
    TodayValidPunchCount: int = 0
    TodayDuplicatePunchCount: int = 0

    @field_serializer('LastPunchTime', when_used='json')
    def serialize_punch_time(self, value):
        return timestamp_json(value, source=True)

    @field_serializer('DeactivatedAt', when_used='json')
    def serialize_deactivated_time(self, value):
        return timestamp_json(value)

# --- Processed Punch Schema ---
class ProcessedPunchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    PunchId: int
    RawPunchId: int
    StudentId: Optional[int] = None
    UserId: str
    StudentName: Optional[str] = None
    HostelName: Optional[str] = None
    DeviceName: Optional[str] = None
    DeviceId: int
    LogDate: datetime
    PunchType: Optional[str] = None
    ProcessingStatus: str
    IsFirstEverPunch: bool
    IsFirstValidPunchOfDay: bool
    PreviousStatus: Optional[str] = None
    Reason: Optional[str] = None
    ProcessedAt: datetime
    HostelIdSnapshot: Optional[int] = None
    RoomNoSnapshot: Optional[str] = None
    HistoricalAssignmentKnown: bool = False
    HistoricalRoomNo: Optional[str] = None
    HistoricalRoomSource: str = 'UNKNOWN'

    @field_serializer('LogDate', when_used='json')
    def serialize_log_time(self, value):
        return timestamp_json(value, source=True)

    @field_serializer('ProcessedAt', when_used='json')
    def serialize_processed_time(self, value):
        return timestamp_json(value)

# --- Dashboard Schemas ---
class DashboardSummaryResponse(BaseModel):
    total_students: int
    pending_enrollments: int = 0
    currently_in: int
    currently_out: int
    not_started: int
    inactive_students: int
    today_total_punches: int
    today_valid_punches: int
    today_duplicate_punches: int

class HostelSummaryItem(BaseModel):
    HostelId: int
    HostelName: str
    HostelCode: Optional[str]
    total_students: int
    pending_enrollments: int = 0
    currently_in: int
    currently_out: int
    not_started: int

# --- Sync Status Schema ---
class SyncStatusResponse(BaseModel):
    SourceName: str
    LastSourceDeviceLogId: int
    LastSyncStartedAt: Optional[datetime] = None
    LastSyncCompletedAt: Optional[datetime] = None
    LastSyncStatus: Optional[str] = None
    LastError: Optional[str] = None

    @field_serializer('LastSyncStartedAt', 'LastSyncCompletedAt', when_used='json')
    def serialize_sync_time(self, value):
        return timestamp_json(value)

class QuarantinedPunchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    QuarantineId: int
    SourceDeviceLogId: int
    DeviceId: Optional[int] = None
    UserId: Optional[str] = None
    LogDate: Optional[datetime] = None
    DownloadDate: Optional[datetime] = None
    RawPayload: Optional[str] = None
    ErrorType: str
    ErrorMessage: str
    QuarantinedAt: datetime
    ResolvedStatus: str
    ResolvedAt: Optional[datetime] = None
    ResolvedBy: Optional[str] = None

    @field_serializer('LogDate', 'DownloadDate', when_used='json')
    def serialize_source_time(self, value):
        return timestamp_json(value, source=True)

    @field_serializer('QuarantinedAt', 'ResolvedAt', when_used='json')
    def serialize_audit_time(self, value):
        return timestamp_json(value)

class QuarantineReprocessRequest(BaseModel):
    corrected_user_id: Optional[str] = Field(None, min_length=1, max_length=50, pattern=r'\S')
    corrected_device_id: Optional[int] = Field(None, gt=0)
    corrected_log_date: Optional[datetime] = None

