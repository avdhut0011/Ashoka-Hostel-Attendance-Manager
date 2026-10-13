from functools import wraps
from threading import BoundedSemaphore
from fastapi import HTTPException
from backend.app.core.config import settings

_slots = BoundedSemaphore(settings.REPORT_CONCURRENCY)

def bounded_export(function):
    @wraps(function)
    def generate(*args, **kwargs):
        if not _slots.acquire(blocking=False):
            raise HTTPException(429, 'A report is being generated. Please retry shortly.', headers={'Retry-After': '10'})
        try:
            return function(*args, **kwargs)
        finally:
            _slots.release()
    return generate
