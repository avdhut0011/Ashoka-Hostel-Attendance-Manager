import pyodbc

conn = pyodbc.connect('Driver={ODBC Driver 17 for SQL Server};Server=MISISC\\SQLEXPRESS;Database=master;Trusted_Connection=yes;TrustServerCertificate=yes;')
cursor = conn.cursor()
cursor.execute("SELECT name, physical_name FROM sys.master_files WHERE database_id > 4")

print("=== ALL USER DATABASES ON YOUR LOCAL SQL SERVER (MISISC\\SQLEXPRESS) ===")
rows = cursor.fetchall()
if not rows:
    print("No custom user databases found yet.")
else:
    for row in rows:
        print(f"Database/File Name: {row[0]}")
        print(f"File Path on Disk:  {row[1]}")
        print("-" * 70)

conn.close()
