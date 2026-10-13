# System Architecture & Technical Specifications

This document outlines the complete architectural design, data pipelines, business rules, and database schema mappings for the **Hostel Attendance Management System**, strictly derived from the 3 visual specification diagrams.

---

## 1. High-Level Data Flow (Diagram 1 Mapping)

```text
eSSL Biometric Punch (UserId, DeviceId, LogDate)
        ↓
   ePush Server
        ↓
IT Local MS SQL Database (Raw Punch Data: DeviceLogId, DownloadDate, DeviceId, UserId, LogDate)
        ↓  [READ-ONLY Incremental Polling every 10s: DeviceLogId > LastSourceDeviceLogId]
Python Sync Worker
        ↓  [Idempotent Raw Copy]
integration.RawPunches  &  integration.SyncCheckpoint
        ↓
Punch Processing Engine (Deterministic Business Logic)
   ├── 1. Device Validation (master.Devices exists & IsActive?) → INVALID_DEVICE if false
   ├── 2. Student Discovery (master.Students exists?) → Create student (PENDING_ENROLLMENT) if new
   ├── 3. Student Registration Status Check → INACTIVE_STUDENT if inactive
   ├── 4. Hostel Assignment Validation → INVALID_DEVICE if device hostel != student hostel
   ├── 5. Duplicate Detection (LogDate diff <= 45s?) → DUPLICATE if true
   └── 6. IN/OUT Attendance Calculation
          ├── First-ever punch → REGISTRATION (No IN/OUT)
          ├── First valid punch of day → OUT if prev status was IN, else IN
          └── Subsequent valid punches → Alternate IN ↔ OUT
        ↓
attendance.ProcessedPunches & attendance.StudentCurrentStatus
        ↓
FastAPI Backend APIs + scoped HTTP polling
        ↓
React Administrative Dashboard & Reports
```

---

## 2. Database Schemas & Relationships (Diagram 2 Mapping)

The database `HostelAttendance` consists of 5 dedicated schemas:

1. **`master` Schema:** Master entity tables (`Hostels`, `Devices`, `Students`, `StudentHostelHistory`, `LookupPunchType`, `LookupProcessingStatus`).
2. **`integration` Schema:** Raw source punch copy (`RawPunches`) and synchronization checkpoint (`SyncCheckpoint`).
3. **`attendance` Schema:** Deterministic processed records (`ProcessedPunches`) and real-time student location state (`StudentCurrentStatus`).
4. **`security` Schema:** User accounts & roles (`Users`).
5. **`system` Schema:** System audit logs & events (`SystemEvents`).

---

## 3. Key Attendance Business Rules

1. **First-ever punch rule:** The first valid punch for a newly discovered student is classified as `REGISTRATION`. Current status remains `REGISTRATION`. No IN/OUT state is triggered.
2. **First valid punch of a day:**
   - If the previous day's final status was `IN` -> Today's first valid punch = `OUT`.
   - If the previous day's final status was `OUT` or `NOT_STARTED` -> Today's first valid punch = `IN`.
3. **Subsequent valid punches of the same day:**
   - Alternate deterministically: `IN` -> `OUT` -> `IN` -> `OUT`.
4. **Duplicate detection:**
   - If `UserId`, `DeviceId` match and `|LogDate - LastValidLogDate| <= DUPLICATE_WINDOW_SECONDS` (default 45s), marked `DUPLICATE`.
5. **Device & Student validation:**
   - Unregistered/inactive devices or hostel mismatch punches are recorded as `INVALID_DEVICE` and ignored for attendance calculations.

## Production hardening

See PRODUCTION_UPDATE_20261010.md for immutable corrections, attendance overrides, effective state history, late-punch replay, scoped pagination, and target-only migrations.
