import pytest
import uuid
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.database import TargetSessionLocal
from backend.app.models.security import User
from backend.app.core.security import create_access_token, get_password_hash

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_users():
    db = TargetSessionLocal()
    from backend.app.models.master import Hostel
    hostel = db.query(Hostel).first()
    if not hostel:
        hostel = Hostel(HostelName="Test Boys Hostel", HostelCode="TBH", IsActive=True)
        db.add(hostel)
        db.flush()
    hostel_id = hostel.HostelId

    roles_users = [
        ("admin", "ADMIN", None),
        ("warden_a", "WARDEN", hostel_id),
        ("it_admin_test", "IT_ADMIN", None),
        ("mgmt_test", "MANAGEMENT", None)
    ]
    for username, role, h_id in roles_users:
        u = db.query(User).filter_by(Username=username).first()
        if not u:
            u = User(Username=username, PasswordHash=get_password_hash("pass123"), Role=role, HostelId=h_id, IsActive=True)
            db.add(u)
        else:
            u.IsActive = True
            u.Role = role
            u.HostelId = h_id
    db.commit()
    db.close()

def test_admin_user_management(setup_users):
    token = create_access_token({"sub": "admin", "role": "ADMIN", "id": 1})
    headers = {"Authorization": f"Bearer {token}"}
    
    # List users
    res = client.get("/api/users", headers=headers)
    assert res.status_code == 200

    # Create new unique user
    db = TargetSessionLocal()
    from backend.app.models.master import Hostel
    h_obj = db.query(Hostel).first()
    valid_hostel_id = h_obj.HostelId if h_obj else None
    db.close()

    unique_user = f"warden_{uuid.uuid4().hex[:6]}"
    new_user_data = {
        "username": unique_user,
        "password": "password123",
        "role": "WARDEN",
        "hostel_id": valid_hostel_id
    }
    create_res = client.post("/api/users", json=new_user_data, headers=headers)
    assert create_res.status_code == 201
    created_id = create_res.json()["SystemUserId"]

    # Soft Delete User
    del_res = client.delete(f"/api/users/{created_id}", headers=headers)
    assert del_res.status_code == 200

def test_warden_read_only_protection(setup_users):
    token = create_access_token({"sub": "warden_a", "role": "WARDEN", "id": 2, "hostel_id": 1})
    headers = {"Authorization": f"Bearer {token}"}

    # Warden trying to access user management -> 403 Forbidden
    res = client.get("/api/users", headers=headers)
    assert res.status_code == 403

    # Warden trying to create hostel -> 403 Forbidden
    res_h = client.post("/api/hostels", json={"HostelName": "Forbidden Hostel", "HostelCode": "FH", "IsActive": True}, headers=headers)
    assert res_h.status_code == 403

    # Warden trying to create device -> 403 Forbidden
    res_d = client.post("/api/devices", json={"DeviceId": 99911, "DeviceName": "Forbidden Device", "HostelId": 1, "IsActive": True}, headers=headers)
    assert res_d.status_code == 403

def test_management_read_only_protection(setup_users):
    token = create_access_token({"sub": "mgmt_test", "role": "MANAGEMENT", "id": 4})
    headers = {"Authorization": f"Bearer {token}"}

    # Management trying to access user management -> 403 Forbidden
    res = client.get("/api/users", headers=headers)
    assert res.status_code == 403

    # Management trying to create student -> 403 Forbidden
    res_s = client.post("/api/students", json={"UserId": "FORBIDDEN01", "StudentName": "Fail", "HostelId": 1, "RoomNo": "101", "RegistrationStatus": "ACTIVE"}, headers=headers)
    assert res_s.status_code == 403

def test_it_admin_enrollment_privilege(setup_users):
    with TargetSessionLocal() as db:
        actual_id = db.query(User).filter_by(Username='it_admin_test').one().SystemUserId
    token = create_access_token({"sub": "it_admin_test", "role": "IT_ADMIN", "id": actual_id})
    headers = {"Authorization": f"Bearer {token}"}

    import random
    dev_id = random.randint(10000, 99999)
    # IT Admin creating/registering device -> 200 OK
    res_d = client.post("/api/devices", json={"DeviceId": dev_id, "DeviceName": "IT Scanner Test", "HostelId": 1, "IsActive": True}, headers=headers)
    assert res_d.status_code == 200

def test_warden_student_registration_authority(setup_users):
    db = TargetSessionLocal()
    from backend.app.models.master import Hostel, Student
    h1 = db.query(Hostel).filter_by(HostelName="Test Boys Hostel").first()
    if not h1:
        h1 = Hostel(HostelName="Test Boys Hostel", HostelCode="TBH", IsActive=True)
        db.add(h1)
        db.commit()
    h1_id = h1.HostelId

    h2 = db.query(Hostel).filter_by(HostelName="Other Hostel 2").first()
    if not h2:
        h2 = Hostel(HostelName="Other Hostel 2", HostelCode="OH2", IsActive=True)
        db.add(h2)
        db.commit()
    h2_id = h2.HostelId

    # Create warden user in DB assigned to h1
    warden = db.query(User).filter_by(Username="warden_a").first()
    if not warden:
        warden = User(Username="warden_a", PasswordHash=get_password_hash("pass123"), Role="WARDEN", HostelId=h1_id, IsActive=True)
        db.add(warden)
    else:
        warden.HostelId = h1_id
        warden.Role = "WARDEN"
        warden.IsActive = True
    db.commit()
    warden_id = warden.SystemUserId
    db.close()

    token = create_access_token({"sub": "warden_a", "role": "WARDEN", "id": warden_id, "hostel_id": h1_id})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Warden CAN register a new student (Scoped to their hostel)
    stu_uid = f"STU_W_{uuid.uuid4().hex[:6]}"
    res_reg = client.post(
        "/api/students",
        json={"UserId": stu_uid, "StudentName": "Warden Registered Student", "RoomNo": "A-101", "RegistrationStatus": "ACTIVE"},
        headers=headers
    )
    assert res_reg.status_code == 200
    stu_data = res_reg.json()
    assert stu_data["HostelId"] == h1_id
    created_student_id = stu_data["StudentId"]

    # 2. Warden CAN enroll/update their own hostel student
    res_enroll = client.put(
        f"/api/students/{created_student_id}/enroll",
        json={"StudentName": "Updated Name By Warden", "HostelId": h1_id, "RoomNo": "A-102"},
        headers=headers
    )
    assert res_enroll.status_code == 200
    assert res_enroll.json()["StudentName"] == "Updated Name By Warden"

    # 3. Warden CANNOT modify student assigned to another hostel (Hostel 2)
    db = TargetSessionLocal()
    other_stu = Student(UserId=f"OTHER_{uuid.uuid4().hex[:6]}", StudentName="Other Hostel Student", HostelId=h2_id, RegistrationStatus="ACTIVE")
    db.add(other_stu)
    db.commit()
    other_stu_id = other_stu.StudentId
    db.close()

    res_forbidden = client.put(
        f"/api/students/{other_stu_id}/enroll",
        json={"StudentName": "Hacked Name", "HostelId": h2_id, "RoomNo": "B-202"},
        headers=headers
    )
    assert res_forbidden.status_code == 403
