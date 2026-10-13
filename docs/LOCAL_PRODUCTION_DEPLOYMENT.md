# Local server deployment

The application serves the built frontend and API from Uvicorn. No domain purchase is needed: users can access `http://SERVER_LAN_IP:8000`. Substitute the server's stable LAN address. This guide does not start services or change production records.

## Installation and configuration

Use Python 3.11 or newer and Node 24 for the verified build. From the project directory:

```powershell
python -m venv .venv-production
.\.venv-production\Scripts\python.exe -m pip install -r backend/requirements.lock
cd frontend
npm ci
npm run build
```

Keep existing backend/.env private. Set APP_ENV=production, ALLOWED_HOSTS=localhost,127.0.0.1,SERVER_LAN_IP and ALLOWED_ORIGINS=http://SERVER_LAN_IP:8000,http://localhost:8000. Hosts are bare addresses; origins include scheme and port. Production mode disables API documentation. Preserve the existing session duration.

A complete SOURCE_DATABASE_URL or TARGET_DATABASE_URL takes precedence over separate host/password/TLS fields. Existing URLs were not replaced. Newly constructed URLs default to encryption and certificate verification; existing full URLs need separate inspection before claiming verified SQL transport.

Do not run schema.sql, seed, reset, truncate, or checkpoint-reset scripts on existing production tables. Use the guarded database.migrate_production --inspect and --apply runner. It targets HostelAttendance, takes application locks, verifies unchanged existing row counts, and leaves new tables empty. Epush is never a migration target.

## Supervise services

Run the API and worker as separate Windows services through an approved service wrapper such as NSSM. Installation/restart needs Windows administrator access. Use the project directory as the working directory and D:\Hostel_Student_Tracker\.venv-production\Scripts\python.exe as the interpreter.

API arguments:

```text
-m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Worker arguments:

```text
-m sync_worker.sync_service
```

Start with one API process for the expected 15 users. Its target pool permits at most ten connections; the separate worker has its own pool. More processes multiply connection/report limits; verify capacity before increasing them. Enable restart on failure and log rotation. RUN_SYSTEM.bat is an interactive launcher, not a supervised service.

If IIS is used later, proxy API and WebSocket paths to Uvicorn, enable WebSockets, and bind Uvicorn to loopback behind the proxy. Do not run this ASGI application through wfastcgi. Verify dashboard updates through the actual proxy.

## Operational checks and remaining limits

HTTP exposes credentials and tokens to network traffic inspection. A trusted internal CA certificate or securely configured VPN can address this without a purchased domain/certificate. Certificate installation, client trust, and firewall changes have not been performed. Restrict access to the intended LAN and do not expose port 8000 through a public tunnel.

Verify SELECT-only Epush grants when administrative access is available. Application safeguards do not replace database permissions. Verify SQL memory headroom, disk capacity, backups/restore testing, and service identities; these have not been established.

Before switching services, verify the migration receipt, rebuild the frontend, and schedule a controlled restart. Check login/logout, warden scope, WebSockets, filtered exports, eligible-punch lag, and worker heartbeat. Normal runtime imports still update existing attendance tables; implementation/testing restrictions do not make the worker read-only.

Exports allow one generation per API process. Concurrent exports receive 429 with Retry-After. This is not a global job queue or point-in-time snapshot. The test receipts describe bounded workloads, not an all-day production soak.
