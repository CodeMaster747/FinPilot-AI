"""Message times are stored as wall-clock time in the user's zone (Asia/Kolkata by default), whatever zone the
server runs in: a bank SMS stamped 23:30 IST belongs to that day, not to the next day in UTC."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import get_settings


@lru_cache
def app_zone() -> ZoneInfo:
    return ZoneInfo(get_settings().app_timezone)


def local_from_epoch_ms(ms: int | float) -> datetime:
    return datetime.fromtimestamp(float(ms) / 1000, tz=timezone.utc).astimezone(app_zone()).replace(tzinfo=None)


def to_local_naive(value: datetime) -> datetime:
    """Aware datetimes are converted to the app zone; naive ones are assumed to be wall-clock time already."""
    if value.tzinfo is None:
        return value
    return value.astimezone(app_zone()).replace(tzinfo=None)


def now_local() -> datetime:
    return datetime.now(tz=app_zone()).replace(tzinfo=None, microsecond=0)
