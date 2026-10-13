import csv
import io
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from backend.app.main import app
from backend.app.core.database import TargetSessionLocal, source_engine
from backend.app.core.time import local_now, business_day, day_bounds
from backend.app.models import Student, Device, Hostel, RawPunch, ProcessedPunch, StudentCurrentStatus, User
from backend.app.models.attendance import AttendanceOverride
from backend.app.services.punch_processor import process_single_raw_punch, rebuild_student
from backend.app.services.state_history import change_state
from backend.app.core.security import create_access_token
from sync_worker.sync_service import run_synchronization_cycle

client = TestClient(app)

def headers(username='admin'):
    with TargetSessionLocal() as db:
        user = db.query(User).filter_by(Username=username).one()
        return {'Authorization': 'Bearer ' + create_access_token({'sub': username, 'id': user.SystemUserId, 'ver': user.TokenVersion or 0})}

def punch(db, source_id, when, uid='LATE', device=101):
    raw = RawPunch(SourceDeviceLogId=source_id, UserId=uid, DeviceId=device, LogDate=when)
    db.add(raw)
    db.flush()
    return process_single_raw_punch(db, raw)

def test_unassigned_warden_denied_everywhere():
    with TargetSessionLocal() as db:
        db.query(User).filter_by(Username='warden_a').one().HostelId = None
        db.commit()
    for path in ['/api/students', '/api/dashboard/summary', '/api/punches/processed', '/api/reports/export?export_format=csv', '/api/attendance/today']:
        assert client.get(path, headers=headers('warden_a')).status_code == 403

def test_profile_edit_preserves_inactive_status_and_punch_history():
    with TargetSessionLocal() as db:
        student = db.query(Student).filter_by(UserId='U1001').one()
        student.RegistrationStatus = 'INACTIVE'
        sid = student.StudentId
        db.commit()
    response = client.put(f'/api/students/{sid}', json={'StudentName': 'Changed Name'}, headers=headers('warden_a'))
    assert response.status_code == 200
    assert response.json()['RegistrationStatus'] == 'INACTIVE'
    assert client.put(f'/api/students/{sid}/enroll', json={'StudentName': 'Name', 'HostelId': 1}, headers=headers('warden_a')).status_code == 409

def test_late_punch_replays_without_changing_punch_ids():
    with TargetSessionLocal() as db:
        db.add(Student(UserId='LATE', HostelId=1, RegistrationStatus='ACTIVE'))
        db.flush()
        start = local_now() - timedelta(hours=6)
        first = punch(db, 1001, start)
        later = punch(db, 1003, start + timedelta(hours=2))
        original_ids = first.PunchId, later.PunchId
        late = punch(db, 1002, start + timedelta(hours=1))
        rows = db.query(ProcessedPunch).filter_by(UserId='LATE').order_by(ProcessedPunch.LogDate).all()
        assert [p.PunchType for p in rows] == ['REGISTRATION', 'IN', 'OUT']
        assert (rows[0].PunchId, rows[2].PunchId) == original_ids
        curr = db.query(StudentCurrentStatus).filter_by(StudentId=rows[0].StudentId).one()
        assert curr.CurrentStatus == 'OUT'
        assert curr.LastPunchTime == start + timedelta(hours=2)

def test_midnight_duplicates_accumulate_on_correct_day():
    with TargetSessionLocal() as db:
        db.add(Student(UserId='LATE', HostelId=1, RegistrationStatus='ACTIVE'))
        db.flush()
        midnight = day_bounds()[0]
        punch(db, 2001, midnight - timedelta(seconds=5))
        assert punch(db, 2002, midnight + timedelta(seconds=5)).ProcessingStatus == 'DUPLICATE'
        assert punch(db, 2003, midnight + timedelta(seconds=10)).ProcessingStatus == 'DUPLICATE'
        curr = db.query(StudentCurrentStatus).one()
        assert curr.CounterDate == business_day(midnight)
        assert curr.TodayDuplicatePunchCount == 2

def test_worker_imports_only_registered_active_device_ids():
    from backend.tests.conftest import logs
    with source_engine.begin() as conn:
        conn.execute(logs.insert(), [{'DeviceLogId': 1, 'DeviceId': 999, 'UserId': 'UNKNOWN', 'LogDate': local_now()},
            {'DeviceLogId': 2, 'DeviceId': 101, 'UserId': 'U1001', 'LogDate': local_now()}])
    result = run_synchronization_cycle()
    assert result['status'] == 'SUCCESS'
    assert result['last_device_log_id'] == 2
    with TargetSessionLocal() as db:
        assert db.query(RawPunch).count() == 1
        assert db.query(ProcessedPunch).filter_by(DeviceId=999).count() == 0

def test_no_get_student_writes():
    with TargetSessionLocal() as db:
        db.add(Student(UserId='UNASSIGNED', HostelId=None))
        db.add(RawPunch(SourceDeviceLogId=100, DeviceId=101, UserId='UNASSIGNED', LogDate=local_now()))
        db.commit()
    assert client.get('/api/students', headers=headers()).status_code == 200
    with TargetSessionLocal() as db:
        assert db.query(Student).filter_by(UserId='UNASSIGNED').one().HostelId is None

def test_override_survives_late_punch_and_is_exported():
    with TargetSessionLocal() as db:
        student = db.query(Student).filter_by(UserId='U1001').one()
        start = local_now() - timedelta(hours=3)
        punch(db, 3001, start, 'U1001')
        sid = student.StudentId
        db.commit()
    result = client.put(f'/api/students/{sid}/attendance-status', json={'CurrentStatus': 'OUT', 'Reason': 'Approved exit'}, headers=headers())
    assert result.status_code == 200
    with TargetSessionLocal() as db:
        punch(db, 3002, start + timedelta(hours=1), 'U1001')
        assert db.query(StudentCurrentStatus).filter_by(StudentId=sid).one().CurrentStatus == 'OUT'
        db.commit()
    export = client.get('/api/reports/export?export_format=csv', headers=headers())
    assert 'MANUAL_OVERRIDE' in export.text and 'Approved exit' in export.text

def test_export_has_no_2000_limit_and_uses_filters():
    with TargetSessionLocal() as db:
        raw_rows = [RawPunch(SourceDeviceLogId=10000+i, UserId='BULK', DeviceId=101, LogDate=local_now()) for i in range(2001)]
        db.add_all(raw_rows)
        db.flush()
        db.add_all([ProcessedPunch(RawPunchId=r.RawPunchId, UserId='BULK', DeviceId=101, LogDate=r.LogDate, PunchType='IN', ProcessingStatus='VALID', HostelIdSnapshot=1) for r in raw_rows])
        db.commit()
    response = client.get('/api/reports/export?export_format=csv&user_id=BULK&punch_type=IN', headers=headers())
    assert response.status_code == 200
    assert len(list(csv.reader(io.StringIO(response.text.lstrip('\ufeff'))))) == 2002
    assert response.headers['x-total-count'] == '2001'
    assert client.get('/api/reports/export?export_format=csv&user_id=NONEXISTENT', headers=headers()).headers['x-total-count'] == '0'

def test_device_unassigned_rejected_and_last_admin_protected():
    assert client.post('/api/devices', json={'DeviceId': 456, 'DeviceName': 'Unassigned'}, headers=headers()).status_code == 400
    assert client.put('/api/users/1', json={'role': 'MANAGEMENT'}, headers=headers()).status_code == 409

def test_invalid_export_dates_and_limits_rejected():
    for path in ['/api/reports/export?start_date=bad', '/api/reports/export?start_date=2026-10-10&end_date=2026-10-01', '/api/students?limit=-1', '/api/punches/processed?limit=100000']:
        assert client.get(path, headers=headers()).status_code == 422

def test_processed_raw_unique_constraint():
    with TargetSessionLocal() as db:
        row = punch(db, 991, local_now(), 'U1001')
        db.add(ProcessedPunch(RawPunchId=row.RawPunchId, UserId=row.UserId, DeviceId=101, LogDate=row.LogDate, ProcessingStatus='VALID'))
        try:
            db.flush()
            assert False, 'Duplicate processed record was accepted'
        except IntegrityError:
            db.rollback()

def test_source_engine_guard_blocks_writes():
    from backend.app.core.database import build_engine
    guarded = build_engine('sqlite:///:memory:', source=True)
    from backend.app.core.config import settings
    # The guard is installed based on APP_ENV at engine construction.
    old = settings.APP_ENV
    settings.APP_ENV = 'development'
    guarded = build_engine('sqlite:///:memory:', source=True)
    settings.APP_ENV = old
    import pytest
    with guarded.connect() as conn:
        assert conn.exec_driver_sql('SELECT 1').scalar() == 1
        with pytest.raises(PermissionError):
            conn.exec_driver_sql('CREATE TABLE unsafe (id INT)')
    guarded.dispose()


def test_enrollment_recalculates_pending_punches_once_and_profile_edit_does_not():
    with TargetSessionLocal() as db:
        start = local_now() - timedelta(hours=4)
        punch(db, 5001, start, 'ENROLL')
        punch(db, 5002, start + timedelta(hours=1), 'ENROLL')
        student = db.query(Student).filter_by(UserId='ENROLL').one()
        sid = student.StudentId
        assert [p.PunchType for p in db.query(ProcessedPunch).filter_by(UserId='ENROLL').all()] == ['REGISTRATION', 'REGISTRATION']
        db.commit()
    payload = {'StudentName': 'Enrolled Student', 'HostelId': 1, 'RoomNo': 'A1'}
    assert client.put(f'/api/students/{sid}/enroll', json=payload, headers=headers()).status_code == 200
    with TargetSessionLocal() as db:
        before = [(p.PunchId, p.PunchType) for p in db.query(ProcessedPunch).filter_by(UserId='ENROLL').order_by(ProcessedPunch.LogDate)]
        assert [kind for _, kind in before] == ['REGISTRATION', 'IN']
    assert client.put(f'/api/students/{sid}', json={'RoomNo': 'A2'}, headers=headers()).status_code == 200
    assert client.put(f'/api/students/{sid}/enroll', json=payload, headers=headers()).status_code == 409
    with TargetSessionLocal() as db:
        after = [(p.PunchId, p.PunchType) for p in db.query(ProcessedPunch).filter_by(UserId='ENROLL').order_by(ProcessedPunch.LogDate)]
        assert before == after


def test_device_registration_does_not_reprocess_old_unknown_punches():
    with TargetSessionLocal() as db:
        start = local_now() - timedelta(hours=4)
        assert punch(db, 6001, start, 'RECOVER', 999).ProcessingStatus == 'INVALID_DEVICE'
        assert punch(db, 6002, start + timedelta(hours=1), 'RECOVER', 999).ProcessingStatus == 'INVALID_DEVICE'
        db.commit()
    result = client.post('/api/devices', json={'DeviceId': 999, 'DeviceName': 'Recovered gate', 'HostelId': 1}, headers=headers())
    assert result.status_code == 200
    with TargetSessionLocal() as db:
        assert db.query(RawPunch).filter_by(UserId='RECOVER').count() == 2
        assert all(p.ProcessingStatus == 'INVALID_DEVICE' for p in db.query(ProcessedPunch).filter_by(UserId='RECOVER'))


def test_historical_hostel_snapshot_survives_transfer():
    with TargetSessionLocal() as db:
        student = db.query(Student).filter_by(UserId='U1001').one()
        sid = student.StudentId
        row = punch(db, 7001, local_now() - timedelta(hours=2), 'U1001')
        assert row.HostelIdSnapshot == 1
        db.commit()
    assert client.put(f'/api/students/{sid}', json={'HostelId': 2, 'RoomNo': 'B1'}, headers=headers()).status_code == 200
    result = client.get('/api/attendance/history?user_id=U1001', headers=headers('warden_a'))
    assert result.status_code == 200
    assert result.json()[0]['HostelIdSnapshot'] == 1
    assert result.json()[0]['HostelName'] == 'Boys Hostel'


def test_unknown_legacy_assignment_is_not_reassigned_or_shown_to_warden():
    with TargetSessionLocal() as db:
        row = punch(db, 7101, local_now(), 'U1001')
        row.HostelIdSnapshot = None
        row.RoomNoSnapshot = None
        db.commit()
    result = client.get('/api/attendance/history?user_id=U1001', headers=headers())
    item = result.json()[0]
    assert item['HostelName'] is None and item['RoomNo'] is None
    assert item['HistoricalAssignmentKnown'] is False
    assert datetime.fromisoformat(item['LogDate']).tzinfo is not None
    assert client.get('/api/attendance/history?user_id=U1001', headers=headers('warden_a')).json() == []


def test_quarantine_correction_preserves_existing_raw_payload():
    from backend.app.models.integration import QuarantinedPunch, PunchCorrection
    with TargetSessionLocal() as db:
        raw = RawPunch(SourceDeviceLogId=8001, UserId='CORRECT', DeviceId=999, LogDate=local_now() - timedelta(hours=1))
        db.add(raw)
        db.flush()
        item = QuarantinedPunch(SourceDeviceLogId=8001, UserId='CORRECT', DeviceId=999, LogDate=raw.LogDate,
            ErrorType='DATA_CORRUPTION', ErrorMessage='Incorrect device')
        db.add(item)
        db.flush()
        qid, raw_id = item.QuarantineId, raw.RawPunchId
        db.commit()
    result = client.post(f'/api/system/quarantine/{qid}/reprocess', json={'corrected_device_id': 101}, headers=headers())
    assert result.status_code == 200
    with TargetSessionLocal() as db:
        assert db.get(RawPunch, raw_id).DeviceId == 999
        assert db.query(PunchCorrection).filter_by(RawPunchId=raw_id).one().DeviceId == 101
        assert db.query(ProcessedPunch).filter_by(RawPunchId=raw_id).one().DeviceId == 101


def test_password_change_revokes_old_token():
    old = headers('warden_a')
    assert client.put('/api/users/2', json={'password': 'NewPassword123'}, headers=headers()).status_code == 200
    assert client.get('/api/students', headers=old).status_code == 401


def test_static_path_cannot_escape_frontend():
    assert client.get('/..%5C..%5Cbackend%5C.env').status_code == 404


def test_schema_null_counter_date_reconstructs_existing_counts():
    with TargetSessionLocal() as db:
        start = local_now() - timedelta(minutes=5)
        punch(db, 9001, start, 'U1001')
        punch(db, 9002, start + timedelta(minutes=1), 'U1001')
        curr = db.query(StudentCurrentStatus).one()
        curr.CounterDate = None  # Schema-only migration leaves legacy rows null.
        db.flush()
        punch(db, 9003, start + timedelta(minutes=2), 'U1001')
        assert curr.TodayValidPunchCount == 3


def test_excel_export_and_formula_cells_are_safe():
    from openpyxl import load_workbook
    with TargetSessionLocal() as db:
        student = db.query(Student).filter_by(UserId='U1001').one()
        student.StudentName = '=1+1'
        punch(db, 10001, local_now(), 'U1001')
        db.commit()
    response = client.get('/api/reports/export?export_format=excel', headers=headers())
    assert response.status_code == 200
    workbook = load_workbook(io.BytesIO(response.content))
    cell = workbook.active['C2']
    assert cell.data_type != 'f'
    assert cell.value.endswith('=1+1')
    workbook.close()


def test_failed_batch_rolls_back_raw_records_and_checkpoint(monkeypatch):
    from backend.tests.conftest import logs
    from backend.app.models.integration import SyncCheckpoint
    from sync_worker import sync_service
    with source_engine.begin() as connection:
        connection.execute(logs.insert(), [
            {'DeviceLogId': 1, 'DeviceId': 101, 'UserId': 'U1001', 'LogDate': local_now()},
            {'DeviceLogId': 2, 'DeviceId': 101, 'UserId': 'U1001', 'LogDate': local_now() + timedelta(minutes=1)},
        ])
    original = sync_service.process_single_raw_punch
    def fail_second(db, raw):
        if raw.SourceDeviceLogId == 2:
            raise RuntimeError('Simulated transient failure')
        return original(db, raw)
    monkeypatch.setattr(sync_service, 'process_single_raw_punch', fail_second)
    assert run_synchronization_cycle()['status'] == 'FAILED'
    with TargetSessionLocal() as db:
        assert db.query(RawPunch).count() == 0
        assert db.query(ProcessedPunch).count() == 0
        assert db.query(SyncCheckpoint).one().LastSourceDeviceLogId == 0
    monkeypatch.setattr(sync_service, 'process_single_raw_punch', original)
    assert run_synchronization_cycle()['status'] == 'SUCCESS'
    with TargetSessionLocal() as db:
        assert db.query(RawPunch).count() == 2


def test_login_throttles_repeated_bad_passwords():
    for _ in range(10):
        assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'bad-password'}).status_code == 401
    response = client.post('/api/auth/login', json={'username': 'admin', 'password': 'bad-password'})
    assert response.status_code == 429
    assert response.headers['retry-after'] == '60'


def test_future_device_clock_is_quarantined_without_attendance():
    from backend.tests.conftest import logs
    from backend.app.models.integration import SyncCheckpoint, QuarantinedPunch
    with source_engine.begin() as connection:
        connection.execute(logs.insert(), {'DeviceLogId': 1, 'DeviceId': 101,
            'UserId': 'U1001', 'LogDate': local_now() + timedelta(hours=2)})
    result = run_synchronization_cycle()
    assert result['synced_count'] == 0
    with TargetSessionLocal() as db:
        assert db.query(RawPunch).count() == 0
        assert db.query(ProcessedPunch).count() == 0
        assert db.query(QuarantinedPunch).one().ResolvedStatus == 'PENDING'
        assert db.query(SyncCheckpoint).one().LastSourceDeviceLogId == 1


def test_invalid_late_punch_does_not_rewrite_legacy_registration_history():
    with TargetSessionLocal() as db:
        start = local_now() - timedelta(hours=3)
        first = punch(db, 11001, start, 'LEGACY')
        second = punch(db, 11002, start + timedelta(hours=1), 'LEGACY')
        student = db.query(Student).filter_by(UserId='LEGACY').one()
        student.RegistrationStatus = 'INACTIVE'
        db.flush()
        before = [(first.PunchId, first.PunchType), (second.PunchId, second.PunchType)]
        late = punch(db, 11003, start - timedelta(minutes=1), 'LEGACY')
        assert late.ProcessingStatus == 'INACTIVE_STUDENT'
        assert before == [(first.PunchId, first.PunchType), (second.PunchId, second.PunchType)]
