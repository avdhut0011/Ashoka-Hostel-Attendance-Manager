"""Read-only target preflight; never starts synchronization or connects to Epush."""
from sqlalchemy import create_engine, text
from backend.app.core.config import settings

def run_health_check():
    engine = create_engine(settings.get_target_db_url(), connect_args={'timeout': 10})
    try:
        with engine.connect() as connection:
            if connection.execute(text('SELECT DB_NAME()')).scalar() != 'HostelAttendance':
                raise RuntimeError('Wrong target database')
            required = [('master.Students', 'EnrolledAt'), ('attendance.ProcessedPunches', 'HostelIdSnapshot'),
                        ('attendance.StudentCurrentStatus', 'CounterDate'), ('security.Users', 'TokenVersion')]
            for table, column in required:
                if connection.execute(text('SELECT COL_LENGTH(:table, :column)'), {'table': table, 'column': column}).scalar() is None:
                    raise RuntimeError('Target schema migration is required')
            for table in ('system.AttendanceRevision', 'security.LoginThrottle', 'security.RevokedTokens', 'security.SecurityAudit', 'integration.RecoveryScans', 'integration.RecoveryPunches', 'master.VerifiedRoomChanges'):
                if connection.execute(text('SELECT OBJECT_ID(:table)'), {'table': table}).scalar() is None:
                    raise RuntimeError('Target recovery/live-update schema migration is required')
        print('HostelAttendance target connection and schema verified. Source was not contacted.')
    finally:
        engine.dispose()

if __name__ == '__main__':
    run_health_check()
