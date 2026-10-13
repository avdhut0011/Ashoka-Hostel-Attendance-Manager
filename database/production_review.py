"""Production review: read Epush, write ONLY new review tables.

No attendance import, profile change, checkpoint change, or replay is possible here.
"""
import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, text, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.models import Student, StudentStateHistory, StudentHostelHistory
from backend.app.models.review import VerifiedRoomChange, RecoveryScan

NEW_WRITABLE = {'integration.RecoveryScans', 'integration.RecoveryPunches', 'master.VerifiedRoomChanges', 'system.AttendanceChanges'}


def fingerprints(connection):
    tables = connection.execute(text("SELECT s.name,t.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id")).all()
    hashes = {}
    for schema, name in tables:
        key = f'{schema}.{name}'
        if schema not in ('master', 'attendance', 'integration', 'security', 'system') or key in NEW_WRITABLE:
            continue
        rows = connection.execute(text(f'SELECT * FROM [{schema.replace("]", "]]")}].[{name.replace("]", "]]")}]')).all()
        encoded = sorted(json.dumps(list(row), default=str, ensure_ascii=True) for row in rows)
        hashes[key] = {'count': len(rows), 'sha256': hashlib.sha256('\n'.join(encoded).encode()).hexdigest()}
    return hashes


def run(args):
    target = make_url(settings.get_target_db_url())
    if target.get_backend_name() != 'mssql' or (target.database or '').lower() != 'hostelattendance' or target.host == '192.168.9.6':
        raise RuntimeError('Expected the HostelAttendance target; source server is forbidden as a write target')
    engine = create_engine(target, connect_args={'timeout': 10})
    @event.listens_for(engine, 'before_cursor_execute')
    def restrict_writes(connection, cursor, statement, parameters, context, executemany):
        normalized = statement.replace('[', '').replace(']', '').strip()
        if normalized.upper().startswith('SELECT'):
            return
        if 'sp_getapplock' in normalized or 'sp_releaseapplock' in normalized:
            return
        match = re.match(r'(?:INSERT INTO|UPDATE)\s+([\w.]+)', normalized, re.I)
        if not match or match.group(1) not in NEW_WRITABLE:
            raise PermissionError('This command may write only to new recovery/history/notification tables')
    receipt = {'source_connected': False}
    try:
        with engine.connect() as connection:
            acquired = []
            try:
                for resource in ('HostelAttendanceSyncLock', 'HostelAttendance:timeline', 'HostelAttendance:accounts'):
                    code = connection.execute(text("SET NOCOUNT ON; DECLARE @r INT; EXEC @r=sp_getapplock @Resource=:key,@LockMode='Exclusive',@LockOwner='Session',@LockTimeout=15000; SELECT @r;"), {'key': resource}).scalar()
                    if code is None or code < 0:
                        raise RuntimeError('Production is busy; review stopped without changing attendance')
                    acquired.append(resource)
                connection.commit()
                before = fingerprints(connection)
                connection.commit()
                with Session(bind=connection, join_transaction_mode='control_fully') as db:
                    student = db.query(Student).filter_by(UserId=args.user_id).first()
                    if not student:
                        raise ValueError('Existing student not found; no student will be created')
                    receipt['student'] = {'user_id': student.UserId, 'current_room': student.RoomNo,
                        'captured_state_rows': db.query(StudentStateHistory).filter_by(StudentId=student.StudentId).count(),
                        'legacy_assignment_rows': db.query(StudentHostelHistory).filter_by(StudentId=student.StudentId).count()}
                    if args.record_room_change:
                        existing = db.query(VerifiedRoomChange).filter_by(StudentId=student.StudentId, ChangeDate=args.change_date).first()
                        if existing and (existing.OldRoomNo != args.old_room or existing.NewRoomNo != args.new_room):
                            raise ValueError('Conflicting verified history exists; no replacement was made')
                        if not existing:
                            db.add(VerifiedRoomChange(StudentId=student.StudentId, OldRoomNo=args.old_room,
                                NewRoomNo=args.new_room, ChangeDate=args.change_date, EffectiveAt=None,
                                Evidence='Operator confirmed room transition on this date; exact time is unknown.',
                                RecordedBy='operator-confirmation'))
                            db.commit()
                        receipt['room_change'] = {'old': args.old_room, 'new': args.new_room,
                            'date': str(args.change_date), 'precision': 'DATE_ONLY', 'existing_profile_changed': False}
                    if args.scan_start:
                        if not args.scan_end:
                            raise ValueError('Both scan dates are required')
                        # Importing application engines does not open a connection.
                        from backend.app.core.database import SourceSessionLocal, source_engine
                        from backend.app.services.recovery import new_scan, scan_missing
                        from sync_worker.sync_service import get_source_device_logs_table
                        previous = db.query(RecoveryScan).filter_by(StartDate=args.scan_start, EndDate=args.scan_end).order_by(RecoveryScan.ScanId.desc()).first()
                        scan_id = previous.ScanId if previous else new_scan(db, args.scan_start, args.scan_end, 'operator-confirmation')
                        try:
                            with SourceSessionLocal() as source:
                                receipt['source_connected'] = True
                                scan = scan_missing(db, source, get_source_device_logs_table(), scan_id, budget_seconds=20)
                                receipt['scan'] = {key: getattr(scan, key) for key in ('ScanId', 'Status', 'ScannedCount', 'CandidateCount', 'UnknownStudentCount', 'SourceWatermark')}
                        except Exception as error:
                            db.rollback()
                            receipt['scan_error'] = type(error).__name__ + ': scan did not complete; retry the saved scan'
                        finally:
                            source_engine.dispose()
                    db.rollback()
                after = fingerprints(connection)
                connection.commit()
                if before != after:
                    raise RuntimeError('Existing table fingerprints changed during review; investigate before any rollout')
                receipt['existing_records_unchanged'] = True
                receipt['existing_table_fingerprints'] = after
            finally:
                connection.rollback()
                for resource in reversed(acquired):
                    connection.execute(text("EXEC sp_releaseapplock @Resource=:key,@LockOwner='Session'"), {'key': resource})
                connection.commit()
    finally:
        engine.dispose()
    receipt['verified_at_utc'] = datetime.now(timezone.utc).isoformat()
    Path('database/migrations/production_review_receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in receipt.items() if key != 'existing_table_fingerprints'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id', default='8001')
    parser.add_argument('--record-room-change', action='store_true')
    parser.add_argument('--old-room')
    parser.add_argument('--new-room')
    parser.add_argument('--change-date', type=date.fromisoformat)
    parser.add_argument('--scan-start', type=date.fromisoformat)
    parser.add_argument('--scan-end', type=date.fromisoformat)
    args = parser.parse_args()
    if args.record_room_change and not all((args.old_room, args.new_room, args.change_date)):
        parser.error('Room change requires old room, new room and change date')
    run(args)
