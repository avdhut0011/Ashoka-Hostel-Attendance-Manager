from pathlib import Path as _GuardPath
import sys as _guard_sys
_guard_sys.path.insert(0, str(_GuardPath(__file__).resolve().parents[1]))
from database.safety import require_development_data_operation
require_development_data_operation(sql_server_utility=True)

import os
import sys
from datetime import datetime, timedelta
import pyodbc

# Ensure root workspace is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.core.database import TargetSessionLocal
from backend.app.models.master import Student, Device, Hostel
from backend.app.models.attendance import ProcessedPunch, StudentCurrentStatus
from sync_worker.sync_service import run_synchronization_cycle

def seed_next_punches():
    print("==========================================================")
    print("Generating Next Biometric Punches for Enrolled Students...")
    print("==========================================================")

    db = TargetSessionLocal()
    stu1001 = db.query(Student).filter_by(UserId="STU1001").first()
    stu1002 = db.query(Student).filter_by(UserId="STU1002").first()

    # Determine matching devices based on assigned hostels
    dev1 = db.query(Device).filter_by(HostelId=stu1001.HostelId).first() if stu1001 and stu1001.HostelId else None
    dev2 = db.query(Device).filter_by(HostelId=stu1002.HostelId).first() if stu1002 and stu1002.HostelId else None

    device_id_1001 = dev1.DeviceId if dev1 else 102
    device_id_1002 = dev2.DeviceId if dev2 else 101

    print(f"Student STU1001 ({stu1001.StudentName if stu1001 else 'N/A'}) -> Assigned Device {device_id_1001}")
    print(f"Student STU1002 ({stu1002.StudentName if stu1002 else 'N/A'}) -> Assigned Device {device_id_1002}")
    db.close()

    # 1. Insert 2 punches into Epush_Dummy
    conn = pyodbc.connect(
        "Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=Epush_Dummy;Trusted_Connection=yes;TrustServerCertificate=yes;",
        autocommit=True
    )
    cursor = conn.cursor()
    now = datetime.utcnow()
    cursor.execute(
        "INSERT INTO dbo.DeviceLogs (DownloadDate, DeviceId, UserId, LogDate) VALUES (?, ?, ?, ?)",
        (now, device_id_1001, "STU1001", now)
    )
    cursor.execute(
        "INSERT INTO dbo.DeviceLogs (DownloadDate, DeviceId, UserId, LogDate) VALUES (?, ?, ?, ?)",
        (now, device_id_1002, "STU1002", now)
    )
    conn.close()
    print("\n1. Inserted 2 new punches into Epush_Dummy.dbo.DeviceLogs.")

    # 2. Trigger Biometric Sync Cycle
    print("\n2. Executing Biometric Synchronization Engine...")
    sync_result = run_synchronization_cycle()
    print(f"   -> Sync Result: {sync_result}")

    # 3. Verify Updated Statuses
    verify_db = TargetSessionLocal()
    print("\n==========================================================")
    print("PUNCH VERIFICATION RESULTS:")
    print("==========================================================")
    for uid in ["STU1001", "STU1002"]:
        s = verify_db.query(Student).filter_by(UserId=uid).first()
        cs = verify_db.query(StudentCurrentStatus).filter_by(StudentId=s.StudentId).first() if s else None
        last_punch = verify_db.query(ProcessedPunch).filter_by(StudentId=s.StudentId).order_by(ProcessedPunch.LogDate.desc()).first() if s else None
        print(f"Student: {s.StudentName} (UserId: {s.UserId})")
        print(f"  - Current Status: {cs.CurrentStatus if cs else 'N/A'}")
        print(f"  - Last Punch Type: {last_punch.PunchType if last_punch else 'N/A'}")
        print(f"  - Last Punch Time: {last_punch.LogDate if last_punch else 'N/A'}")
        print(f"  - Processing Status: {last_punch.ProcessingStatus if last_punch else 'N/A'}")
        print(f"  - Today IN Count: {cs.TodayInCount if cs else 0} | Today OUT Count: {cs.TodayOutCount if cs else 0}")
        print("----------------------------------------------------------")
    verify_db.close()

if __name__ == "__main__":
    seed_next_punches()
