# Production update — 10 October 2026

## Database boundary and applied migration

During the initial implementation only the HostelAttendance target on MISISC\SQLEXPRESS was contacted. After explicit authorization, the October 8–10 recovery review read Epush using SELECT-only statements. Its connection settings were preserved and no source data or schema was modified. The source engine rejects data-changing statements, and development seed/reset utilities refuse SQL Server databases.

The initial target migration applied 18 schema statements: five nullable columns, four empty tables, and nine indexes. Existing data was neither seeded, backfilled, corrected, nor replayed. Row counts before/after are recorded in `database/migrations/20261010_applied.json`. A second inspection found zero pending schema statements. A later migration added four new review/notification tables and three indexes (seven statements), again preserving existing row counts. Current receipts are in database/migrations/latest_applied.json; initial counts below refer to the first migration.

| Existing table | Unchanged count |
|---|---:|
| Students | 4 |
| RawPunches | 36 |
| ProcessedPunches | 36 |
| StudentCurrentStatus | 4 |
| Users | 2 |
| Hostels / Devices | 1 / 1 |

New empty tables: AttendanceOverrides, PunchCorrections, StudentStateHistory, DeviceStateHistory. QuarantinedPunches already existed and remained empty.

Nullable additions: Students.EnrolledAt, ProcessedPunches.HostelIdSnapshot and RoomNoSnapshot, StudentCurrentStatus.CounterDate, Users.TokenVersion. Existing rows remain NULL in these new fields. No historical dates or assignments were invented.

## Preserved business rules

- First accepted biometric punch is REGISTRATION.
- Pending students remain registration-only and are excluded from active headcounts.
- Formal enrollment retains chronological recalculation of registration history. Subsequent accepted punches alternate IN/OUT, across calendar days as before.
- The configured 45-second duplicate window remains; same-device and same-hostel cross-device duplicates do not change attendance.
- Inactive students, invalid devices, and hostel mismatches do not affect attendance.
- Profile editing never enrolls/reactivates students or replays attendance. An already enrolled student cannot be enrolled again.

## Correctness and audit changes

The initial preservation/reprocessing behavior was superseded by the operator's active-device-only policy. Source queries now select only registered active device IDs in their current activation period. Device configuration no longer re-evaluates older invalid punches. Eligible raw logs and their checkpoint advance atomically with processing/quarantine outcomes.

Late punches replay the affected timeline chronologically with stable source-ID ordering. Replay updates derived records in place, preserving PunchIds and original raw data. Attendance writers share a transaction-owned SQL Server application lock. The synchronization session-owned lock uses a dedicated physical connection until release.

Manual overrides are separate immutable events with actor, reason, old/new states, effective time, and assignment snapshots. They survive timeline replay and appear in history and exports. Overrides do not masquerade as biometric punches.

Corrections reference original raw punches rather than replacing them. Quarantine payloads remain unchanged. Changing the identity of an already processed punch is refused pending an explicit correction review. Legacy manual states without a reconstructable event are protected: replay returns a conflict rather than silently erasing them.

Student and device state changes capture an effective history at the time of a real user operation. Existing processed assignment snapshots remain stable on transfers. Legacy rows without snapshots display unknown hostel/room. Hostel-filtered and warden reports exclude those unverified rows; administrators can review them in unfiltered history. No historic assignments were invented or backfilled.

Calendar-day boundaries use APP_TIMEZONE; naive biometric timestamps retain SOURCE_TIMEZONE wall-clock semantics. Both default to Asia/Kolkata. Aware correction timestamps are normalized on input. Counters reconcile existing punches when legacy CounterDate is NULL, and cross-midnight duplicates accumulate on the correct day.

## Access, reporting, and UI

Wardens without an active hostel are denied centrally. All report/export paths apply the same hostel scope. Account changes validate assignments, protect the last active admin, and revoke previous tokens after password/account changes.

Listings expose X-Total-Count and bounded pagination. The UI includes Previous/Next controls, error/stale-data notices, and cancellation of superseded requests. Report filters are shared across lists and exports. Exports have no 1,000/2,000-row cutoff, use bounded temporary storage, include matching manual overrides, and escape spreadsheet formula inputs.

The old unused WebSocket path was removed. The new authenticated /api/dashboard/live endpoint now sends refresh notifications from committed attendance changes, with HTTP polling as a disconnected fallback. Monitoring considers synchronization freshness and failure/quarantine status. Login throttling is process-local; deployments with multiple workers should additionally enforce shared limits at the reverse proxy.

Static file paths must resolve inside the frontend directory. Hardcoded credentials and default secrets were removed. The local placeholder JWT secret was replaced with a random secret without printing it; users must sign in again after the backend restarts.

## Verification and rollout

The final backend suite passed 65 tests. Two frontend India-time tests passed with America/Los_Angeles as the process timezone. The frontend production build succeeded.

Tests run only on disposable in-memory SQLite databases, with all SQL Server test connections blocked. Coverage includes original punch rules, enrollment, late punches, midnight duplicates, source write prevention, GET purity, warden isolation, device recovery, overrides, corrections, historical assignments, complete CSV/Excel export, token revocation, and static-path boundaries.

No live synchronization or production load test was run. A uniquely named disposable SQL Server database was created for transaction-lock concurrency, duplicate-punch serialization, and rollback checks, then removed. All three checks passed. These initial probes were followed by the full worker and 50-user tests documented below. Production table data and Epush were not accessed by the verifier. Receipt: database/migrations/sqlserver_test_receipt.json.

The backend was not restarted and the worker was not started. Restart the backend in the normal maintenance window to load the updated code and JWT secret. Start/restart the worker only when ready for ordinary production ingestion; that operation naturally imports new biometric records into the target. No historical backfill is automatic.

Future schema updates: use `python -m database.migrate_production --inspect` followed by `--apply`. Duplicate existing records or busy locks cause the migration to abort without deleting records. The generated SQL is a review artifact; the Python runner performs the transactional preconditions.

## Additional verification and remaining limits

Dashboard requests are serialized and canceled on unmount; the student-history popup now has pagination. Punch and sync API timestamps include explicit timezone offsets. The load tester supports mixed account scenarios and expected attendance/permission checks using LOAD_TEST_SCENARIOS_FILE; these correctness scenarios were not run against production. Each account scenario contains username, password, and checks with path, status, expected fields, or expected_ids plus id_field. Keep credentials outside version control.

Existing HostelAttendance records were not inserted, updated, deleted, or backfilled during this work. Epush remains untouched. The backend and worker were not started. Ordinary runtime writes remain part of the application business logic, so starting ingestion or invoking write endpoints would modify existing target tables and requires a separately authorized rollout. Skipped punches now have a separate recovery-review flow. The authorized October 8–10 scan found no missing candidates for existing students. Full synchronization-cycle SQL Server concurrency, mixed-role 50-user correctness, and cross-process push tests have passed in a disposable database.

## Issue 10 completed: India time and read-only daily counters

The user confirmed that biometric records are India wall-clock timestamps. APP_TIMEZONE and SOURCE_TIMEZONE accept Asia/Kolkata (the Asia/Calcutta alias is normalized); conflicting timezone configuration fails validation. Punch timestamps retain their original database values. Source timestamps receive +05:30 in JSON; UTC audit timestamps receive +00:00. All frontend timestamp displays explicitly format Asia/Kolkata, including sync health, quarantine, manual attendance events, and refresh timestamps. Correction inputs convert timestamps into India wall-clock values. Export timestamps are labeled Asia/Kolkata. New student registration dates use the India calendar date.

Student list, detail and write-response DTOs expose TodayInCount, TodayOutCount, TodayValidPunchCount and TodayDuplicatePunchCount, calculated from existing processed punches in a single bulk SELECT for each page. IN/OUT totals count only VALID biometric events; manual overrides remain separate and do not count as biometric punches. The dashboard already derives today's totals directly from processed punches. Stored legacy counter caches remain unchanged and are not used to determine API daily totals. At midnight, the next read selects the new India-day window and returns zero if there are no punches, without any database reset job or writes. Current IN/OUT location continues across midnight according to existing business logic.

Boundary tests cover 23:59:59, 00:00:00, the exclusive next-midnight limit, duplicates, invalid punches, stale cached counters, a day with no punches, GET purity and browser-timezone independence. No database migration or production connection was needed for this update. Backend/worker services were not restarted.

## Remaining five issues: final verification

Issue 2: RecoveryScans and RecoveryPunches plus an admin/IT review page were added. The authorized 2026-10-08 through 2026-10-10 scan checked 5,397 records below the captured checkpoint (1,271,853): 37 already-imported punches, 5,360 unknown-student punches excluded, and zero missing candidates for existing students. The scan completed. No existing punch, checkpoint, student, or user record was changed. Review status changes affect only the new review table and never trigger attendance import.

Issue 5: The SQL Server test runs a separate worker process, pauses it after a committed batch, verifies another worker cannot acquire its cycle lock, and reprocesses a punch concurrently. It checks late ordering, stable PunchIds, immutable raw data, simultaneous manual override/replay, failed-batch rollback and checkpoint retry. All checks passed.

Issue 11: Existing student 8001 already has current room 2 and three legacy assignment rows. The operator-confirmed room 1 → 2 transition on 2026-10-10 was stored only in the new VerifiedRoomChanges table. Its EffectiveAt remains NULL, preserving DATE_ONLY precision. The student profile, old history, original punches and snapshots were not updated. Future timeline replay also preserves NULL legacy snapshots rather than replacing unknown assignments with current profile values. Unverified older assignments and the exact room on the change date remain unknown unless a snapshot or captured exact state provides evidence.

Issue 17: New AttendanceChanges entries are written in the same transaction as real attendance/profile changes; rollback removes the notification. A shared per-process task checks count plus maximum identity once a second, which also catches transactions committing out of identity order. It sends generic invalidations over authenticated WebSockets; clients fetch data using the existing scoped APIs. Tokens never appear in URLs, origins are checked, and authentication/warden assignment is revalidated before each message. Heartbeats, reconnect backoff, HTTP fallback, serialized refreshes and India-midnight refresh are included. Vite proxies WebSocket upgrades. A separate worker process triggered a real WebSocket refresh during the SQL Server test, and token revocation closed the connection.

Issue 20: Fifty simultaneous isolated accounts across ADMIN, IT_ADMIN, MANAGEMENT and both WARDEN hostel scopes performed 150 correctness iterations. Each iteration validated summary/current status, daily counters, scoped student/punch lists, complete CSV exports including overrides, and user-management permissions. Reads left current-state records and change notifications unchanged. All checks passed. Each iteration contains five API requests; mean iteration duration was 3,703.5 ms and p95 was 5,286.3 ms. This was a short correctness test on the local SQL Server, not a sustained production throughput benchmark.

All disposable test databases were removed. Evidence: database/migrations/attendance_sqlserver_test_receipt.json and database/migrations/production_review_receipt.json. The production review compared row counts and SHA-256 fingerprints of all pre-existing application table contents before/after, confirming no existing records changed during that operation. No synthetic student/user data was created in production. The production backend and worker were not restarted; the finished push/review endpoints become available after a separately authorized service restart.

## Latest policy clarification: active matching device IDs only

The operator explicitly requires matching active DeviceIds from HostelAttendance.Devices and Epush.DeviceLogs_Processed, and punches from activation onward only. The worker now applies that filter in the source SELECT before any target raw/quarantine insertion. Every new device registration captures a DeviceStateHistory entry; reactivation uses the beginning of the latest continuous active period. Name/hostel edits and repeated active requests preserve the cutoff. Source LogDate is compared in India time, including the activation instant and excluding earlier late arrivals. No earlier punches are automatically recovered into review tables when a device becomes active. The review scanner and quarantine reprocessing also enforce the active-ID/time boundary.

Existing active devices without historical activation metadata retain the normal checkpoint behavior. No past activation date was invented. Device status should be managed through the application; a contradictory active flag/history is rejected and logged, requiring the status to be recorded correctly through the Devices page. No old production table records or activation histories were backfilled during this update. No schema migration was needed.

The worker holds the attendance transaction lock across the active-device snapshot, source query, batch processing and checkpoint commit. Device updates use that same lock; source selection and activation cannot race. Lists are split into 500-device query groups and merged by DeviceLogId, avoiding SQL Server parameter limits. Unmatched/inactive devices produce neither raw nor quarantine records. Existing imported history remains unchanged by registration or activation.

Final verification: 65 isolated backend tests passed and the frontend build passed. The SQL Server verifier additionally created exactly 116 active device IDs with individual activation cutoffs, checked matching-only ingestion (including an exact-boundary punch and exclusions for inactive, unknown and pre-activation rows), then paused a separate worker's source query and verified an activation request waited until its transaction completed. After activation, a pre-activation punch was excluded and a punch at the recorded activation time was imported. All eight SQL Server checks passed, including the existing 50-user, concurrency and push tests. Latest 50-user iteration metrics: mean 2,289.2 ms, p95 3,297.2 ms for five requests per iteration. These remain short correctness-run measurements.

The disposable database was removed. No production records were read or changed by these tests; Epush was not connected to for this policy update. The production backend and worker were not restarted. Both must load the updated code together before the new activation rule is enforced in the running system. Evidence: database/migrations/attendance_sqlserver_test_receipt.json.
