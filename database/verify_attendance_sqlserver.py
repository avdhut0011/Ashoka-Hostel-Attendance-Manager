"""End-to-end worker concurrency and configurable user load on disposable SQL Server.

No production table or Epush connection is opened. Temporary database is removed.
"""
import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from sqlalchemy import create_engine, text, event, Engine
from sqlalchemy.engine import make_url


def configure(name, url):
    os.environ.update(APP_ENV='sqlserver_test', ISOLATED_TEST_DATABASE=name,
                      TARGET_DATABASE_URL=url.render_as_string(hide_password=False),
                      SOURCE_DATABASE_URL=url.render_as_string(hide_password=False), SOURCE_TABLE='TestDeviceLogs',
                      JWT_SECRET=secrets.token_hex(32))


def guard(name):
    @event.listens_for(Engine, 'before_cursor_execute')
    def reject_production(connection, cursor, statement, parameters, context, executemany):
        if connection.engine.url.database != name:
            raise PermissionError('Attendance verification may access only its disposable database')


def child(ready, release, query_probe=False):
    from backend.app.core.config import settings
    if settings.APP_ENV != 'sqlserver_test':
        raise RuntimeError('Child must use isolated test configuration')
    guard(settings.ISOLATED_TEST_DATABASE)
    from sync_worker import sync_service as worker
    original = worker.process_single_raw_punch
    seen = 0
    def paused(db, raw):
        nonlocal seen
        seen += 1
        if seen == 2:
            Path(ready).write_text('ready', encoding='utf-8')
            deadline = time.monotonic() + 25
            while not Path(release).exists():
                if time.monotonic() > deadline:
                    raise RuntimeError('Concurrency coordinator timed out')
                time.sleep(.05)
        return original(db, raw)
    if query_probe:
        original_query = worker.eligible_source_rows
        queried = False
        def paused_query(*args, **kwargs):
            nonlocal queried
            rows = original_query(*args, **kwargs)
            if rows and not queried:
                queried = True
                Path(ready).write_text('ready', encoding='utf-8')
                deadline = time.monotonic() + 25
                while not Path(release).exists():
                    if time.monotonic() > deadline:
                        raise RuntimeError('Source-query coordinator timed out')
                    time.sleep(.05)
            return rows
        worker.eligible_source_rows = paused_query
    else:
        worker.process_single_raw_punch = paused
    result = worker.run_synchronization_cycle(time_budget_seconds=45, batch_size=1)
    if result['status'] != 'SUCCESS':
        raise RuntimeError('Isolated child worker failed')


def verify(users=15):
    from backend.app.core.config import settings
    target = make_url(settings.get_target_db_url())
    if target.get_backend_name() != 'mssql' or target.database.lower() != 'hostelattendance' or target.host == '192.168.9.6':
        raise RuntimeError('Expected original HostelAttendance target, never Epush')
    name = 'HostelAttendance_Test_' + uuid.uuid4().hex
    master = create_engine(target.set(database='master'), isolation_level='AUTOCOMMIT', connect_args={'timeout': 10})
    created = False
    process = None
    results = {}
    failure = None
    ready = Path('database/migrations') / (name + '.ready')
    release = Path('database/migrations') / (name + '.release')
    engines = []
    try:
        with master.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE [{name}]')
            created = True
        test_url = target.set(database=name)
        # Configure the already-read settings before any application engine import.
        configure(name, test_url)
        settings.APP_ENV = 'sqlserver_test'
        settings.ISOLATED_TEST_DATABASE = name
        settings.TARGET_DATABASE_URL = os.environ['TARGET_DATABASE_URL']
        settings.SOURCE_DATABASE_URL = os.environ['SOURCE_DATABASE_URL']
        settings.SOURCE_TABLE = 'TestDeviceLogs'
        settings.JWT_SECRET = os.environ['JWT_SECRET']
        from backend.app.core.database import target_engine, source_engine, TargetSessionLocal
        engines.extend([target_engine, source_engine])
        # Engine-specific safety guards also protect any future accidental SQL.
        for engine in engines:
            @event.listens_for(engine, 'before_cursor_execute')
            def reject_production(connection, cursor, statement, parameters, context, executemany):
                if connection.engine.url.database != name:
                    raise PermissionError('Isolated verification may never access production')
        from backend.app.models import Base, Hostel, Device, Student, User, RawPunch, ProcessedPunch, StudentCurrentStatus, SyncCheckpoint
        from backend.app.models.attendance import AttendanceOverride
        from backend.app.core import security
        from backend.app.core.time import local_now, business_day
        from backend.app.core.locking import attendance_lock
        from backend.app.services.punch_processor import process_single_raw_punch, rebuild_student, apply_override
        from backend.app.services.change_events import change_marker
        from sync_worker import sync_service as worker
        with target_engine.begin() as connection:
            assert connection.execute(text('SELECT DB_NAME()')).scalar_one() == name
            for schema in ('master', 'integration', 'attendance', 'security', 'system'):
                connection.exec_driver_sql(f'CREATE SCHEMA [{schema}]')
            Base.metadata.create_all(connection)
            connection.exec_driver_sql('CREATE TABLE dbo.TestDeviceLogs (DeviceLogId BIGINT PRIMARY KEY, DeviceId INT, UserId VARCHAR(50), LogDate DATETIME, DownloadDate DATETIME NULL)')
        security.pwd_context.update(bcrypt__rounds=4)
        credentials = []
        with TargetSessionLocal() as db:
            db.add_all([Hostel(HostelName='Test A'), Hostel(HostelName='Test B')])
            db.flush()
            db.add_all([Device(DeviceId=101, DeviceName='Test A gate', HostelId=1), Device(DeviceId=102, DeviceName='Test B gate', HostelId=2)])
            for index in range(20):
                db.add(Student(UserId=f'TEST{index:02}', StudentName=f'Isolated student {index}', HostelId=1 if index < 10 else 2, RoomNo='1'))
            for index in range(50):
                role = ['ADMIN', 'IT_ADMIN', 'MANAGEMENT', 'WARDEN', 'WARDEN'][index % 5]
                hostel = (1 if index % 5 == 3 else 2) if role == 'WARDEN' else None
                username = f'load_{index:02}'
                password = secrets.token_urlsafe(18)
                db.add(User(Username=username, PasswordHash=security.get_password_hash(password), Role=role, HostelId=hostel))
                credentials.append((username, password, role, hostel))
            db.commit()
        today = business_day(local_now())
        base = datetime.combine(today, datetime.min.time())
        logs = []
        for index in range(20):
            # Arrival order intentionally differs from event order.
            for offset in (0, 7200, 3600, 7210):
                logs.append(dict(sid=len(logs) + 1, did=101 if index < 10 else 102,
                                 uid=f'TEST{index:02}', when=base + timedelta(seconds=offset)))
        with target_engine.begin() as connection:
            connection.execute(text('INSERT INTO dbo.TestDeviceLogs (DeviceLogId,DeviceId,UserId,LogDate) VALUES (:sid,:did,:uid,:when)'), logs)
        environment = os.environ.copy()
        process = subprocess.Popen([sys.executable, '-B', '-m', 'database.verify_attendance_sqlserver', '--child', str(ready), str(release)],
                                   env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 25
        while not ready.exists():
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise RuntimeError('Isolated worker exited before concurrency probe: ' + stderr[-2000:])
            if time.monotonic() > deadline:
                raise RuntimeError('Isolated worker did not reach the probe')
            time.sleep(.05)
        # Child has committed its first batch and still owns the sync lock.
        assert worker.run_synchronization_cycle()['status'] == 'IN_PROGRESS'
        results['sync_lock_protects_cycle_across_batch_commits_and_processes'] = 'passed'
        def reprocess_same():
            with TargetSessionLocal() as db:
                raw = db.query(RawPunch).filter_by(SourceDeviceLogId=1).one()
                process_single_raw_punch(db, raw)
                db.commit()
        with ThreadPoolExecutor(max_workers=2) as pool:
            concurrent = pool.submit(reprocess_same)
            release.write_text('release', encoding='utf-8')
            concurrent.result(timeout=35)
            stdout, stderr = process.communicate(timeout=45)
            assert process.returncode == 0, stderr[-2000:]
        process = None
        assert worker.run_synchronization_cycle()['status'] == 'SUCCESS'
        with TargetSessionLocal() as db:
            assert db.query(RawPunch).count() == 80 and db.query(ProcessedPunch).count() == 80
            assert db.query(SyncCheckpoint).one().LastSourceDeviceLogId == 80
            first = db.query(Student).filter_by(UserId='TEST00').one()
            first_id = first.StudentId
            timeline = db.query(ProcessedPunch).filter_by(StudentId=first_id).order_by(ProcessedPunch.LogDate).all()
            assert [(row.PunchType, row.ProcessingStatus) for row in timeline] == [('REGISTRATION', 'VALID'), ('IN', 'VALID'), ('OUT', 'VALID'), (None, 'DUPLICATE')]
            original_ids = {row.RawPunchId: row.PunchId for row in timeline}
            raw_values = [(row.SourceDeviceLogId, row.LogDate, row.UserId, row.DeviceId) for row in db.query(RawPunch).order_by(RawPunch.RawPunchId)]
        results['worker_reprocessing_idempotence_and_late_ordering'] = 'passed'
        def manual_override():
            with TargetSessionLocal() as db:
                with attendance_lock(db):
                    student = db.get(Student, first_id)
                    current = db.get(StudentCurrentStatus, first_id)
                    override = AttendanceOverride(StudentId=first_id, PreviousStatus=current.CurrentStatus, CurrentStatus='IN',
                        EffectiveAt=base + timedelta(hours=5), Reason='Isolated concurrency check', CreatedBy='load_00', HostelIdSnapshot=1, RoomNoSnapshot='1')
                    db.add(override)
                    apply_override(db, student, override)
                db.commit()
        def replay():
            with TargetSessionLocal() as db:
                rebuild_student(db, db.get(Student, first_id))
                db.commit()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(manual_override), pool.submit(replay)]
            for future in futures:
                future.result(timeout=30)
        with TargetSessionLocal() as db:
            assert db.get(StudentCurrentStatus, first_id).CurrentStatus == 'IN'
            assert db.query(AttendanceOverride).count() == 1
            assert original_ids == {row.RawPunchId: row.PunchId for row in db.query(ProcessedPunch).filter_by(StudentId=first_id)}
            assert raw_values == [(row.SourceDeviceLogId, row.LogDate, row.UserId, row.DeviceId) for row in db.query(RawPunch).order_by(RawPunch.RawPunchId)]
        results['manual_override_vs_replay_preserves_events_and_ids'] = 'passed'
        # Inject a transient failure after one record has been staged in a batch.
        with target_engine.begin() as connection:
            connection.execute(text('INSERT INTO dbo.TestDeviceLogs (DeviceLogId,DeviceId,UserId,LogDate) VALUES (:sid,101,\'TEST01\',:when)'),
                               [{'sid': 81, 'when': base + timedelta(hours=4)}, {'sid': 82, 'when': base + timedelta(hours=5)}])
        original = worker.process_single_raw_punch
        def fail_second(db, raw):
            if raw.SourceDeviceLogId == 82:
                raise RuntimeError('Isolated transient failure')
            return original(db, raw)
        worker.process_single_raw_punch = fail_second
        try:
            assert worker.run_synchronization_cycle(batch_size=500)['status'] == 'FAILED'
        finally:
            worker.process_single_raw_punch = original
        with TargetSessionLocal() as db:
            assert db.query(RawPunch).count() == 80
            assert db.query(SyncCheckpoint).one().LastSourceDeviceLogId == 80
        assert worker.run_synchronization_cycle(batch_size=500)['status'] == 'SUCCESS'
        results['failed_batch_rolls_back_and_retries_without_checkpoint_loss'] = 'passed'
        # TEST01 receives IN then OUT; expected location remains OUT.
        from fastapi.testclient import TestClient
        from backend.app.main import app
        import logging
        logging.getLogger('httpx').setLevel(logging.WARNING)
        latencies = []
        failures = []
        from threading import Barrier, Lock
        barrier = Barrier(users)
        metrics_lock = Lock()
        with TargetSessionLocal() as db:
            before_marker = change_marker(db)
            baseline = [(row.StudentId, row.CurrentStatus, row.LastPunchId, row.LastPunchTime) for row in db.query(StudentCurrentStatus).order_by(StudentCurrentStatus.StudentId)]
        def virtual_user(account):
            username, password, role, hostel = account
            with TestClient(app) as client:
                login = client.post('/api/auth/login', json={'username': username, 'password': password})
                assert login.status_code == 200, f'login status {login.status_code}'
                headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
                barrier.wait(timeout=30)
                for unused in range(3):
                    started = time.perf_counter()
                    summary = client.get('/api/dashboard/summary', headers=headers).json()
                    expected_total = 10 if role == 'WARDEN' else 20
                    expected_in = 0 if role == 'WARDEN' and hostel == 2 else 1
                    assert summary['total_students'] == expected_total, 'dashboard total'
                    assert summary['currently_in'] == expected_in and summary['currently_out'] == expected_total - expected_in, 'dashboard status counts'
                    students = client.get('/api/students?limit=100', headers=headers).json()
                    assert len(students) == expected_total, 'student page size'
                    if role == 'WARDEN':
                        assert all(row['HostelId'] == hostel for row in students)
                    for row in students:
                        assert row['CurrentStatus'] == ('IN' if row['UserId'] == 'TEST00' else 'OUT')
                        assert row['TodayValidPunchCount'] == (5 if row['UserId'] == 'TEST01' else 3)
                        assert row['TodayDuplicatePunchCount'] == 1
                    history = client.get('/api/attendance/history?limit=100', headers=headers).json()
                    expected_punches = 40 if role == 'WARDEN' and hostel == 2 else 42 if role == 'WARDEN' else 82
                    assert len(history) == expected_punches, 'history page size'
                    if role == 'WARDEN':
                        assert all(row['HostelId'] == hostel for row in history)
                    exported = client.get('/api/reports/export?export_format=csv', headers=headers)
                    retry_until = time.monotonic() + 30
                    while exported.status_code == 429 and time.monotonic() < retry_until:
                        time.sleep(.1)
                        exported = client.get('/api/reports/export?export_format=csv', headers=headers)
                    assert exported.status_code == 200, f'export status {exported.status_code} after bounded retry'
                    assert int(exported.headers['x-total-count']) == expected_punches + expected_in
                    permission = client.get('/api/users', headers=headers)
                    assert permission.status_code == (200 if role == 'ADMIN' else 403), f'account permission status {permission.status_code}'
                    with metrics_lock:
                        latencies.append((time.perf_counter() - started) * 1000)
        print(f'Checking {users} simultaneous users', flush=True)
        with ThreadPoolExecutor(max_workers=users) as pool:
            futures = [pool.submit(virtual_user, credentials[index]) for index in range(users)]
            for future in futures:
                try:
                    future.result(timeout=120)
                except Exception as error:
                    failures.append(type(error).__name__ + ': ' + str(error))
        assert not failures, failures[:5]
        with TargetSessionLocal() as db:
            assert baseline == [(row.StudentId, row.CurrentStatus, row.LastPunchId, row.LastPunchTime) for row in db.query(StudentCurrentStatus).order_by(StudentCurrentStatus.StudentId)]
            assert before_marker == change_marker(db)
        results[f'{users}_simultaneous_users_mixed_roles_attendance_exports_read_purity'] = 'passed'
        ordered = sorted(latencies)
        metrics = {'users': users, 'iterations_per_user': 3, 'correctness_iterations': len(latencies),
                   'mean_iteration_ms': round(mean(latencies), 1), 'p95_iteration_ms': round(ordered[int(len(ordered) * .95) - 1], 1)}
        from starlette.websockets import WebSocketDisconnect
        with TestClient(app) as client:
            with TargetSessionLocal() as db:
                admin = db.query(User).filter_by(Username='load_00').one()
                live_token = security.create_access_token({'sub': admin.Username, 'id': admin.SystemUserId, 'ver': 0})
            with client.websocket_connect('/api/dashboard/live') as socket:
                socket.send_json({'token': live_token})
                assert socket.receive_json() == {'type': 'ready'}
                assert socket.receive_json() == {'type': 'refresh'}
                with target_engine.begin() as connection:
                    connection.execute(text("INSERT INTO dbo.TestDeviceLogs (DeviceLogId,DeviceId,UserId,LogDate) VALUES (83,101,'TEST02',:when)"), {'when': base + timedelta(hours=6)})
                completed = subprocess.run([sys.executable, '-B', '-m', 'database.verify_attendance_sqlserver', '--sync-once'],
                    env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
                assert completed.returncode == 0, completed.stderr[-2000:]
                # A separate worker process committed; connected browser is notified.
                message = socket.receive_json()
                if message['type'] == 'heartbeat':
                    message = socket.receive_json()
                assert message == {'type': 'refresh'}
                with TargetSessionLocal() as db:
                    user = db.query(User).filter_by(Username='load_00').one()
                    user.TokenVersion = 1
                    db.get(Student, first_id).RoomNo = '2'
                    db.commit()
                try:
                    socket.receive_json()
                except WebSocketDisconnect as error:
                    assert error.code == 1008
                else:
                    raise AssertionError('Revoked live token was not rejected')
        results['cross_process_live_notification_and_token_revocation'] = 'passed'
        from backend.app.models import DeviceStateHistory
        from backend.app.services.device_ingestion import active_device_windows
        # Exactly 116 active devices: only matching IDs and their activation windows.
        activation = base + timedelta(hours=7)
        with TargetSessionLocal() as db:
            db.get(Device, 101).IsActive = False
            db.get(Device, 102).IsActive = False
            for index in range(116):
                db.add(Device(DeviceId=1000 + index, DeviceName=f'Isolated active {index}', HostelId=1))
            db.flush()
            for index in range(116):
                db.add(DeviceStateHistory(DeviceId=1000 + index, HostelId=1, IsActive=True,
                                         EffectiveFrom=activation + timedelta(seconds=index)))
            db.add(Device(DeviceId=2000, DeviceName='Activation race', HostelId=1, IsActive=False))
            db.flush()
            db.add(DeviceStateHistory(DeviceId=2000, HostelId=1, IsActive=False, EffectiveFrom=base))
            db.commit()
            assert len(active_device_windows(db)) == 116
        eligible = [dict(sid=84 + index, did=1000 + index, uid='TEST03', when=activation + timedelta(seconds=index)) for index in range(116)]
        excluded = [dict(sid=200, did=101, uid='TEST03', when=activation),
                    dict(sid=201, did=99999, uid='TEST03', when=activation),
                    dict(sid=202, did=1000, uid='TEST03', when=activation - timedelta(seconds=1)),
                    dict(sid=203, did=1000, uid='TEST03', when=activation)]
        with target_engine.begin() as connection:
            connection.execute(text('INSERT INTO dbo.TestDeviceLogs (DeviceLogId,DeviceId,UserId,LogDate) VALUES (:sid,:did,:uid,:when)'), eligible + excluded)
        assert worker.run_synchronization_cycle(batch_size=500)['synced_count'] == 117
        with TargetSessionLocal() as db:
            imported = db.query(RawPunch).filter(RawPunch.SourceDeviceLogId >= 84).all()
            assert len(imported) == 117 and {row.DeviceId for row in imported} == set(range(1000, 1116))
            assert not db.query(RawPunch).filter(RawPunch.SourceDeviceLogId.in_([200, 201, 202])).count()
            assert db.query(SyncCheckpoint).one().LastSourceDeviceLogId == 203
        results['116_active_device_ids_only_and_individual_activation_cutoffs'] = 'passed'
        # Pause a real source query while its device-status lock is still held.
        ready.unlink()
        release.unlink()
        with target_engine.begin() as connection:
            connection.execute(text('INSERT INTO dbo.TestDeviceLogs (DeviceLogId,DeviceId,UserId,LogDate) VALUES (:sid,:did,\'TEST04\',:when)'),
                               [{'sid': 204, 'did': 1000, 'when': activation + timedelta(minutes=2)},
                                {'sid': 205, 'did': 2000, 'when': local_now() - timedelta(minutes=5)}])
        process = subprocess.Popen([sys.executable, '-B', '-m', 'database.verify_attendance_sqlserver', '--query-probe', str(ready), str(release)],
                                   env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 25
        while not ready.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Query probe did not become ready')
            time.sleep(.05)
        def activate_during_query():
            from backend.app.api.devices import update_device_status, DeviceStatusUpdate
            with TargetSessionLocal() as db:
                admin = db.query(User).filter_by(Username='load_00').one()
                return update_device_status(2000, DeviceStatusUpdate(is_active=True), db, admin)
        with ThreadPoolExecutor(max_workers=1) as pool:
            activation_request = pool.submit(activate_during_query)
            time.sleep(.2)
            assert not activation_request.done(), 'Device status changed during an in-flight source query'
            release.write_text('release', encoding='utf-8')
            activation_request.result(timeout=30)
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, stderr[-2000:]
        process = None
        with TargetSessionLocal() as db:
            cutoff = active_device_windows(db)[2000]
            assert cutoff is not None
        with target_engine.begin() as connection:
            connection.execute(text("INSERT INTO dbo.TestDeviceLogs (DeviceLogId,DeviceId,UserId,LogDate) VALUES (206,2000,'TEST04',:when)"), {'when': cutoff})
        assert worker.run_synchronization_cycle()['synced_count'] == 1
        with TargetSessionLocal() as db:
            assert db.query(RawPunch).filter_by(SourceDeviceLogId=205).count() == 0
            assert db.query(RawPunch).filter_by(SourceDeviceLogId=206).count() == 1
        results['activation_during_sync_is_serialized_and_only_new_period_imported'] = 'passed'
        # The million-row benchmark previously had only 1,000 rows per student.
        # Verify actual replay beyond the SQL Server parameter ceiling.
        with TargetSessionLocal() as db:
            long_student = Student(UserId='LONG_REPLAY', StudentName='Disposable long history', HostelId=1, RoomNo='1')
            db.add(long_student)
            db.commit()
            long_sid = long_student.StudentId
        history_start = base - timedelta(days=3)
        with target_engine.begin() as connection:
            connection.execute(text('''WITH numbers(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM numbers WHERE n<2105)
                INSERT integration.RawPunches (SourceDeviceLogId,DeviceId,UserId,LogDate,ReceivedAt)
                SELECT 1000000+n,101,'LONG_REPLAY',DATEADD(minute,n,:start),GETUTCDATE() FROM numbers OPTION (MAXRECURSION 0)'''), {'start': history_start})
            connection.execute(text('''INSERT attendance.ProcessedPunches
                (RawPunchId,StudentId,UserId,DeviceId,LogDate,PunchType,ProcessingStatus,IsFirstEverPunch,IsFirstValidPunchOfDay,ProcessedAt,HostelIdSnapshot,RoomNoSnapshot)
                SELECT RawPunchId,:sid,UserId,DeviceId,LogDate,'IN','VALID',0,0,GETUTCDATE(),1,'1'
                FROM integration.RawPunches WHERE UserId='LONG_REPLAY' '''), {'sid': long_sid})
        print('Checking 2105-punch chronological replay', flush=True)
        with TargetSessionLocal() as db:
            before_ids = {row[0] for row in db.query(ProcessedPunch.PunchId).filter_by(StudentId=long_sid)}
            replay_started = time.perf_counter()
            rebuild_student(db, db.get(Student, long_sid))
            db.commit()
            replay_seconds = round(time.perf_counter() - replay_started, 2)
            assert before_ids == {row[0] for row in db.query(ProcessedPunch.PunchId).filter_by(StudentId=long_sid)}
            assert len(before_ids) == 2105
            assert db.get(StudentCurrentStatus, long_sid).CurrentStatus == 'OUT'
            assert db.query(ProcessedPunch).filter_by(StudentId=long_sid, ProcessingStatus='REPLAY_PENDING').count() == 0
        results['2105_punch_student_replay_preserves_ids_and_sequence'] = {'status': 'passed', 'seconds': replay_seconds}
    except Exception as error:
        failure = {'status': 'failed', 'users': users, 'checks': results,
                   'error': type(error).__name__ + ': ' + str(error)}
        raise
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate()
        for engine in engines:
            engine.dispose()
        for path in (ready, release):
            if path.exists():
                path.unlink()
        if created:
            assert name.startswith('HostelAttendance_Test_') and len(name) == 54
            with master.connect() as connection:
                connection.exec_driver_sql(f'ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
                connection.exec_driver_sql(f'DROP DATABASE [{name}]')
        master.dispose()
        if failure is not None:
            failure.update(test_database=name, temporary_database_removed=created,
                           production_data_accessed=False, source_connected=False,
                           verified_at_utc=datetime.now(timezone.utc).isoformat())
            Path(f'database/migrations/attendance_sqlserver_{users}_users_failed_receipt.json').write_text(
                json.dumps(failure, indent=2), encoding='utf-8')
    receipt = {'test_database': name, 'temporary_database_removed': True, 'production_data_accessed': False,
               'source_connected': False, 'checks': results, 'load_metrics': metrics,
               'verified_at_utc': datetime.now(timezone.utc).isoformat()}
    Path('database/migrations/attendance_sqlserver_test_receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', nargs=2)
    parser.add_argument('--query-probe', nargs=2)
    parser.add_argument('--sync-once', action='store_true')
    parser.add_argument('--users', type=int, default=15, choices=range(1, 51))
    args = parser.parse_args()
    if args.child:
        child(*args.child)
    elif args.query_probe:
        child(*args.query_probe, query_probe=True)
    elif args.sync_once:
        from backend.app.core.config import settings
        if settings.APP_ENV != 'sqlserver_test':
            raise RuntimeError('Worker probe requires the disposable test environment')
        guard(settings.ISOLATED_TEST_DATABASE)
        from sync_worker.sync_service import run_synchronization_cycle
        assert run_synchronization_cycle()['status'] == 'SUCCESS'
    else:
        verify(args.users)
