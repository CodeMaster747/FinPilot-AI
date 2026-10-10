"""Exact money handling.

SQLite has no exact decimal type, so amounts are stored as integer paise and surfaced in Python
as ``Decimal`` rupees. Floats are only ever used for statistics and charts, never for balances.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy.types import BigInteger, TypeDecorator

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def D(value: Any) -> Decimal:
    """Coerce numbers / numeric strings (including '1,23,456.50') to a 2dp Decimal."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value.quantize(CENT, ROUND_HALF_UP)
    if isinstance(value, float):
        value = repr(value)
    text = str(value).replace(",", "").replace("₹", "").strip()
    try:
        return Decimal(text).quantize(CENT, ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"not a money amount: {value!r}") from exc


def to_paise(value: Any) -> int:
    return int((D(value) * 100).to_integral_value(ROUND_HALF_UP))


def from_paise(paise: int) -> Decimal:
    return (Decimal(paise) / 100).quantize(CENT)


class Money(TypeDecorator):
    """Decimal rupees in Python, integer paise in the database."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> int | None:
        if value is None:
            return None
        return to_paise(value)

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return from_paise(int(value))


def fmt_inr(amount: Decimal | float | int, decimals: bool = False) -> str:
    """Format with Indian digit grouping: 1234567.5 -> ₹12,34,567."""
    value = D(amount)
    negative = value < 0
    value = abs(value)
    if not decimals:
        value = value.quantize(Decimal("1"), ROUND_HALF_UP)
    whole, frac = f"{value:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    text = f"₹{whole}.{frac}" if decimals else f"₹{whole}"
    return f"-{text}" if negative else text
