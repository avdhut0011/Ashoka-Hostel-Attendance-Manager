from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy.orm import Session, joinedload
from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.core.locking import attendance_lock
from backend.app.core.time import local_now, business_day
from backend.app.models.master import Student, Hostel, StudentHostelHistory
from backend.app.models.attendance import StudentCurrentStatus, ProcessedPunch, AttendanceOverride
from backend.app.models.security import User, SystemEvent
from backend.app.services.punch_processor import rebuild_student, apply_override
from backend.app.services.state_history import change_state
from backend.app.services.daily_counters import daily_counters
from backend.app.schemas.schemas import StudentResponse, StudentCreate, StudentUpdate, StudentStatusUpdate, StudentAttendanceStatusUpdate, ProcessedPunchResponse

router = APIRouter(prefix='/students', tags=['Students'])

def _student(db, student_id, user):
    row = db.query(Student).filter_by(StudentId=student_id).first()
    if row is None:
        raise HTTPException(404, 'Student not found')
    if user.Role == 'WARDEN' and (not user.HostelId or row.HostelId != user.HostelId):
        raise HTTPException(403, 'Student is outside your assigned hostel')
    return row

def _hostel(db, hostel_id):
    if hostel_id and not db.query(Hostel).filter_by(HostelId=hostel_id, IsActive=True).first():
        raise HTTPException(400, 'Choose an active hostel')

def _response(student, counts=None):
    res = StudentResponse.model_validate(student)
    res.HostelName = student.hostel.HostelName if student.hostel else None
    curr = student.current_status
    res.CurrentStatus = curr.CurrentStatus if curr else 'NOT_STARTED'
    res.LastPunchTime = curr.LastPunchTime if curr else None
    if counts is not None:
        for name, value in counts.items():
            setattr(res, name, value)
    return res

def _audit(db, user, kind, description):
    db.add(SystemEvent(EventType=kind, Description=description[:1000], CreatedBy=user.Username))

def _assignment(db, student, hostel_id, room, when):
    changed = student.HostelId != hostel_id or student.RoomNo != room
    if changed:
        old = db.query(StudentHostelHistory).filter_by(StudentId=student.StudentId, ToDate=None).all()
        for history in old:
            history.ToDate = business_day(when)
        if hostel_id:
            db.add(StudentHostelHistory(StudentId=student.StudentId, HostelId=hostel_id, RoomNo=room, FromDate=business_day(when)))
    change_state(db, student, {'HostelId': hostel_id, 'RoomNo': room}, when)

@router.get('', response_model=List[StudentResponse])
def list_students(response: Response, hostel_id: Optional[int] = None, status: Optional[str] = None,
    search: Optional[str] = None, pending_enrollment: Optional[bool] = None,
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Student).options(joinedload(Student.hostel), joinedload(Student.current_status))
    if current_user.Role == 'WARDEN':
        if not current_user.HostelId:
            raise HTTPException(403, 'Warden has no assigned hostel')
        query = query.filter(Student.HostelId == current_user.HostelId)
    elif hostel_id:
        query = query.filter(Student.HostelId == hostel_id)
    if pending_enrollment:
        query = query.filter(Student.RegistrationStatus != 'INACTIVE',
            (Student.RegistrationStatus == 'PENDING_ENROLLMENT') | (Student.StudentName.is_(None)) | (Student.StudentName == ''))
    elif status:
        query = query.filter(Student.RegistrationStatus == status)
    if search:
        query = query.filter((Student.UserId.like(f'%{search}%')) | (Student.StudentName.like(f'%{search}%')))
    response.headers['X-Total-Count'] = str(query.count())
    students = query.order_by(Student.StudentId.desc()).offset(skip).limit(limit).all()
    counts = daily_counters(db, [s.StudentId for s in students])
    return [_response(s, counts[s.StudentId]) for s in students]

@router.get('/{student_id}', response_model=StudentResponse)
def get_student(student_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    student = _student(db, student_id, current_user)
    return _response(student, daily_counters(db, [student_id])[student_id])

@router.post('', response_model=StudentResponse)
def create_student(student_in: StudentCreate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN', 'WARDEN']))):
    with attendance_lock(db):
        if db.query(Student).filter_by(UserId=student_in.UserId.strip()).first():
            raise HTTPException(400, 'Student UserId already exists')
        hostel_id = current_user.HostelId if current_user.Role == 'WARDEN' else student_in.HostelId
        _hostel(db, hostel_id)
        student = Student(**{**student_in.model_dump(), 'UserId': student_in.UserId.strip(), 'HostelId': hostel_id})
        db.add(student)
        db.flush()
        db.add(StudentCurrentStatus(StudentId=student.StudentId, CurrentStatus='NOT_STARTED'))
        _audit(db, current_user, 'STUDENT_REGISTERED', f'Student {student.UserId} registered in hostel {hostel_id}')
        db.commit()
        db.refresh(student)
        return _response(student, daily_counters(db, [student.StudentId])[student.StudentId])

@router.put('/{student_id}', response_model=StudentResponse)
def update_student(student_id: int, student_in: StudentUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN', 'WARDEN']))):
    with attendance_lock(db):
        student = _student(db, student_id, current_user)
        hostel_id = student_in.HostelId if student_in.HostelId is not None else student.HostelId
        if current_user.Role == 'WARDEN' and hostel_id != current_user.HostelId:
            raise HTTPException(403, 'Wardens cannot transfer students')
        _hostel(db, hostel_id)
        room = student_in.RoomNo if student_in.RoomNo is not None else student.RoomNo
        _assignment(db, student, hostel_id, room, local_now())
        if student_in.StudentName is not None:
            student.StudentName = student_in.StudentName.strip()
        _audit(db, current_user, 'STUDENT_PROFILE_UPDATED', f'Student {student.UserId} profile updated; attendance preserved')
        db.commit()
        db.refresh(student)
        return _response(student, daily_counters(db, [student.StudentId])[student.StudentId])

@router.put('/{student_id}/enroll', response_model=StudentResponse)
def enroll_student(student_id: int, student_in: StudentUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN', 'WARDEN']))):
    with attendance_lock(db):
        student = _student(db, student_id, current_user)
        if student.RegistrationStatus == 'INACTIVE':
            raise HTTPException(409, 'Inactive students must be reactivated by an administrator')
        if student.EnrolledAt is not None:
            raise HTTPException(409, 'Already enrolled; use profile editing')
        hostel_id = current_user.HostelId if current_user.Role == 'WARDEN' else student_in.HostelId
        if not student_in.StudentName or not hostel_id:
            raise HTTPException(400, 'StudentName and HostelId are required')
        _hostel(db, hostel_id)
        now = local_now()
        _assignment(db, student, hostel_id, student_in.RoomNo, now)
        change_state(db, student, {'RegistrationStatus': 'ACTIVE'}, now)
        student.StudentName, student.EnrolledAt = student_in.StudentName.strip(), now
        _audit(db, current_user, 'STUDENT_ENROLLED', f'Student {student.UserId} enrolled; registration timeline recalculated chronologically')
        try:
            rebuild_student(db, student, enrolled=True)
        except ValueError as error:
            raise HTTPException(409, str(error))
        db.commit()
        db.refresh(student)
        return _response(student, daily_counters(db, [student.StudentId])[student.StudentId])

@router.put('/{student_id}/status', response_model=StudentResponse)
def update_student_status(student_id: int, status_in: StudentStatusUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN']))):
    with attendance_lock(db):
        student = _student(db, student_id, current_user)
        change_state(db, student, {'RegistrationStatus': status_in.RegistrationStatus})
        student.DeactivatedAt = datetime.utcnow() if status_in.RegistrationStatus == 'INACTIVE' else None
        student.DeactivationReason = status_in.DeactivationReason if status_in.RegistrationStatus == 'INACTIVE' else None
        _audit(db, current_user, 'STUDENT_STATUS_CHANGED', f'Student {student.UserId}: {status_in.RegistrationStatus}; {status_in.DeactivationReason or ""}')
        db.commit()
        db.refresh(student)
        return _response(student, daily_counters(db, [student.StudentId])[student.StudentId])

@router.put('/{student_id}/attendance-status', response_model=StudentResponse)
def update_student_attendance_status(student_id: int, status_in: StudentAttendanceStatusUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN']))):
    with attendance_lock(db):
        student = _student(db, student_id, current_user)
        curr = db.query(StudentCurrentStatus).filter_by(StudentId=student_id).first()
        previous = curr.CurrentStatus if curr else 'NOT_STARTED'
        now = local_now()
        if curr and curr.LastPunchTime and curr.LastPunchTime > now:
            raise HTTPException(409, 'Future-dated attendance must be corrected before an override')
        override = AttendanceOverride(StudentId=student_id, PreviousStatus=previous, CurrentStatus=status_in.CurrentStatus,
            EffectiveAt=now, Reason=status_in.Reason, CreatedBy=current_user.Username,
            HostelIdSnapshot=student.HostelId, RoomNoSnapshot=student.RoomNo)
        db.add(override)
        apply_override(db, student, override)
        _audit(db, current_user, 'MANUAL_STATUS_OVERRIDE', f'Student {student.UserId}: {previous} -> {status_in.CurrentStatus}; {status_in.Reason}')
        db.commit()
        db.refresh(student)
        return _response(student, daily_counters(db, [student.StudentId])[student.StudentId])

@router.delete('/{student_id}')
def delete_student(student_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN']))):
    update_student_status(student_id, StudentStatusUpdate(RegistrationStatus='INACTIVE', DeactivationReason=f'Soft deleted by {current_user.Username}'), db, current_user)
    return {'message': 'Student deactivated'}

@router.get('/{student_id}/history', response_model=List[ProcessedPunchResponse])
def get_student_punch_history(student_id: int, response: Response, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _student(db, student_id, current_user)
    from backend.app.services.reporting import punch_query, punch_response, punch_count, punch_page
    query = punch_query(db, current_user).filter(ProcessedPunch.StudentId == student_id)
    response.headers['X-Total-Count'] = str(punch_count(query))
    return [punch_response(row, db) for row in punch_page(query, skip, limit)]


@router.get('/{student_id}/assignment-history')
def assignment_history(student_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from backend.app.models.review import VerifiedRoomChange
    from backend.app.models.master import StudentStateHistory
    from backend.app.schemas.schemas import timestamp_json
    _student(db, student_id, current_user)
    query = db.query(StudentStateHistory).filter_by(StudentId=student_id)
    if current_user.Role == 'WARDEN':
        query = query.filter(StudentStateHistory.HostelId == current_user.HostelId)
    states = query.order_by(StudentStateHistory.EffectiveFrom).all()
    changes = db.query(VerifiedRoomChange).filter_by(StudentId=student_id).order_by(VerifiedRoomChange.ChangeDate).all()
    # Date-only operator evidence contains no historical hostel; admin/IT review only.
    if current_user.Role == 'WARDEN':
        changes = []
    return {'captured_states': [dict(HostelId=row.HostelId, RoomNo=row.RoomNo,
            EffectiveFrom=timestamp_json(row.EffectiveFrom, source=True), EffectiveTo=timestamp_json(row.EffectiveTo, source=True)) for row in states],
            'verified_room_changes': [dict(OldRoomNo=row.OldRoomNo, NewRoomNo=row.NewRoomNo,
            ChangeDate=row.ChangeDate, EffectiveAt=timestamp_json(row.EffectiveAt, source=True),
            TimePrecision='EXACT' if row.EffectiveAt else 'DATE_ONLY', Evidence=row.Evidence) for row in changes]}
