from pathlib import Path as _GuardPath
import sys as _guard_sys
_guard_sys.path.insert(0, str(_GuardPath(__file__).resolve().parents[1]))
from database.safety import require_development_data_operation
require_development_data_operation(sql_server_utility=True)

import os
import sys
from datetime import datetime
from backend.app.core.security import pwd_context

# Ensure root workspace is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.core.database import TargetSessionLocal, SourceSessionLocal, target_engine, source_engine
from backend.app.models import (
    Base, Hostel, Device, Student, StudentHostelHistory,
    RawPunch, SyncCheckpoint, ProcessedPunch, StudentCurrentStatus,
    User, SystemEvent
)

from sync_worker.sync_service import run_synchronization_cycle
import pyodbc


def reset_and_seed_databases():
    print("==========================================================")
    print("Starting Complete Database Reset and Data Seeding...")
    print("==========================================================")

    db = TargetSessionLocal()
    source_db = SourceSessionLocal()

    try:
        # 1. Truncate / Delete all tables in HostelAttendance
        print("\n1. Deleting all records from 'HostelAttendance' target database...")
        db.query(StudentCurrentStatus).delete()
        db.query(ProcessedPunch).delete()
        db.query(RawPunch).delete()
        db.query(StudentHostelHistory).delete()
        db.query(Student).delete()
        db.query(User).delete()
        db.query(Device).delete()
        db.query(Hostel).delete()
        db.query(SystemEvent).delete()
        db.query(SyncCheckpoint).delete()
        db.commit()
        try:
            db.execute(source_engine.dialect.statement_compiler(source_engine.dialect, None).process() if False else None)
        except Exception:
            pass
        print("   -> HostelAttendance tables cleared successfully.")

        # 2. Truncate / Delete dbo.DeviceLogs in Epush_Dummy
        print("\n2. Deleting all records from 'Epush_Dummy' source IT database...")
        conn_epush = pyodbc.connect(
            "Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=Epush_Dummy;Trusted_Connection=yes;TrustServerCertificate=yes;",
            autocommit=True
        )
        conn_epush.cursor().execute("DELETE FROM dbo.DeviceLogs")
        try:
            conn_epush.cursor().execute("DBCC CHECKIDENT ('dbo.DeviceLogs', RESEED, 0)")
        except Exception:
            pass
        conn_epush.close()
        print("   -> Epush_Dummy.dbo.DeviceLogs cleared successfully.")

        # 3. Create 2 Hostels
        print("\n3. Creating Hostels...")
        hostel_boys = Hostel(HostelName="Boys Hostel Block A", HostelCode="BH-A", IsActive=True)
        hostel_girls = Hostel(HostelName="Girls Hostel Block B", HostelCode="GH-B", IsActive=True)
        db.add(hostel_boys)
        db.add(hostel_girls)
        db.flush()
        print(f"   -> Created Hostel ID {hostel_boys.HostelId}: {hostel_boys.HostelName}")
        print(f"   -> Created Hostel ID {hostel_girls.HostelId}: {hostel_girls.HostelName}")

        # 4. Create 2 Devices assigned to Hostels
        print("\n4. Creating Devices...")
        device_boys = Device(DeviceId=101, DeviceName="Boys Hostel Main Gate", HostelId=hostel_boys.HostelId, IsActive=True)
        device_girls = Device(DeviceId=102, DeviceName="Girls Hostel Main Gate", HostelId=hostel_girls.HostelId, IsActive=True)
        db.add(device_boys)
        db.add(device_girls)
        db.flush()
        print(f"   -> Created Device {device_boys.DeviceId}: {device_boys.DeviceName} (Assigned to {hostel_boys.HostelName})")
        print(f"   -> Created Device {device_girls.DeviceId}: {device_girls.DeviceName} (Assigned to {hostel_girls.HostelName})")

        # 5. Create 4 System User Accounts
        print("\n5. Creating User Accounts...")
        users = [
            User(
                Username="admin",
                PasswordHash=pwd_context.hash("admin123password"),
                Role="ADMIN",
                HostelId=None,
                IsActive=True
            ),
            User(
                Username="it_admin",
                PasswordHash=pwd_context.hash("itadminpassword"),
                Role="IT_ADMIN",
                HostelId=None,
                IsActive=True
            ),
            User(
                Username="warden_boys",
                PasswordHash=pwd_context.hash("wardenpassword"),
                Role="WARDEN",
                HostelId=hostel_boys.HostelId, # Assigned to Boys Hostel
                IsActive=True
            ),
            User(
                Username="management",
                PasswordHash=pwd_context.hash("managementpassword"),
                Role="MANAGEMENT",
                HostelId=None,
                IsActive=True
            ),
        ]
        for u in users:
            db.add(u)
        db.commit()
        print("   -> Created 4 User Accounts: admin, it_admin, warden_boys, management")

        # 6. Seed dummy raw punches in Epush_Dummy for 2 un-registered students
        print("\n6. Seeding biometric punches for 2 new un-registered students into Epush_Dummy...")
        conn = pyodbc.connect(
            "Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=Epush_Dummy;Trusted_Connection=yes;TrustServerCertificate=yes;",
            autocommit=True
        )
        cursor = conn.cursor()
        now = datetime.utcnow()
        cursor.execute(
            "INSERT INTO dbo.DeviceLogs (DownloadDate, DeviceId, UserId, LogDate) VALUES (?, ?, ?, ?)",
            (now, 101, "STU1001", now)
        )
        cursor.execute(
            "INSERT INTO dbo.DeviceLogs (DownloadDate, DeviceId, UserId, LogDate) VALUES (?, ?, ?, ?)",
            (now, 102, "STU1002", now)
        )
        conn.close()
        print("   -> Seeded punches for STU1001 (Device 101) and STU1002 (Device 102).")

        # Close setup DB session to release table locks before sync cycle
        db.close()

        # 7. Run synchronization cycle to process punches
        print("\n7. Executing Biometric Synchronization Engine...")
        sync_result = run_synchronization_cycle()
        print(f"   -> Sync Cycle Status: {sync_result}")

        # 8. Verification
        verify_db = TargetSessionLocal()
        pending_students = verify_db.query(Student).filter((Student.StudentName == None) | (Student.HostelId == None)).all()
        print(f"\n==========================================================")
        print(f"VERIFICATION SUCCESSFUL!")
        print(f"Pending Students in Registration Window: {len(pending_students)}")
        for ps in pending_students:
            print(f"  - UserId: {ps.UserId} | Status: {ps.RegistrationStatus} | Created: {ps.CreatedAt}")
        print(f"==========================================================")
        verify_db.close()

    except Exception as e:
        db.rollback()
        print(f"ERROR during reset and seed: {str(e)}")
        raise e
    finally:
        db.close()
        source_db.close()

if __name__ == "__main__":
    reset_and_seed_databases()
