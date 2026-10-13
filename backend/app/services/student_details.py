"""Read-only current student lists with one India-day biometric aggregation."""
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, literal
from backend.app.core.time import business_day, day_bounds, local_now
from backend.app.models.master import Student, Hostel
from backend.app.models.attendance import ProcessedPunch, StudentCurrentStatus
from backend.app.schemas.schemas import timestamp_json


def detailed_query(db, user, view, hostel_id=None, search=None, direction='either', now=None, include_counts=True):
    now = now or local_now()
    start, end = day_bounds(business_day(now))
    if user.Role == 'WARDEN':
        if not user.HostelId:
            raise HTTPException(403, 'Warden has no assigned hostel')
        if hostel_id is not None and hostel_id != user.HostelId:
            raise HTTPException(403, 'Hostel is outside your assignment')
        hostel_id = user.HostelId
    # Restrict the aggregation too, rather than aggregating other hostels for a warden.
    daily = db.query(
        ProcessedPunch.StudentId.label('sid'),
        func.sum(case((ProcessedPunch.PunchType == 'IN', 1), else_=0)).label('ins'),
        func.sum(case((ProcessedPunch.PunchType == 'OUT', 1), else_=0)).label('outs'),
    ).join(Student, Student.StudentId == ProcessedPunch.StudentId).filter(
        Student.RegistrationStatus == 'ACTIVE', ProcessedPunch.ProcessingStatus == 'VALID',
        ProcessedPunch.LogDate >= start, ProcessedPunch.LogDate < end,
        ProcessedPunch.PunchType.in_(['IN', 'OUT']))
    if hostel_id is not None:
        daily = daily.filter(Student.HostelId == hostel_id)
    daily = daily.group_by(ProcessedPunch.StudentId).subquery()
    ins, outs = (func.coalesce(daily.c.ins, 0), func.coalesce(daily.c.outs, 0)) if include_counts else (literal(0), literal(0))
    # Processor and manual overrides both maintain this latest effective event.
    # Legacy OUT statuses without an OUT timestamp remain unknown.
    out_since = case((and_(StudentCurrentStatus.CurrentStatus == 'OUT',
                          StudentCurrentStatus.LastPunchType == 'OUT'), StudentCurrentStatus.LastPunchTime), else_=None)
    query = db.query(Student.StudentId, Student.UserId, Student.StudentName, Student.HostelId,
                     Hostel.HostelName, Student.RoomNo,
                     func.coalesce(StudentCurrentStatus.CurrentStatus, 'NOT_STARTED').label('CurrentStatus'),
                     StudentCurrentStatus.LastPunchTime, ins.label('TodayInCount'), outs.label('TodayOutCount'),
                     out_since.label('OutSince')).outerjoin(Hostel, Student.HostelId == Hostel.HostelId).outerjoin(
        StudentCurrentStatus, Student.StudentId == StudentCurrentStatus.StudentId).filter(Student.RegistrationStatus == 'ACTIVE')
    if include_counts:
        query = query.outerjoin(daily, Student.StudentId == daily.c.sid)
    if hostel_id is not None:
        query = query.filter(Student.HostelId == hostel_id)
    if search:
        # Search is literal; SQL LIKE wildcard characters are not user wildcards.
        term = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.filter(or_(Student.UserId.like(f'%{term}%', escape='\\'), Student.StudentName.like(f'%{term}%', escape='\\')))
    if view in ('in', 'out'):
        query = query.filter(StudentCurrentStatus.CurrentStatus == view.upper())
    elif view == 'frequent':
        query = query.filter(ins >= 5 if direction == 'in' else outs >= 5 if direction == 'out' else or_(ins >= 5, outs >= 5))
    elif view == 'out_24h':
        query = query.filter(out_since < now - timedelta(hours=24))
    else:
        raise HTTPException(422, 'Unknown student list')
    return query, now


def detail_row(row, now):
    result = dict(row._mapping)
    since = result['OutSince']
    result['OutHours'] = round(max(0, (now - since).total_seconds() / 3600), 2) if since else None
    result['OutSince'] = timestamp_json(since, source=True)
    result['LastPunchTime'] = timestamp_json(result['LastPunchTime'], source=True)
    result['TodayInCount'], result['TodayOutCount'] = int(result['TodayInCount']), int(result['TodayOutCount'])
    return result
