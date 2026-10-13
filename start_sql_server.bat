@echo off
echo Starting SQL Server (SQLEXPRESS) and SQL Browser services...
net start "SQL Server (SQLEXPRESS)"
net start "SQLBrowser"
echo.
echo Checking Service Status...
sc query "MSSQL$SQLEXPRESS"
pause
