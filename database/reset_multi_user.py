from pathlib import Path as _GuardPath
import sys as _guard_sys
_guard_sys.path.insert(0, str(_GuardPath(__file__).resolve().parents[1]))
from database.safety import require_development_data_operation
require_development_data_operation(sql_server_utility=True)

import pyodbc

conn_str = "Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=master;Trusted_Connection=yes;TrustServerCertificate=yes;"
conn = pyodbc.connect(conn_str, autocommit=True)
cursor = conn.cursor()

try:
    cursor.execute("ALTER DATABASE HostelAttendance SET MULTI_USER WITH ROLLBACK IMMEDIATE")
    print("Database 'HostelAttendance' set to MULTI_USER mode.")
except Exception as e:
    print(f"HostelAttendance multi_user note: {e}")

try:
    cursor.execute("ALTER DATABASE Epush_Dummy SET MULTI_USER WITH ROLLBACK IMMEDIATE")
    print("Database 'Epush_Dummy' set to MULTI_USER mode.")
except Exception as e:
    print(f"Epush_Dummy multi_user note: {e}")

conn.close()
