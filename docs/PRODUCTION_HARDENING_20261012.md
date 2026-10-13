# Production hardening implementation

This is the implementation follow-up to PRODUCTION_SECURITY_REVIEW_20261012.md. The original review describes the earlier state and is retained as the baseline.

## Changes delivered

- Upgraded backend and frontend dependencies. A dedicated .venv-production and exact Python runtime lock avoid changing the running server's interpreter. Runtime dependencies exclude test/load tools. Python and npm advisory scans reported zero known vulnerabilities in the upgraded sets; this is not a guarantee against all vulnerabilities.
- Replaced python-jose/passlib usage with PyJWT and direct bcrypt while preserving existing password hashes, HS256 tokens, and session duration. New tokens have unique IDs. Logout revokes the exact token server-side. Account/IP throttles are shared through a new table; a concurrency test exposed and led to removal of a redundant lock acquisition after login.
- Added non-secret account change auditing in a new supporting table. Added static-path rejection before filesystem resolution, production CSP, trusted-host support, disabled production API documentation, and API no-store headers.
- Bounded database pools and query timeouts, limited report generation per process, paged narrow punch IDs before display joins, added cursor navigation and supporting indexes, and removed unnecessary count joins. Ordinary current-status student lists aggregate counters only for displayed students.
- Replaced the growing live-change scan with one transactional revision row. Rollback/savepoint and cross-process notification tests preserve correctness.
- Removed unbounded replay IN-parameter lists, loaded state/correction/device history in batches, and retained chronological decisions, punch IDs, duplicates, manual overrides, and enrollment behavior. Recovery work commits one bounded batch per resume request.
- Quarantined punches more than five minutes in the future, with a configurable tolerance. Health checks distinguish worker heartbeat from an eligible pending punch's age. Corrected SQL Server activation-boundary parameter precision.
- Added debouncing for exception/detailed searches and visible-page refresh for Detailed Student Lists. Corrected warden capability wording, added secret/database ignore rules, and replaced unsafe deployment/reset guidance.

## Production database boundary

The guarded migration applied ten DDL statements: four empty tables (system.AttendanceRevision, security.LoginThrottle, security.RevokedTokens, security.SecurityAudit) and six indexes. Existing application-table row counts were unchanged, and new tables were checked empty. No inserts, updates, deletes, user creation, attendance backfill, or checkpoint reset was performed on production application tables. Epush was never connected to during this implementation. Receipts are stored locally under database/migrations; keep them private.

Backend and worker services have not been restarted. They must use the patched environment after a controlled restart before the runtime fixes are active. The frontend production bundle has been rebuilt. Follow LOCAL_PRODUCTION_DEPLOYMENT.md.

## Verification

- 98 isolated in-memory backend regression tests passed, including rejection of wildcard production hosts/origins.
- Frontend production build passed after dependency and frontend changes.
- Dedicated Python environment and complete npm dependency audits reported zero known advisories.
- Disposable SQL Server checks passed: worker lock ownership across process/batch commits; idempotence and late ordering; concurrent manual override/replay; failed-batch rollback/retry; 15 simultaneous mixed-role users; filtered exports/read purity; cross-process live notification/token revocation; 116 active device IDs and activation cutoffs; activation during a source query; and 2,105-punch replay preserving IDs and sequence.
- The 15-user correctness workload completed 45 iterations, each with several API checks; mean iteration 833.8 ms and p95 2,243.4 ms. The long replay took 10.87 seconds. Its disposable database was removed.
- The initial 50-user run exposed the login lock/pool interaction. After that fix, the 50-user small-data workload failed because simultaneous export requests still received the intentional 429 busy response after the test's 30-second retry window. The one-report-per-process limit protects resources, but does not guarantee fair queuing or completion for 50 simultaneous exporters. Do not claim this workload passed or confuse it with the separate earlier SQL insufficient-memory failure.
- Three million-row reruns timed out during synthetic fixture creation before API measurements. The final attempt used smaller committed setup batches but still timed out inserting a 10,000-row fixture batch. Every disposable database was removed. This is not a 15-user request failure, but it prevents validating this build's million-row capacity on the current SQL Server. Preserve the earlier successful receipt as baseline evidence, not certification of these changes.

## Remaining release work and practical limits

| Review findings | Current status / remaining work |
|---|---|
| H1, H4; M1, M4, M6, M10, M11, M13, M15 | Code/dependency changes delivered and covered by the checks above. Browser-level routing/style verification remains separate from build success. |
| H2 | Secure defaults apply to constructed database URLs. Existing complete URLs remain unchanged; verified SQL encryption/certificate trust and least-privilege grants remain operational checks. |
| H3 | Local deployment instructions and patched launcher prepared. Service supervision, explicit LAN hosts/origins, firewall, and transport configuration must be activated on the server. |
| H5 | Replay and recovery queries improved, but global attendance serialization remains. A long replay can still delay other writers; incremental durable replay/job redesign is not implemented. |
| H6 | Pools/timeouts/export generation are bounded and the small 15-user SQL workload passed. Sustained capacity, million-row/current-day workloads, memory monitoring, and cross-process export scheduling still need verification. |
| M2 | Shared database limits implemented; gateway limits, suspicious-login monitoring and distributed password-verification quotas are not implemented. |
| M3 | Server logout and CSP implemented. Token duration deliberately unchanged; tokens remain in localStorage. A cookie/CSRF/session redesign is deferred. |
| M5 | Eligible pending detection/age added. This samples the next eligible source ID, not an exact backlog size or minimum timestamp; full throughput/failure-streak metrics are not implemented. |
| M7 | Epush lower-ID commit/visibility ordering remains unconfirmed. No overlap/reconciliation redesign was made without that evidence. |
| M8 | Worker future-clock validation and quarantine test implemented. The operational tolerance is five minutes; monitor device clocks. |
| M9 | Stable ordering/cursors added; reports are not guaranteed point-in-time snapshots while attendance changes. No production isolation setting was altered. |
| M12 | Debouncing, cleared exception results and detailed-list refresh improved. Browser race, failure, midnight, and logout scenarios need end-to-end testing. |
| M14 | Ignore rules added. No Git history exists in this workspace; a release artifact allowlist/secret scan and rotation of previously disclosed credentials remain necessary before distribution. |

No purchased domain/certificate is necessary for LAN access. HTTP still exposes credentials/tokens to traffic inspection; internal trusted TLS or a securely configured VPN can address that without a purchase. SQL Server hardware/memory, backup restoration, service identity, and actual network configuration have not been certified. Do not describe this update as unrestricted production approval.
