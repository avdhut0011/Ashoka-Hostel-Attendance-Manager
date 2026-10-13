import time
import signal
import logging
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy import Table, MetaData, Column, BigInteger, Integer, String, DateTime, text

from backend.app.core.database import TargetSessionLocal, SourceSessionLocal, target_engine, source_engine
from backend.app.models.master import Device
from backend.app.models.integration import RawPunch, SyncCheckpoint, QuarantinedPunch
from backend.app.models.attendance import ProcessedPunch
from backend.app.services.punch_processor import process_single_raw_punch
from backend.app.core.config import settings
from backend.app.core.time import source_time, local_now
from backend.app.core.locking import attendance_lock
from backend.app.services.device_ingestion import active_device_windows, eligible_source_rows

logger = logging.getLogger("SyncWorker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Global in-memory cache for source table to eliminate repeated SQL Server catalog queries
_cached_source_table: Optional[Table] = None
_in_process_lock = threading.Lock()
_shutdown_requested = False

class LockAcquisitionError(Exception):
    """Raised when another process or thread already holds the distributed sync lock."""
    pass

@contextmanager
def distributed_db_lock(db: Session, lock_name: str = "HostelAttendanceSyncLock", timeout_ms: int = 0):
    """
    Acquires a cross-process distributed application lock on MS SQL Server (sp_getapplock).
    Falls back to in-process threading.Lock for SQLite/test environments.
    Uses the dedicated connection held by the cycle; release or invalidate it before pooling.
    """
    is_mssql = "mssql" in db.bind.dialect.name
    acquired_mssql_lock = False

    # 1. Acquire in-process lock first
    if not _in_process_lock.acquire(blocking=False):
        raise LockAcquisitionError("Another thread in this process is actively synchronizing.")

    try:
        # 2. Acquire SQL Server distributed lock across all server processes
        if is_mssql:
            stmt = text("""
                SET NOCOUNT ON;
                DECLARE @res INT;
                EXEC @res = sp_getapplock 
                    @Resource = :lock_name, 
                    @LockMode = 'Exclusive', 
                    @LockOwner = 'Session', 
                    @LockTimeout = :timeout_ms;
                SELECT @res AS LockResult;
            """)
            result = db.execute(stmt, {"lock_name": lock_name, "timeout_ms": timeout_ms}).scalar()
            if result is None or result < 0:
                raise LockAcquisitionError(
                    f"Distributed lock '{lock_name}' is held by another worker process (sp_getapplock code: {result})."
                )
            acquired_mssql_lock = True

        yield

    finally:
        if is_mssql and acquired_mssql_lock:
            release_stmt = text("""
                EXEC sp_releaseapplock 
                    @Resource = :lock_name, 
                    @LockOwner = 'Session';
            """)
            try:
                # Recover a failed transaction before releasing the session lock.
                # The physical connection remains checked out across rollback.
                db.rollback()
                db.execute(release_stmt, {"lock_name": lock_name})
                db.commit()
            except Exception as e:
                logger.warning('Distributed lock release failed; discarding its connection')
                bind = db.get_bind()
                if hasattr(bind, 'invalidate'):
                    bind.invalidate()

        _in_process_lock.release()

def get_source_device_logs_table() -> Table:
    """
    Returns high-speed SQLAlchemy Table object for the IT DeviceLogs table.
    Uses a predefined column mapping; query performance depends on source indexes and network latency.
    """
    global _cached_source_table
    if _cached_source_table is None:
        metadata = MetaData()
        _cached_source_table = Table(
            settings.SOURCE_TABLE, metadata,
            Column("DeviceLogId", BigInteger, primary_key=True),
            Column("DownloadDate", DateTime, nullable=True),
            Column("DeviceId", Integer, nullable=False),
            Column("UserId", String(50), nullable=False),
            Column("LogDate", DateTime, nullable=False)
        )
    return _cached_source_table

def run_synchronization_cycle(time_budget_seconds: float = 10.0, batch_size: int = 500) -> Dict[str, Any]:
    """
    Executes an enterprise-grade incremental synchronization cycle:
    1. Distributed Lock: Cross-process mutual exclusion via SQL Server sp_getapplock.
    2. Dynamic Backlog Draining: Continuously drains large backlogs within a time budget.
    3. Failure Isolation: Corrupted data is persisted to QuarantinedPunches table, preventing poison pills.
    4. Transient Error Safety: Connection dropouts/deadlocks rollback without advancing the watermark.
    5. Atomic checkpointing: commit each batch and its durable outcomes together.
    """
    target_db: Optional[Session] = None
    target_connection = None
    source_db: Optional[Session] = None
    start_time = datetime.utcnow()
    budget_started = time.monotonic()
    total_synced_count = 0
    total_quarantined_count = 0

    try:
        # Keep a single physical connection checked out for the session-owned lock.
        target_connection = target_engine.connect()
        target_db = TargetSessionLocal(bind=target_connection, join_transaction_mode='control_fully')

        with distributed_db_lock(target_db):
            # 1. Atomic Checkpoint Initialization / Fetch
            checkpoint = target_db.query(SyncCheckpoint).filter_by(SourceName="IT_SQL_SERVER").first()
            if not checkpoint:
                checkpoint = SyncCheckpoint(
                    SourceName="IT_SQL_SERVER",
                    LastSourceDeviceLogId=0,
                    LastSyncStartedAt=start_time,
                    LastSyncStatus="RUNNING"
                )
                target_db.add(checkpoint)
                target_db.commit()

            checkpoint.LastSyncStartedAt = start_time
            checkpoint.LastSyncStatus = "RUNNING"
            checkpoint.LastError = None
            target_db.commit()

            current_watermark = checkpoint.LastSourceDeviceLogId
            source_table = get_source_device_logs_table()

            # Import only registered active devices in their current activation period.

            # Open source connection once for the entire cycle
            source_db = SourceSessionLocal()

            # Dynamic Queue Drain Loop
            batch_iteration = 0
            while not _shutdown_requested:
                # Check execution time budget to prevent monopolizing database connection
                elapsed = time.monotonic() - budget_started
                if elapsed >= time_budget_seconds and batch_iteration > 0:
                    logger.info(f"Time budget of {time_budget_seconds}s reached. Yielding control until next cycle.")
                    break

                batch_iteration += 1

                # Status changes use the same transaction lock. Keep the device
                # snapshot, source query, batch insert and checkpoint atomic with
                # registration/activation/deactivation to avoid advancing past a
                # just-activated device's eligible punches.
                with attendance_lock(target_db):
                    windows = active_device_windows(target_db)
                    rows = eligible_source_rows(source_db, source_table, windows,
                        [source_table.c.DeviceLogId > current_watermark], batch_size)
                    if not rows:
                        break

                    logger.info(f"[Batch #{batch_iteration}] Syncing {len(rows)} logs starting > DeviceLogId {current_watermark}...")

                    batch_synced = 0
                    batch_quarantined = 0
                    new_last_id = current_watermark

                    for row in rows:
                        source_log_id = row.DeviceLogId
                        download_date = row.DownloadDate
                        device_id = row.DeviceId
                        user_id = str(row.UserId).strip() if row.UserId is not None else ""
                        log_date = source_time(row.LogDate) if row.LogDate else None

                        # Always advance watermark pointer to the highest evaluated log ID
                        new_last_id = source_log_id

                        # Row-Level Savepoint Isolation
                        try:
                            with target_db.begin_nested():
                                # Permanent Validation Check
                                if not user_id:
                                    raise ValueError(f"Missing UserId on DeviceLogId #{source_log_id}")
                                if len(user_id) > 50:
                                    raise ValueError("UserId exceeds 50 characters")
                                if not log_date:
                                    raise ValueError(f"Missing LogDate on DeviceLogId #{source_log_id}")
                                if (log_date - local_now()).total_seconds() > settings.MAX_FUTURE_PUNCH_SECONDS:
                                    raise ValueError('Punch timestamp is beyond the allowed device clock tolerance')

                                # Idempotent Raw Punch Insertion
                                raw_punch = target_db.query(RawPunch).filter_by(SourceDeviceLogId=source_log_id).first()
                                if not raw_punch:
                                    raw_punch = RawPunch(
                                        SourceDeviceLogId=source_log_id,
                                        DeviceId=device_id,
                                        UserId=user_id,
                                        LogDate=log_date,
                                        DownloadDate=download_date,
                                        ReceivedAt=datetime.utcnow()
                                    )
                                    target_db.add(raw_punch)
                                    target_db.flush()

                                # Deterministic Attendance Evaluation
                                process_single_raw_punch(target_db, raw_punch)
                                batch_synced += 1

                        except (ValueError, TypeError) as data_err:
                            # PERMANENT DATA CORRUPTION: Quarantine to database and advance watermark safely
                            batch_quarantined += 1
                            err_text = str(data_err)
                            logger.warning(f"Quarantining corrupted record #{source_log_id} (User: '{user_id}'): {err_text}")

                            quarantine_rec = QuarantinedPunch(
                                SourceDeviceLogId=source_log_id,
                                DeviceId=device_id,
                                UserId=user_id[:50] or None,
                                LogDate=log_date,
                                DownloadDate=download_date,
                                RawPayload=f"DeviceId={device_id}, UserId='{user_id}', LogDate='{log_date}'"[:1000],
                                ErrorType="DATA_CORRUPTION",
                                ErrorMessage=err_text[:2000],
                                QuarantinedAt=datetime.utcnow(),
                                ResolvedStatus="PENDING"
                            )
                            target_db.add(quarantine_rec)
                            target_db.flush()

                        except Exception as transient_err:
                            # TRANSIENT / UNEXPECTED ERROR: Abort current batch so it will be retried
                            logger.error('Processing record %s failed: %s', source_log_id, type(transient_err).__name__)
                            raise transient_err

                    # Commit batch and persist watermark atomically
                    current_watermark = new_last_id
                    checkpoint.LastSourceDeviceLogId = current_watermark
                    checkpoint.LastSyncCompletedAt = datetime.utcnow()
                    target_db.commit()

                total_synced_count += batch_synced
                total_quarantined_count += batch_quarantined

                # If batch was smaller than batch_size, backlog is completely drained
                if len(rows) < batch_size:
                    break

            # Close source session
            source_db.close()
            source_db = None

            # Finalize Status: Report PARTIAL_SUCCESS if any rows were quarantined
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            if total_quarantined_count > 0:
                checkpoint.LastSyncStatus = "PARTIAL_SUCCESS"
                checkpoint.LastError = f"{total_quarantined_count} records were quarantined due to corrupted payload."
            else:
                checkpoint.LastSyncStatus = "SUCCESS"
                checkpoint.LastError = None

            checkpoint.LastSyncCompletedAt = datetime.utcnow()
            target_db.commit()

            logger.info(
                f"Sync cycle finished: {total_synced_count} synced, {total_quarantined_count} quarantined "
                f"up to ID {current_watermark} in {duration_ms}ms (Status: {checkpoint.LastSyncStatus})."
            )
            return {
                "status": checkpoint.LastSyncStatus,
                "synced_count": total_synced_count,
                "quarantined_count": total_quarantined_count,
                "last_device_log_id": current_watermark,
                "duration_ms": duration_ms
            }

    except LockAcquisitionError as lock_err:
        logger.warning(f"Sync cycle skipped: {lock_err}")
        return {"status": "IN_PROGRESS", "message": "Synchronization is already running by another process."}

    except Exception as e:
        err_msg = f'{type(e).__name__}: synchronization failed; consult restricted server logs'
        logger.error('Synchronization failed: %s', type(e).__name__)
        if target_db:
            try:
                target_db.rollback()
                checkpoint = target_db.query(SyncCheckpoint).filter_by(SourceName="IT_SQL_SERVER").first()
                if checkpoint:
                    checkpoint.LastSyncStatus = "FAILED"
                    checkpoint.LastError = err_msg[:2000]
                    target_db.commit()
            except Exception:
                pass
        return {"status": "FAILED", "error": err_msg, "synced_count": total_synced_count}

    finally:
        if source_db:
            try:
                source_db.close()
            except Exception:
                pass
        if target_db:
            try:
                target_db.close()
            except Exception:
                pass

        if target_connection is not None:
            target_connection.close()

def _handle_signal(signum, frame):
    global _shutdown_requested
    logger.info(f"Shutdown signal ({signum}) received. Finishing active sync before exiting...")
    _shutdown_requested = True

def start_worker_loop():
    """
    Continuous background daemon loop with signal handling and reconnect backoff.
    """
    global _shutdown_requested
    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except Exception:
        pass # Signal handlers might be restricted on some Windows thread contexts

    logger.info(f"Starting Enterprise Sync Worker Loop (Interval: {settings.SYNC_INTERVAL_SECONDS}s)...")
    consecutive_errors = 0

    while not _shutdown_requested:
        try:
            res = run_synchronization_cycle()
            status = res.get("status")
            if status in ["SUCCESS", "PARTIAL_SUCCESS", "IN_PROGRESS"]:
                consecutive_errors = 0
            else:
                consecutive_errors += 1
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Unexpected error in sync loop: {e}")

        # Exponential backoff during remote database outages (max 60s)
        sleep_time = settings.SYNC_INTERVAL_SECONDS
        if consecutive_errors > 3:
            sleep_time = min(60, settings.SYNC_INTERVAL_SECONDS * (2 ** min(consecutive_errors - 3, 3)))
            logger.warning(f"Connection issues detected ({consecutive_errors} failures). Backing off for {sleep_time}s...")

        # Sleep in 1-second slices so shutdown signal is responsive
        for _ in range(sleep_time):
            if _shutdown_requested:
                break
            time.sleep(1)

    logger.info("Sync Worker daemon stopped cleanly.")

if __name__ == "__main__":
    start_worker_loop()

