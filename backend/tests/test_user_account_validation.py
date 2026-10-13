import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.database import TargetSessionLocal
from backend.app.core.security import create_access_token
from backend.app.models import User, Hostel


def auth():
    with TargetSessionLocal() as db:
        user = db.query(User).filter_by(Username='admin').one()
        return {'Authorization': 'Bearer ' + create_access_token({'sub': user.Username, 'id': user.SystemUserId, 'ver': 0})}


@pytest.mark.parametrize('role', ['ADMIN', 'IT_ADMIN', 'MANAGEMENT'])
@pytest.mark.parametrize('scope', ['omitted', None, '', 999])
def test_nonwarden_creation_never_requires_hostel(role, scope):
    payload = {'username': '  fresh_account  ', 'password': 'SafePassword123', 'role': role}
    if scope != 'omitted':
        payload['hostel_id'] = scope
    with TestClient(app) as client:
        result = client.post('/api/users', json=payload, headers=auth())
        assert result.status_code == 201, result.text
        assert result.json()['HostelId'] is None and result.json()['Username'] == 'fresh_account'


@pytest.mark.parametrize('scope', [None, '', 999])
def test_warden_rejects_missing_or_invalid_hostel(scope):
    with TargetSessionLocal() as db:
        baseline = db.query(User).count()
    with TestClient(app) as client:
        response = client.post('/api/users', json={'username': 'new_warden', 'password': 'SafePassword123',
                                                  'role': 'WARDEN', 'hostel_id': scope}, headers=auth())
        assert response.status_code == 400 and 'active assigned hostel' in response.json()['detail']
    with TargetSessionLocal() as db:
        assert db.query(User).count() == baseline


def test_warden_creation_active_assignment_and_inactive_rejection():
    with TargetSessionLocal() as db:
        hostel = db.get(Hostel, 2)
        hostel.IsActive = False
        db.commit()
    with TestClient(app) as client:
        payload = {'username': 'new_warden', 'password': 'SafePassword123', 'role': ' warden ', 'hostel_id': 2}
        assert client.post('/api/users', json=payload, headers=auth()).status_code == 400
        payload['hostel_id'] = 1
        result = client.post('/api/users', json=payload, headers=auth())
        assert result.status_code == 201 and result.json()['HostelId'] == 1


def test_edit_role_clears_scope_blank_password_preserves_hash_and_warden_cannot_clear_scope():
    with TargetSessionLocal() as db:
        warden = db.query(User).filter_by(Username='warden_a').one()
        uid, old_hash = warden.SystemUserId, warden.PasswordHash
    with TestClient(app) as client:
        assert client.put(f'/api/users/{uid}', json={'hostel_id': None}, headers=auth()).status_code == 400
        result = client.put(f'/api/users/{uid}', json={'role': 'MANAGEMENT', 'hostel_id': '', 'password': ''}, headers=auth())
        assert result.status_code == 200 and result.json()['HostelId'] is None
        assert client.put(f'/api/users/{uid}', json={'role': 'WARDEN'}, headers=auth()).status_code == 400
        assert client.put(f'/api/users/{uid}', json={'role': 'WARDEN', 'hostel_id': 1}, headers=auth()).status_code == 200
    with TargetSessionLocal() as db:
        assert db.get(User, uid).PasswordHash == old_hash


@pytest.mark.parametrize('password', ['short', 'a'*73, '界'*25])
def test_invalid_password_returns_field_error_without_account_creation(password):
    with TestClient(app) as client:
        response = client.post('/api/users', json={'username': 'bad_password', 'password': password,
                                                  'role': 'MANAGEMENT'}, headers=auth())
        assert response.status_code == 422
        assert response.json()['detail'][0]['loc'] == ['body', 'password']
    with TargetSessionLocal() as db:
        assert db.query(User).filter_by(Username='bad_password').first() is None
