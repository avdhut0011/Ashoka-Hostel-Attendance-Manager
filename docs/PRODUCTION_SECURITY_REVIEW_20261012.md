# Production security and performance review

**Implementation follow-up:** See [Production hardening](PRODUCTION_HARDENING_20261012.md) for subsequent changes, new test evidence, and remaining release work. Findings below record the original review state.

**Review date:** 12 October 2026. **Expected workload:** 15 simultaneous users, with attendance history growing beyond one million rows.

**Decision:** complete the high-priority security and reliability work below before an unrestricted production rollout. Existing tests support functional correctness and a short 15-user workload; they do not certify sustained production capacity or absence of vulnerabilities.

## Scope and boundaries

Reviewed frontend navigation, authentication, request handling, lists, exports and live updates; backend authentication/authorization, account management, student enrollment, attendance processing, reporting, devices, recovery and monitoring; synchronization selection, transactions, locks, checkpointing and replay; models/index declarations, configuration, maintenance guards, deployment scripts, dependencies and existing test evidence.

This was a source/configuration review with isolated tests, a frontend build, npm advisory checks and primary-source advisory verification. No production database connection, source scan, live penetration test, service restart, account creation, migration or production load test was performed. No application source fixes were applied during this review. The frontend build regenerated the existing build output.

The SQL Server edition, RAM, server-side encryption, grants, firewall, live IIS configuration, deployed process count, installed Windows service identity and backup restoration status were not inspected. Local settings may differ from environment variables supplied to a deployed service. Python dependency findings below cover selected installed application packages, not a complete pip-audit run; pip-audit is not installed.

## Evidence collected

| Check | Result |
|---|---|
| Current backend regression tests | 90 passed in isolated in-memory databases; production connections forbidden |
| Current frontend production build | Passed; JavaScript bundle about 379 kB, about 105 kB gzip |
| npm audit, complete dependency tree | 12 affected package entries: 7 high and 5 moderate; zero critical entries reported |
| npm audit, production dependencies only | 2 moderate entries: react-router and react-router-dom, sharing underlying advisories |
| Local configuration loaded without opening databases | APP_ENV development; token lifetime 1,440 minutes; localhost HTTP origins |
| Local database URL options, secrets omitted | ODBC Driver 17; Encrypt not explicitly set; TrustServerCertificate yes on source and target |
| Replay-shaped query compiled for MSSQL, without executing it | 2,101 IDs produced 2,101 bound parameters |
| Root source packaging protection | No root .gitignore; backend/.env and local database files present |

Audit counts describe packages and dependency chains, not 12 independent exploitable vulnerabilities. Development-tool findings are distinct from vulnerabilities in the deployed static bundle.

### Existing million-row evidence, not repeated in this review

The 10 October disposable SQL Server test used 1,000 synthetic students, one million raw punches, one million processed punches, and 15 concurrent accounts. All 135 requests passed. Its concurrent phase lasted **12.21 seconds**.

| Endpoint / operation | Average | 95th percentile |
|---|---:|---:|
| Dashboard summary under 15-user traffic | 46.8 ms | 106.0 ms |
| Student list under 15-user traffic | 154.5 ms | 297.3 ms |
| Punch pages under 15-user traffic | 3,393.9 ms | 5,198.7 ms |
| Full million-row CSV plus test validation | 33.48 seconds | Not measured |

The last page alone took 4.899 seconds. The earlier 50-user test failed with SQL Server error 701 while executing a count query. That failure does not establish a specific hardware or configuration cause.

The 15-user benchmark used in-process TestClient, already-issued tokens, historical data and no current-day punches. It did not measure login hashing, sustained WebSockets, worker ingestion, concurrent exports, the newly added Detailed Student Lists, browser rendering, deployed HTTP/proxy overhead or multi-process pool behavior. These limits matter before calling the production system smooth under load.

## High-priority findings

### H1. Windows static-file resolution can initiate outbound SMB before rejecting a path

**Evidence:** `backend/app/main.py:65` mounts Starlette StaticFiles, and `main.py:99` calls `os.path.realpath` on a path derived from a request before checking containment. Installed Starlette is 0.37.2. Hosting is Windows.

**Impact:** the maintainer reports an unauthenticated Windows StaticFiles SSRF/NTLM credential-disclosure vulnerability in affected releases. A response can still be 404 after an outbound connection already occurred. The custom SPA resolver follows the same resolve-before-containment pattern, which warrants its own fix. The existing directory-containment check prevents ordinary outside-folder reads but does not eliminate this earlier filesystem/network side effect.

**Action:** serve the frontend through IIS; remove public Python static-file handling where appropriate. Reject UNC, device, drive-qualified and absolute paths before filesystem resolution. Upgrade to a compatible FastAPI/Starlette set addressing the advisory. Apply service-account least privilege and outbound SMB restrictions after checking legitimate requirements. Do not treat changing follow_symlink behavior as a complete fix. No exploit request or outbound SMB connection was attempted in this review.

**Source:** [Starlette maintainer advisory GHSA-wqp7-x3pw-xc5r](https://github.com/Kludex/starlette/security/advisories/GHSA-wqp7-x3pw-xc5r). The advisory lists Starlette below 1.1.0 as affected and 1.1.0 as patched. Upgrade FastAPI and its compatible Starlette dependency together, rather than forcing an incompatible transitive version.

### H2. Database transport is not configured to require verified encryption

**Evidence:** local source and target URL options use ODBC Driver 17, omit Encrypt, and specify TrustServerCertificate=yes. The URL builder also defaults to those options (`backend/app/core/config.py:79`).

**Impact:** the application does not require authenticated encrypted database transport. Actual encryption depends on server settings that were not inspected. Driver 17 defaults do not provide the same encryption default as Driver 18; trusting the certificate also bypasses certificate validation when encryption is used.

**Action:** coordinate trusted SQL Server certificates and require Encrypt=yes with TrustServerCertificate=no. Test compatibility in a separate environment. Independently verify that the Epush identity has SELECT-only grants, and use a restricted target runtime account rather than a schema-administration identity. The Python SELECT guard is useful but is not a substitute for database permissions. No Epush permissions, connection configuration or records were changed.

**Source:** [Microsoft ODBC version differences](https://learn.microsoft.com/en-us/sql/connect/odbc/major-version-differences?view=sql-server-ver17).

### H3. Launcher and local settings are not a hardened production deployment

**Evidence:** `RUN_SYSTEM.bat:31` starts plain HTTP Uvicorn on 0.0.0.0 and opens interactive worker/server windows. It advertises a public tunnel and prints ACTIVE without verifying readiness. Local APP_ENV is development. Deployment documentation offers HTTP or HTTPS without requiring HTTPS.

**Impact:** if deployed as shown without an appropriate gateway/firewall, passwords and bearer tokens travel over HTTP and closing a window can stop attendance import. A tunnel alone does not establish access policy, service resilience or origin protection.

**Action:** use supervised Windows services, explicit restart policies and a restricted service identity. Bind the API to loopback behind IIS, enforce HTTPS, block public/direct port 8000 access and enable WebSocket proxy support. Set APP_ENV=production with explicit origins and production secret management. Use an authenticated readiness probe instead of assuming a process launch succeeded. Configure response security policy at the HTTPS edge. Live topology was not verified, so exposure is conditional on deployment.

### H4. Student replay can exceed SQL Server's parameter limit and stall ingestion

**Evidence:** `backend/app/services/punch_processor.py:157` and `:168` build unbounded IN lists from an entire student's history. The MSSQL compile probe produced 2,101 parameters for 2,101 IDs. Additional query predicates can reduce the usable margin. Replay is called by enrollment, quarantine correction and late-arriving valid punches.

**Impact:** sufficiently long student histories can fail replay. If the worker repeatedly meets that late punch, batch rollback keeps the checkpoint behind it and synchronization can remain blocked. The million-row test had only 1,000 punches per student and bypassed ingestion, so it did not exercise this boundary.

**Action:** replace Python ID lists with relational joins/subqueries or bounded chunks. Add a disposable SQL Server test with well over 2,100 punches for a single student, including a late arrival and a manual override. Preserve raw records, IDs, registration rules, duplicate handling and chronological semantics.

**Source:** [Microsoft SQL Server capacity limits](https://learn.microsoft.com/en-us/sql/sql-server/maximum-capacity-specifications-for-sql-server?view=sql-server-ver17). This is a code/compile finding; a failing production query was not executed.

### H5. Replay, import and recovery hold a global attendance lock for long operations

**Evidence:** replay loads and processes full student histories, including per-row correction/history queries. The worker holds the timeline lock over source SELECT and up to 500 row savepoints. Recovery holds the same lock through its scan and final commit (`services/recovery.py:26`). Timeline app-lock acquisition waits up to 15 seconds.

**Impact:** a slow source query, a large replay or a recovery scan can block unrelated attendance writes and administrative operations. Python cycle budgets are checked between batches; they do not interrupt an individual slow SQL statement. A connection/login timeout is not a query-execution timeout.

**Action:** configure measured query timeouts; shorten recovery batches; remove replay N+1 queries; introduce bounded replay work or a background job. Consider per-student locks only with a carefully designed lock order and tests that retain activation/checkpoint atomicity. Do not simply remove the existing lock.

### H6. Query and connection concurrency has insufficient protection against memory pressure

**Evidence:** list endpoints count joined queries then use OFFSET pagination; unfiltered exports run to completion before returning response data. `core/database.py:21` allows up to 40 target connections per process. The deployment guide suggests four API processes, potentially 160 API target connections before the worker; actual usage is lazy and may be much lower.

**Impact:** expensive requests can multiply SQL memory requirements, disk use and response delays. The 50-user failure and 15-user punch-page timings are observed evidence of limited headroom, not proof that all 15-user production workloads will succeed.

**Action:** inspect query plans in a disposable environment, simplify count queries while retaining authorization filters, use cursor pagination for history, add measured target-only covering indexes and tune a total connection/concurrency budget across processes. Limit simultaneous exports and move large reports to jobs with cancellation, expiration and quotas. Do not increase pool sizes or worker counts as an automatic fix.

## Medium-priority findings and required improvements

| ID | Finding and evidence | Practical action |
|---|---|---|
| M1 | **Dependency advisories and unreproducible Python builds.** Installed python-jose 3.3.0 is in known affected ranges; Python requirements use lower bounds without a lock. FastAPI 0.115.0 / Starlette 0.37.2 / python-multipart 0.0.12 are old. | Upgrade a compatible, audited dependency set; pin exact resolved production versions and use a dedicated virtual environment. Run a full Python dependency audit. Keep pytest/Locust and other test-only tools out of the runtime requirements where appropriate. |
| M2 | **Login throttling is local and can be diluted.** `core/login_limit.py:11` keys limits by process, IP and username; changing usernames, hitting different processes or evicting old keys can weaken aggregate protection. | Shared limits for IP and account across processes, preferably at the gateway or a shared store; trust forwarded headers only from the configured proxy. Bound concurrent password verification and audit suspicious attempts. |
| M3 | **Long-lived tokens are readable by JavaScript; logout is local.** localStorage stores the token; default lifetime is 24 hours. Logout does not revoke the server token. No unsafe HTML rendering was found, so this is exposure conditional on XSS/token theft, not a demonstrated XSS exploit. | Reduce access-token lifetime; add server-side session revocation/logout. Consider HttpOnly Secure cookies with appropriate CSRF protection if moving away from bearer storage. Add a tested CSP; do not claim localStorage alone proves a vulnerability. |
| M4 | **Privileged account operations lack application audit events.** Account creation, password changes, role changes, deactivation and deletion change Users/TokenVersion but do not create SystemEvent entries in `api/users.py`. | Add actor, target, action and before/after role/scope audit events without logging passwords/tokens. Establish restricted audit access and retention. This would be a runtime write; it was not implemented during this review. |
| M5 | **Fresh synchronization can still have a backlog.** `api/system.py:45` checks status and completion age; the worker can mark a time-budgeted cycle SUCCESS without draining all eligible source rows. | Track eligible backlog, oldest pending age, throughput, cycle duration and failure streak. Distinguish worker heartbeat from data freshness. Keep metrics queries read-only on Epush and use only matching active-device eligibility. |
| M6 | **Live-update table growth creates persistent polling work.** `services/change_events.py:13` inserts on watched flushes, potentially multiple times per punch/replay. `:22` performs COUNT and MAX over the growing table, once per second for each API process with subscribers. There is no retention/compaction path. | Reduce notifications to a transaction/batch boundary and design an indexed, bounded revision mechanism that still detects out-of-order commits. Test before introducing cleanup; replacing COUNT with MAX alone loses an existing correctness safeguard. |
| M7 | **Source checkpoint correctness depends on visibility order.** The worker reads only IDs above one global watermark. Increasing IDs do not themselves prove that lower-ID transactions become visible first. | Confirm the Epush processed-table contract through read-only inspection/DBA documentation. If visibility can be out of order, use a bounded overlap with idempotency or per-device reconciliation. Do not interpret intentional exclusion of inactive/pre-activation punches as a defect. |
| M8 | **Future punch timestamps are accepted.** Worker validation checks required fields and identifier length, but not an implausibly future LogDate. | Agree an allowed device-clock tolerance; quarantine future data without letting it advance a student's effective attendance state. Add tests for future events and subsequent manual changes. |
| M9 | **Report totals and rows can change between reads.** Count and page queries are separate statements; exports and list pages can run while worker updates derived records. No explicit snapshot policy is configured. | Define point-in-time report semantics. Evaluate snapshot isolation or a stable report watermark in a disposable target environment; preserve ID/date ordering. Account for database configuration effects before changing production isolation. |
| M10 | **Detailed Student Lists repeats current-day aggregation.** `services/student_details.py:20` aggregates the day; `api/student_details.py:26` executes a count before retrieving the page. The million-row benchmark did not cover this new endpoint or populated current-day data. | For current IN/OUT views, count the scoped student/status query independently and fetch counters only for the page's IDs. For five-punch lists, validate aggregate/index plans and consider a separate daily-summary cache with clear invalidation rules. |
| M11 | **Frontend search differs from backend filtering.** Punches sends search as user_id/name filtering but then filters the returned page by UserId/DeviceId/Reason, omitting StudentName. A name can match the backend and disappear from the display; a device/reason match can be excluded before it reaches the browser. | Define a single server-side search contract for name/ID/device/reason and render its results without an incompatible second filter. Keep totals and exports on that same contract. |
| M12 | **Request races are mitigated, but not all freshness flows are complete.** useListState aborts stale requests; some pages retain old rows during a failed or changed filter, and Detailed Student Lists only refreshes on user/filter actions. Some searches are not debounced. | Clear or visibly mark stale results, use consistent request/error handling, debounce high-frequency searches and refresh current status/day labels appropriately. Add browser tests for filter changes, midnight rollover, logout and failed refreshes. |
| M13 | **Deployment instructions conflict with safe operation.** `docs/PRODUCTION_CHECKLIST.md:73` instructs resetting the old SyncCheckpoint; it also discusses separate DB fields without warning that a supplied URL takes precedence. Deployment docs mention wfastcgi without an ASGI WebSocket deployment design. | Remove the checkpoint-reset procedure for the current production restrictions; document URL precedence, ASGI reverse proxy, WebSocket settings, supervised services and rollback. Never run those historical reset instructions on production. |
| M14 | **Release packaging can include secrets and databases.** Root .gitignore is absent; backend/.env and SQLite databases exist. This review did not establish that any are already committed or published. | Add an explicit release allowlist/ignore policy for .env, databases, logs, caches and sensitive receipts. Secret-scan the planned artifact and any version history. Coordinate rotation of previously disclosed credentials; do not reproduce them in reports. |
| M15 | **Permissions are described inconsistently.** The User Management role option labels WARDEN read-only, but scoped student creation/profile editing/enrollment are intentionally allowed in the API and UI. | Publish an accurate role/action matrix. If the intended policy is truly read-only, get that business decision before removing capabilities. Hostel scoping alone does not resolve this labeling mismatch. |

## Dependency findings: reachability matters

Installed/locked versions were inspected rather than assuming the lower bounds in package manifests were the resolved versions. Frontend examples: axios 1.20.0, react-router-dom 6.30.6, Vite 5.4.21, esbuild 0.21.5 and Tailwind 3.4.19.

- **React Router:** production npm audit flags open redirect and SSR error deserialization advisories. This app uses BrowserRouter with fixed navigation targets, not SSR hydration or user-controlled destinations in the paths reviewed. No exploit path was demonstrated; upgrade with routing regression tests. [Open redirect advisory](https://github.com/advisories/GHSA-wrjc-x8rr-h8h6), [SSR advisory](https://github.com/advisories/GHSA-337j-9hxr-rhxg).
- **Vite/esbuild/build chain:** the complete audit includes development-server and build-tool findings. Vite is configured with host=true. Keep development servers off the production network and serve built dist assets; update development dependencies separately rather than using npm audit fix --force without migration/testing. [Vite Windows path advisory](https://github.com/advisories/GHSA-fx2h-pf6j-xcff), [esbuild advisory](https://github.com/advisories/GHSA-67mh-4wv8-2f99).
- **python-jose 3.3.0:** affected by named OpenSSH ECDSA algorithm-confusion and compressed JWE advisories. Current JWT verification allows the configured HS256 algorithm with a symmetric secret and does not call JWE decryption, so those named exploit paths were not demonstrated. Upgrade nevertheless; the named fixes start at 3.4.0, but choose a currently audited compatible release. [Algorithm advisory](https://github.com/advisories/GHSA-6c5p-j8vq-pqhj), [JWE advisory](https://github.com/advisories/GHSA-cjwg-qfpm-7377).
- **Starlette/python-multipart:** installed versions are in multipart advisory ranges, but reviewed API routes use JSON and have no upload/Form dependencies. Imported but unused OAuth2PasswordRequestForm does not mean parsing is performed. Treat multipart issues as conditional until a form/upload path is established. StaticFiles on Windows is separately relevant under H1. [Multipart advisory](https://github.com/Kludex/python-multipart/security/advisories/GHSA-59g5-xgcq-4qw3), [Starlette multipart advisory](https://github.com/Kludex/starlette/security/advisories/GHSA-2c2j-9gv5-cj73).
- **Avoid false positives:** the Starlette Range-processing advisory affects versions 0.39.0–0.49.0, not the installed 0.37.2. It must not be counted as an installed-version finding. [Range advisory](https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8).

The bcrypt/passlib version warning seen in previous tests is a compatibility/maintenance issue, not evidence that password hashing is bypassed. Upgrade/test the authentication stack; do not weaken hashing to improve performance.

## Existing safeguards worth preserving

- Backend authentication checks active users, token versions, current roles and active warden assignments; frontend role hiding is not the only authorization layer.
- Warden list/report/export queries use hostel restrictions. Missing hostel assignment fails closed.
- SQLAlchemy-bound values are used for normal API queries; no request-driven SQL injection path was identified in the routes inspected. LIKE wildcards can broaden a filter, but are not SQL injection.
- First-registration behavior, duplicate window, chronological replay, immutable source payloads, manual override events and historical snapshots are explicit.
- Matching active-device source filters and activation cutoffs enforce the current ingestion policy.
- The worker uses a pinned session-owned distributed synchronization lock; attendance mutations use transaction locks; raw and processed uniqueness and batch checkpoint commits protect idempotency.
- Lists are paginated; exports no longer have the old 1,000/2,000-record cap, use bounded iteration/spooled files, escape spreadsheet formulas and split oversized Excel sheets.
- Tests are isolated and reject production connections; legacy SQL Server seed/reset utilities are guarded or disabled.
- India time is centralized; counters are calculated on read rather than trusting stale persisted counter values.
- Live updates authenticate without placing tokens in URLs and recheck authorization; dashboard reconnect/fallback behavior exists.

These safeguards do not remove the high-priority risks or replace deployment verification.

## Recommended implementation and release sequence

1. **Before external exposure:** address H1; upgrade and lock dependencies; harden release packaging, HTTPS/host/origin policy and service identity; establish verified database transport and grants without changing Epush records.
2. **Before relying on long histories:** fix replay parameter growth and N+1 processing; bound recovery/write lock durations and SQL query execution; test one student's long history on a separate SQL Server database.
3. **For responsive 15-user use:** optimize scoped counts and history pagination, evaluate target indexes, configure a combined pool budget, limit exports, and reduce live-change polling costs. Preserve attendance semantics and permissions in every optimization.
4. **For operations:** implement account/security audit events, backlog/freshness metrics, restrictive log access and rotation, backup plus actual disposable restoration drills, disk-space checks and alerting.
5. **Release only after validation:** run sustained deployed HTTP tests on an isolated SQL Server environment with 15 users, populated current-day data, Detailed Student Lists, live WebSockets, simultaneous worker batches, one or two exports, late events and manual overrides. Test restart, source outage/reconnect and midnight rollover. Suggested initial goals for agreement: common read p95 under one second, history p95 under two seconds, zero unexpected errors, no growing backlog and exact scoped exports. These are targets, not measured guarantees.

Some improvements are code-only; target indexes/new tables, server encryption, permissions, isolation and service settings require separate rollout planning. Existing production records must remain unchanged during implementation and verification. Epush remains SELECT-only; this plan does not authorize ALTER, writes or indexes there.

## Evidence files

- `database/migrations/million_rows_15_users_receipt.json`
- `database/migrations/million_rows_receipt.json` (original 50-user failure)
- `docs/MILLION_ROW_15_USERS_TEST_20261010.md`
- `backend/tests/` (90 current passing tests)

This review is an engineering release assessment, not a complete penetration test or a guarantee of security or production capacity.
