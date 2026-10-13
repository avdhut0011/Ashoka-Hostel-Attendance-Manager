from typing import List
from datetime import datetime, date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.app.core.time import day_bounds
from backend.app.services.reporting import hostel_column

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models.master import Student, Hostel, Device
from backend.app.models.attendance import StudentCurrentStatus, ProcessedPunch
from backend.app.models.security import User
from backend.app.schemas.schemas import DashboardSummaryResponse, HostelSummaryItem

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    is_warden = current_user.Role == "WARDEN" and current_user.HostelId is not None

    # 1. Student registration status totals (Scoped for Warden)
    reg_query = db.query(Student.RegistrationStatus, func.count(Student.StudentId))
    if is_warden:
        reg_query = reg_query.filter(Student.HostelId == current_user.HostelId)
    students_reg = reg_query.group_by(Student.RegistrationStatus).all()

    reg_counts = {status: count for status, count in students_reg}
    total_students = reg_counts.get("ACTIVE", 0)
    pending_enrollments = reg_counts.get("PENDING_ENROLLMENT", 0)
    inactive_students = reg_counts.get("INACTIVE", 0)

    # 2. Current location status counts for ACTIVE students only (Scoped for Warden)
    status_query = (
        db.query(StudentCurrentStatus.CurrentStatus, func.count(StudentCurrentStatus.StudentId))
        .join(Student, Student.StudentId == StudentCurrentStatus.StudentId)
        .filter(Student.RegistrationStatus == "ACTIVE")
    )
    if is_warden:
        status_query = status_query.filter(Student.HostelId == current_user.HostelId)
    status_raw = status_query.group_by(StudentCurrentStatus.CurrentStatus).all()
    sc_counts = {st: count for st, count in status_raw}

    # 3. Today's punch counts (Scoped for Warden)
    today_start, today_end = day_bounds()
    today_query = (
        db.query(ProcessedPunch.ProcessingStatus, func.count(ProcessedPunch.PunchId))
        .filter(ProcessedPunch.LogDate >= today_start, ProcessedPunch.LogDate < today_end)
    )
    if is_warden:
        warden_devices = db.query(Device.DeviceId).filter(Device.HostelId == current_user.HostelId)
        today_query = today_query.outerjoin(Student, ProcessedPunch.StudentId == Student.StudentId).filter(
            hostel_column() == current_user.HostelId
        )
    today_punches_raw = today_query.group_by(ProcessedPunch.ProcessingStatus).all()
    tp_counts = {ps: count for ps, count in today_punches_raw}

    return DashboardSummaryResponse(
        total_students=total_students,
        pending_enrollments=pending_enrollments,
        currently_in=sc_counts.get("IN", 0),
        currently_out=sc_counts.get("OUT", 0),
        not_started=max(0, total_students - sc_counts.get("IN", 0) - sc_counts.get("OUT", 0)),
        inactive_students=inactive_students,
        today_total_punches=sum(tp_counts.values()),
        today_valid_punches=tp_counts.get("VALID", 0),
        today_duplicate_punches=tp_counts.get("DUPLICATE", 0)
    )

@router.get("/hostels", response_model=List[HostelSummaryItem])
def get_hostel_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    hostel_query = db.query(Hostel).filter(Hostel.IsActive == True)
    if current_user.Role == "WARDEN" and current_user.HostelId is not None:
        hostel_query = hostel_query.filter(Hostel.HostelId == current_user.HostelId)

    hostels = hostel_query.all()
    if not hostels:
        return []

    hostel_ids = [h.HostelId for h in hostels]

    # Single bulk aggregation query for ACTIVE students across scoped hostels
    status_counts_raw = (
        db.query(
            Student.HostelId,
            StudentCurrentStatus.CurrentStatus,
            func.count(Student.StudentId)
        )
        .join(StudentCurrentStatus, Student.StudentId == StudentCurrentStatus.StudentId)
        .filter(Student.HostelId.in_(hostel_ids), Student.RegistrationStatus == "ACTIVE")
        .group_by(Student.HostelId, StudentCurrentStatus.CurrentStatus)
        .all()
    )

    # Total ACTIVE students per hostel
    total_students_raw = (
        db.query(Student.HostelId, func.count(Student.StudentId))
        .filter(Student.HostelId.in_(hostel_ids), Student.RegistrationStatus == "ACTIVE")
        .group_by(Student.HostelId)
        .all()
    )
    hostel_totals = {hid: count for hid, count in total_students_raw}

    # Total PENDING_ENROLLMENT students per hostel
    pending_students_raw = (
        db.query(Student.HostelId, func.count(Student.StudentId))
        .filter(Student.HostelId.in_(hostel_ids), Student.RegistrationStatus == "PENDING_ENROLLMENT")
        .group_by(Student.HostelId)
        .all()
    )
    pending_totals = {hid: count for hid, count in pending_students_raw}

    status_map = {}
    for hid, status, count in status_counts_raw:
        if hid not in status_map:
            status_map[hid] = {"IN": 0, "OUT": 0, "NOT_STARTED": 0, "REGISTRATION": 0}
        status_map[hid][status] = count

    result = []
    for h in hostels:
        counts = status_map.get(h.HostelId, {"IN": 0, "OUT": 0, "NOT_STARTED": 0, "REGISTRATION": 0})
        result.append(HostelSummaryItem(
            HostelId=h.HostelId,
            HostelName=h.HostelName,
            HostelCode=h.HostelCode,
            total_students=hostel_totals.get(h.HostelId, 0),
            pending_enrollments=pending_totals.get(h.HostelId, 0),
            currently_in=counts.get("IN", 0),
            currently_out=counts.get("OUT", 0),
            not_started=max(0, hostel_totals.get(h.HostelId, 0) - counts.get("IN", 0) - counts.get("OUT", 0))
        ))

    return result
