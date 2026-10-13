from datetime import date
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.app.core.database import get_db, get_source_db
from backend.app.core.security import require_roles
from backend.app.core.locking import attendance_lock
from backend.app.models.security import User
from backend.app.models.review import RecoveryPunch, RecoveryScan
from backend.app.schemas.schemas import timestamp_json
from backend.app.services.recovery import new_scan, scan_missing
from sync_worker.sync_service import get_source_device_logs_table

router = APIRouter(prefix='/recovery', tags=['Recovery review'])
reviewer = require_roles(['ADMIN', 'IT_ADMIN'])


class ScanRequest(BaseModel):
    start_date: date
    end_date: date


class ReviewRequest(BaseModel):
    status: Literal['REVIEWED', 'IGNORED']
    note: str = Field(min_length=1, max_length=500, pattern=r'\S')


def scan_response(scan):
    return {name: getattr(scan, name) for name in (
        'ScanId', 'StartDate', 'EndDate', 'SourceWatermark', 'LastScannedSourceId',
        'ScannedCount', 'CandidateCount', 'UnknownStudentCount', 'Status', 'RequestedBy')}


@router.post('/scans')
def start_scan(body: ScanRequest, db: Session = Depends(get_db), user: User = Depends(reviewer)):
    try:
        scan_id = new_scan(db, body.start_date, body.end_date, user.Username)
    except ValueError as error:
        raise HTTPException(422, str(error))
    return scan_response(db.get(RecoveryScan, scan_id))


@router.post('/scans/{scan_id}/continue')
def continue_scan(scan_id: int, db: Session = Depends(get_db), source: Session = Depends(get_source_db), user: User = Depends(reviewer)):
    try:
        return scan_response(scan_missing(db, source, get_source_device_logs_table(), scan_id))
    except ValueError as error:
        raise HTTPException(404, str(error))
    except Exception:
        db.rollback()
        raise HTTPException(503, 'Recovery scan could not complete; no attendance was imported. Retry this scan.')


@router.get('/scans')
def list_scans(response: Response, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
               db: Session = Depends(get_db), user: User = Depends(reviewer)):
    query = db.query(RecoveryScan)
    response.headers['X-Total-Count'] = str(query.count())
    return [scan_response(row) for row in query.order_by(RecoveryScan.ScanId.desc()).offset(skip).limit(limit)]


@router.get('/punches')
def list_candidates(response: Response, status: Optional[Literal['PENDING', 'REVIEWED', 'IGNORED']] = None,
                    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                    db: Session = Depends(get_db), user: User = Depends(reviewer)):
    query = db.query(RecoveryPunch)
    if status:
        query = query.filter(RecoveryPunch.ReviewStatus == status)
    response.headers['X-Total-Count'] = str(query.count())
    return [dict(RecoveryId=row.RecoveryId, SourceDeviceLogId=row.SourceDeviceLogId, StudentId=row.StudentId,
                 UserId=row.UserId, DeviceId=row.DeviceId, LogDate=timestamp_json(row.LogDate, source=True),
                 ReviewStatus=row.ReviewStatus, Reason=row.Reason, ReviewNote=row.ReviewNote,
                 ReviewedBy=row.ReviewedBy, ReviewedAt=timestamp_json(row.ReviewedAt))
            for row in query.order_by(RecoveryPunch.LogDate, RecoveryPunch.RecoveryId).offset(skip).limit(limit)]


@router.put('/punches/{recovery_id}/review')
def review_candidate(recovery_id: int, body: ReviewRequest, db: Session = Depends(get_db), user: User = Depends(reviewer)):
    from datetime import datetime
    with attendance_lock(db, 'recovery'):
        row = db.get(RecoveryPunch, recovery_id)
        if row is None:
            raise HTTPException(404, 'Recovery candidate not found')
        row.ReviewStatus, row.ReviewNote = body.status, body.note
        row.ReviewedBy, row.ReviewedAt = user.Username, datetime.utcnow()
        db.commit()
    return {'status': body.status, 'attendance_imported': False}
