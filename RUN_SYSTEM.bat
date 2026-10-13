@echo off
setlocal
cd /d "%~dp0"
title Hostel Attendance - Interactive Local Launcher
set "APP_PYTHON=%~dp0.venv-production\Scripts\python.exe"
if not exist "%APP_PYTHON%" (
    echo Missing patched environment. Follow docs\LOCAL_PRODUCTION_DEPLOYMENT.md.
    pause
    exit /b 1
)
"%APP_PYTHON%" -m backend.app.core.health_check
if errorlevel 1 (
    echo Pre-flight check failed. No services were started.
    pause
    exit /b 1
)
echo This interactive launcher is for local operation. Use supervised Windows services for production.
echo Normal worker operation imports attendance. This launcher does not seed or migrate databases.
start "Hostel Sync Worker" "%APP_PYTHON%" -m sync_worker.sync_service
start "Hostel Web Server" "%APP_PYTHON%" -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1
echo Dashboard: http://localhost:8000
echo Keep the worker and server windows open. Stop both before restarting.
pause
