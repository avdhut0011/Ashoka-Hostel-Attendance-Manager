from datetime import datetime
from types import SimpleNamespace
from sqlalchemy import or_, func, case
from backend.app.core.config import settings
from backend.app.core.locking import attendance_lock
from backend.app.core.time import source_time, business_day, day_bounds
from backend.app.models.master import Student, Device, Hostel
from backend.app.models.integration import RawPunch, PunchCorrection
from backend.app.models.attendance import ProcessedPunch, StudentCurrentStatus, AttendanceOverride
from backend.app.services.state_history import state_at


def effective_raw(db, raw):
    correction = db.query(PunchCorrection).filter_by(RawPunchId=raw.RawPunchId).order_by(PunchCorrection.CorrectionId.desc()).first()
    if not correction:
        return raw
    return SimpleNamespace(RawPunchId=raw.RawPunchId, SourceDeviceLogId=raw.SourceDeviceLogId,
        DeviceId=correction.DeviceId, UserId=correction.UserId, LogDate=correction.LogDate)


def _status(db, student):
    replay = db.info.get('replay_context')
    if replay and replay['student'].StudentId == student.StudentId:
        return replay['current']
    row = db.query(StudentCurrentStatus).filter_by(StudentId=student.StudentId).first()
    if row is None:
        row = StudentCurrentStatus(StudentId=student.StudentId, CurrentStatus='NOT_STARTED',
            TodayInCount=0, TodayOutCount=0, TodayValidPunchCount=0, TodayDuplicatePunchCount=0)
        db.add(row)
        db.flush()
    return row


def _counter_day(db, curr, day):
    if curr.CounterDate == day:
        return
    if db.info.get('replay_context', {}).get('fast'):
        curr.CounterDate = day
        curr.TodayInCount = curr.TodayOutCount = curr.TodayValidPunchCount = curr.TodayDuplicatePunchCount = 0
        return
    start, end = day_bounds(day)
    counts = db.query(
        func.sum(case((ProcessedPunch.PunchType == 'IN', 1), else_=0)),
        func.sum(case((ProcessedPunch.PunchType == 'OUT', 1), else_=0)),
        func.sum(case((ProcessedPunch.ProcessingStatus == 'VALID', 1), else_=0)),
        func.sum(case((ProcessedPunch.ProcessingStatus == 'DUPLICATE', 1), else_=0)),
    ).filter(ProcessedPunch.StudentId == curr.StudentId, ProcessedPunch.LogDate >= start,
             ProcessedPunch.LogDate < end, ProcessedPunch.ProcessingStatus.in_(['VALID', 'DUPLICATE'])).one()
    curr.CounterDate = day
    curr.TodayInCount, curr.TodayOutCount, curr.TodayValidPunchCount, curr.TodayDuplicatePunchCount = [int(value or 0) for value in counts]


def _save(db, raw, student, status, reason, existing=None, **values):
    row = existing or ProcessedPunch(RawPunchId=raw.RawPunchId)
    row.StudentId = student.StudentId if student else None
    row.UserId, row.DeviceId, row.LogDate = raw.UserId, raw.DeviceId, source_time(raw.LogDate)
    row.ProcessingStatus, row.Reason = status, reason
    row.PunchType = values.pop('PunchType', None)
    row.IsFirstEverPunch = values.pop('IsFirstEverPunch', False)
    row.IsFirstValidPunchOfDay = values.pop('IsFirstValidPunchOfDay', False)
    row.PreviousStatus = values.pop('PreviousStatus', None)
    # Replay must preserve even unknown legacy snapshots; current assignments
    # cannot turn missing historical evidence into a verified assignment.
    if student and not existing:
        historical = state_at(db, student, row.LogDate)
        row.HostelIdSnapshot, row.RoomNoSnapshot = historical.HostelId, historical.RoomNo
    for key, value in values.items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    return row


def _process(db, raw, existing=None, enrolled=False, revalidate=False):
    when = source_time(raw.LogDate)
    replay = db.info.get('replay_context')
    device = replay['devices'].get(raw.DeviceId) if replay else db.query(Device).filter_by(DeviceId=raw.DeviceId).first()
    student = replay['student'] if replay and replay['student'].UserId == raw.UserId else db.query(Student).filter_by(UserId=raw.UserId).first()
    # Replay preserves existing validation decisions unless explicitly re-evaluated.
    preserve = existing is not None and not revalidate
    if preserve and existing.ProcessingStatus in ('INVALID_DEVICE', 'INACTIVE_STUDENT'):
        return existing
    dev_state = state_at(db, device, when) if device else None
    hostel = (replay['hostels'].get(dev_state.HostelId) if replay else db.query(Hostel).filter_by(HostelId=dev_state.HostelId).first()) if dev_state and dev_state.HostelId else None
    if not preserve and (not device or not dev_state.IsActive or not hostel or not hostel.IsActive):
        return _save(db, raw, student, 'INVALID_DEVICE', 'Device missing, inactive, unassigned, or hostel inactive', existing)
    if student is None:
        student = Student(UserId=raw.UserId, HostelId=dev_state.HostelId, RegistrationDate=business_day(when),
                          RegistrationStatus='PENDING_ENROLLMENT')
        db.add(student)
        db.flush()
    student_state = state_at(db, student, when)
    registration = student_state.RegistrationStatus
    # Formal enrollment retains the established retrospective registration rule.
    if enrolled and registration == 'PENDING_ENROLLMENT':
        registration = 'ACTIVE'
    if not preserve and registration not in ('ACTIVE', 'PENDING_ENROLLMENT'):
        return _save(db, raw, student, 'INACTIVE_STUDENT', 'Student inactive at punch time', existing)
    if not preserve and student_state.HostelId is not None and student_state.HostelId != dev_state.HostelId:
        return _save(db, raw, student, 'INVALID_DEVICE', 'Device does not match student hostel at punch time', existing)
    if student.HostelId is None and dev_state:
        student.HostelId = dev_state.HostelId
    curr = _status(db, student)
    punch_day = business_day(when)
    _counter_day(db, curr, punch_day)
    last = replay['last_valid'] if replay and replay['fast'] else db.query(ProcessedPunch).filter(ProcessedPunch.StudentId == student.StudentId,
        ProcessedPunch.ProcessingStatus == 'VALID', ProcessedPunch.LogDate <= when,
        ProcessedPunch.RawPunchId != raw.RawPunchId).order_by(ProcessedPunch.LogDate.desc(), ProcessedPunch.PunchId.desc()).first()
    if last:
        distance = (when - last.LogDate).total_seconds()
        last_dev = replay['devices'].get(last.DeviceId) if replay else db.query(Device).filter_by(DeviceId=last.DeviceId).first()
        last_hostel = last.HostelIdSnapshot
        if last_hostel is None and last_dev:
            last_hostel = state_at(db, last_dev, last.LogDate).HostelId
        hostel_id = existing.HostelIdSnapshot if preserve and existing.HostelIdSnapshot else (dev_state.HostelId if dev_state else None)
        if 0 <= distance <= settings.DUPLICATE_WINDOW_SECONDS and (last.DeviceId == raw.DeviceId or (hostel_id and hostel_id == last_hostel)):
            curr.TodayDuplicatePunchCount += 1
            return _save(db, raw, student, 'DUPLICATE', f'Within {distance:.1f}s of preceding valid punch', existing)
    first = last is None
    first_today = curr.LastValidAttendanceDate is None or curr.LastValidAttendanceDate < punch_day
    previous = curr.CurrentStatus
    # An override is authoritative until the next biometric event, even with no prior raw punch.
    has_override = any(o.EffectiveAt <= when for o in replay['overrides']) if replay else db.query(AttendanceOverride.OverrideId).filter(AttendanceOverride.StudentId == student.StudentId,
        AttendanceOverride.EffectiveAt <= when).first() is not None
    if registration == 'PENDING_ENROLLMENT' or (first and not has_override):
        kind = 'REGISTRATION'
    elif curr.CurrentStatus == 'IN':
        kind = 'OUT'
    else:
        kind = 'IN'
    row = _save(db, raw, student, 'VALID', 'Valid attendance punch', existing, PunchType=kind,
        IsFirstEverPunch=first, IsFirstValidPunchOfDay=first_today, PreviousStatus=previous)
    curr.CurrentStatus = kind
    curr.LastPunchId, curr.LastPunchTime, curr.LastPunchType = row.PunchId, when, kind
    curr.LastValidAttendanceDate = punch_day
    curr.TodayValidPunchCount += 1
    curr.TodayInCount += int(kind == 'IN')
    curr.TodayOutCount += int(kind == 'OUT')
    db.flush()
    return row


def apply_override(db, student, override):
    curr = _status(db, student)
    day = business_day(override.EffectiveAt)
    _counter_day(db, curr, day)
    curr.CurrentStatus = override.CurrentStatus
    curr.LastPunchTime, curr.LastPunchType = override.EffectiveAt, override.CurrentStatus
    curr.LastValidAttendanceDate = day
    curr.LastPunchId = None
    # Overrides are not biometric punches, so biometric counters are unchanged.
    db.flush()


def rebuild_student(db, student, enrolled=False, revalidate_ids=None):
    """Rebuild in one transaction without deleting raw records or changing PunchIds."""
    with attendance_lock(db):
        db.flush()
        curr = _status(db, student)
        existing = db.query(ProcessedPunch).filter_by(StudentId=student.StudentId).all()
        # Include corrected identities; original raw records remain untouched.
        candidate_ids = db.query(ProcessedPunch.RawPunchId).filter_by(StudentId=student.StudentId)
        corrected_ids = db.query(PunchCorrection.RawPunchId).filter_by(UserId=student.UserId)
        raws = db.query(RawPunch).filter(or_(RawPunch.UserId == student.UserId,
                RawPunch.RawPunchId.in_(candidate_ids), RawPunch.RawPunchId.in_(corrected_ids))).all()
        # One bounded join instead of a correction query per historical punch.
        latest = db.query(PunchCorrection.RawPunchId, func.max(PunchCorrection.CorrectionId).label('cid')).join(
            RawPunch, RawPunch.RawPunchId == PunchCorrection.RawPunchId).filter(or_(
                RawPunch.UserId == student.UserId, RawPunch.RawPunchId.in_(candidate_ids), RawPunch.RawPunchId.in_(corrected_ids))).group_by(PunchCorrection.RawPunchId).subquery()
        corrections = {c.RawPunchId: c for c in db.query(PunchCorrection).join(latest, PunchCorrection.CorrectionId == latest.c.cid)}
        raw_events = [SimpleNamespace(RawPunchId=r.RawPunchId, SourceDeviceLogId=r.SourceDeviceLogId,
            UserId=corrections[r.RawPunchId].UserId, DeviceId=corrections[r.RawPunchId].DeviceId,
            LogDate=corrections[r.RawPunchId].LogDate) if r.RawPunchId in corrections else r for r in raws]
        raw_events = [r for r in raw_events if r.UserId == student.UserId]
        overrides = db.query(AttendanceOverride).filter_by(StudentId=student.StudentId).all()
        # Legacy manual states cannot be reconstructed reliably; refuse destructive replay.
        last_row = db.get(ProcessedPunch, curr.LastPunchId) if curr.LastPunchId else None
        if curr.LastPunchTime and not overrides and existing and (last_row is None or last_row.LogDate != curr.LastPunchTime):
            raise ValueError('Legacy manual status requires an explicit auditable override before replay')
        curr.LastPunchId = curr.LastPunchTime = curr.LastPunchType = curr.LastValidAttendanceDate = curr.CounterDate = None
        curr.CurrentStatus = 'NOT_STARTED'
        curr.TodayInCount = curr.TodayOutCount = curr.TodayValidPunchCount = curr.TodayDuplicatePunchCount = 0
        event_ids = {r.RawPunchId for r in raw_events}
        by_raw = {p.RawPunchId: p for p in db.query(ProcessedPunch).join(RawPunch, RawPunch.RawPunchId == ProcessedPunch.RawPunchId).filter(or_(
            RawPunch.UserId == student.UserId, RawPunch.RawPunchId.in_(candidate_ids), RawPunch.RawPunchId.in_(corrected_ids))) if p.RawPunchId in event_ids}
        fast = {p.RawPunchId for p in existing if p.ProcessingStatus in ('VALID', 'DUPLICATE')} <= event_ids
        # Temporarily exclude future derived rows from preceding-punch lookup, preserving IDs.
        for row in by_raw.values():
            if row.ProcessingStatus in ('VALID', 'DUPLICATE'):
                row.ProcessingStatus = 'REPLAY_PENDING'
        db.flush()
        events = [(source_time(r.LogDate), 0, r.SourceDeviceLogId, r) for r in raw_events]
        events += [(o.EffectiveAt, 1, o.OverrideId, o) for o in overrides]
        from backend.app.models.master import StudentStateHistory, DeviceStateHistory
        devices, device_states = {}, {}
        device_ids = list({r.DeviceId for r in raw_events})
        for offset in range(0, len(device_ids), 500):
            chunk = device_ids[offset:offset+500]
            devices.update({d.DeviceId: d for d in db.query(Device).filter(Device.DeviceId.in_(chunk))})
            for state in db.query(DeviceStateHistory).filter(DeviceStateHistory.DeviceId.in_(chunk)).order_by(DeviceStateHistory.EffectiveFrom.desc(), DeviceStateHistory.StateId.desc()):
                device_states.setdefault(('DeviceId', state.DeviceId), []).append(state)
        histories = device_states
        histories[('StudentId', student.StudentId)] = db.query(StudentStateHistory).filter_by(StudentId=student.StudentId).order_by(StudentStateHistory.EffectiveFrom.desc(), StudentStateHistory.StateId.desc()).all()
        context = {'student': student, 'current': curr, 'devices': devices, 'hostels': {h.HostelId: h for h in db.query(Hostel)},
                   'histories': histories, 'last_valid': None, 'overrides': overrides, 'fast': fast}
        db.info['replay_context'] = context
        try:
            for _, kind, _, event in sorted(events, key=lambda item: item[:3]):
                if kind:
                    apply_override(db, student, event)
                else:
                    processed = _process(db, event, by_raw.get(event.RawPunchId), enrolled=enrolled or student.EnrolledAt is not None,
                                         revalidate=event.RawPunchId in (revalidate_ids or set()))
                    if processed.ProcessingStatus == 'VALID':
                        context['last_valid'] = processed
        finally:
            db.info.pop('replay_context', None)
        db.flush()
        return curr


def process_single_raw_punch(db, raw_punch):
    with attendance_lock(db):
        db.flush()
        existing = db.query(ProcessedPunch).filter_by(RawPunchId=raw_punch.RawPunchId).first()
        if existing:
            return existing
        raw = effective_raw(db, raw_punch)
        student = db.query(Student).filter_by(UserId=raw.UserId).first()
        curr = _status(db, student) if student else None
        if curr and curr.LastPunchTime and source_time(raw.LogDate) <= curr.LastPunchTime:
            # Invalid late records cannot affect location and need no replay.
            when = source_time(raw.LogDate)
            historical = state_at(db, student, when)
            device = db.query(Device).filter_by(DeviceId=raw.DeviceId).first()
            dev_state = state_at(db, device, when) if device else None
            hostel = db.query(Hostel).filter_by(HostelId=dev_state.HostelId, IsActive=True).first() if dev_state and dev_state.HostelId else None
            if historical.RegistrationStatus not in ('ACTIVE', 'PENDING_ENROLLMENT') or not dev_state or not dev_state.IsActive or not hostel or (historical.HostelId and historical.HostelId != dev_state.HostelId):
                return _process(db, raw, enrolled=bool(student.EnrolledAt))
            rebuild_student(db, student)
            return db.query(ProcessedPunch).filter_by(RawPunchId=raw.RawPunchId).one()
        if curr and curr.LastPunchTime is None and db.query(ProcessedPunch.PunchId).filter_by(StudentId=student.StudentId, ProcessingStatus='VALID').first():
            rebuild_student(db, student)
            return db.query(ProcessedPunch).filter_by(RawPunchId=raw.RawPunchId).one()
        return _process(db, raw, enrolled=bool(student and student.EnrolledAt))
