"""Shared metric functions — one source of truth for the dashboard, insights, the coach and affordability."""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Budget, Category, Goal, Transaction


@dataclass
class Row:
    date: date
    amount: Decimal  # signed: credit +, debit -
    category: str
    kind: str  # income | expense | savings
    essential: bool
    discretionary: bool
    sensitive: bool
    merchant: str
    origin: str
    id: int


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def months_ago(d: date, months: int) -> date:
    """The same day `months` calendar months earlier (clamped to the month's length)."""
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


def rows(db: Session, user_id: int, start: date | None = None, end: date | None = None, origins: set[str] | None = None) -> list[Row]:
    q = select(Transaction, Category).join(Category, Category.id == Transaction.category_id).where(
        Transaction.user_id == user_id, Transaction.status == "posted", Transaction.is_transfer.is_(False))
    if start:
        q = q.where(Transaction.txn_date >= start)
    if end:
        q = q.where(Transaction.txn_date <= end)
    out = []
    for t, c in db.execute(q).all():
        if origins is not None and t.origin not in origins:
            continue
        out.append(Row(t.txn_date, t.amount if t.direction == "credit" else -t.amount, c.name, c.kind, c.is_essential,
                       c.is_discretionary, c.is_sensitive, t.merchant_name, t.origin, t.id))
    return out


def coverage_start(db: Session, user_id: int) -> date | None:
    """The first day the user's records cover (their earliest transaction)."""
    return db.scalar(select(func.min(Transaction.txn_date)).where(Transaction.user_id == user_id, Transaction.status == "posted"))


def first_full_month(db: Session, user_id: int) -> date | None:
    start = coverage_start(db, user_id)
    if start is None:
        return None
    return start if start.day == 1 else add_months(month_start(start), 1)


def complete_months(db: Session, user_id: int, today: date | None = None) -> int:
    """How many whole calendar months (before the current one) the user's records cover."""
    today = today or date.today()
    first = first_full_month(db, user_id)
    if first is None:
        return 0
    current = month_start(today)
    return max(0, (current.year - first.year) * 12 + current.month - first.month)


def spend(rs: list[Row]) -> Decimal:
    """Net spending on expenses (refunds in expense categories reduce it)."""
    return -sum((r.amount for r in rs if r.kind == "expense"), Decimal(0))


def income(rs: list[Row]) -> Decimal:
    return sum((r.amount for r in rs if r.kind == "income" and r.amount > 0), Decimal(0))


def savings(rs: list[Row]) -> Decimal:
    return -sum((r.amount for r in rs if r.kind == "savings"), Decimal(0))


def by_category(rs: list[Row]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(Decimal)
    for r in rs:
        if r.kind == "expense":
            out[r.category] -= r.amount
    return {k: v for k, v in sorted(out.items(), key=lambda kv: -kv[1]) if v > 0}


def month_summary(db: Session, user_id: int, month: date) -> dict:
    start, end = month_start(month), add_months(month_start(month), 1) - timedelta(days=1)
    rs = rows(db, user_id, start, end)
    inc, out, sav = income(rs), spend(rs), savings(rs)
    rate = float((inc - out) / inc * 100) if inc else 0.0
    return {"month": start.isoformat(), "income": inc, "spend": out, "invested": sav, "net": inc - out - sav, "savings_rate": round(rate, 1)}


def monthly_series(db: Session, user_id: int, months: int, today: date | None = None) -> list[dict]:
    today = today or date.today()
    first = add_months(month_start(today), -(months - 1))
    rs = rows(db, user_id, first, today)
    buckets: dict[date, list[Row]] = defaultdict(list)
    for r in rs:
        buckets[month_start(r.date)].append(r)
    out = []
    for i in range(months):
        m = add_months(first, i)
        b = buckets.get(m, [])
        inc, sp, sv = income(b), spend(b), savings(b)
        out.append({"month": m.isoformat(), "income": inc, "spend": sp, "invested": sv,
                    "savings_rate": round(float((inc - sp) / inc * 100), 1) if inc else 0.0})
    return out


def median_monthly(db: Session, user_id: int, months: int, pick, today: date | None = None, origins: set[str] | None = None) -> Decimal:  # noqa: ANN001
    """Median over the last N *complete* months of the monthly total of rows matching `pick`.
    Only months the user's records fully cover count: a user who joined last week has no complete month
    yet (rather than five empty ones that would drag the median to ₹0)."""
    today = today or date.today()
    covered = complete_months(db, user_id, today)
    months = min(months, covered)
    if months <= 0:
        return Decimal(0)
    first = add_months(month_start(today), -months)
    rs = rows(db, user_id, first, month_start(today) - timedelta(days=1), origins)
    totals: dict[date, Decimal] = {add_months(first, i): Decimal(0) for i in range(months)}
    for r in rs:
        if pick(r):
            totals[month_start(r.date)] += -r.amount if r.amount < 0 else r.amount
    vals = sorted(totals.values())
    return statistics.median(vals) if vals else Decimal(0)


def budgets_status(db: Session, user_id: int, today: date | None = None) -> list[dict]:
    today = today or date.today()
    start = month_start(today)
    rs = rows(db, user_id, start, today)
    spent = by_category(rs)
    days_in_month = (add_months(start, 1) - start).days
    out = []
    for b, c in db.execute(select(Budget, Category).join(Category, Category.id == Budget.category_id).where(Budget.user_id == user_id)).all():
        used = spent.get(c.name, Decimal(0))
        pct = float(used / b.amount * 100) if b.amount else 0.0
        expected = today.day / days_in_month * 100
        out.append({"id": b.id, "category": c.name, "category_id": c.id, "icon": c.icon, "budget": b.amount, "spent": used,
                    "pct": round(pct, 1), "pace_pct": round(expected, 1), "over_pace": pct > expected + 10, "over": used > b.amount})
    out.sort(key=lambda x: -x["pct"])
    return out


def goals_status(db: Session, user_id: int, today: date | None = None) -> list[dict]:
    today = today or date.today()
    out = []
    for g in db.scalars(select(Goal).where(Goal.user_id == user_id, Goal.status == "active").order_by(Goal.target_date)).all():
        months_left = max(1, (g.target_date.year - today.year) * 12 + g.target_date.month - today.month)
        remaining = max(Decimal(0), g.target - g.saved)
        out.append({"id": g.id, "name": g.name, "target": g.target, "saved": g.saved, "target_date": g.target_date,
                    "pct": round(float(g.saved / g.target * 100), 1) if g.target else 0.0, "remaining": remaining,
                    "months_left": months_left, "monthly_needed": (remaining / months_left).quantize(Decimal("0.01")),
                    "wishlist_item_id": g.wishlist_item_id, "keywords": g.keywords})
    return out
