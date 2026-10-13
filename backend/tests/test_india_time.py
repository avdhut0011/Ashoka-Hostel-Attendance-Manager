from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.database import TargetSessionLocal
from backend.app.core import time as clock
from backend.app.core.security import create_access_token
from backend.app.models import Student, StudentCurrentStatus, RawPunch, ProcessedPunch, User
from backend.app.services.daily_counters import daily_counters
from backend.app.schemas.schemas import timestamp_json


def test_india_midnight_bounds_for_utc_instant():
    assert clock.business_day(datetime(2026, 10, 9, 18, 30, tzinfo=timezone.utc)).isoformat() == '2026-10-10'
    start, end = clock.day_bounds(clock.business_day(datetime(2026, 10, 9, 18, 30, tzinfo=timezone.utc)))
    assert start == datetime(2026, 10, 10) and end == datetime(2026, 10, 11)


def test_counter_reads_ignore_stale_cache_and_do_not_write(monkeypatch):
    from backend.app.services import daily_counters as service
    now = datetime(2026, 10, 10)
    monkeypatch.setattr(service, 'day_bounds', lambda: (now, now + timedelta(days=1)))
    with TargetSessionLocal() as db:
        student = db.query(Student).filter_by(UserId='U1001').one()
        sid = student.StudentId
        cache = StudentCurrentStatus(StudentId=sid, CurrentStatus='IN', CounterDate=now.date() - timedelta(days=1),
                                     TodayInCount=99, TodayOutCount=98, TodayValidPunchCount=197, TodayDuplicatePunchCount=55)
        db.add(cache)
        for i, (when, kind, status) in enumerate([
            (now - timedelta(seconds=1), 'OUT', 'VALID'),
            (now, 'IN', 'VALID'),
            (now + timedelta(seconds=1), None, 'DUPLICATE'),
            (now + timedelta(hours=23, minutes=59, seconds=59), 'OUT', 'VALID'),
            (now + timedelta(days=1), 'IN', 'VALID'),
            (now + timedelta(hours=1), 'IN', 'INVALID_DEVICE'),
        ], 1):
            raw = RawPunch(SourceDeviceLogId=i, UserId=student.UserId, DeviceId=101, LogDate=when)
            db.add(raw)
            db.flush()
            db.add(ProcessedPunch(RawPunchId=raw.RawPunchId, StudentId=sid, UserId=student.UserId,
                                  DeviceId=101, LogDate=when, PunchType=kind, ProcessingStatus=status,
                                  HostelIdSnapshot=1))
        db.commit()
        counts = daily_counters(db, [sid])[sid]
        assert counts == dict(TodayInCount=1, TodayOutCount=1, TodayValidPunchCount=2, TodayDuplicatePunchCount=1)
        assert not db.dirty and not db.new and not db.deleted
        admin = db.query(User).filter_by(Username='admin').one()
        token = create_access_token({'sub': admin.Username, 'id': admin.SystemUserId, 'ver': 0})
    client = TestClient(app)
    for path in ('/api/students', f'/api/students/{sid}'):
        response = client.get(path, headers={'Authorization': 'Bearer ' + token})
        assert response.status_code == 200
        item = response.json()[0] if isinstance(response.json(), list) else response.json()
        assert all(item[key] == value for key, value in counts.items())
    with TargetSessionLocal() as db:
        cache = db.get(StudentCurrentStatus, sid)
        assert cache.TodayInCount == 99 and cache.TodayDuplicatePunchCount == 55
    monkeypatch.setattr(service, 'day_bounds', lambda: (now + timedelta(days=2), now + timedelta(days=3)))
    with TargetSessionLocal() as db:
        assert all(value == 0 for value in daily_counters(db, [sid])[sid].values())


def test_source_and_audit_timestamp_offsets_are_distinct():
    value = datetime(2026, 10, 10, 2)
    assert timestamp_json(value, source=True).endswith('+05:30')
    assert timestamp_json(value).endswith('+00:00')
