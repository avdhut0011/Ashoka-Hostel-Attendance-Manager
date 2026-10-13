"""Write tests ONLY in a uniquely named disposable database; never connects to Epush.

Run: python -B -m database.verify_sqlserver
Requires CREATE DATABASE permission on the target SQL Server.
"""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.locking import attendance_lock


def verify():
    target = make_url(settings.get_target_db_url())
    if target.get_backend_name() != 'mssql' or (target.database or '').lower() != 'hostelattendance':
        raise RuntimeError('Expected the configured HostelAttendance target')
    if (target.host or '').lower() == '192.168.9.6':
        raise RuntimeError('Source server is forbidden')
    name = 'HostelAttendance_Test_' + uuid.uuid4().hex
    master = create_engine(target.set(database='master'), isolation_level='AUTOCOMMIT', connect_args={'timeout': 10})
    isolated = None
    created = False
    results = {}
    try:
        with master.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE [{name}]')
            created = True
        isolated = create_engine(target.set(database=name), connect_args={'timeout': 10})
        with isolated.begin() as connection:
            if connection.execute(text('SELECT DB_NAME()')).scalar() != name:
                raise RuntimeError('Isolation check failed')
            connection.exec_driver_sql('CREATE TABLE dbo.ConcurrencyProbe (Id INT PRIMARY KEY, Value INT NOT NULL)')
            connection.exec_driver_sql('INSERT INTO dbo.ConcurrencyProbe VALUES (1, 0)')
            connection.exec_driver_sql('CREATE TABLE dbo.PunchProbe (Id INT IDENTITY PRIMARY KEY, RawPunchId BIGINT NOT NULL UNIQUE)')
        barrier = Barrier(4)
        def increment(_):
            barrier.wait(timeout=15)
            for unused in range(10):
                with Session(isolated) as db:
                    with attendance_lock(db):
                        value = db.execute(text('SELECT Value FROM dbo.ConcurrencyProbe WHERE Id=1')).scalar_one()
                        db.execute(text('UPDATE dbo.ConcurrencyProbe SET Value=:value WHERE Id=1'), {'value': value + 1})
                    db.commit()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(increment, range(4)))
        with isolated.connect() as connection:
            value = connection.execute(text('SELECT Value FROM dbo.ConcurrencyProbe WHERE Id=1')).scalar_one()
        assert value == 40, f'Lost concurrent updates: {value}'
        results['transaction_lock_concurrent_increments'] = 'passed'
        def same_punch(_):
            with Session(isolated) as db:
                with attendance_lock(db):
                    exists = db.execute(text('SELECT COUNT(*) FROM dbo.PunchProbe WHERE RawPunchId=42')).scalar_one()
                    if not exists:
                        db.execute(text('INSERT INTO dbo.PunchProbe (RawPunchId) VALUES (42)'))
                db.commit()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(same_punch, range(12)))
        with isolated.connect() as connection:
            assert connection.execute(text('SELECT COUNT(*) FROM dbo.PunchProbe')).scalar_one() == 1
        results['concurrent_unique_punch'] = 'passed'
        with Session(isolated) as db:
            with attendance_lock(db):
                db.execute(text('UPDATE dbo.ConcurrencyProbe SET Value=999 WHERE Id=1'))
            db.rollback()
        with isolated.connect() as connection:
            assert connection.execute(text('SELECT Value FROM dbo.ConcurrencyProbe WHERE Id=1')).scalar_one() == 40
        results['rollback_preserves_committed_state'] = 'passed'
    finally:
        if isolated is not None:
            isolated.dispose()
        if created:
            # Name is locally generated, never accepted from configuration or CLI.
            assert name.startswith('HostelAttendance_Test_') and len(name) == 54
            with master.connect() as connection:
                connection.exec_driver_sql(f'ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
                connection.exec_driver_sql(f'DROP DATABASE [{name}]')
        master.dispose()
    receipt = {'test_database': name, 'production_data_accessed': False,
               'source_connected': False, 'temporary_database_removed': True,
               'checks': results, 'verified_at_utc': datetime.now(timezone.utc).isoformat()}
    Path('database/migrations/sqlserver_test_receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    verify()
