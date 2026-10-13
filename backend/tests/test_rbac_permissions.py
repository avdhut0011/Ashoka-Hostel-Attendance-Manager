import pytest
from datetime import date
from backend.app.core.database import TargetSessionLocal, target_engine
from backend.app.models.master import Student, Hostel
from backend.app.models.security import User
from backend.app.core.security import create_access_token
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_admin_can_deactivate_student():
    db = TargetSessionLocal()
    hostel = db.query(Hostel).filter_by(HostelCode="HA-BOYS").first()
    student = db.query(Student).filter_by(UserId="U1001").first()
    db.close()

    if not student:
        pytest.skip("Student U1001 not found")

    token = create_access_token({"sub": "admin", "role": "ADMIN", "id": 1})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.put(f"/api/students/{student.StudentId}/status", json={"RegistrationStatus": "INACTIVE", "DeactivationReason": "Test Deactivation"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["RegistrationStatus"] == "INACTIVE"

    # Restore to ACTIVE for clean state
    resp_restore = client.put(f"/api/students/{student.StudentId}/status", json={"RegistrationStatus": "ACTIVE"}, headers=headers)
    assert resp_restore.status_code == 200

def test_warden_cannot_deactivate_student():
    db = TargetSessionLocal()
    student = db.query(Student).filter_by(UserId="U1001").first()
    db.close()

    if not student:
        pytest.skip("Student U1001 not found")

    token = create_access_token({"sub": "warden_a", "role": "WARDEN", "id": 2, "hostel_id": student.HostelId})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.put(f"/api/students/{student.StudentId}/status", json={"RegistrationStatus": "INACTIVE"}, headers=headers)
    assert resp.status_code == 403 # WARDEN is strictly forbidden from student status activation/deactivation
