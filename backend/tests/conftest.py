"""All tests use disposable in-memory databases; SQL Server connections are forbidden."""
import os
import secrets
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
os.environ.update(APP_ENV='test', TARGET_DATABASE_URL='sqlite:///:memory:',
                  SOURCE_DATABASE_URL='sqlite:///:memory:', SOURCE_TABLE='DeviceLogs',
                  JWT_SECRET=secrets.token_hex(32))

import pytest
from sqlalchemy import event, Engine, Table, MetaData, Column, Integer, String, DateTime

@event.listens_for(Engine, 'do_connect')
def forbid_production_test_connections(dialect, connection_record, args, kwargs):
    if dialect.name != 'sqlite':
        raise RuntimeError('Tests may never connect to SQL Server or production')

from backend.app.core.database import target_engine, source_engine, TargetSessionLocal
from backend.app.models import Base, Hostel, Device, Student, User
from backend.app.core import security
security.pwd_context.update(bcrypt__rounds=4)

source_metadata = MetaData()
logs = Table('DeviceLogs', source_metadata, Column('DeviceLogId', Integer, primary_key=True),
    Column('DownloadDate', DateTime), Column('DeviceId', Integer), Column('UserId', String(100)), Column('LogDate', DateTime))

@pytest.fixture(autouse=True)
def isolated_databases():
    from backend.app.core.login_limit import _attempts
    _attempts.clear()
    Base.metadata.drop_all(target_engine)
    Base.metadata.create_all(target_engine)
    source_metadata.drop_all(source_engine)
    source_metadata.create_all(source_engine)
    with TargetSessionLocal() as db:
        a = Hostel(HostelName='Boys Hostel', HostelCode='HA-BOYS')
        b = Hostel(HostelName='Girls Hostel', HostelCode='HB-GIRLS')
        db.add_all([a, b])
        db.flush()
        for username, role, hostel_id, password in [
            ('admin', 'ADMIN', None, 'admin123password'),
            ('warden_a', 'WARDEN', a.HostelId, 'wardenpassword'),
            ('it_admin', 'IT_ADMIN', None, 'itadminpassword'),
            ('mgmt_test', 'MANAGEMENT', None, 'managementpassword'),
            ('it_admin_test', 'IT_ADMIN', None, 'pass123'),
            ('warden_boys', 'WARDEN', a.HostelId, 'wardenpassword')]:
            db.add(User(Username=username, Role=role, HostelId=hostel_id, PasswordHash=security.get_password_hash(password)))
        db.add_all([Device(DeviceId=101, DeviceName='Boys Gate', HostelId=a.HostelId),
                    Device(DeviceId=102, DeviceName='Girls Gate', HostelId=b.HostelId),
                    Student(UserId='U1001', StudentName='Seeded Test Student', HostelId=a.HostelId)])
        db.commit()
    yield
