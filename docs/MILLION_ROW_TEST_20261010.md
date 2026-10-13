# Million-row application test — 10 October 2026

The application can retrieve and export one million stored attendance records, but the 50-user concurrent test failed. This result does not establish production readiness at this scale.

## Isolation and dataset

- Created and removed `HostelAttendance_Test_641c0761c2fe46019209bbd1fe6123b4` on the configured target SQL Server instance.
- No connection to Epush. No production application tables were read or modified.
- Seeded 1,000 synthetic students, two hostels, 50 synthetic test accounts, 1,000,000 raw punches and 1,000,000 processed punches inside the disposable database only.
- Exercised the actual FastAPI endpoints using TestClient. The test does not measure browser rendering, reverse-proxy overhead, or a deployed HTTP server.
- Stored punches are synthetic historical records with assignment snapshots. This test measures retrieval and export performance, not biometric ingestion throughput or attendance sequence processing.
- The disposable database shared the SQL Server instance and its resources; database isolation does not isolate CPU or memory consumption.

## Single-user results

| Check | Time | Result |
|---|---:|---|
| First 100 records | 0.21 seconds | Passed |
| Page at offset 500,000 | 2.50 seconds | Passed |
| Last 100 records | 4.94 seconds | Passed |
| Page after the final record | 4.88 seconds | Correctly empty |
| Student filter | 0.88 seconds | Correct total of 1,000 matches |
| Date filter | 0.11 seconds | Correct total of 1,000,000 matches |
| Complete CSV export and validation | 30.36 seconds | Every event ID present exactly once |

The CSV was 108,282,084 bytes. Export time includes reading and validating the downloaded content in the test process. Excel export was not tested at this scale.

## Concurrent result

The test attempted 50 simultaneous users, split evenly between administrators and wardens, with three rounds of punch-list, dashboard, and student-list requests per user. It failed before the planned 450 requests could all be verified.

SQL Server returned error 701: `There is insufficient system memory in resource pool 'internal' to run this query.` The captured failure occurred during a punch-list total-count query. Partial successful requests are not treated as a passing concurrent test, and no complete concurrent latency summary is available.

## Follow-up needed

1. Investigate SQL Server memory availability and configuration together with query execution plans in an isolated environment.
2. Reduce the work needed for total counts and hostel-scoped queries, validating equivalent results and permissions.
3. Consider cursor pagination to avoid increasingly expensive deep offsets.
4. Retest the full 50-user workload after improvements, including current-day data and realistic date distribution.

No production query, schema, memory configuration, or service setting was changed as part of this benchmark. The reproduction script is `database/verify_million_rows.py`; the machine-readable evidence is `database/migrations/million_rows_receipt.json`.
