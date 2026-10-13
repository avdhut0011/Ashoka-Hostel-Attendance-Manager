from pathlib import Path as _GuardPath
import sys as _guard_sys
_guard_sys.path.insert(0, str(_GuardPath(__file__).resolve().parents[1]))
from database.safety import require_development_data_operation
require_development_data_operation(sql_server_utility=True)

import pyodbc
from datetime import datetime, timedelta, date

print("Connecting to local MS SQL Server (MISISC\\SQLEXPRESS)...")

# 1. Target Database (HostelAttendance)
target_conn_str = "Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=HostelAttendance;Trusted_Connection=yes;TrustServerCertificate=yes;"
t_conn = pyodbc.connect(target_conn_str, autocommit=True)
t_cursor = t_conn.cursor()

print("Creating Schemas: master, integration, attendance, security, system...")
schemas = ["master", "integration", "attendance", "security", "system"]
for s in schemas:
    t_cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = '{s}') EXEC('CREATE SCHEMA {s}')")

print("Applying Production Database Schema & Tables...")
with open("database/schema.sql", "r", encoding="utf-8") as f:
    sql_script = f.read()

batches = [b.strip() for b in sql_script.split("\nGO\n") if b.strip()]
for batch in batches:
    try:
        t_cursor.execute(batch)
    except Exception as e:
        pass

print("Seeding Master Data (Hostels, Devices, Students, Users)...")

admin_hash = "$2b$12$UFfiJc2EnRBCMwsxHyMiCeok8yh/Lp20AERu9hPqumSBCkUrwgDgS"
warden_hash = "$2b$12$UFfiJc2EnRBCMwsxHyMiCeok8yh/Lp20AERu9hPqumSBCkUrwgDgS"
itadmin_hash = "$2b$12$UFfiJc2EnRBCMwsxHyMiCeok8yh/Lp20AERu9hPqumSBCkUrwgDgS"

t_cursor.execute("IF NOT EXISTS (SELECT * FROM security.Users WHERE Username = 'admin') INSERT INTO security.Users (Username, PasswordHash, Role, IsActive) VALUES ('admin', '" + admin_hash + "', 'ADMIN', 1)")
t_cursor.execute("IF NOT EXISTS (SELECT * FROM security.Users WHERE Username = 'warden_a') INSERT INTO security.Users (Username, PasswordHash, Role, IsActive) VALUES ('warden_a', '" + warden_hash + "', 'WARDEN', 1)")
t_cursor.execute("IF NOT EXISTS (SELECT * FROM security.Users WHERE Username = 'it_admin') INSERT INTO security.Users (Username, PasswordHash, Role, IsActive) VALUES ('it_admin', '" + itadmin_hash + "', 'IT_ADMIN', 1)")

# Seed Hostels
t_cursor.execute("IF NOT EXISTS (SELECT * FROM master.Hostels WHERE HostelCode = 'HA-BOYS') INSERT INTO master.Hostels (HostelName, HostelCode, IsActive) VALUES ('Hostel A - Boys Block', 'HA-BOYS', 1)")
t_cursor.execute("IF NOT EXISTS (SELECT * FROM master.Hostels WHERE HostelCode = 'HB-GIRLS') INSERT INTO master.Hostels (HostelName, HostelCode, IsActive) VALUES ('Hostel B - Girls Block', 'HB-GIRLS', 1)")

# Get Hostel IDs
t_cursor.execute("SELECT HostelId FROM master.Hostels WHERE HostelCode = 'HA-BOYS'")
hostel_a_id = t_cursor.fetchone()[0]

t_cursor.execute("SELECT HostelId FROM master.Hostels WHERE HostelCode = 'HB-GIRLS'")
hostel_b_id = t_cursor.fetchone()[0]

# Seed Devices
t_cursor.execute(f"IF NOT EXISTS (SELECT * FROM master.Devices WHERE DeviceId = 101) INSERT INTO master.Devices (DeviceId, DeviceName, HostelId, IsActive) VALUES (101, 'Main Gate Boys Scanner', {hostel_a_id}, 1)")
t_cursor.execute(f"IF NOT EXISTS (SELECT * FROM master.Devices WHERE DeviceId = 102) INSERT INTO master.Devices (DeviceId, DeviceName, HostelId, IsActive) VALUES (102, 'Main Gate Girls Scanner', {hostel_b_id}, 1)")
t_cursor.execute(f"IF NOT EXISTS (SELECT * FROM master.Devices WHERE DeviceId = 103) INSERT INTO master.Devices (DeviceId, DeviceName, HostelId, IsActive) VALUES (103, 'Disabled Gate Scanner', {hostel_a_id}, 0)")

# Seed Students
reg_date = date.today() - timedelta(days=10)
t_cursor.execute(f"IF NOT EXISTS (SELECT * FROM master.Students WHERE UserId = 'U1001') INSERT INTO master.Students (UserId, StudentName, HostelId, RoomNo, RegistrationDate, RegistrationStatus) VALUES ('U1001', 'John Doe', {hostel_a_id}, '101', '{reg_date}', 'ACTIVE')")
t_cursor.execute(f"IF NOT EXISTS (SELECT * FROM master.Students WHERE UserId = 'U1002') INSERT INTO master.Students (UserId, StudentName, HostelId, RoomNo, RegistrationDate, RegistrationStatus) VALUES ('U1002', 'Jane Smith', {hostel_b_id}, '202', '{reg_date}', 'ACTIVE')")
t_cursor.execute(f"IF NOT EXISTS (SELECT * FROM master.Students WHERE UserId = 'U1003') INSERT INTO master.Students (UserId, StudentName, HostelId, RoomNo, RegistrationDate, RegistrationStatus, DeactivatedAt, DeactivationReason) VALUES ('U1003', 'Robert Brown', {hostel_a_id}, '103', '{reg_date}', 'INACTIVE', GETDATE(), 'Graduated')")

# Seed Checkpoint
t_cursor.execute("IF NOT EXISTS (SELECT * FROM integration.SyncCheckpoint WHERE SourceName = 'IT_SQL_SERVER') INSERT INTO integration.SyncCheckpoint (SourceName, LastSourceDeviceLogId, LastSyncStatus) VALUES ('IT_SQL_SERVER', 0, 'NEVER_RUN')")

t_conn.close()
print("Target Database 'HostelAttendance' configured and seeded successfully!")

# 2. Source Database (Epush_Dummy)
print("Configuring Source IT Database...")
try:
    source_conn_str = "Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=Epush_Dummy;Trusted_Connection=yes;TrustServerCertificate=yes;"
    s_conn = pyodbc.connect(source_conn_str, autocommit=True)
except Exception:
    print("Database 'Epush_Dummy' not found on SQL Server. Using 'HostelAttendance' as source database...")
    source_conn_str = "Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=HostelAttendance;Trusted_Connection=yes;TrustServerCertificate=yes;"
    s_conn = pyodbc.connect(source_conn_str, autocommit=True)

s_cursor = s_conn.cursor()
s_cursor.execute("""
IF OBJECT_ID('dbo.DeviceLogs', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DeviceLogs (
        DeviceLogId BIGINT IDENTITY(1,1) PRIMARY KEY,
        DownloadDate DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        DeviceId INT NOT NULL,
        UserId NVARCHAR(50) NOT NULL,
        LogDate DATETIME2 NOT NULL
    )
END
""")

s_cursor.execute("SELECT COUNT(*) FROM dbo.DeviceLogs")
count = s_cursor.fetchone()[0]
if count == 0:
    print("Seeding initial biometric punches into dbo.DeviceLogs...")
    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)
    two_days_ago = now - timedelta(days=2)

    punches = [
        (datetime.utcnow(), 101, 'U1001', two_days_ago.replace(hour=8, minute=0, second=0)),
        (datetime.utcnow(), 101, 'U1001', yesterday.replace(hour=7, minute=30, second=0)),
        (datetime.utcnow(), 101, 'U1001', yesterday.replace(hour=20, minute=0, second=0)),
        (datetime.utcnow(), 101, 'U1001', now.replace(hour=8, minute=15, second=0)),
        (datetime.utcnow(), 101, 'U1001', now.replace(hour=8, minute=15, second=20)),
        (datetime.utcnow(), 102, 'U1002', yesterday.replace(hour=9, minute=0, second=0)),
        (datetime.utcnow(), 102, 'U1002', now.replace(hour=7, minute=45, second=0)),
        (datetime.utcnow(), 101, 'U1003', now.replace(hour=9, minute=0, second=0)),
        (datetime.utcnow(), 101, 'U1004', now.replace(hour=10, minute=0, second=0)),
        (datetime.utcnow(), 103, 'U1001', now.replace(hour=11, minute=0, second=0)),
    ]
    for p in punches:
        s_cursor.execute("INSERT INTO dbo.DeviceLogs (DownloadDate, DeviceId, UserId, LogDate) VALUES (?, ?, ?, ?)", p)
    print(f"Seeded {len(punches)} biometric punches in dbo.DeviceLogs.")

s_conn.close()

print("\n==========================================================================")
print("SUCCESS! YOUR LOCAL MS SQL SERVER (MISISC\\SQLEXPRESS) IS 100% POPULATED & SEEDED!")
print("==========================================================================")
