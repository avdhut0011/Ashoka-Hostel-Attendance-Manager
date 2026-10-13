import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.database import TargetSessionLocal
from backend.app.models.master import Student, Hostel, Device
from backend.app.models.integration import RawPunch
from backend.app.services.punch_processor import process_single_raw_punch

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    if response.headers.get('content-type', '').startswith('text/html'):
        assert '<div id="root"></div>' in response.text
    else:
        assert response.json()['status'] == 'ONLINE' 

def test_auth_login_success():
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123password"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "ADMIN"

def test_auth_login_failure():
    response = client.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert response.status_code == 401

def test_dashboard_summary_api():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123password"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/dashboard/summary", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_students" in data
    assert "currently_in" in data
    assert "currently_out" in data

def test_hostel_and_device_apis():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123password"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Ensure at least 1 hostel exists
    client.post("/api/hostels", json={"HostelName": "Main Campus Hostel", "HostelCode": "MCH", "IsActive": True}, headers=headers)
    h_resp = client.get("/api/hostels", headers=headers)
    assert h_resp.status_code == 200
    assert len(h_resp.json()) >= 1
    hostel_id = h_resp.json()[0]["HostelId"]

    import random
    dev_id = random.randint(10000, 99999)
    client.post("/api/devices", json={"DeviceId": dev_id, "DeviceName": "Gate Scanner Test", "HostelId": hostel_id, "IsActive": True}, headers=headers)

    d_resp = client.get("/api/devices", headers=headers)
    assert d_resp.status_code == 200
    assert len(d_resp.json()) >= 1

def test_detailed_student_history_api():
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123password"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Test single date history query
    resp_single = client.get(f"/api/attendance/history?single_date={today_str}", headers=headers)
    assert resp_single.status_code == 200

    # Test date range history query
    resp_range = client.get(f"/api/attendance/history?start_date=2026-01-01&end_date={today_str}", headers=headers)
    assert resp_range.status_code == 200
    assert isinstance(resp_range.json(), list)

def test_system_health_api():
    # 1. Public ping endpoint
    ping_resp = client.get("/api/system/ping")
    assert ping_resp.status_code == 200
    assert ping_resp.json()["status"] == "UP"

    # 2. Authenticated health check
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123password"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/system/health", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] in ["HEALTHY", "DEGRADED"]

def test_admin_manual_attendance_status_override():
    # 1. Admin login
    admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123password"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create dedicated test student
    import uuid
    unique_user_id = f"TEST_STU_{uuid.uuid4().hex[:6]}"
    create_res = client.post(
        "/api/students",
        json={"UserId": unique_user_id, "StudentName": "Override Tester", "RegistrationStatus": "ACTIVE"},
        headers=admin_headers
    )
    assert create_res.status_code == 200
    student_id = create_res.json()["StudentId"]

    # 2. Admin overrides status to OUT
    override_out = client.put(
        f"/api/students/{student_id}/attendance-status",
        json={"CurrentStatus": "OUT", "Reason": "Special permission by Admin"},
        headers=admin_headers
    )
    assert override_out.status_code == 200
    assert override_out.json()["CurrentStatus"] == "OUT"

    # 3. Admin overrides status to IN
    override_in = client.put(
        f"/api/students/{student_id}/attendance-status",
        json={"CurrentStatus": "IN", "Reason": "Returned to hostel"},
        headers=admin_headers
    )
    assert override_in.status_code == 200
    assert override_in.json()["CurrentStatus"] == "IN"

    # 4. Admin overrides status to REGISTRATION
    override_reg = client.put(
        f"/api/students/{student_id}/attendance-status",
        json={"CurrentStatus": "REGISTRATION", "Reason": "Reset to registration"},
        headers=admin_headers
    )
    assert override_reg.status_code == 200
    assert override_reg.json()["CurrentStatus"] == "REGISTRATION"

    # 5. Non-admin (Warden) denied 403
    warden_login = client.post("/api/auth/login", json={"username": "warden_boys", "password": "wardenpassword"})
    if warden_login.status_code == 200:
        warden_token = warden_login.json()["access_token"]
        warden_headers = {"Authorization": f"Bearer {warden_token}"}
        warden_res = client.put(
            f"/api/students/{student_id}/attendance-status",
            json={"CurrentStatus": "OUT", "Reason": "Warden attempting override"},
            headers=warden_headers
        )
        assert warden_res.status_code == 403

def test_quarantine_management_and_reprocess():
    from backend.app.models.integration import QuarantinedPunch
    from backend.app.models.master import Device, Hostel

    admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123password"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    db = TargetSessionLocal()
    # 1. Create a test device if needed
    hostel = db.query(Hostel).first()
    if not hostel:
        hostel = Hostel(HostelName="Quarantine Test Hostel", IsActive=True)
        db.add(hostel)
        db.commit()

    device = db.query(Device).filter_by(DeviceId=88888).first()
    if not device:
        device = Device(DeviceId=88888, DeviceName="Gate 88", HostelId=hostel.HostelId, IsActive=True)
        db.add(device)
    else:
        device.IsActive = True
        device.HostelId = hostel.HostelId
    db.commit()

    # 2. Insert dummy quarantined punch (missing UserId)
    import random
    unique_log_id = random.randint(1000000, 99999999)
    q_punch = QuarantinedPunch(
        SourceDeviceLogId=unique_log_id,
        DeviceId=88888,
        UserId="",
        LogDate=datetime.utcnow(),
        ErrorType="DATA_CORRUPTION",
        ErrorMessage="Empty or missing UserId",
        ResolvedStatus="PENDING"
    )
    db.add(q_punch)
    db.commit()
    db.refresh(q_punch)
    q_id = q_punch.QuarantineId
    db.close()

    # 3. List quarantine records
    list_resp = client.get("/api/system/quarantine?status=PENDING", headers=admin_headers)
    assert list_resp.status_code == 200
    assert any(q["QuarantineId"] == q_id for q in list_resp.json())

    # 4. Reprocess with corrected UserId
    corrected_user = f"STU_Q_{unique_log_id}"
    reprocess_resp = client.post(
        f"/api/system/quarantine/{q_id}/reprocess",
        json={"corrected_user_id": corrected_user, "corrected_device_id": 88888},
        headers=admin_headers
    )
    assert reprocess_resp.status_code == 200
    data = reprocess_resp.json()
    assert data["processing_status"] == "VALID"
    assert data["punch_type"] == "REGISTRATION"

    # 5. Verify status updated to RESOLVED in database
    db = TargetSessionLocal()
    updated_q = db.query(QuarantinedPunch).filter_by(QuarantineId=q_id).first()
    assert updated_q.ResolvedStatus == "RESOLVED"
    assert updated_q.UserId == ''  # Original quarantine payload is immutable.
    assert db.query(RawPunch).filter_by(SourceDeviceLogId=unique_log_id).one().UserId == corrected_user
    db.close()

def test_formal_enrollment_gate_and_headcount_isolation():
    # 1. Admin login
    admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123password"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    import random
    dev_id = random.randint(20000, 30000)
    user_id = f"RFID_UNKNOWN_{random.randint(10000, 99999)}"

    # Create active device
    db = TargetSessionLocal()
    hostel = Hostel(HostelName="Gate Isolation Hostel", HostelCode=f"GIH_{random.randint(100, 999)}")
    db.add(hostel)
    db.flush()
    device = Device(DeviceId=dev_id, DeviceName=f"Scanner {dev_id}", HostelId=hostel.HostelId, IsActive=True)
    db.add(device)
    db.commit()
    hostel_id = hostel.HostelId
    db.close()

    # Step 1: Initial dashboard summary baseline
    summary_before = client.get("/api/dashboard/summary", headers=admin_headers).json()
    active_before = summary_before["total_students"]
    pending_before = summary_before["pending_enrollments"]

    # Step 2: First-time punch arrives from unknown card
    raw_punch_1 = RawPunch(
        SourceDeviceLogId=random.randint(200000, 300000),
        DeviceId=dev_id,
        UserId=user_id,
        LogDate=datetime.utcnow()
    )
    db = TargetSessionLocal()
    db.add(raw_punch_1)
    db.commit()
    db.refresh(raw_punch_1)
    p1 = process_single_raw_punch(db, raw_punch_1)
    db.commit()
    assert p1.ProcessingStatus == "VALID"
    assert p1.PunchType == "REGISTRATION"
    db.close()

    # Verify student is in PENDING_ENROLLMENT status
    db = TargetSessionLocal()
    student = db.query(Student).filter_by(UserId=user_id).first()
    assert student is not None
    assert student.RegistrationStatus == "PENDING_ENROLLMENT"
    student_id = student.StudentId
    db.close()

    # Step 3: Verify dashboard metrics isolate this student (not added to total active students)
    summary_mid = client.get("/api/dashboard/summary", headers=admin_headers).json()
    assert summary_mid["total_students"] == active_before
    assert summary_mid["pending_enrollments"] == pending_before + 1

    # Step 4: Verify student appears in the pending enrollment queue
    pending_queue_res = client.get("/api/students?pending_enrollment=true", headers=admin_headers)
    assert pending_queue_res.status_code == 200
    pending_ids = [s["StudentId"] for s in pending_queue_res.json()]
    assert student_id in pending_ids

    # Step 5: Warden / Admin officially enrolls the student
    enroll_res = client.put(
        f"/api/students/{student_id}/enroll",
        json={"StudentName": "Rahul Sharma", "HostelId": hostel_id, "RoomNo": "B-204"},
        headers=admin_headers
    )
    assert enroll_res.status_code == 200
    assert enroll_res.json()["RegistrationStatus"] == "ACTIVE"
    assert enroll_res.json()["StudentName"] == "Rahul Sharma"

    # Step 6: Verify student now joins the active dashboard headcount
    summary_after = client.get("/api/dashboard/summary", headers=admin_headers).json()
    assert summary_after["total_students"] == active_before + 1
    assert summary_after["pending_enrollments"] == pending_before
