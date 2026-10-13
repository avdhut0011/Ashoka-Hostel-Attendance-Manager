# Million-row test with 15 simultaneous users — 10 October 2026

The tested 15-user workload passed all 135 requests without SQL errors. This is a short API correctness and performance test, not a sustained production capacity guarantee.

## Isolation

Created and removed `HostelAttendance_Test_b1365f423fa349ad9a48bf9a0b3ec972`. Production application tables were not accessed or changed, and Epush was not connected. The test used 1,000 synthetic students, two hostels, 15 synthetic accounts, one million raw punches, and one million processed punches, all in the disposable database. Database isolation does not isolate SQL Server CPU and memory because the test used the configured target instance.

## Results

Eight administrator and seven warden sessions each made three rounds of punch-list, dashboard, and student-list requests. All 135 requests passed expected counts and hostel permission checks. The concurrent phase lasted 12.21 seconds.

| Concurrent endpoint | Requests | Average | 95th percentile | Maximum |
|---|---:|---:|---:|---:|
| Punch pages (offsets 0, 100,000, 200,000) | 45 | 3.394 s | 5.199 s | 5.246 s |
| Dashboard summary | 45 | 0.047 s | 0.106 s | 0.142 s |
| Student list | 45 | 0.155 s | 0.297 s | 0.325 s |

Single-user first-page retrieval took 0.234 seconds, middle-page retrieval 2.262 seconds, and last-page retrieval 4.899 seconds. Student and date filters passed. A page beyond the final record correctly returned no rows.

The CSV export contained all one million event IDs exactly once and occupied 108,282,084 bytes. Export plus test validation took 33.48 seconds. Excel export was not tested. Reads preserved the change marker and both million-row table counts.

## Practical interpretation

The 15-user workload passed where the previous 50-user workload failed with SQL Server error 701. Dashboard and student-list requests performed well in this run; punch-page retrieval still needs improvement, particularly for deep offsets and hostel filters.

This test used FastAPI TestClient, with synthetic historical records and no current-day punches. It does not include browser rendering, network and reverse-proxy latency, sustained live dashboard traffic, worker ingestion, concurrent exports, or a deployed server's thread and process configuration. Its 12-second concurrent phase is insufficient to establish long-term capacity.

No production code queries or SQL Server configuration were changed for this run. Reproduction: `python -B -m database.verify_million_rows --users 15`. Evidence: `database/migrations/million_rows_15_users_receipt.json`. The original 50-user receipt remains preserved separately.
