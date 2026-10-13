"""Database-backed login limits, with a legacy local helper for isolated callers."""
from collections import OrderedDict
import threading
import time
from fastapi import HTTPException

_attempts = OrderedDict()
_lock = threading.Lock()


def check_login(client_ip, username, db=None):
    if db is not None:
        return shared_login(client_ip, username, db)
    key = client_ip, username.casefold()
    now = time.monotonic()
    with _lock:
        times = [value for value in _attempts.pop(key, []) if now - value < 60]
        if len(times) >= 10:
            _attempts[key] = times
            raise HTTPException(429, 'Too many login attempts; retry in one minute', headers={'Retry-After': '60'})
        _attempts[key] = times + [now]
        while len(_attempts) > 5000:
            _attempts.popitem(last=False)


def clear_login(client_ip, username):
    with _lock:
        _attempts.pop((client_ip, username.casefold()), None)


def shared_login(client_ip, username, db):
    """Atomic IP/account limits shared by all processes; failed requests persist."""
    from datetime import datetime, timedelta
    from hashlib import sha256
    from sqlalchemy import select
    from backend.app.models.hardening import LoginThrottle
    now = datetime.utcnow()
    table = LoginThrottle.__table__
    buckets = [('ip:' + client_ip, 60), ('account:' + username.strip().casefold(), 10)]
    buckets = sorted((sha256(key.encode()).hexdigest(), maximum) for key, maximum in buckets)
    with _lock:
        # Only the newly created throttle table is maintained.
        db.execute(table.delete().where(table.c.UpdatedAt < now - timedelta(days=1)))
        blocked = False
        for key, maximum in buckets:
            row = db.execute(select(table).where(table.c.BucketKey == key).with_hint(table, 'WITH (UPDLOCK, HOLDLOCK)', 'mssql')).mappings().first()
            if row is None:
                db.execute(table.insert().values(BucketKey=key, WindowStart=now, Attempts=1, UpdatedAt=now))
            elif now - row['WindowStart'] >= timedelta(seconds=60):
                db.execute(table.update().where(table.c.BucketKey == key).values(WindowStart=now, Attempts=1, UpdatedAt=now))
            elif row['Attempts'] >= maximum:
                blocked = True
            else:
                db.execute(table.update().where(table.c.BucketKey == key).values(Attempts=table.c.Attempts + 1, UpdatedAt=now))
        db.commit()
    if blocked:
        raise HTTPException(429, 'Too many login attempts; retry in one minute', headers={'Retry-After': '60'})
