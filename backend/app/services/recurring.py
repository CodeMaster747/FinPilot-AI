"""Recurring-payment detection shared by forecasting (the known schedule), subscriptions and affordability.

Groups payments by merchant and direction, then looks for a stable interval (weekly / monthly / bimonthly /
quarterly / annual) with a stable amount. Price changes are allowed: the *recent* run must be stable.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Transaction

CADENCES = [("weekly", 7, 2), ("monthly", 30.4, 4), ("bimonthly", 60.8, 6), ("quarterly", 91.3, 8), ("annual", 365.2, 12)]


@dataclass
class Recurring:
    merchant: str
    direction: str
    category: str
    category_kind: str
    cadence: str
    period_days: float
    amount: Decimal  # current (most recent) amount
    first: date
    last: date
    count: int
    day_of_month: int | None
    next_date: date
    active: bool
    amounts: list[Decimal] = field(default_factory=list)
    dates: list[date] = field(default_factory=list)
    txn_ids: list[int] = field(default_factory=list)

    @property
    def monthly_equivalent(self) -> Decimal:
        return (self.amount * Decimal(30.4) / Decimal(self.period_days)).quantize(Decimal("0.01"))

    def occurrences(self, start: date, end: date) -> list[date]:
        """Expected dates in [start, end]."""
        out, d = [], self.next_date
        while d < start:
            d = self._advance(d)
        while d <= end:
            out.append(d)
            d = self._advance(d)
        return out

    def _advance(self, d: date) -> date:
        if self.cadence in ("monthly", "bimonthly", "quarterly", "annual"):
            months = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "annual": 12}[self.cadence]
            y, m = divmod(d.month - 1 + months, 12)
            day = self.day_of_month or d.day
            for dd in (day, 30, 29, 28):
                try:
                    return date(d.year + y, m + 1, dd)
                except ValueError:
                    continue
        return d + timedelta(days=round(self.period_days))


def _classify(interval: float) -> tuple[str, float, float] | None:
    for name, period, tol in CADENCES:
        if abs(interval - period) <= tol:
            return name, period, tol
    return None


def detect_recurring(db: Session, user_id: int, today: date | None = None, min_count: int = 3,
                     origins: set[str] | None = None, until: date | None = None) -> list[Recurring]:
    """`until`: only look at payments up to that day (the forecast backtest asks "what was known back then?")."""
    today = today or date.today()
    q = select(Transaction, Category).join(Category, Category.id == Transaction.category_id).where(
        Transaction.user_id == user_id, Transaction.status == "posted", Transaction.is_transfer.is_(False))
    if until is not None:
        q = q.where(Transaction.txn_date <= until)
    rows = db.execute(q.order_by(Transaction.txn_date)).all()
    groups: dict[tuple[str, str], list[tuple[Transaction, Category]]] = {}
    for t, c in rows:
        if origins is not None and t.origin not in origins:
            continue
        groups.setdefault((t.merchant_name, t.direction), []).append((t, c))
    found: list[Recurring] = []
    for (merchant, direction), items in groups.items():
        if len(items) < 2:
            continue
        dates = [t.txn_date for t, _ in items]
        # collapse same-day duplicates (e.g. two SIPs to the same merchant are separate series by name)
        intervals = [(b - a).days for a, b in zip(dates, dates[1:]) if (b - a).days > 0]
        if not intervals:
            continue
        med = statistics.median(intervals)
        cad = _classify(med)
        if cad is None:
            continue
        name, period, tol = cad
        regular = sum(1 for iv in intervals if abs(iv - period) <= tol or abs(iv - 2 * period) <= tol)
        needed = 2 if name == "annual" else min_count
        if len(items) < needed or regular < 0.75 * len(intervals):
            continue
        amounts = [t.amount for t, _ in items]
        recent = amounts[-4:]
        spread = (max(recent) - min(recent)) / max(Decimal(1), statistics.median(recent))
        if spread > Decimal("0.15"):
            continue
        last = dates[-1]
        day = round(statistics.median([d.day for d in dates[-6:]])) if name != "weekly" else None
        rec = Recurring(
            merchant=merchant, direction=direction, category=items[-1][1].name, category_kind=items[-1][1].kind, cadence=name,
            period_days=period, amount=amounts[-1], first=dates[0], last=last, count=len(items), day_of_month=day,
            next_date=last, active=(today - last).days <= period * 1.5 + tol, amounts=amounts, dates=dates,
            txn_ids=[t.id for t, _ in items],
        )
        nxt = rec._advance(last)
        while nxt <= today - timedelta(days=0) and rec.active:
            nxt = rec._advance(nxt)
        rec.next_date = nxt
        found.append(rec)
    return found
