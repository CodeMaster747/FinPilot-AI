from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def iso(value: datetime | date | None) -> str | None:
    """ISO-8601; naive datetimes are UTC and get a 'Z' so browsers convert to local time."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds") + ("Z" if value.tzinfo is None else "")
    return value.isoformat()


def num(value: Decimal | float | int | None) -> float | None:
    """Money -> JSON number (2dp). Exact Decimal maths happens server-side; this is display only."""
    if value is None:
        return None
    return float(round(Decimal(value), 2))
