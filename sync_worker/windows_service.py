"""
Hostel Attendance Synchronization Service - Windows Service Runner
Can be installed as a native Windows Service using NSSM (Non-Sucking Service Manager)
or PyWin32.

Command to install via NSSM on Windows Server:
  nssm install HostelSyncWorker "C:\\Python311\\python.exe" "D:\\Hostel_Student_Tracker\\sync_worker\\sync_service.py"
  nssm set HostelSyncWorker AppDirectory "D:\\Hostel_Student_Tracker"
  nssm set HostelSyncWorker Start SERVICE_AUTO_START
  nssm start HostelSyncWorker
"""

import sys
import os
import time
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sync_worker.sync_service import start_worker_loop

if __name__ == "__main__":
    logging.info("Starting Hostel Attendance Sync Worker Windows Service...")
    try:
        start_worker_loop()
    except KeyboardInterrupt:
        logging.info("Sync Worker Service Stopped.")
