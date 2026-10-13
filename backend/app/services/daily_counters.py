"""Read-only daily totals. Stored counter caches never determine API totals."""
from sqlalchemy import case, func, and_
from backend.app.core.time import day_bounds
from backend.app.models.attendance import ProcessedPunch


def daily_counters(db, student_ids, day=None):
    start, end = day_bounds(day) if day is not None else day_bounds()
    empty = dict(TodayInCount=0, TodayOutCount=0, TodayValidPunchCount=0, TodayDuplicatePunchCount=0)
    result = {sid: dict(empty) for sid in student_ids}
    if not result:
        return result
    valid = ProcessedPunch.ProcessingStatus == 'VALID'
    rows = db.query(
        ProcessedPunch.StudentId,
        func.sum(case((and_(valid, ProcessedPunch.PunchType == 'IN'), 1), else_=0)),
        func.sum(case((and_(valid, ProcessedPunch.PunchType == 'OUT'), 1), else_=0)),
        func.sum(case((valid, 1), else_=0)),
        func.sum(case((ProcessedPunch.ProcessingStatus == 'DUPLICATE', 1), else_=0)),
    ).filter(ProcessedPunch.StudentId.in_(result), ProcessedPunch.LogDate >= start,
             ProcessedPunch.LogDate < end).group_by(ProcessedPunch.StudentId).all()
    for sid, *counts in rows:
        result[sid] = dict(zip(empty, (int(value or 0) for value in counts)))
    return result
