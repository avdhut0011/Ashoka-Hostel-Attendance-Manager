from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from backend.app.core.config import settings


def source_time(value: datetime) -> datetime:
    """Naive timestamps are source wall-clock values; normalize aware inputs."""
    if value.tzinfo is not None:
        return value.astimezone(ZoneInfo(settings.SOURCE_TIMEZONE)).replace(tzinfo=None)
    return value


def local_now() -> datetime:
    return datetime.now(ZoneInfo(settings.SOURCE_TIMEZONE)).replace(tzinfo=None)


def business_day(value: datetime) -> date:
    aware = source_time(value).replace(tzinfo=ZoneInfo(settings.SOURCE_TIMEZONE))
    return aware.astimezone(ZoneInfo(settings.APP_TIMEZONE)).date()


def day_bounds(day: date | None = None):
    day = day or datetime.now(ZoneInfo(settings.APP_TIMEZONE)).date()
    start = datetime.combine(day, time.min, ZoneInfo(settings.APP_TIMEZONE))
    end = datetime.combine(day + timedelta(days=1), time.min, ZoneInfo(settings.APP_TIMEZONE))
    return source_time(start), source_time(end)
