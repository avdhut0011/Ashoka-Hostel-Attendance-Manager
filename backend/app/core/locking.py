from contextlib import contextmanager
import threading
from sqlalchemy import text, event

_locks = {}
_guard = threading.Lock()


@contextmanager
def attendance_lock(db, key='timeline'):
    """All attendance writers share a lock held until outer commit/rollback."""
    if db.get_bind().dialect.name == 'mssql':
        code = db.execute(text("""
            SET NOCOUNT ON; DECLARE @r INT;
            EXEC @r = sp_getapplock @Resource=:resource, @LockMode='Exclusive',
                @LockOwner='Transaction', @LockTimeout=15000;
            SELECT @r;
        """), {'resource': 'HostelAttendance:' + key}).scalar()
        if code is None or code < 0:
            raise RuntimeError('Attendance is busy; retry this operation')
        yield
    else:
        with _guard:
            lock = _locks.setdefault(key, threading.Lock())
        marker = 'attendance_lock:' + key
        if db.info.get(marker):
            yield
            return
        lock.acquire()
        db.info[marker] = True
        def release(session, transaction):
            if transaction.parent is None and session.info.pop(marker, False):
                lock.release()
        listener_key = 'attendance_listener:' + key
        if not db.info.get(listener_key):
            event.listen(db, 'after_transaction_end', release)
            db.info[listener_key] = True
        yield
