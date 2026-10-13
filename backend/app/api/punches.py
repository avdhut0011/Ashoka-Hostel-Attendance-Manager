from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models.attendance import ProcessedPunch
from backend.app.models.security import User
from backend.app.schemas.schemas import ProcessedPunchResponse
from backend.app.services.reporting import punch_query, punch_response, punch_count, punch_page

router = APIRouter(prefix='/punches', tags=['Punches'])

def page(db, user, response, skip, limit, status=None, punch_type=None, device_id=None, user_id=None, cursor=None):
    query = punch_query(db, user, status=status, punch_type=punch_type, user_id=user_id, search_all=True)
    if device_id:
        query = query.filter(ProcessedPunch.DeviceId == device_id)
    response.headers['X-Total-Count'] = str(punch_count(query))
    return [punch_response(row, db) for row in punch_page(query, skip, limit, cursor, response)]

@router.get('/processed', response_model=List[ProcessedPunchResponse])
def get_processed_punches(response: Response, status: Optional[str] = None, punch_type: Optional[str] = None,
    device_id: Optional[int] = None, user_id: Optional[str] = None, skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500), cursor: Optional[str] = Query(None, max_length=200), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return page(db, current_user, response, skip, limit, status, punch_type, device_id, user_id, cursor)

@router.get('/duplicates', response_model=List[ProcessedPunchResponse])
def get_duplicate_punches(response: Response, user_id: Optional[str] = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), cursor: Optional[str] = Query(None, max_length=200), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return page(db, current_user, response, skip, limit, 'DUPLICATE', user_id=user_id, cursor=cursor)

@router.get('/invalid-device', response_model=List[ProcessedPunchResponse])
def get_invalid_device_punches(response: Response, user_id: Optional[str] = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), cursor: Optional[str] = Query(None, max_length=200), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return page(db, current_user, response, skip, limit, 'INVALID_DEVICE', user_id=user_id, cursor=cursor)

@router.get('/inactive-students', response_model=List[ProcessedPunchResponse])
def get_inactive_student_punches(response: Response, user_id: Optional[str] = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), cursor: Optional[str] = Query(None, max_length=200), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return page(db, current_user, response, skip, limit, 'INACTIVE_STUDENT', user_id=user_id, cursor=cursor)
