"""Million-row API benchmark. Writes only to a generated disposable SQL Server database."""
import argparse
import csv
import io
import json
import logging
import os
import secrets
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from threading import Barrier
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from database.verify_attendance_sqlserver import configure


def run(users=15):
    if not 1 <= users <= 50:
        raise ValueError('User count must be between 1 and 50')
    from backend.app.core.config import settings
    target = make_url(settings.get_target_db_url())
    if target.get_backend_name() != 'mssql' or target.database.lower() != 'hostelattendance' or target.host == '192.168.9.6':
        raise RuntimeError('Expected target SQL Server; Epush is prohibited')
    name = 'HostelAttendance_Test_' + uuid.uuid4().hex
    master = create_engine(target.set(database='master'), isolation_level='AUTOCOMMIT', connect_args={'timeout': 10})
    engines, created = [], False
    receipt = {'database': name, 'production_data_accessed': False, 'epush_connected': False,
               'synthetic_attendance_rows': 1000000, 'synthetic_students': 1000,
               'concurrent_users': users, 'planned_concurrent_requests': users * 9, 'checks': {}, 'metrics': {}}
    started = time.perf_counter()
    def progress(message):
        print(message, flush=True)
    try:
        with master.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE [{name}]')
            created = True
        configure(name, target.set(database=name))
        settings.APP_ENV = 'sqlserver_test'
        settings.ISOLATED_TEST_DATABASE = name
        settings.TARGET_DATABASE_URL = os.environ['TARGET_DATABASE_URL']
        settings.SOURCE_DATABASE_URL = os.environ['SOURCE_DATABASE_URL']
        settings.SOURCE_TABLE = 'TestDeviceLogs'
        settings.JWT_SECRET = os.environ['JWT_SECRET']
        from backend.app.core.database import target_engine, source_engine, TargetSessionLocal
        engines.extend([target_engine, source_engine])
        for engine in engines:
            @event.listens_for(engine, 'before_cursor_execute')
            def protect(connection, cursor, statement, parameters, context, executemany):
                if connection.engine.url.database != name:
                    raise PermissionError('Benchmark may access only generated test database')
        from backend.app.models import Base, Hostel, Device, Student, User
        from backend.app.core import security
        from backend.app.services.change_events import change_marker
        security.pwd_context.update(bcrypt__rounds=4)
        with target_engine.begin() as connection:
            assert connection.execute(text('SELECT DB_NAME()')).scalar_one() == name
            for schema in ('master', 'integration', 'attendance', 'security', 'system'):
                connection.exec_driver_sql(f'CREATE SCHEMA [{schema}]')
            Base.metadata.create_all(connection)
        tokens = []
        with TargetSessionLocal() as db:
            db.add_all([Hostel(HostelName='Synthetic A'), Hostel(HostelName='Synthetic B')])
            db.flush()
            db.add_all([Device(DeviceId=101, DeviceName='Synthetic gate A', HostelId=1), Device(DeviceId=102, DeviceName='Synthetic gate B', HostelId=2)])
            db.add_all([Student(UserId=f'BENCH{i:04}', StudentName=f'Synthetic student {i}', HostelId=1 if i <= 500 else 2, RoomNo='1') for i in range(1, 1001)])
            for i in range(users):
                role = 'WARDEN' if i % 2 else 'ADMIN'
                user = User(Username=f'benchmark_{i}', PasswordHash=security.get_password_hash(secrets.token_hex(16)), Role=role, HostelId=1 if role == 'WARDEN' else None)
                db.add(user)
                db.flush()
                tokens.append((security.create_access_token({'sub': user.Username, 'id': user.SystemUserId, 'ver': 0}), role))
            db.commit()
        progress('Created isolated schema and 1,000 synthetic students. Seeding 1,000,000 attendance rows...')
        seed_start = time.perf_counter()
        with target_engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE dbo.BenchmarkNumbers (n INT PRIMARY KEY)')
        # Small committed fixture batches avoid a million-row sort/memory grant.
        # Application requests retain the ordinary runtime timeouts and limits.
        for offset in range(0, 1000000, 10000):
            with target_engine.begin() as connection:
                connection.execute(text('''WITH digits(v) AS (SELECT v FROM (VALUES(0),(1),(2),(3),(4),(5),(6),(7),(8),(9)) a(v))
                    INSERT dbo.BenchmarkNumbers SELECT :offset+1+a.v+10*b.v+100*c.v+1000*d.v
                    FROM digits a CROSS JOIN digits b CROSS JOIN digits c CROSS JOIN digits d'''), {'offset': offset})
                connection.execute(text('''INSERT integration.RawPunches (SourceDeviceLogId,DeviceId,UserId,LogDate,ReceivedAt)
                SELECT n,CASE WHEN (n-1)%1000<500 THEN 101 ELSE 102 END,
                'BENCH'+RIGHT('0000'+CAST(1+(n-1)%1000 AS VARCHAR(4)),4),
                DATEADD(minute,(n-1)/1000,'2024-01-01'),GETUTCDATE() FROM dbo.BenchmarkNumbers
                WHERE n>:offset AND n<=:end'''), {'offset': offset, 'end': offset+10000})
                connection.execute(text('''INSERT attendance.ProcessedPunches
                (RawPunchId,StudentId,UserId,DeviceId,LogDate,PunchType,ProcessingStatus,IsFirstEverPunch,IsFirstValidPunchOfDay,ProcessedAt,HostelIdSnapshot,RoomNoSnapshot)
                SELECT RawPunchId,1+(SourceDeviceLogId-1)%1000,UserId,DeviceId,LogDate,
                CASE WHEN ((SourceDeviceLogId-1)/1000)%2=0 THEN 'IN' ELSE 'OUT' END,'VALID',0,0,GETUTCDATE(),
                CASE WHEN DeviceId=101 THEN 1 ELSE 2 END,'1' FROM integration.RawPunches
                WHERE SourceDeviceLogId>:offset AND SourceDeviceLogId<=:end'''), {'offset': offset, 'end': offset+10000})
            if (offset+10000) % 100000 == 0:
                progress(f'Seeded {offset+10000:,} synthetic rows')
        with target_engine.begin() as connection:
            connection.exec_driver_sql('''INSERT attendance.StudentCurrentStatus
                (StudentId,CurrentStatus,TodayInCount,TodayOutCount,TodayValidPunchCount,TodayDuplicatePunchCount,UpdatedAt)
                SELECT StudentId,'OUT',0,0,0,0,GETUTCDATE() FROM master.Students''')
            connection.exec_driver_sql('UPDATE STATISTICS attendance.ProcessedPunches WITH FULLSCAN')
            assert connection.exec_driver_sql('SELECT COUNT_BIG(*) FROM attendance.ProcessedPunches').scalar_one() == 1000000
        receipt['metrics']['seed_seconds'] = round(time.perf_counter()-seed_start, 2)
        from fastapi.testclient import TestClient
        from backend.app.main import app
        logging.getLogger('httpx').setLevel(logging.WARNING)
        headers = {'Authorization': 'Bearer ' + tokens[0][0]}
        timings = {}
        with TargetSessionLocal() as db:
            marker = change_marker(db)
            last_page_ids = set(db.execute(text('SELECT TOP (100) PunchId FROM attendance.ProcessedPunches ORDER BY LogDate ASC, PunchId ASC')).scalars())
        with TestClient(app) as client:
            for label, route, expected_total, expected_length in [
                ('first_page', '/api/punches/processed?limit=100', 1000000, 100),
                ('middle_page', '/api/punches/processed?skip=500000&limit=100', 1000000, 100),
                ('last_page', '/api/punches/processed?skip=999900&limit=100', 1000000, 100),
                ('past_last_page', '/api/punches/processed?skip=1000000&limit=100', 1000000, 0),
                ('student_filter', '/api/punches/processed?user_id=BENCH0001&limit=100', 1000, 100),
                ('date_filter', '/api/reports/date-range?start_date=2024-01-01&end_date=2024-01-01&limit=100', 1000000, 100),
            ]:
                t = time.perf_counter()
                response = client.get(route, headers=headers)
                timings[label] = round((time.perf_counter()-t)*1000, 1)
                assert response.status_code == 200, (label, response.status_code, response.text[:300])
                assert int(response.headers['x-total-count']) == expected_total
                rows = response.json()
                assert len(rows) == expected_length
                if label == 'last_page':
                    assert {row['PunchId'] for row in rows} == last_page_ids
                if label == 'student_filter':
                    assert all(row['UserId'] == 'BENCH0001' for row in rows)
                receipt['checks'][label] = 'passed'
                progress(f'{label}: passed, {timings[label]} ms')
            progress('Testing full one-million-row CSV export; checking every exported event ID...')
            t = time.perf_counter()
            response = client.get('/api/reports/export?export_format=csv', headers=headers)
            assert response.status_code == 200
            assert int(response.headers['x-total-count']) == 1000000
            reader = csv.reader(io.StringIO(response.content.decode('utf-8-sig')))
            next(reader)
            count, seen = 0, bytearray(1000001)
            for row in reader:
                identity = int(row[0])
                assert 1 <= identity <= 1000000 and not seen[identity]
                seen[identity] = 1
                count += 1
            assert count == 1000000 and all(seen[1:])
            receipt['checks']['full_csv_every_event_once'] = 'passed'
            receipt['metrics']['full_csv_seconds_including_validation'] = round(time.perf_counter()-t, 2)
            receipt['metrics']['csv_bytes'] = len(response.content)
            del response, reader, seen
            progress(f'Full CSV verified. Starting {users} simultaneous users, three rounds each...')
        barrier = Barrier(users)
        def virtual_user(account):
            token, role = account
            h = {'Authorization': 'Bearer ' + token}
            values = []
            with TestClient(app) as client:
                barrier.wait(timeout=60)
                for iteration in range(3):
                    for label, route in [('punch_page', f'/api/punches/processed?skip={iteration*100000}&limit=100'),
                                         ('dashboard', '/api/dashboard/summary'), ('students', '/api/students?limit=100')]:
                        t = time.perf_counter()
                        response = client.get(route, headers=h)
                        elapsed = (time.perf_counter()-t)*1000
                        assert response.status_code == 200, (label, response.status_code)
                        rows = response.json()
                        if label == 'punch_page':
                            assert len(rows) == 100
                            assert int(response.headers['x-total-count']) == (500000 if role == 'WARDEN' else 1000000)
                            if role == 'WARDEN':
                                assert all(row['HostelIdSnapshot'] == 1 for row in rows)
                        elif label == 'dashboard':
                            assert rows['total_students'] == (500 if role == 'WARDEN' else 1000)
                        else:
                            assert len(rows) == 100 and all(row['TodayValidPunchCount'] == 0 for row in rows)
                        values.append((label, elapsed))
            return values
        t = time.perf_counter()
        with ThreadPoolExecutor(max_workers=users) as pool:
            all_values = list(pool.map(virtual_user, tokens))
        receipt['metrics']['concurrent_wall_seconds'] = round(time.perf_counter()-t, 2)
        for label in ('punch_page', 'dashboard', 'students'):
            values = sorted(v for group in all_values for kind, v in group if kind == label)
            receipt['metrics'][label] = {'requests': len(values), 'mean_ms': round(mean(values), 1),
                                        'p95_ms': round(values[int(len(values)*.95)-1], 1), 'max_ms': round(max(values), 1)}
        receipt['checks'][f'{users}_users_{users * 9}_requests_permissions_counts'] = 'passed'
        with TargetSessionLocal() as db:
            assert marker == change_marker(db)
            assert db.execute(text('SELECT COUNT_BIG(*) FROM attendance.ProcessedPunches')).scalar_one() == 1000000
            assert db.execute(text('SELECT COUNT_BIG(*) FROM integration.RawPunches')).scalar_one() == 1000000
        receipt['checks']['reads_preserve_records_and_change_marker'] = 'passed'
        receipt['status'] = 'passed'
    except Exception as error:
        receipt['status'] = 'failed'
        receipt['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        for engine in engines:
            engine.dispose()
        if created:
            assert name.startswith('HostelAttendance_Test_') and len(name) == 54
            with master.connect() as connection:
                connection.exec_driver_sql(f'ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
                connection.exec_driver_sql(f'DROP DATABASE [{name}]')
            receipt['temporary_database_removed'] = True
        master.dispose()
        receipt['elapsed_seconds'] = round(time.perf_counter()-started, 2)
        receipt['metrics']['sequential_requests_ms'] = timings if 'timings' in locals() else {}
        receipt['verified_at_utc'] = datetime.now(timezone.utc).isoformat()
        receipt_path = f'database/migrations/million_rows_{users}_users_receipt.json'
        Path(receipt_path).write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(receipt, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--users', type=int, default=15, choices=range(1, 51))
    run(parser.parse_args().users)
