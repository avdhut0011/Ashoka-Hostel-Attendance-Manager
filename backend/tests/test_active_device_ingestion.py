from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import event
from backend.app.main import app
from backend.app.core.database import TargetSessionLocal, source_engine
from backend.app.core.time import local_now
from backend.app.models import Device, DeviceStateHistory, RawPunch, QuarantinedPunch, SyncCheckpoint, Student, User
from backend.app.core.security import create_access_token
from backend.app.services.device_ingestion import active_device_windows
from sync_worker.sync_service import run_synchronization_cycle
from backend.tests.conftest import logs


def headers():
    with TargetSessionLocal() as db:
        user = db.query(User).filter_by(Username='admin').one()
        return {'Authorization': 'Bearer ' + create_access_token({'sub': user.Username, 'id': user.SystemUserId, 'ver': 0})}


def add_logs(values):
    with source_engine.begin() as connection:
        connection.execute(logs.insert(), values)


def test_worker_excludes_inactive_unknown_devices_and_never_quarantines_them():
    with TargetSessionLocal() as db:
        db.get(Device, 102).IsActive = False
        db.commit()
    add_logs([{'DeviceLogId': sid, 'DeviceId': device, 'UserId': 'U1001', 'LogDate': local_now()}
              for sid, device in [(1, 999), (2, 102), (3, 101)]])
    result = run_synchronization_cycle()
    assert result['synced_count'] == 1 and result['last_device_log_id'] == 3
    with TargetSessionLocal() as db:
        assert [row.DeviceId for row in db.query(RawPunch)] == [101]
        assert db.query(QuarantinedPunch).count() == 0


def test_no_active_devices_means_no_source_query():
    with TargetSessionLocal() as db:
        db.query(Device).update({Device.IsActive: False})
        db.commit()
    add_logs([{'DeviceLogId': 1, 'DeviceId': 101, 'UserId': 'U1001', 'LogDate': local_now()}])
    queries = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        queries.append(statement)
    event.listen(source_engine, 'before_cursor_execute', capture)
    try:
        assert run_synchronization_cycle()['synced_count'] == 0
    finally:
        event.remove(source_engine, 'before_cursor_execute', capture)
    assert queries == []
    with TargetSessionLocal() as db:
        assert db.query(RawPunch).count() == 0
        assert db.query(SyncCheckpoint).one().LastSourceDeviceLogId == 0


def test_activation_cutoff_and_reactivation_never_import_earlier_punches(monkeypatch):
    from backend.app.services import state_history
    activation = local_now() - timedelta(hours=1)
    with TargetSessionLocal() as db:
        db.get(Device, 102).IsActive = False
        db.add(Student(UserId='ACTIVATION', StudentName='Isolated student', HostelId=2))
        db.commit()
    add_logs([{'DeviceLogId': 1, 'DeviceId': 102, 'UserId': 'ACTIVATION', 'LogDate': activation - timedelta(seconds=1)},
              {'DeviceLogId': 2, 'DeviceId': 101, 'UserId': 'U1001', 'LogDate': activation - timedelta(seconds=2)}])
    assert run_synchronization_cycle()['last_device_log_id'] == 2
    client = TestClient(app)
    monkeypatch.setattr(state_history, 'local_now', lambda: activation)
    assert client.put('/api/devices/102/status', json={'is_active': True}, headers=headers()).status_code == 200
    add_logs([{'DeviceLogId': sid, 'DeviceId': 102, 'UserId': 'ACTIVATION', 'LogDate': when}
              for sid, when in [(3, activation - timedelta(seconds=1)), (4, activation), (5, activation + timedelta(minutes=1))]])
    assert run_synchronization_cycle(batch_size=1)['synced_count'] == 2
    monkeypatch.setattr(state_history, 'local_now', lambda: activation + timedelta(minutes=2))
    assert client.put('/api/devices/102/status', json={'is_active': False}, headers=headers()).status_code == 200
    add_logs([{'DeviceLogId': 6, 'DeviceId': 102, 'UserId': 'ACTIVATION', 'LogDate': activation + timedelta(seconds=90)}])
    assert run_synchronization_cycle()['synced_count'] == 0
    second = activation + timedelta(minutes=3)
    monkeypatch.setattr(state_history, 'local_now', lambda: second)
    assert client.put('/api/devices/102/status', json={'is_active': True}, headers=headers()).status_code == 200
    add_logs([{'DeviceLogId': sid, 'DeviceId': 102, 'UserId': 'ACTIVATION', 'LogDate': when}
              for sid, when in [(7, second - timedelta(seconds=1)), (8, second)]])
    assert run_synchronization_cycle()['synced_count'] == 1
    with TargetSessionLocal() as db:
        assert {row.SourceDeviceLogId for row in db.query(RawPunch)} == {2, 4, 5, 8}
        assert active_device_windows(db)[102] == second
    # Changing an active device's hostel or repeating active status must not reset its cutoff.
    monkeypatch.setattr(state_history, 'local_now', lambda: second + timedelta(minutes=1))
    assert client.put('/api/devices/102', json={'DeviceId': 102, 'DeviceName': 'Edited name', 'HostelId': 1, 'IsActive': True}, headers=headers()).status_code == 200
    assert client.put('/api/devices/102/status', json={'is_active': True}, headers=headers()).status_code == 200
    with TargetSessionLocal() as db:
        assert active_device_windows(db)[102] == second


def test_new_device_registration_imports_from_registration_time(monkeypatch):
    from backend.app.api import devices
    activation = local_now() - timedelta(minutes=10)
    monkeypatch.setattr(devices, 'local_now', lambda: activation)
    client = TestClient(app)
    assert client.post('/api/devices', json={'DeviceId': 999, 'DeviceName': 'New gate', 'HostelId': 1}, headers=headers()).status_code == 200
    add_logs([{'DeviceLogId': sid, 'DeviceId': 999, 'UserId': 'U1001', 'LogDate': when}
              for sid, when in [(1, activation - timedelta(seconds=1)), (2, activation)]])
    assert run_synchronization_cycle()['synced_count'] == 1
    with TargetSessionLocal() as db:
        assert [row.SourceDeviceLogId for row in db.query(RawPunch)] == [2]


def test_quarantine_cannot_bypass_activation_window():
    activation = local_now()
    with TargetSessionLocal() as db:
        db.add(DeviceStateHistory(DeviceId=101, HostelId=1, IsActive=True, EffectiveFrom=activation))
        item = QuarantinedPunch(SourceDeviceLogId=20, DeviceId=101, UserId='U1001', LogDate=activation - timedelta(seconds=1),
                                ErrorType='DATA_CORRUPTION', ErrorMessage='Test quarantine', ResolvedStatus='PENDING')
        db.add(item)
        db.commit()
        qid = item.QuarantineId
    result = TestClient(app).post(f'/api/system/quarantine/{qid}/reprocess', headers=headers())
    assert result.status_code == 409
    with TargetSessionLocal() as db:
        assert db.query(RawPunch).count() == 0
        assert db.get(QuarantinedPunch, qid).ResolvedStatus == 'PENDING'


def test_out_of_band_activation_is_not_silently_treated_as_healthy():
    with TargetSessionLocal() as db:
        db.add(DeviceStateHistory(DeviceId=101, HostelId=1, IsActive=False, EffectiveFrom=local_now()))
        db.commit()
    add_logs([{'DeviceLogId': 1, 'DeviceId': 101, 'UserId': 'U1001', 'LogDate': local_now()}])
    assert run_synchronization_cycle()['status'] == 'FAILED'
    with TargetSessionLocal() as db:
        assert db.query(RawPunch).count() == 0


def test_review_excludes_inactive_and_pre_activation_punches():
    from backend.app.services.recovery import new_scan, scan_missing
    from backend.app.core.database import SourceSessionLocal
    from sync_worker.sync_service import get_source_device_logs_table
    activation = local_now() - timedelta(minutes=5)
    with TargetSessionLocal() as db:
        db.get(Device, 102).IsActive = False
        db.add(DeviceStateHistory(DeviceId=101, HostelId=1, IsActive=True, EffectiveFrom=activation))
        db.add(SyncCheckpoint(SourceName='IT_SQL_SERVER', LastSourceDeviceLogId=4))
        db.commit()
    add_logs([{'DeviceLogId': sid, 'DeviceId': device, 'UserId': 'U1001', 'LogDate': when}
              for sid, device, when in [(1, 101, activation - timedelta(seconds=1)), (2, 102, activation),
                                        (3, 999, activation), (4, 101, activation)]])
    with TargetSessionLocal() as db, SourceSessionLocal() as source:
        from backend.app.core.time import business_day
        scan_id = new_scan(db, business_day(activation - timedelta(days=1)), business_day(activation), 'admin')
        scan = scan_missing(db, source, get_source_device_logs_table(), scan_id)
        assert scan.ScannedCount == 1 and scan.CandidateCount == 1
        from backend.app.models.review import RecoveryPunch
        assert db.query(RecoveryPunch).one().SourceDeviceLogId == 4
