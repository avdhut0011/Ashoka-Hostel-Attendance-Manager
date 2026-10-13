import os
import pytest
from datetime import datetime, timedelta, date
from backend.app.core.database import TargetSessionLocal, SourceSessionLocal, target_engine, Base
from backend.app.models.master import Student, Device, Hostel
from backend.app.models.integration import RawPunch, SyncCheckpoint
from backend.app.models.attendance import ProcessedPunch, StudentCurrentStatus
from backend.app.services.punch_processor import process_single_raw_punch
from sync_worker.sync_service import run_synchronization_cycle

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=target_engine)
    db = TargetSessionLocal()
    yield db
    db.close()

def test_device_validation(setup_db):
    db = setup_db
    raw = RawPunch(
        SourceDeviceLogId=99991, DeviceId=999, UserId="U999", LogDate=datetime.utcnow()
    )
    db.add(raw)
    db.flush()

    processed = process_single_raw_punch(db, raw)
    assert processed.ProcessingStatus == "INVALID_DEVICE"
    assert "Device missing" in processed.Reason

def test_student_auto_registration(setup_db):
    db = setup_db
    # Create active device
    hostel = Hostel(HostelName="Test Hostel", HostelCode="TH1")
    db.add(hostel)
    db.flush()
    device = Device(DeviceId=901, DeviceName="Test Device 901", HostelId=hostel.HostelId, IsActive=True)
    db.add(device)
    db.flush()

    raw = RawPunch(SourceDeviceLogId=99992, DeviceId=901, UserId="UAUTO1", LogDate=datetime.utcnow())
    db.add(raw)
    db.flush()

    processed = process_single_raw_punch(db, raw)
    assert processed.ProcessingStatus == "VALID"
    assert processed.PunchType == "REGISTRATION"
    assert processed.IsFirstEverPunch == True

    student = db.query(Student).filter_by(UserId="UAUTO1").first()
    assert student is not None
    assert student.RegistrationStatus == "PENDING_ENROLLMENT"

def test_duplicate_punch_detection(setup_db):
    db = setup_db
    hostel = Hostel(HostelName="Test Hostel 2", HostelCode="TH2")
    db.add(hostel)
    db.flush()
    device = Device(DeviceId=902, DeviceName="Test Device 902", HostelId=hostel.HostelId, IsActive=True)
    db.add(device)
    db.flush()

    student = Student(UserId="UDUP1", StudentName="Dup Student", HostelId=hostel.HostelId, RegistrationStatus="ACTIVE")
    db.add(student)
    db.flush()

    now = datetime.utcnow()
    raw1 = RawPunch(SourceDeviceLogId=99993, DeviceId=902, UserId="UDUP1", LogDate=now)
    raw2 = RawPunch(SourceDeviceLogId=99994, DeviceId=902, UserId="UDUP1", LogDate=now + timedelta(seconds=15))

    db.add_all([raw1, raw2])
    db.flush()

    p1 = process_single_raw_punch(db, raw1)
    assert p1.ProcessingStatus == "VALID"
    assert p1.PunchType == "REGISTRATION"

    p2 = process_single_raw_punch(db, raw2)
    assert p2.ProcessingStatus == "DUPLICATE"
    assert p2.PunchType is None

def test_in_out_alternation(setup_db):
    db = setup_db
    hostel = Hostel(HostelName="Test Hostel 3", HostelCode="TH3")
    db.add(hostel)
    db.flush()
    device = Device(DeviceId=903, DeviceName="Test Device 903", HostelId=hostel.HostelId, IsActive=True)
    db.add(device)
    db.flush()

    student = Student(UserId="UINOUT1", StudentName="InOut Student", HostelId=hostel.HostelId, RegistrationStatus="ACTIVE")
    db.add(student)
    db.flush()

    now = datetime.utcnow()
    t1 = now - timedelta(days=2)
    t2 = now - timedelta(days=1, hours=2) # Day 2, 7:00 AM
    t3 = now - timedelta(days=1, hours=1) # Day 2, 8:00 AM

    r1 = RawPunch(SourceDeviceLogId=99995, DeviceId=903, UserId="UINOUT1", LogDate=t1)
    r2 = RawPunch(SourceDeviceLogId=99996, DeviceId=903, UserId="UINOUT1", LogDate=t2)
    r3 = RawPunch(SourceDeviceLogId=99997, DeviceId=903, UserId="UINOUT1", LogDate=t3)
    db.add_all([r1, r2, r3])
    db.flush()

    p1 = process_single_raw_punch(db, r1)
    assert p1.PunchType == "REGISTRATION"

    p2 = process_single_raw_punch(db, r2)
    assert p2.PunchType == "IN" # Previous status was NOT_STARTED/OUT

    p3 = process_single_raw_punch(db, r3)
    assert p3.PunchType == "OUT" # Alternates from IN

def test_multiple_punches_before_enrollment_remain_registration(setup_db):
    db = setup_db
    hostel = Hostel(HostelName="Test Hostel Pending", HostelCode="THP")
    db.add(hostel)
    db.flush()
    device = Device(DeviceId=904, DeviceName="Test Device 904", HostelId=hostel.HostelId, IsActive=True)
    db.add(device)
    db.flush()

    # Student punches 3 times on different days before being registered
    now = datetime.utcnow()
    t1 = now - timedelta(days=3)
    t2 = now - timedelta(days=2)
    t3 = now - timedelta(days=1)

    r1 = RawPunch(SourceDeviceLogId=99998, DeviceId=904, UserId="UPENDING1", LogDate=t1)
    r2 = RawPunch(SourceDeviceLogId=99999, DeviceId=904, UserId="UPENDING1", LogDate=t2)
    r3 = RawPunch(SourceDeviceLogId=100000, DeviceId=904, UserId="UPENDING1", LogDate=t3)
    db.add_all([r1, r2, r3])
    db.flush()

    p1 = process_single_raw_punch(db, r1)
    assert p1.PunchType == "REGISTRATION"

    student = db.query(Student).filter_by(UserId="UPENDING1").first()
    assert student.RegistrationStatus == "PENDING_ENROLLMENT"

    # Second punch before enrollment - must still be REGISTRATION (NOT IN or OUT)
    p2 = process_single_raw_punch(db, r2)
    assert p2.PunchType == "REGISTRATION"
    curr = db.query(StudentCurrentStatus).filter_by(StudentId=student.StudentId).first()
    assert curr.CurrentStatus == "REGISTRATION"
    assert curr.TodayInCount == 0
    assert curr.TodayOutCount == 0

    # Third punch before enrollment - must still be REGISTRATION (NOT IN or OUT)
    p3 = process_single_raw_punch(db, r3)
    assert p3.PunchType == "REGISTRATION"
    assert curr.CurrentStatus == "REGISTRATION"

    # Now officially enroll student
    student.StudentName = "Enrolled Student"
    student.RegistrationStatus = "ACTIVE"
    db.flush()

    # Fourth punch AFTER enrollment - now transitions to IN
    r4 = RawPunch(SourceDeviceLogId=100001, DeviceId=904, UserId="UPENDING1", LogDate=now)
    db.add(r4)
    db.flush()
    p4 = process_single_raw_punch(db, r4)
    assert p4.PunchType == "IN"
    assert curr.CurrentStatus == "IN"
