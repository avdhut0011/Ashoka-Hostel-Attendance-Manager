from pathlib import Path as _GuardPath
import sys as _guard_sys
_guard_sys.path.insert(0, str(_GuardPath(__file__).resolve().parents[1]))
from database.safety import require_development_data_operation
require_development_data_operation(sql_server_utility=True)

import pyodbc
from datetime import datetime, timedelta

conn_str = "Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=Epush_Dummy;Trusted_Connection=yes;TrustServerCertificate=yes;"

print("Connecting to 'Epush_Dummy' database on local MS SQL Server (MISISC\\SQLEXPRESS)...")
conn = pyodbc.connect(conn_str, autocommit=True)
cursor = conn.cursor()

# 1. Create table dbo.DeviceLogs
print("Creating table dbo.DeviceLogs...")
cursor.execute("""
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
print("Table 'dbo.DeviceLogs' created successfully.")

# 2. Seed initial biometric punches if empty
cursor.execute("SELECT COUNT(*) FROM dbo.DeviceLogs")
count = cursor.fetchone()[0]

if count == 0:
    print("Seeding 10 raw biometric punches into Epush_Dummy.dbo.DeviceLogs...")
    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)
    two_days_ago = now - timedelta(days=2)

    punches = [
        (datetime.utcnow(), 101, 'U1001', two_days_ago.replace(hour=8, minute=0, second=0)),
        (datetime.utcnow(), 101, 'U1001', yesterday.replace(hour=7, minute=30, second=0)),
        (datetime.utcnow(), 101, 'U1001', yesterday.replace(hour=20, minute=0, second=0)),
        (datetime.utcnow(), 101, 'U1001', now.replace(hour=8, minute=15, second=0)),
        (datetime.utcnow(), 101, 'U1001', now.replace(hour=8, minute=15, second=20)), # Duplicate
        (datetime.utcnow(), 102, 'U1002', yesterday.replace(hour=9, minute=0, second=0)),
        (datetime.utcnow(), 102, 'U1002', now.replace(hour=7, minute=45, second=0)),
        (datetime.utcnow(), 101, 'U1003', now.replace(hour=9, minute=0, second=0)), # Inactive
        (datetime.utcnow(), 101, 'U1004', now.replace(hour=10, minute=0, second=0)), # New student
        (datetime.utcnow(), 103, 'U1001', now.replace(hour=11, minute=0, second=0)), # Invalid device
    ]

    for p in punches:
        cursor.execute("INSERT INTO dbo.DeviceLogs (DownloadDate, DeviceId, UserId, LogDate) VALUES (?, ?, ?, ?)", p)

    print("Seeded 10 raw biometric punches successfully.")
else:
    print(f"Table dbo.DeviceLogs already contains {count} records.")

conn.close()
print("\nSUCCESS! Table 'dbo.DeviceLogs' is created and seeded inside 'Epush_Dummy' database!")
