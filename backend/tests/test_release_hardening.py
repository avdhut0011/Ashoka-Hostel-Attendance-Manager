from hashlib import sha256
from datetime import datetime, timedelta
import jwt
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.database import TargetSessionLocal
from backend.app.core.security import create_access_token, get_password_hash, verify_password
from backend.app.core.config import settings
from backend.app.core.safe_paths import safe_request_path
from backend.app.core import login_limit
from backend.app.models import Student, User
from backend.app.models.hardening import AttendanceRevision, SecurityAudit, RevokedToken, LoginThrottle
from backend.app.models.review import AttendanceChange
from backend.app.services.change_events import change_marker


def test_production_requires_explicit_hosts_and_origins():
    import pytest
    from backend.app.core.config import Settings
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match='explicit allowed hosts'):
        Settings(APP_ENV='production', JWT_SECRET='a' * 64, ALLOWED_HOSTS='*')
    with pytest.raises(ValidationError, match='explicit allowed hosts'):
        Settings(APP_ENV='production', JWT_SECRET='a' * 64, ALLOWED_HOSTS='localhost', ALLOWED_ORIGINS='*')
    assert Settings(APP_ENV='production', JWT_SECRET='a' * 64, ALLOWED_HOSTS='localhost',
                    ALLOWED_ORIGINS='http://localhost:8000').JWT_EXPIRATION_MINUTES == settings.JWT_EXPIRATION_MINUTES

def auth():
    with TargetSessionLocal() as db:
        user = db.query(User).filter_by(Username='admin').one()
        return {'Authorization': 'Bearer ' + create_access_token({'sub': user.Username, 'id': user.SystemUserId, 'ver': 0})}

def test_unsafe_paths_rejected_before_resolution():
    for path in ('//remote/share', '/assets/\\\\remote\\share', '/C:/secret', '/assets/../secret', '/assets/file:stream', '/bad\x00'):
        assert not safe_request_path(path)
    assert safe_request_path('/assets/index.js') and safe_request_path('/student-details')
    with TestClient(app) as client:
        assert client.get('/assets/C:/secret').status_code == 404

def test_logout_revokes_only_exact_token_without_changing_session_duration():
    h = auth()
    token = h['Authorization'][7:]
    claims = jwt.decode(token, settings.JWT_SECRET, algorithms=['HS256'])
    assert abs((datetime.utcfromtimestamp(claims['exp']) - datetime.utcnow()).total_seconds() - settings.JWT_EXPIRATION_MINUTES * 60) < 2
    second = auth()
    assert second != h
    with TestClient(app) as client:
        assert client.post('/api/auth/logout', headers=h).status_code == 200
        assert client.get('/api/auth/me', headers=h).status_code == 401
        assert client.get('/api/auth/me', headers=second).status_code == 200
    with TargetSessionLocal() as db:
        row = db.get(RevokedToken, sha256(token.encode()).hexdigest())
        assert row is not None
        assert db.query(User).filter_by(Username='admin').one().TokenVersion == 0

def test_throttle_persists_across_process_local_reset():
    with TestClient(app) as client:
        for unused in range(10):
            assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'wrong'}).status_code == 401
        login_limit._attempts.clear()
        assert client.post('/api/auth/login', json={'username': 'ADMIN', 'password': 'wrong'}).status_code == 429
    with TargetSessionLocal() as db:
        assert db.query(LoginThrottle).count() == 2

def test_revision_is_bounded_and_rolls_back_with_savepoint():
    with TargetSessionLocal() as db:
        row = db.query(Student).one()
        before = change_marker(db)
        savepoint = db.begin_nested()
        row.RoomNo = 'rolledback'
        db.flush()
        assert change_marker(db) != before
        savepoint.rollback()
        assert change_marker(db) == before
        for i in range(20):
            row.RoomNo = str(i)
            db.flush()
        db.commit()
        assert db.query(AttendanceRevision).count() == 1 and db.query(AttendanceChange).count() == 0

def test_account_audit_never_contains_password():
    h = auth()
    with TestClient(app) as client:
        created = client.post('/api/users', json={'username': 'audited', 'password': 'SafePassword123', 'role': 'MANAGEMENT'}, headers=h)
        assert created.status_code == 201
        assert client.put(f"/api/users/{created.json()['SystemUserId']}", json={'password': 'UpdatedPassword123'}, headers=h).status_code == 200
    with TargetSessionLocal() as db:
        rows = db.query(SecurityAudit).all()
        assert len(rows) == 2 and all('Password123' not in row.Details for row in rows)
        assert '"password_changed": true' in rows[-1].Details
        user = db.query(User).filter_by(Username='audited').one()
        assert verify_password('UpdatedPassword123', user.PasswordHash)

def test_cursor_paging_equal_timestamps_keeps_scope_and_rejects_bad_cursor():
    from backend.app.models import RawPunch, ProcessedPunch
    stamp = datetime(2026, 10, 10, 8)
    with TargetSessionLocal() as db:
        row = db.query(Student).one()
        for i in range(6):
            raw = RawPunch(SourceDeviceLogId=i + 1, DeviceId=101, UserId=row.UserId, LogDate=stamp)
            db.add(raw)
            db.flush()
            db.add(ProcessedPunch(RawPunchId=raw.RawPunchId, StudentId=row.StudentId, UserId=row.UserId,
                DeviceId=101, LogDate=stamp, PunchType='IN', ProcessingStatus='VALID', HostelIdSnapshot=1 if i < 5 else 2))
        db.commit()
        warden = db.query(User).filter_by(Username='warden_a').one()
        h = {'Authorization': 'Bearer ' + create_access_token({'sub': warden.Username, 'id': warden.SystemUserId, 'ver': 0})}
    with TestClient(app) as client:
        first = client.get('/api/attendance/history?limit=2', headers=h)
        second = client.get('/api/attendance/history', params={'limit': 2, 'skip': 999999, 'cursor': first.headers['x-next-cursor']}, headers=h)
        assert first.headers['x-total-count'] == second.headers['x-total-count'] == '5'
        assert len(second.json()) == 2
        assert not ({r['PunchId'] for r in first.json()} & {r['PunchId'] for r in second.json()})
        assert all(r['HostelId'] == 1 for r in second.json())
        assert client.get('/api/attendance/history?cursor=BAD', headers=h).status_code == 422
