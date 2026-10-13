"""Bounded SELECT-only source scans; writes confined to new review tables."""
import time
from datetime import datetime
from backend.app.core.locking import attendance_lock
from backend.app.core.time import day_bounds, source_time
from backend.app.models import Student, Device, RawPunch, QuarantinedPunch, SyncCheckpoint
from backend.app.models.review import RecoveryScan, RecoveryPunch
from backend.app.services.device_ingestion import active_device_windows, eligible_source_rows


def new_scan(db, start, end, actor):
    if start > end:
        raise ValueError('Start date must not be after end date')
    checkpoint = db.query(SyncCheckpoint).filter_by(SourceName='IT_SQL_SERVER').first()
    if not checkpoint:
        raise ValueError('No synchronization checkpoint exists; skipped punches cannot be distinguished from new punches')
    scan = RecoveryScan(StartDate=start, EndDate=end, SourceWatermark=checkpoint.LastSourceDeviceLogId,
                        RequestedBy=actor, Status='PENDING')
    db.add(scan)
    db.commit()
    return scan.ScanId


def scan_missing(db, source, table, scan_id, budget_seconds=5, batch_size=100):
    started = time.monotonic()
    with attendance_lock(db), attendance_lock(db, 'recovery'):
        scan = db.get(RecoveryScan, scan_id)
        if scan is None:
            raise ValueError('Recovery scan not found')
        if scan.Status == 'COMPLETE':
            return scan
        start = day_bounds(scan.StartDate)[0]
        end = day_bounds(scan.EndDate)[1]
        # Timeline first, then recovery: consistent ordering with device updates.
        while time.monotonic() - started < budget_seconds:
            windows = active_device_windows(db)
            rows = eligible_source_rows(source, table, windows, [
                table.c.DeviceLogId > scan.LastScannedSourceId,
                table.c.DeviceLogId <= scan.SourceWatermark,
                table.c.LogDate >= start, table.c.LogDate < end,
            ], batch_size)
            if not rows:
                scan.Status, scan.CompletedAt = 'COMPLETE', datetime.utcnow()
                break
            ids = [row.DeviceLogId for row in rows]
            known = {
                row[0] for row in db.query(RawPunch.SourceDeviceLogId).filter(RawPunch.SourceDeviceLogId.in_(ids))}
            known.update(row[0] for row in db.query(QuarantinedPunch.SourceDeviceLogId).filter(QuarantinedPunch.SourceDeviceLogId.in_(ids)))
            reviewed = {row[0] for row in db.query(RecoveryPunch.SourceDeviceLogId).filter(RecoveryPunch.SourceDeviceLogId.in_(ids))}
            user_ids = {str(row.UserId).strip() for row in rows if row.UserId is not None}
            students = {student.UserId: student.StudentId for student in db.query(Student).filter(Student.UserId.in_(user_ids))}
            devices = {device.DeviceId: device for device in db.query(Device).filter(Device.DeviceId.in_({row.DeviceId for row in rows}))}
            for row in rows:
                scan.ScannedCount += 1
                scan.LastScannedSourceId = row.DeviceLogId
                if row.DeviceLogId in known or row.DeviceLogId in reviewed:
                    continue
                uid = str(row.UserId).strip() if row.UserId is not None else ''
                if uid not in students:
                    scan.UnknownStudentCount += 1
                    continue  # Never creates a student or stores new-user candidates.
                device = devices.get(row.DeviceId)
                reason = 'Missing from imported and quarantined punches below the synchronization checkpoint; original skip reason is unknown.'
                if device is None or not device.IsActive or not device.HostelId:
                    reason += ' Device is currently unregistered, inactive, or unassigned.'
                db.add(RecoveryPunch(ScanId=scan_id, SourceDeviceLogId=row.DeviceLogId, StudentId=students[uid],
                                    UserId=uid, DeviceId=row.DeviceId, LogDate=source_time(row.LogDate),
                                    DownloadDate=source_time(row.DownloadDate) if row.DownloadDate else None, Reason=reason))
                scan.CandidateCount += 1
            db.flush()
            if len(rows) < batch_size:
                scan.Status, scan.CompletedAt = 'COMPLETE', datetime.utcnow()
                break
            # Commit one short batch and return; the review UI resumes explicitly.
            break
        if scan.Status != 'COMPLETE':
            scan.Status = 'PARTIAL'
        db.commit()
        return scan
