from pathlib import Path as _GuardPath
import sys as _guard_sys
_guard_sys.path.insert(0, str(_GuardPath(__file__).resolve().parents[1]))
from database.safety import require_development_data_operation
require_development_data_operation(sql_server_utility=True)

import os
import sys
import pyodbc
from backend.app.core.security import pwd_context

# Ensure root workspace is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.core.database import TargetSessionLocal
from backend.app.models import (
    Hostel, Device, Student, StudentHostelHistory,
    RawPunch, SyncCheckpoint, ProcessedPunch, StudentCurrentStatus,
    User, SystemEvent
)


def truncate_all_databases(keep_admin_account=True):
    print("==========================================================")
    print("TRUNCATING ALL TABLES IN BOTH DATABASES")
    print("==========================================================")

    # 1. Truncate Target Database (HostelAttendance)
    print("\n1. Clearing all tables in target database 'HostelAttendance'...")
    db = TargetSessionLocal()
    try:
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

        # Reseed identity columns in HostelAttendance
        conn_target = pyodbc.connect(
            "Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=HostelAttendance;Trusted_Connection=yes;TrustServerCertificate=yes;",
            autocommit=True
        )
        cursor_target = conn_target.cursor()
        tables_to_reseed = [
            "dbo.StudentCurrentStatus",
            "dbo.ProcessedPunches",
            "dbo.RawPunches",
            "dbo.StudentHostelHistory",
            "dbo.Students",
            "dbo.Users",
            "dbo.Devices",
            "dbo.Hostels",
            "dbo.SystemEvents",
            "dbo.SyncCheckpoints"
        ]
        for tbl in tables_to_reseed:
            try:
                cursor_target.execute(f"DBCC CHECKIDENT ('{tbl}', RESEED, 0)")
            except Exception:
                pass
        conn_target.close()
        print("   -> Target database 'HostelAttendance' completely cleared and identity counters reseeded to 0.")

        # 2. Truncate Source Database (Epush_Dummy / Epush)
        print("\n2. Clearing 'DeviceLogs' table in source database 'Epush_Dummy'...")
        conn_epush = pyodbc.connect(
            "Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=Epush_Dummy;Trusted_Connection=yes;TrustServerCertificate=yes;",
            autocommit=True
        )
        cursor_epush = conn_epush.cursor()
        cursor_epush.execute("DELETE FROM dbo.DeviceLogs")
        try:
            cursor_epush.execute("DBCC CHECKIDENT ('dbo.DeviceLogs', RESEED, 0)")
        except Exception:
            pass
        conn_epush.close()
        print("   -> Source database 'Epush_Dummy.dbo.DeviceLogs' completely cleared and identity reseeded to 0.")

        # 3. Create Default Admin & IT Admin Accounts for System Login
        if keep_admin_account:
            print("\n3. Creating default System Admin and IT Admin accounts...")
            admin_user = User(
                Username="admin",
                PasswordHash=pwd_context.hash("admin123password"),
                Role="ADMIN",
                HostelId=None,
                IsActive=True
            )
            it_admin_user = User(
                Username="it_admin",
                PasswordHash=pwd_context.hash("itadminpassword"),
                Role="IT_ADMIN",
                HostelId=None,
                IsActive=True
            )
            db.add(admin_user)
            db.add(it_admin_user)

            # Initialize Checkpoint with 0
            checkpoint = SyncCheckpoint(
                SourceName="IT_SQL_SERVER",
                LastSourceDeviceLogId=0,
                LastSyncStatus="SUCCESS"
            )
            db.add(checkpoint)
            db.commit()
            print(f"   -> Created Master Admin user: 'admin' (password: admin123password)")
            print(f"   -> Created IT Admin user: 'it_admin' (password: itadminpassword)")
            print(f"   -> Initialized Sync Checkpoint (LastSourceDeviceLogId = 0)")

        print("\n==========================================================")
        print("ALL TABLES TRUNCATED & RESET SUCCESSFULLY!")
        print("==========================================================")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {str(e)}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    truncate_all_databases(keep_admin_account=True)
