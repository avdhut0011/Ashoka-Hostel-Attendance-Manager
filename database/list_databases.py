import pyodbc

conn_str = "Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=master;Trusted_Connection=yes;TrustServerCertificate=yes;"

print("Connecting to master database on MISISC\\SQLEXPRESS...")
conn = pyodbc.connect(conn_str, autocommit=True)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sys.databases WHERE database_id > 4")
databases = [row[0] for row in cursor.fetchall()]

print("\n=== CURRENT DATABASES ON YOUR LOCAL SQL SERVER (MISISC\\SQLEXPRESS) ===")
if not databases:
    print("No user databases found.")
else:
    for db_name in databases:
        print(f" -> Database Name: '{db_name}'")

conn.close()
