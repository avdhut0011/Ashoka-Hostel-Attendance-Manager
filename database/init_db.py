from pathlib import Path as _GuardPath
import sys as _guard_sys
_guard_sys.path.insert(0, str(_GuardPath(__file__).resolve().parents[1]))
from database.safety import require_development_data_operation
require_development_data_operation()

import os
import sys
from datetime import datetime, timedelta, date

# Ensure root workspace is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import Table, Column, Integer, BigInteger, String, DateTime, MetaData
from backend.app.core.database import target_engine, source_engine, TargetSessionLocal, SourceSessionLocal
from backend.app.models.base import Base
from backend.app.models.master import Hostel, Device, Student
from backend.app.models.security import User
from backend.app.models.integration import SyncCheckpoint
from backend.app.core.security import pwd_context


# Dummy IT table for SQLite / DB
metadata = MetaData()
device_logs_table = Table(
    "DeviceLogs", metadata,
    Column("DeviceLogId", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("DownloadDate", DateTime, default=datetime.utcnow),
    Column("DeviceId", Integer, nullable=False),
    Column("UserId", String(50), nullable=False),
    Column("LogDate", DateTime, nullable=False)
)

def init_databases():
    print("Creating Target Database tables...")
    Base.metadata.create_all(bind=target_engine)

    print("Creating Source IT Database tables...")
    metadata.create_all(bind=source_engine)

    db = TargetSessionLocal()
    source_db = SourceSessionLocal()

    try:
        # 1. Seed System Users
        if not db.query(User).filter_by(Username="admin").first():
            db.add(User(
                Username="admin",
                PasswordHash=pwd_context.hash("admin123password"),
                Role="ADMIN",
                IsActive=True
            ))
        if not db.query(User).filter_by(Username="warden_a").first():
            db.add(User(
                Username="warden_a",
                PasswordHash=pwd_context.hash("wardenpassword"),
                Role="WARDEN",
                IsActive=True
            ))
        if not db.query(User).filter_by(Username="it_admin").first():
            db.add(User(
                Username="it_admin",
                PasswordHash=pwd_context.hash("itadminpassword"),
                Role="IT_ADMIN",
                IsActive=True
            ))

        # 2. Seed Hostels
        hostel_a = db.query(Hostel).filter_by(HostelCode="HA-BOYS").first()
        if not hostel_a:
            hostel_a = Hostel(HostelName="Hostel A - Boys Block", HostelCode="HA-BOYS", IsActive=True)
            db.add(hostel_a)
            db.flush()

        hostel_b = db.query(Hostel).filter_by(HostelCode="HB-GIRLS").first()
        if not hostel_b:
            hostel_b = Hostel(HostelName="Hostel B - Girls Block", HostelCode="HB-GIRLS", IsActive=True)
            db.add(hostel_b)
            db.flush()

        # 3. Seed Devices
        if not db.query(Device).filter_by(DeviceId=101).first():
            db.add(Device(DeviceId=101, DeviceName="Main Gate Boys", HostelId=hostel_a.HostelId, IsActive=True))
        if not db.query(Device).filter_by(DeviceId=102).first():
            db.add(Device(DeviceId=102, DeviceName="Main Gate Girls", HostelId=hostel_b.HostelId, IsActive=True))
        if not db.query(Device).filter_by(DeviceId=103).first():
            db.add(Device(DeviceId=103, DeviceName="Disabled Gate", HostelId=hostel_a.HostelId, IsActive=False))

        # 4. Seed Students
        if not db.query(Student).filter_by(UserId="U1001").first():
            db.add(Student(
                UserId="U1001", StudentName="John Doe", HostelId=hostel_a.HostelId,
                RoomNo="101", RegistrationDate=date.today() - timedelta(days=10), RegistrationStatus="ACTIVE"
            ))
        if not db.query(Student).filter_by(UserId="U1002").first():
            db.add(Student(
                UserId="U1002", StudentName="Jane Smith", HostelId=hostel_b.HostelId,
                RoomNo="202", RegistrationDate=date.today() - timedelta(days=10), RegistrationStatus="ACTIVE"
            ))
        if not db.query(Student).filter_by(UserId="U1003").first():
            db.add(Student(
                UserId="U1003", StudentName="Robert Brown", HostelId=hostel_a.HostelId,
                RoomNo="103", RegistrationDate=date.today() - timedelta(days=10),
                RegistrationStatus="INACTIVE", DeactivatedAt=datetime.utcnow(), DeactivationReason="Graduated / Left Hostel"
            ))

        # 5. Initialize Sync Checkpoint
        if not db.query(SyncCheckpoint).filter_by(SourceName="IT_SQL_SERVER").first():
            db.add(SyncCheckpoint(
                SourceName="IT_SQL_SERVER", LastSourceDeviceLogId=0, LastSyncStatus="NEVER_RUN"
            ))

        db.commit()
        print("Target Database Seeded Successfully.")

        # 6. Seed Dummy IT Database Punches if empty
        conn = source_engine.connect()
        result = conn.execute(device_logs_table.select()).fetchall()
        if len(result) == 0:
            print("Seeding Dummy IT Database Punches...")
            now = datetime.utcnow()
            yesterday = now - timedelta(days=1)
            two_days_ago = now - timedelta(days=2)

            punches = [
                # U1001: Historical Registration + Punches
                {"DeviceId": 101, "UserId": "U1001", "LogDate": two_days_ago.replace(hour=8, minute=0, second=0)}, # Registration punch
                {"DeviceId": 101, "UserId": "U1001", "LogDate": yesterday.replace(hour=7, minute=30, second=0)}, # OUT
                {"DeviceId": 101, "UserId": "U1001", "LogDate": yesterday.replace(hour=20, minute=0, second=0)}, # IN
                {"DeviceId": 101, "UserId": "U1001", "LogDate": now.replace(hour=8, minute=15, second=0)}, # OUT
                {"DeviceId": 101, "UserId": "U1001", "LogDate": now.replace(hour=8, minute=15, second=20)}, # DUPLICATE (within 20s)

                # U1002: Punch on Girls Device 102
                {"DeviceId": 102, "UserId": "U1002", "LogDate": yesterday.replace(hour=9, minute=0, second=0)}, # Registration
                {"DeviceId": 102, "UserId": "U1002", "LogDate": now.replace(hour=7, minute=45, second=0)}, # OUT

                # U1003: Inactive student punch
                {"DeviceId": 101, "UserId": "U1003", "LogDate": now.replace(hour=9, minute=0, second=0)}, # INACTIVE_STUDENT

                # U1004: New undiscovered student punch
                {"DeviceId": 101, "UserId": "U1004", "LogDate": now.replace(hour=10, minute=0, second=0)}, # AUTO_REGISTRATION

                # Invalid Device punch (Device 103 is inactive)
                {"DeviceId": 103, "UserId": "U1001", "LogDate": now.replace(hour=11, minute=0, second=0)}, # INVALID_DEVICE
            ]

            for p in punches:
                conn.execute(device_logs_table.insert().values(
                    DownloadDate=datetime.utcnow(),
                    DeviceId=p["DeviceId"],
                    UserId=p["UserId"],
                    LogDate=p["LogDate"]
                ))
            conn.commit()
            print(f"Seeded {len(punches)} raw biometric punches in IT source database.")
        conn.close()

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()
        source_db.close()

if __name__ == "__main__":
    init_databases()
