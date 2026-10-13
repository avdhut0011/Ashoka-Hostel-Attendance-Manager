# Hostel Attendance Management System

FastAPI, React, SQLAlchemy, and SQL Server application for hostel biometric attendance.

## Production database boundary

- The biometric source is SELECT-only. Application code never creates, seeds, updates, or deletes source records.
- All application writes belong to `HostelAttendance`.
- Production updates use schema-only migrations. No demo accounts, historical backfill, or attendance replay runs during deployment.
- Development data/reset utilities are blocked against SQL Server.

## Attendance rules

First accepted punch is REGISTRATION. Pending students remain in registration until enrollment. Formal enrollment recalculates earlier punches chronologically using the established registration/IN/OUT rules. Ordinary profile edits never replay attendance or activate students. Further accepted punches alternate IN and OUT, including across days. Duplicates within the configured window do not change attendance. Device, hostel, and student validation apply before attendance.

Late punches replay the affected student's timeline in one transaction. Existing processed IDs, manual override events, raw punches, and correction audit records are preserved. Source queries import only IDs registered as active in Devices. New registration and reactivation record an India-time boundary in DeviceStateHistory; punches earlier than the current activation period are excluded. Device activation does not replay previously imported invalid punches.

## Configuration

Set `backend/.env` using `.env.example`. Full DATABASE_URL settings take precedence over individual connection fields. JWT_SECRET must be a random secret of at least 32 characters. No credentials are embedded in source code.

Biometric timestamps and attendance calendar days use Asia/Kolkata. Conflicting timezone configuration is rejected. API counters are calculated from punches in the current India-day window without resetting stored records.

## Schema updates

From the repository root:

```powershell
python -m database.migrate_production --inspect
python -m database.migrate_production --apply
```

The migration verifies the target database identity, obtains application locks, rejects duplicate processed-punch groups, adds nullable columns/indexes/empty tables, and checks existing row counts before committing. It imports no source engine and never opens a source connection. Receipts are saved under `database/migrations`.

For a fresh empty target, execute `database/schema.sql` against HostelAttendance first. No seeding is required or performed.

## Verification

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest backend/tests -q
```

Tests use only in-memory SQLite databases and explicitly reject SQL Server connections. Test fixtures never seed production. Run `npm run build` inside `frontend` to build the UI.

## Running

```powershell
python -m backend.app.core.health_check
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Start the sync worker separately only when ready for normal production ingestion:

```powershell
python -m sync_worker.sync_service
```

The dashboard receives authenticated WebSocket invalidations and refreshes scoped HTTP endpoints when attendance changes. A shared server task checks committed notifications once per second, including changes from the separate worker and India midnight. Ten-second HTTP polling is used only while the socket is disconnected. Reports and lists use pagination; exports include all matching records and matching manual overrides. Legacy records without verified assignment snapshots are clearly identified.

Read [the production update notes](docs/PRODUCTION_UPDATE_20261010.md) for verification evidence and rollout details.

## Recovery review and verified history

Administrators and IT administrators can open **Skipped Punch Review**. Scans read matching active devices in their current activation period for a selected date range up to the saved synchronization checkpoint. Only missing punches for existing students are stored in the new RecoveryPunches table. Unknown students are excluded, quarantined/imported punches are skipped, and repeated scans do not duplicate candidates. Long scans can be resumed. Marking a record reviewed or ignored never imports attendance or modifies existing tables.

Operator-confirmed room changes are stored in VerifiedRoomChanges with their evidence and time precision. Historical punch snapshots take precedence. A date-only room change leaves that day's room unknown when no snapshot or captured exact state exists; earlier unknown history is not guessed. The student-history popup shows confirmed changes and historical rooms.

## Disposable SQL Server verification

```powershell
python -B -m database.verify_attendance_sqlserver
```

This creates a uniquely named HostelAttendance_Test database on the configured target server, runs worker concurrency and 50 simultaneous mixed-role user checks, verifies cross-process push and token revocation, then removes the database. It never connects to Epush or reads/writes production tables. SQL Server test mode rejects the production database name. The receipt is saved in database/migrations/attendance_sqlserver_test_receipt.json. The load metrics measure short correctness runs, not a sustained capacity guarantee.

## Active-device ingestion policy

If Devices contains 116 active IDs, only those IDs are included in the source query. Inactive and unregistered device IDs are excluded before raw-punch or quarantine insertion. An activation boundary uses the biometric LogDate in Asia/Kolkata, not the download/arrival time. Punches exactly at the boundary are eligible; late arrivals with an earlier punch time are excluded. Each reactivation starts a new allowed period. Name/hostel edits and repeated active-status requests do not reset that period.

Manage registration and activation through the Devices page so the application records the activation time. Existing continuously active devices without recorded history continue from the current synchronization checkpoint; no historical activation time is invented or backfilled. An active flag inconsistent with recorded state history fails synchronization instead of silently treating the worker as healthy. Quarantine reprocessing and recovery review enforce the same active-ID and activation-period restrictions. Previously stored historical records are preserved.

The source query, batch writes and checkpoint share the device-status transaction lock, preventing activation/deactivation from racing past the worker's source selection. Large device lists are split into groups of 500 to stay below SQL Server's parameter limit, with rows merged in source-ID order. Existing first-punch, duplicate, enrollment and IN/OUT rules remain unchanged for eligible punches.

Restart the updated backend and worker together to activate the new policy. Neither service is automatically restarted by these implementation or verification commands. No additional database schema migration is needed: DeviceStateHistory already exists.
