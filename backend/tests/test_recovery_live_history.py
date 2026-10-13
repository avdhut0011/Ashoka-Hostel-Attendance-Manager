from datetime import datetime, date, timedelta
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import text
import pytest
from backend.app.main import app
from backend.app.core.database import TargetSessionLocal, SourceSessionLocal
from backend.app.core.security import create_access_token
from backend.app.models import Student, User, RawPunch, SyncCheckpoint, ProcessedPunch
from backend.app.models.review import RecoveryPunch, RecoveryScan, VerifiedRoomChange
from backend.app.services.recovery import new_scan, scan_missing
from backend.app.services.change_events import change_marker
from backend.app.services.verified_history import historical_room
from sync_worker.sync_service import get_source_device_logs_table


def token(username='admin'):
    with TargetSessionLocal() as db:
        user = db.query(User).filter_by(Username=username).one()
        return create_access_token({'sub': username, 'id': user.SystemUserId, 'ver': user.TokenVersion or 0})


def test_recovery_only_saves_missing_existing_students_and_is_idempotent():
    start = datetime(2026, 10, 8)
    with TargetSessionLocal() as db:
        db.add(SyncCheckpoint(SourceName='IT_SQL_SERVER', LastSourceDeviceLogId=4))
        db.add(RawPunch(SourceDeviceLogId=1, DeviceId=101, UserId='U1001', LogDate=start))
        db.commit()
    with SourceSessionLocal() as source:
        for sid, uid in [(1, 'U1001'), (2, 'U1001'), (3, 'NEW_USER'), (4, 'U1001'), (5, 'U1001')]:
            source.execute(text('INSERT INTO DeviceLogs (DeviceLogId,DeviceId,UserId,LogDate) VALUES (:sid,101,:uid,:when)'),
                           {'sid': sid, 'uid': uid, 'when': start + timedelta(hours=sid)})
        source.commit()
    with TargetSessionLocal() as db, SourceSessionLocal() as source:
        initial = (db.query(Student).count(), db.query(RawPunch).count(), db.query(ProcessedPunch).count())
        scan_id = new_scan(db, date(2026, 10, 8), date(2026, 10, 10), 'admin')
        scan = scan_missing(db, source, get_source_device_logs_table(), scan_id, batch_size=2)
        assert scan.Status == 'PARTIAL'
        while scan.Status != 'COMPLETE':
            scan = scan_missing(db, source, get_source_device_logs_table(), scan_id, batch_size=2)
        assert scan.Status == 'COMPLETE' and scan.CandidateCount == 2 and scan.UnknownStudentCount == 1
        assert {row.SourceDeviceLogId for row in db.query(RecoveryPunch)} == {2, 4}
        second = new_scan(db, date(2026, 10, 8), date(2026, 10, 10), 'admin')
        assert scan_missing(db, source, get_source_device_logs_table(), second).CandidateCount == 0
        assert initial == (db.query(Student).count(), db.query(RawPunch).count(), db.query(ProcessedPunch).count())
        assert db.query(SyncCheckpoint).one().LastSourceDeviceLogId == 4
    client = TestClient(app)
    headers = {'Authorization': 'Bearer ' + token()}
    candidates = client.get('/api/recovery/punches', headers=headers).json()
    response = client.put(f"/api/recovery/punches/{candidates[0]['RecoveryId']}/review", headers=headers,
                          json={'status': 'REVIEWED', 'note': 'Confirmed; review only'})
    assert response.json()['attendance_imported'] is False
    assert client.get('/api/recovery/punches', headers={'Authorization': 'Bearer ' + token('warden_a')}).status_code == 403


def test_date_only_room_evidence_never_invents_change_time():
    with TargetSessionLocal() as db:
        student = db.query(Student).one()
        db.add(VerifiedRoomChange(StudentId=student.StudentId, OldRoomNo='1', NewRoomNo='2', ChangeDate=date(2026, 10, 10),
                                 Evidence='Operator confirmation', RecordedBy='admin'))
        db.commit()
        from types import SimpleNamespace
        sample = SimpleNamespace(StudentId=student.StudentId, RoomNoSnapshot=None, LogDate=datetime(2026, 10, 10, 20))
        assert historical_room(db, sample) == (None, 'CHANGE_TIME_UNKNOWN')
        sample.LogDate = datetime(2026, 10, 11)
        assert historical_room(db, sample) == ('2', 'OPERATOR_CONFIRMED')
        sample.LogDate = datetime(2026, 10, 9)
        assert historical_room(db, sample) == (None, 'UNKNOWN')
        sample.RoomNoSnapshot = '1'
        assert historical_room(db, sample) == ('1', 'PUNCH_SNAPSHOT')
        assert student.RoomNo is None


def test_notification_rollback_and_commit():
    with TargetSessionLocal() as db:
        before = change_marker(db)
        student = db.query(Student).one()
        student.RoomNo = 'ROLLBACK'
        db.flush()
        assert change_marker(db) != before
        db.rollback()
        assert change_marker(db) == before
        student = db.query(Student).one()
        student.RoomNo = 'COMMITTED'
        db.commit()
        assert change_marker(db) != before


def test_replay_does_not_backfill_unknown_legacy_assignment():
    from backend.app.services.punch_processor import process_single_raw_punch, rebuild_student
    from backend.app.core.time import local_now
    with TargetSessionLocal() as db:
        student = db.query(Student).one()
        raw = RawPunch(SourceDeviceLogId=999, DeviceId=101, UserId=student.UserId, LogDate=local_now())
        db.add(raw)
        db.flush()
        row = process_single_raw_punch(db, raw)
        row.HostelIdSnapshot, row.RoomNoSnapshot = None, None
        db.commit()
        rebuild_student(db, student)
        db.commit()
        assert row.HostelIdSnapshot is None and row.RoomNoSnapshot is None


def test_live_authentication_and_read_only_connection():
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/dashboard/live') as socket:
            socket.send_json({'token': 'invalid'})
            socket.receive_json()
    with TargetSessionLocal() as db:
        before = change_marker(db)
    with client.websocket_connect('/api/dashboard/live') as socket:
        socket.send_json({'token': token()})
        assert socket.receive_json() == {'type': 'ready'}
        assert socket.receive_json() == {'type': 'refresh'}
    with TargetSessionLocal() as db:
        assert change_marker(db) == before


def test_live_denies_warden_without_hostel():
    with TargetSessionLocal() as db:
        db.query(User).filter_by(Username='warden_a').one().HostelId = None
        db.commit()
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/dashboard/live') as socket:
            socket.send_json({'token': token('warden_a')})
            socket.receive_json()


def test_isolated_test_configuration_cannot_target_production():
    from backend.app.core.config import Settings
    with pytest.raises(ValueError):
        Settings(APP_ENV='sqlserver_test', ISOLATED_TEST_DATABASE='HostelAttendance',
                 TARGET_DATABASE_URL='mssql+pyodbc://localhost/HostelAttendance',
                 SOURCE_DATABASE_URL='mssql+pyodbc://localhost/HostelAttendance')


def test_recovery_range_limits_unknown_and_after_checkpoint_rows():
    with TargetSessionLocal() as db:
        with pytest.raises(ValueError):
            new_scan(db, date(2026, 10, 10), date(2026, 10, 8), 'admin')
        with pytest.raises(ValueError):
            new_scan(db, date(2026, 10, 8), date(2026, 10, 10), 'admin')
        assert db.query(RecoveryScan).count() == 0


def test_live_rejects_untrusted_origin():
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/dashboard/live', headers={'origin': 'https://untrusted.invalid'}) as socket:
            socket.send_json({'token': token()})
