from datetime import datetime
from typing import List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.core.database import get_db, SourceSessionLocal
from backend.app.core.config import settings
from backend.app.core.security import get_current_user, require_roles
from backend.app.core.locking import attendance_lock
from backend.app.core.time import source_time
from backend.app.models.integration import SyncCheckpoint, RawPunch, QuarantinedPunch, PunchCorrection
from backend.app.models.master import Student
from backend.app.models.attendance import ProcessedPunch
from backend.app.models.security import User, SystemEvent
from backend.app.schemas.schemas import SyncStatusResponse, QuarantinedPunchResponse, QuarantineReprocessRequest, timestamp_json
from backend.app.services.punch_processor import process_single_raw_punch, rebuild_student, effective_raw
from sync_worker.sync_service import run_synchronization_cycle
from backend.app.services.device_ingestion import active_device_windows

router = APIRouter(prefix='/system', tags=['System & Monitoring'])

@router.get('/ping')
def ping_service():
    return {'status': 'UP', 'timestamp': datetime.utcnow().isoformat() + 'Z'}

@router.get('/health')
def get_system_health(db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN']))):
    try:
        db.execute(text('SELECT 1'))
        checkpoint = db.query(SyncCheckpoint).filter_by(SourceName='IT_SQL_SERVER').first()
        total_raw = db.query(RawPunch).count()
        quarantined = db.query(QuarantinedPunch).filter_by(ResolvedStatus='PENDING').count()
    except Exception:
        db.rollback()
        return {'status': 'DEGRADED', 'target_db_connected': False, 'source_db_connected': None, 'last_sync_status': 'UNKNOWN'}
    try:
        with SourceSessionLocal() as source:
            source.execute(text('SELECT 1'))
            from sync_worker.sync_service import get_source_device_logs_table
            from backend.app.services.device_ingestion import eligible_source_rows
            from backend.app.core.time import local_now
            table = get_source_device_logs_table()
            pending = eligible_source_rows(source, table, active_device_windows(db),
                [table.c.DeviceLogId > checkpoint.LastSourceDeviceLogId], 1) if checkpoint else []
            pending_age = max(0, (local_now() - source_time(pending[0].LogDate)).total_seconds()) if pending and pending[0].LogDate else None
        source_ok = True
    except Exception:
        source_ok = False
        pending, pending_age = [], None
    last_completed = checkpoint.LastSyncCompletedAt if checkpoint else None
    age = max(0, (datetime.utcnow() - last_completed).total_seconds()) if last_completed else None
    fresh = age is not None and age <= settings.SYNC_STALE_SECONDS
    sync_ok = checkpoint is not None and checkpoint.LastSyncStatus in ('SUCCESS', 'PARTIAL_SUCCESS', 'RUNNING')
    return {'status': 'HEALTHY' if source_ok and fresh and sync_ok and not quarantined and (pending_age is None or pending_age <= settings.SYNC_STALE_SECONDS) else 'DEGRADED',
        'target_db_connected': True, 'source_db_connected': source_ok, 'sync_fresh': fresh, 'sync_age_seconds': age,
        'total_raw_punches': total_raw, 'pending_quarantined_punches': quarantined,
        'last_sync_time': timestamp_json(last_completed), 'last_source_device_log_id': checkpoint.LastSourceDeviceLogId if checkpoint else 0,
        'eligible_backlog_detected': bool(pending), 'next_pending_punch_age_seconds': pending_age,
        'next_pending_source_id': pending[0].DeviceLogId if pending else None,
        'last_sync_status': checkpoint.LastSyncStatus if checkpoint else 'NEVER_RUN',
        'last_error': checkpoint.LastError if checkpoint else None}

@router.get('/sync-status', response_model=SyncStatusResponse)
def get_sync_status(db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN']))):
    checkpoint = db.query(SyncCheckpoint).filter_by(SourceName='IT_SQL_SERVER').first()
    if checkpoint is None:
        raise HTTPException(404, 'Synchronization has not run')
    return SyncStatusResponse(**{name: getattr(checkpoint, name) for name in SyncStatusResponse.model_fields})

@router.post('/sync-trigger')
def trigger_manual_sync(db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN']))):
    result = run_synchronization_cycle()
    if result['status'] == 'FAILED':
        raise HTTPException(503, 'Synchronization failed; check system status')
    return {'message': 'Synchronization cycle finished', 'result': result}

@router.get('/quarantine', response_model=List[QuarantinedPunchResponse])
def get_quarantined_punches(response: Response, status: Optional[Literal['PENDING', 'RESOLVED', 'IGNORED']] = None,
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN']))):
    query = db.query(QuarantinedPunch)
    if status:
        query = query.filter_by(ResolvedStatus=status)
    response.headers['X-Total-Count'] = str(query.count())
    return query.order_by(QuarantinedPunch.QuarantineId.desc()).offset(skip).limit(limit).all()

@router.post('/quarantine/{quarantine_id}/resolve')
def resolve_quarantined_punch(quarantine_id: int, action: Literal['RESOLVED', 'IGNORED'] = 'RESOLVED', db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN']))):
    with attendance_lock(db):
        item = db.query(QuarantinedPunch).filter_by(QuarantineId=quarantine_id).first()
        if item is None:
            raise HTTPException(404, 'Quarantine record not found')
        item.ResolvedStatus, item.ResolvedAt, item.ResolvedBy = action, datetime.utcnow(), current_user.Username
        db.add(SystemEvent(EventType='QUARANTINE_RESOLVED', Description=f'Quarantine {quarantine_id}: {action}', CreatedBy=current_user.Username))
        db.commit()
        return {'message': f'Quarantine record marked {action}'}

@router.post('/quarantine/{quarantine_id}/reprocess')
def reprocess_quarantined_punch(quarantine_id: int, req: Optional[QuarantineReprocessRequest] = None, db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN']))):
    with attendance_lock(db):
        item = db.query(QuarantinedPunch).filter_by(QuarantineId=quarantine_id).first()
        if item is None:
            raise HTTPException(404, 'Quarantine record not found')
        if item.ResolvedStatus != 'PENDING':
            raise HTTPException(409, 'Record is already resolved or ignored')
        uid = req.corrected_user_id.strip() if req and req.corrected_user_id else item.UserId
        device_id = req.corrected_device_id if req and req.corrected_device_id else item.DeviceId
        when = req.corrected_log_date if req and req.corrected_log_date else item.LogDate
        if not uid or not device_id or not when:
            raise HTTPException(400, 'Valid UserId, DeviceId, and LogDate are required')
        windows = active_device_windows(db, [device_id])
        if device_id not in windows or (windows[device_id] is not None and source_time(when) < windows[device_id]):
            raise HTTPException(409, 'Only punches from an active registered device in its current activation period may be imported')
        raw = db.query(RawPunch).filter_by(SourceDeviceLogId=item.SourceDeviceLogId).first()
        old_uid = effective_raw(db, raw).UserId if raw else None
        if raw is None:
            raw = RawPunch(SourceDeviceLogId=item.SourceDeviceLogId, UserId=uid, DeviceId=device_id,
                LogDate=source_time(when), DownloadDate=item.DownloadDate)
            db.add(raw)
            db.flush()
        else:
            old_processed = db.query(ProcessedPunch).filter_by(RawPunchId=raw.RawPunchId).first()
            if old_uid != uid and old_processed is not None:
                raise HTTPException(409, 'Changing the identity of an already processed punch requires an explicit attendance correction review')
            db.add(PunchCorrection(RawPunchId=raw.RawPunchId, UserId=uid, DeviceId=device_id,
                LogDate=source_time(when), Reason=f'Quarantine {quarantine_id} correction', CreatedBy=current_user.Username))
            db.flush()
        student = db.query(Student).filter_by(UserId=uid).first()
        try:
            if student:
                rebuild_student(db, student, revalidate_ids={raw.RawPunchId})
                processed = db.query(ProcessedPunch).filter_by(RawPunchId=raw.RawPunchId).one()
            else:
                processed = process_single_raw_punch(db, raw)
        except ValueError as error:
            raise HTTPException(409, str(error))
        if processed.ProcessingStatus in ('INVALID_DEVICE', 'INACTIVE_STUDENT'):
            raise HTTPException(409, 'Correction still fails device or student validation')
        item.ResolvedStatus, item.ResolvedAt, item.ResolvedBy = 'RESOLVED', datetime.utcnow(), current_user.Username
        # Original quarantine payload remains unchanged.
        db.add(SystemEvent(EventType='QUARANTINE_REPROCESSED', Description=f'Quarantine {quarantine_id}: punch {processed.PunchId}', CreatedBy=current_user.Username))
        db.commit()
        return {'message': 'Quarantine record reprocessed', 'punch_id': processed.PunchId,
            'processing_status': processed.ProcessingStatus, 'punch_type': processed.PunchType, 'student_id': processed.StudentId}
