"""What the user can afford, judged against their real finances. Used by the dashboard, the wishlist,
"Can I afford…?" checks, insights and the coach.

  income     = median monthly income over the complete months the user's records cover (up to 6);
               with under 2 such months, the take-home pay they entered during setup
  committed  = recurring outflows (rent, EMIs, SIPs, insurance, subscriptions, bills) per month
  essential  = median monthly essential spending outside those recurring items (3 months)
  goals      = what active goals need per month
  surplus    = income - committed - essential - goals
  buffer     = max(user floor, one month of committed + essential)
  safe_to_spend = max(0, min(liquid - buffer - dues before next income - goals, lowest 60-day forecast (p10) - buffer))
  wants_left = monthly wants budget (30% of income unless set) - discretionary spending so far this month

Verdicts: buy_now (fits safe_to_spend and wants_left, the forecast never dips below the buffer, and the emergency
fund is in place unless it's an everyday replenishment); save_up (affordable within 12 months of surplus);
not_now otherwise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.money import fmt_inr
from app.models import User
from app.services import metrics
from app.services.accounts import balance_known, liquid_balance
from app.services.forecasting.engine import lowest_point, what_if
from app.services.forecasting.service import latest as latest_forecast
from app.services.recurring import detect_recurring

DISCLAIMER = ("Estimates to help you plan, not financial advice. FinPilot has no affiliate links and no paid placements — "
              "it never tells you to buy anything.")
COMMITTED_CATEGORIES = {"Rent", "Loan EMI", "Investments", "Insurance", "Subscriptions", "Phone & Internet", "Utilities",
                        "Sports & Fitness", "Education"}
DEFAULT_BUFFER_FLOOR = 10000


@dataclass
class Snapshot:
    income: Decimal
    committed: Decimal
    essential: Decimal
    goals: Decimal
    surplus: Decimal
    buffer: Decimal
    emergency_target: Decimal
    liquid: Decimal
    dues_before_income: Decimal
    next_income: date | None
    forecast_low: Decimal | None
    forecast_low_date: str | None
    safe_to_spend: Decimal
    wants_budget: Decimal
    wants_spent: Decimal
    wants_left: Decimal
    emergency_ok: bool
    income_source: str = "history"  # history | profile | none
    balance_known: bool = True  # False until a bank alert, statement or the user tells us an account balance
    months_of_data: int = 0
    wants_known: bool = True  # False while there is no income (measured or entered) and no wants budget to derive one from
    explain: list[str] = field(default_factory=list)

    @property
    def spendable(self) -> Decimal:
        """What is comfortable to spend now: safe-to-spend, capped by this month's wants budget when there is one.
        (With no income known yet there is no basis for a wants budget, so it must not cap the figure at zero.)"""
        return min(self.safe_to_spend, self.wants_left) if self.wants_known else self.safe_to_spend

    def as_json(self) -> dict[str, Any]:
        out = {}
        for k, v in self.__dict__.items():
            out[k] = float(v) if isinstance(v, Decimal) else v.isoformat() if isinstance(v, date) else v
        out["spendable"] = float(self.spendable)
        return out


def _commitments(db: Session, user_id: int, today: date):  # noqa: ANN202
    recurring = [r for r in detect_recurring(db, user_id, today) if r.active]
    committed_recs = [r for r in recurring if r.direction == "debit" and r.category in COMMITTED_CATEGORIES]
    committed = sum((r.monthly_equivalent for r in committed_recs), Decimal(0))
    recurring_merchants = {r.merchant for r in committed_recs}
    essential = metrics.median_monthly(db, user_id, 3, lambda r: r.kind == "expense" and r.essential and r.amount < 0
                                       and r.merchant not in recurring_merchants, today)
    return recurring, committed_recs, committed, recurring_merchants, essential


def _floor(user: User) -> Decimal:
    return Decimal(str((user.preferences or {}).get("buffer_floor", DEFAULT_BUFFER_FLOOR)))


def _declared_rent(user: User) -> Decimal:
    return Decimal(str((user.preferences or {}).get("rent_monthly") or 0))


def safety_buffer(db: Session, user: User, today: date | None = None) -> Decimal:
    """The one safety-buffer rule used everywhere: max(the user's floor, one month of must-pays)."""
    _, committed_recs, committed, _, essential = _commitments(db, user.id, today or date.today())
    if not any(r.category == "Rent" for r in committed_recs):
        committed += _declared_rent(user)
    return max(_floor(user), committed + essential)


def monthly_income(db: Session, user: User, today: date) -> tuple[Decimal, str, int]:
    """(income per month, where it came from, complete months of records)."""
    months = metrics.complete_months(db, user.id, today)
    income = metrics.median_monthly(db, user.id, 6, lambda r: r.kind == "income" and r.amount > 0, today)
    declared = (user.preferences or {}).get("take_home_monthly")
    if declared and (months < 2 or income <= 0):
        return Decimal(str(declared)), "profile", months
    return income, ("history" if months else "none"), months


def affordability(db: Session, user: User, today: date | None = None) -> Snapshot:
    today = today or date.today()
    prefs = user.preferences or {}
    income, income_source, months = monthly_income(db, user, today)
    recurring, committed_recs, committed, recurring_merchants, essential = _commitments(db, user.id, today)
    if not any(r.category == "Rent" for r in committed_recs):
        committed += _declared_rent(user)  # rent the user told us about, until three payments make it "recurring"
    goal_rows = metrics.goals_status(db, user.id, today)
    goals = sum((g["monthly_needed"] for g in goal_rows), Decimal(0))
    surplus = income - committed - essential - goals
    must_pay = committed + essential
    buffer = max(_floor(user), must_pay)
    emergency_target = must_pay * Decimal(str(prefs.get("emergency_months", 3)))
    known = balance_known(db, user.id)
    liquid = liquid_balance(db, user.id)
    salary = [r for r in recurring if r.direction == "credit" and r.category == "Salary"]
    next_income = min((r.next_date for r in salary), default=None)
    if next_income is None and prefs.get("payday"):
        day = int(prefs["payday"])
        candidate = today.replace(day=min(day, 28))
        next_income = candidate if candidate > today else metrics.add_months(today.replace(day=1), 1).replace(day=min(day, 28))
    horizon_end = next_income or today + timedelta(days=30)
    dues = Decimal(0)
    for r in committed_recs:
        dues += r.amount * len(r.occurrences(today + timedelta(days=1), horizon_end))
    fc = latest_forecast(db, user.id)
    f_low, f_date = (None, None)
    if fc is not None and known:
        low, f_date = lowest_point(fc.payload["projection"], 60)
        f_low = Decimal(str(round(low, 2)))
    wants_known = bool(prefs.get("wants_budget")) or income > 0
    wants_budget = Decimal(str(prefs["wants_budget"])) if prefs.get("wants_budget") else (income * Decimal("0.30")).quantize(Decimal("1"))
    month_rows = metrics.rows(db, user.id, today.replace(day=1), today)
    wants_spent = -sum((r.amount for r in month_rows if r.kind == "expense" and r.discretionary and r.merchant not in recurring_merchants),
                       Decimal(0))
    wants_left = max(Decimal(0), wants_budget - wants_spent)
    if known:
        safe_a = liquid - buffer - dues - goals
        safe = max(Decimal(0), min(safe_a, f_low - buffer) if f_low is not None else safe_a)
    else:
        safe = wants_left  # no balance yet: the monthly wants budget is the only honest limit
    snap = Snapshot(income, committed, essential, goals, surplus, buffer, emergency_target, liquid, dues, next_income, f_low, f_date,
                    safe.quantize(Decimal("1")), wants_budget, wants_spent, wants_left, known and liquid >= emergency_target,
                    income_source=income_source, balance_known=known, months_of_data=months, wants_known=wants_known)
    if income_source == "profile":
        income_line = f"Monthly income {fmt_inr(income)} — the take-home pay you entered (we need 2 full months of records to measure it)."
    elif income_source == "history":
        income_line = f"Typical monthly income {fmt_inr(income)} (median of your last {min(months, 6)} complete month(s))."
    else:
        income_line = "Income unknown yet — add your take-home pay in Settings, or connect SMS so salary credits are seen."
    snap.explain = [
        income_line,
        f"Committed {fmt_inr(committed)}/month: rent, EMIs, SIPs, insurance, subscriptions and bills.",
        f"Essential spending {fmt_inr(essential)}/month and goal savings {fmt_inr(goals)}/month.",
        f"Safety buffer {fmt_inr(buffer)} — one month of must-pays — is never counted as spendable.",
        f"Safe to spend now: {fmt_inr(snap.safe_to_spend)}; wants budget left this month: {fmt_inr(wants_left)}." if wants_known
        else f"Safe to spend now: {fmt_inr(snap.safe_to_spend)}. There's no monthly wants budget until your income is known.",
    ]
    if not known:
        snap.explain.append("Your account balance isn't known yet, so safe-to-spend is your wants budget. Add a balance in "
                            "Settings → Accounts, or it appears with the next bank SMS that shows one.")
    return snap


def snapshot_projection(db: Session, user: User, snap: Snapshot) -> list[dict] | None:
    """The forecast for what-if checks, when it is anchored to a real balance."""
    if not snap.balance_known:
        return None
    fc = latest_forecast(db, user.id)
    return fc.payload["projection"] if fc else None


def evaluate_price(price: Decimal, snap: Snapshot, projection: list[dict] | None, replenish: bool = False) -> dict[str, Any]:
    limit = snap.spendable
    impact = None
    stays = True
    if projection:
        w = what_if(projection, float(price))
        stays = w["lowest_after"] >= float(snap.buffer)
        impact = {"lowest_before": w["lowest_before"], "lowest_after": w["lowest_after"], "date": w["lowest_after_date"],
                  "buffer": float(snap.buffer), "stays_above_buffer": stays}
    if price <= limit and stays and (snap.emergency_ok or replenish or not snap.balance_known):
        return {"tier": "buy_now", "months": 0, "monthly": 0.0, "impact": impact}
    capacity = max(snap.surplus, Decimal(0))
    gap = max(price - limit, Decimal(0))
    if capacity > 0:
        months = max(1, math.ceil(gap / capacity))
        if months <= 12:
            return {"tier": "save_up", "months": months, "monthly": float((gap / months).quantize(Decimal("1"))), "impact": impact}
    return {"tier": "not_now", "months": None, "monthly": None, "impact": impact}


def verdict_text(v: dict[str, Any], price: Decimal, snap: Snapshot) -> str:
    if v["tier"] == "buy_now":
        text = f"You can buy this now — {fmt_inr(price)} fits your safe-to-spend and this month's wants budget."
        if not snap.balance_known:
            text += " (Checked against your budget only: your account balance isn't known yet.)"
        return text
    if v["tier"] == "save_up":
        return f"Save {fmt_inr(Decimal(str(v['monthly'])))}/month for {v['months']} month(s) and you can buy it without touching your buffer."
    if snap.income <= 0:
        return "Not yet — FinPilot doesn't know your income yet. Add your take-home pay in Settings or connect your bank SMS."
    return "Not right now — it would cut into money you need for bills, goals or your safety buffer."
