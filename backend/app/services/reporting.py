from datetime import date
from fastapi import HTTPException
from sqlalchemy import func, or_, and_, true, String
from backend.app.core.time import day_bounds
from backend.app.models.attendance import ProcessedPunch, AttendanceOverride
from backend.app.models.master import Student, Hostel, Device
from backend.app.schemas.schemas import ProcessedPunchResponse


def hostel_column():
    # Legacy rows are explicitly marked unknown rather than silently backfilled.
    return ProcessedPunch.HostelIdSnapshot


def punch_query(db, user, start=None, end=None, hostel_id=None, user_id=None, punch_type=None, status=None, search_all=False):
    query = db.query(ProcessedPunch, Student.StudentName, Hostel.HostelName, Device.DeviceName, Student.RoomNo).outerjoin(
        Student, ProcessedPunch.StudentId == Student.StudentId).outerjoin(
        Hostel, hostel_column() == Hostel.HostelId).outerjoin(Device, ProcessedPunch.DeviceId == Device.DeviceId)
    if start and end and start > end:
        raise HTTPException(422, 'Start date must not be after end date')
    if start:
        query = query.filter(ProcessedPunch.LogDate >= day_bounds(start)[0])
    if end:
        query = query.filter(ProcessedPunch.LogDate < day_bounds(end)[1])
    if user.Role == 'WARDEN':
        if not user.HostelId:
            raise HTTPException(403, 'Warden has no assigned hostel')
        query = query.filter(hostel_column() == user.HostelId)
    elif hostel_id:
        query = query.filter(hostel_column() == hostel_id)
    if user_id:
        name_match = db.query(Student.StudentId).filter(Student.StudentId == ProcessedPunch.StudentId,
            Student.StudentName.like(f'%{user_id}%')).correlate(ProcessedPunch).exists()
        matches = [ProcessedPunch.UserId.like(f'%{user_id}%'), name_match]
        if search_all:
            matches += [func.cast(ProcessedPunch.DeviceId, String).like(f'%{user_id}%'), ProcessedPunch.Reason.like(f'%{user_id}%')]
        query = query.filter(or_(*matches))
    if punch_type:
        query = query.filter(ProcessedPunch.PunchType == punch_type)
    if status:
        query = query.filter(ProcessedPunch.ProcessingStatus == status)
    return query


def punch_count(query):
    # Display joins are unnecessary for counts; search uses an EXISTS predicate.
    return query.session.query(func.count(ProcessedPunch.PunchId)).filter(query.whereclause if query.whereclause is not None else true()).scalar() or 0


def punch_page(query, skip, limit, cursor=None, response=None):
    # Page narrow IDs before fetching wide display columns and joining names.
    ids = query.session.query(ProcessedPunch.PunchId.label('pid')).filter(query.whereclause if query.whereclause is not None else true())
    if cursor:
        import base64, json
        from datetime import datetime
        from backend.app.core.time import source_time
        try:
            if len(cursor) > 200:
                raise ValueError()
            stamp, identity = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            when = source_time(datetime.fromisoformat(stamp))
            if type(identity) is not int or not 0 < identity <= 9223372036854775807:
                raise ValueError()
        except Exception:
            raise HTTPException(422, 'Invalid pagination cursor')
        ids = ids.filter(or_(ProcessedPunch.LogDate < when, and_(ProcessedPunch.LogDate == when, ProcessedPunch.PunchId < identity)))
    ids = ids.order_by(ProcessedPunch.LogDate.desc(), ProcessedPunch.PunchId.desc())
    if not cursor:
        ids = ids.offset(skip)
    ids = ids.limit(limit).subquery()
    rows = query.join(ids, ids.c.pid == ProcessedPunch.PunchId).order_by(ProcessedPunch.LogDate.desc(), ProcessedPunch.PunchId.desc()).all()
    if response is not None and rows:
        import base64, json
        last = rows[-1][0]
        response.headers['X-Next-Cursor'] = base64.urlsafe_b64encode(json.dumps([last.LogDate.isoformat(), last.PunchId]).encode()).decode()
    return rows


def punch_response(row, db=None):
    punch, name, hostel, device, room = row
    result = ProcessedPunchResponse.model_validate(punch)
    result.StudentName, result.HostelName, result.DeviceName = name, hostel if punch.HostelIdSnapshot is not None else None, device
    result.HistoricalAssignmentKnown = punch.HostelIdSnapshot is not None
    if db is not None:
        from backend.app.services.verified_history import historical_room
        result.HistoricalRoomNo, result.HistoricalRoomSource = historical_room(db, punch)
    return result


def override_query(db, user, start=None, end=None, hostel_id=None, user_id=None, punch_type=None, status=None):
    query = db.query(AttendanceOverride, Student.UserId, Student.StudentName, Hostel.HostelName).join(
        Student, AttendanceOverride.StudentId == Student.StudentId).outerjoin(Hostel, AttendanceOverride.HostelIdSnapshot == Hostel.HostelId)
    if start:
        query = query.filter(AttendanceOverride.EffectiveAt >= day_bounds(start)[0])
    if end:
        query = query.filter(AttendanceOverride.EffectiveAt < day_bounds(end)[1])
    if user.Role == 'WARDEN':
        if not user.HostelId:
            raise HTTPException(403, 'Warden has no assigned hostel')
        query = query.filter(AttendanceOverride.HostelIdSnapshot == user.HostelId)
    elif hostel_id:
        query = query.filter(AttendanceOverride.HostelIdSnapshot == hostel_id)
    if user_id:
        query = query.filter((Student.UserId.like(f'%{user_id}%')) | (Student.StudentName.like(f'%{user_id}%')))
    if punch_type:
        query = query.filter(AttendanceOverride.CurrentStatus == punch_type)
    if status and status != 'MANUAL_OVERRIDE':
        query = query.filter(AttendanceOverride.OverrideId < 0)
    return query
