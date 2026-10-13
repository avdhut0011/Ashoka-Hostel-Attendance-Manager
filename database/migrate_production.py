"""Target-only, idempotent schema migration. Never imports application engines.

Usage: python -m database.migrate_production --inspect
       python -m database.migrate_production --apply
No INSERT, UPDATE, DELETE, MERGE, seed, backfill, or attendance replay is executed.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateTable, CreateIndex
from backend.app.core.config import settings
from backend.app.models import Base

NEW_TABLES = ['integration.QuarantinedPunches', 'integration.PunchCorrections',
              'attendance.AttendanceOverrides', 'master.StudentStateHistory', 'master.DeviceStateHistory',
              'integration.RecoveryScans', 'integration.RecoveryPunches', 'master.VerifiedRoomChanges', 'system.AttendanceChanges',
              'system.AttendanceRevision', 'security.LoginThrottle', 'security.RevokedTokens', 'security.SecurityAudit']
COLUMNS = {
    'master.Students': {'EnrolledAt': 'DATETIME NULL'},
    'attendance.ProcessedPunches': {'HostelIdSnapshot': 'INT NULL', 'RoomNoSnapshot': 'VARCHAR(50) NULL'},
    'attendance.StudentCurrentStatus': {'CounterDate': 'DATE NULL'},
    'security.Users': {'TokenVersion': 'INT NULL'},
}


def counts(connection):
    names = connection.execute(text("SELECT s.name, t.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id")).all()
    return {f'{schema}.{name}': connection.execute(text(f'SELECT COUNT_BIG(*) FROM [{schema.replace("]", "]]")}].[{name.replace("]", "]]")}]')).scalar()
            for schema, name in names if schema in ('master', 'attendance', 'integration', 'security', 'system')}


def migrate(apply=False):
    url = make_url(settings.get_target_db_url())
    if url.get_backend_name() != 'mssql' or (url.database or '').lower() != 'hostelattendance':
        raise RuntimeError('Migration requires the HostelAttendance SQL Server target')
    if (url.host or '').lower() == '192.168.9.6' or url == make_url(settings.get_source_db_url()):
        raise RuntimeError('Production source connection is explicitly forbidden')
    engine = create_engine(url, connect_args={'timeout': 10}, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            name = connection.execute(text('SELECT DB_NAME()')).scalar()
            if name != 'HostelAttendance':
                raise RuntimeError('Connected database is not HostelAttendance')
            if apply:
                connection.execute(text('SET XACT_ABORT ON; SET LOCK_TIMEOUT 15000;'))
                for resource in ('HostelAttendanceSyncLock', 'HostelAttendance:timeline', 'HostelAttendance:accounts'):
                    code = connection.execute(text("""
                        SET NOCOUNT ON; DECLARE @r INT;
                        EXEC @r=sp_getapplock @Resource=:resource, @LockMode='Exclusive',
                            @LockOwner='Transaction', @LockTimeout=15000;
                        SELECT @r;
                    """), {'resource': resource}).scalar()
                    if code is None or code < 0:
                        raise RuntimeError('Target is busy; schema migration rolled back without changing data')
            before = counts(connection)
            required = set(COLUMNS)
            if not required.issubset(before):
                raise RuntimeError('Existing application tables are missing; migration will not seed or initialize production')
            duplicates = connection.execute(text('SELECT COUNT_BIG(*) FROM (SELECT RawPunchId FROM attendance.ProcessedPunches GROUP BY RawPunchId HAVING COUNT_BIG(*) > 1) d')).scalar()
            if duplicates:
                raise RuntimeError(f'{duplicates} duplicate processed-punch groups require review; no records were removed')
            statements = []
            for table, columns in COLUMNS.items():
                for column, ddl in columns.items():
                    if connection.execute(text('SELECT COL_LENGTH(:table, :column)'), {'table': table, 'column': column}).scalar() is None:
                        statements.append(f'ALTER TABLE {table} ADD {column} {ddl}')
            for key in NEW_TABLES:
                if key not in before:
                    statements.append(str(CreateTable(Base.metadata.tables[key]).compile(dialect=engine.dialect)))
            # Add indexes through metadata; existing indexes are preserved.
            for table in Base.metadata.sorted_tables:
                for index in sorted(table.indexes, key=lambda i: i.name):
                    exists = connection.execute(text('SELECT COUNT(*) FROM sys.indexes WHERE object_id=OBJECT_ID(:table) AND name=:name'),
                        {'table': table.fullname, 'name': index.name}).scalar()
                    if not exists:
                        statements.append(str(CreateIndex(index).compile(dialect=engine.dialect)))
            if apply:
                for statement in statements:
                    connection.execute(text(statement))
                after = counts(connection)
                if any(after.get(table) != count for table, count in before.items()):
                    raise RuntimeError('Existing row counts changed; transaction rolled back')
                if any(after[table] != 0 for table in after.keys() - before.keys()):
                    raise RuntimeError('A new table contains data; transaction rolled back')
            else:
                after = before
        receipt = {'database': name, 'server': url.host, 'applied': apply,
                   'schema_statements': len(statements), 'existing_row_counts': before,
                   'new_empty_tables': sorted(after.keys() - before.keys()),
                   'verified_at_utc': datetime.now(timezone.utc).isoformat()}
        output = Path(__file__).parent / 'migrations'
        output.mkdir(exist_ok=True)
        suffix = 'applied' if apply else 'inspection'
        (output / (datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_') + suffix + '.json')).write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        (output / ('latest_' + suffix + '.json')).write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        if statements:
            # Inspection artifact only. The runner rechecks schema and locks transactionally.
            (output / (datetime.now(timezone.utc).strftime('%Y%m%d') + '_schema.sql')).write_text("-- Use python -m database.migrate_production --apply to execute with transactional checks.\nIF DB_NAME() <> N'HostelAttendance' THROW 51000, 'Wrong target database', 1;\n" + '\nGO\n'.join(statements), encoding='utf-8')
        print(json.dumps(receipt, indent=2))
    finally:
        engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--inspect', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    migrate(args.apply)
