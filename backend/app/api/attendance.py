from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.core.time import day_bounds, business_day, local_now
from backend.app.models.master import Student, Hostel
from backend.app.models.attendance import ProcessedPunch, AttendanceOverride
from backend.app.models.security import User
from backend.app.schemas.schemas import ProcessedPunchResponse, timestamp_json
from backend.app.services.reporting import punch_query, punch_response, override_query, punch_count, punch_page

router = APIRouter(prefix='/attendance', tags=['Attendance'])

def _page(query, response, skip, limit, cursor=None):
    response.headers['X-Total-Count'] = str(punch_count(query))
    return punch_page(query, skip, limit, cursor, response)

@router.get('/today', response_model=List[ProcessedPunchResponse])
def get_today_attendance(response: Response, user_id: Optional[str] = None, punch_type: Optional[str] = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    today = business_day(local_now())
    return [punch_response(row, db) for row in _page(punch_query(db, current_user, today, today, status='VALID', user_id=user_id, punch_type=punch_type), response, skip, limit)]

@router.get('/history')
def get_detailed_student_history(response: Response, start_date: Optional[date] = None, end_date: Optional[date] = None,
    single_date: Optional[date] = None, user_id: Optional[str] = None, hostel_id: Optional[int] = None,
    punch_type: Optional[str] = None, status: Optional[str] = None,
    cursor: Optional[str] = Query(None, max_length=200),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = punch_query(db, current_user, single_date or start_date, single_date or end_date, hostel_id, user_id, punch_type, status)
    rows = _page(query, response, skip, limit, cursor)
    result = []
    for row in rows:
        punch, _, _, _, room = row
        item = punch_response(row, db).model_dump(mode='json')
        item['HostelId'] = punch.HostelIdSnapshot
        item['RoomNo'] = item['HistoricalRoomNo']
        result.append(item)
    return result

@router.get('/overrides')
def list_overrides(response: Response, hostel_id: Optional[int] = None, user_id: Optional[str] = None, punch_type: Optional[str] = None, status: Optional[str] = None, student_id: Optional[int] = None, start_date: Optional[date] = None, end_date: Optional[date] = None,
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, 'Start date must not be after end date')
    query = override_query(db, current_user, start_date, end_date, hostel_id, user_id, punch_type, status)
    if student_id:
        query = query.filter(AttendanceOverride.StudentId == student_id)
    response.headers['X-Total-Count'] = str(query.count())
    return [dict(OverrideId=o.OverrideId, StudentId=o.StudentId, UserId=uid, StudentName=name, HostelName=hostel,
        PreviousStatus=o.PreviousStatus, CurrentStatus=o.CurrentStatus, EffectiveAt=timestamp_json(o.EffectiveAt, source=True),
        Reason=o.Reason, CreatedBy=o.CreatedBy) for o, uid, name, hostel in query.order_by(AttendanceOverride.EffectiveAt.desc()).offset(skip).limit(limit)]

@router.get('/student/{student_id}', response_model=List[ProcessedPunchResponse])
def get_student_attendance(student_id: int, response: Response, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not db.query(Student).filter_by(StudentId=student_id).first():
        raise HTTPException(404, 'Student not found')
    query = punch_query(db, current_user, status='VALID').filter(ProcessedPunch.StudentId == student_id)
    return [punch_response(row, db) for row in _page(query, response, skip, limit)]

@router.get('/hostel/{hostel_id}', response_model=List[ProcessedPunchResponse])
def get_hostel_attendance(hostel_id: int, response: Response, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.Role == 'WARDEN' and current_user.HostelId != hostel_id:
        raise HTTPException(403, 'Hostel is outside your assignment')
    if not db.query(Hostel).filter_by(HostelId=hostel_id).first():
        raise HTTPException(404, 'Hostel not found')
    return [punch_response(row, db) for row in _page(punch_query(db, current_user, hostel_id=hostel_id, status='VALID'), response, skip, limit)]
