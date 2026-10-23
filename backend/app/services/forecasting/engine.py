"""Cash-flow forecasting: known schedule + Prophet on the residual, benchmarked against baselines.

The liquid position (savings minus card dues) changes by every non-transfer, posted transaction, so the
target is the daily net flow of those. Recurring items found by services.recurring (salary, rent, EMIs,
SIPs, subscriptions) plus announced bills form the *schedule*; Prophet (weekly + yearly seasonality,
Indian holidays) models what's left. Uncertainty comes from Prophet's predictive samples, accumulated
day by day, so the balance band widens honestly with the horizon.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import D
from app.models import Category, Transaction, UpcomingPayment, User
from app.services.accounts import liquid_balance
from app.services.recurring import Recurring, detect_recurring

log = logging.getLogger("finpilot.forecast")
HORIZON = 90
BACKTEST_HORIZON = 30
BACKTEST_FOLDS = 6
MIN_PROPHET_DAYS = 120
BACKTEST_MIN_DAYS = 400  # six 30-day folds need a long history before them to train on


@dataclass
class Series:
    daily: pd.Series  # net flow per day (₹, float), indexed by date
    scheduled: pd.Series  # scheduled portion of the history (same index)
    recurring: list[Recurring]


def _declared(user: User | None, recurring: list[Recurring], today: date) -> list[Recurring]:
    """Salary and rent the user told us about (onboarding), as schedule items, until three real occurrences make
    them recurring by themselves. Only items that aren't already detected are added."""
    if user is None:
        return []
    prefs = user.preferences or {}
    have = {r.category for r in recurring if r.active}
    out = []

    def monthly(name: str, direction: str, category: str, kind: str, amount: float, day: int) -> Recurring:
        first = today.replace(day=min(day, 28))
        nxt = first if first > today else (first.replace(day=1) + timedelta(days=32)).replace(day=min(day, 28))
        return Recurring(merchant=name, direction=direction, category=category, category_kind=kind, cadence="monthly",
                         period_days=30.4, amount=D(amount), first=today, last=today, count=0, day_of_month=min(day, 28),
                         next_date=nxt, active=True)

    if prefs.get("take_home_monthly") and prefs.get("payday") and "Salary" not in have:
        out.append(monthly("Salary (you told us)", "credit", "Salary", "income", float(prefs["take_home_monthly"]), int(prefs["payday"])))
    if prefs.get("rent_monthly") and "Rent" not in have:
        out.append(monthly(f"Rent{' — ' + prefs['rent_payee'] if prefs.get('rent_payee') else ''}", "debit", "Rent", "expense",
                           float(prefs["rent_monthly"]), int(prefs.get("rent_day") or 5)))
    return out


def _flows(db: Session, user_id: int, today: date) -> list[tuple[date, float, int, str]]:
    rows = db.execute(select(Transaction.txn_date, Transaction.amount, Transaction.direction, Transaction.id, Category.name)
                      .join(Category, Category.id == Transaction.category_id, isouter=True).where(
        Transaction.user_id == user_id, Transaction.status == "posted", Transaction.is_transfer.is_(False),
        Transaction.txn_date <= today)).all()
    return [(d, float(a) if direction == "credit" else -float(a), tid, cat or "") for d, a, direction, tid, cat in rows]


def _scheduled_history(flows: list[tuple[date, float, int, str]], idx: pd.DatetimeIndex, recurring: list[Recurring],
                       declared: list[Recurring], until: date | None = None) -> pd.Series:
    ids = {tid for r in recurring for tid in r.txn_ids}
    declared_cats = {r.category for r in declared}
    scheduled = pd.Series(0.0, index=idx)
    for d, value, tid, cat in flows:
        if until is not None and d > until:
            continue
        # declared salary/rent: past salary credits and rent payments are part of the schedule, not the noise
        if tid in ids or (cat in declared_cats and ((cat == "Salary" and value > 0) or (cat == "Rent" and value < 0))):
            scheduled[pd.Timestamp(d)] += value
    return scheduled


def build_series(db: Session, user_id: int, today: date, user: User | None = None) -> Series:
    flows = _flows(db, user_id, today)
    if not flows:
        idx = pd.date_range(today - timedelta(days=29), today, freq="D")
        declared = _declared(user, [], today)
        return Series(pd.Series(0.0, index=idx), pd.Series(0.0, index=idx), declared)
    start = min(f[0] for f in flows)
    idx = pd.date_range(start, today, freq="D")
    daily = pd.Series(0.0, index=idx)
    for d, value, _, _ in flows:
        daily[pd.Timestamp(d)] += value
    recurring = [r for r in detect_recurring(db, user_id, today) if r.cadence != "weekly"]
    declared = _declared(user, recurring, today)
    return Series(daily, _scheduled_history(flows, idx, recurring, declared), recurring + declared)


def future_schedule(db: Session, user_id: int, recurring: list[Recurring], start: date, end: date) -> tuple[pd.Series, list[dict]]:
    idx = pd.date_range(start, end, freq="D")
    s = pd.Series(0.0, index=idx)
    events: list[dict] = []
    for r in recurring:
        if not r.active:
            continue
        for d in r.occurrences(start, end):
            value = float(r.amount) if r.direction == "credit" else -float(r.amount)
            s[pd.Timestamp(d)] += value
            events.append({"date": d.isoformat(), "name": r.merchant, "amount": round(value, 2), "category": r.category,
                           "source": f"recurring ({r.cadence})"})
    # announced bills (from SMS/email) that aren't already a recurring series
    names = {r.merchant.lower() for r in recurring}
    for up in db.scalars(select(UpcomingPayment).where(UpcomingPayment.user_id == user_id, UpcomingPayment.status == "upcoming",
                                                       UpcomingPayment.due_date >= start, UpcomingPayment.due_date <= end)).all():
        if up.kind == "card_due" or up.payee.lower() in names:
            continue  # card dues are already counted when the card was used (liquid position)
        s[pd.Timestamp(up.due_date)] -= float(up.amount)
        events.append({"date": up.due_date.isoformat(), "name": up.payee, "amount": -float(up.amount), "category": "Bill",
                       "source": "announced bill"})
    events.sort(key=lambda e: e["date"])
    return s, events


# -- models ------------------------------------------------------------------------------------------
def baseline_forecast(history: pd.Series, horizon: int) -> np.ndarray:
    """Seasonal-naive (same weekday, trailing 4 weeks) blended 50/50 with the trailing 90-day daily mean."""
    hist = history.iloc[-120:]
    mean90 = float(hist.iloc[-90:].mean()) if len(hist) else 0.0
    out = []
    last = history.index[-1]
    for h in range(1, horizon + 1):
        day = last + pd.Timedelta(days=h)
        same = hist[(hist.index.dayofweek == day.dayofweek)].iloc[-4:]
        sn = float(same.mean()) if len(same) else mean90
        out.append(0.5 * sn + 0.5 * mean90)
    return np.array(out)


def prophet_fit_predict(history: pd.Series, horizon: int, samples: int = 0):  # noqa: ANN201
    from app.services.forecasting.prophet_model import load_prophet

    Prophet = load_prophet()
    df = pd.DataFrame({"ds": history.index, "y": history.values})
    yearly = len(df) >= 400
    model = Prophet(weekly_seasonality=True, yearly_seasonality=yearly, daily_seasonality=False,
                    uncertainty_samples=samples, changepoint_prior_scale=0.05)
    model.add_country_holidays(country_name="IN")
    model.fit(df)
    future = model.make_future_dataframe(periods=horizon, include_history=False)
    fc = model.predict(future)
    sample_paths = model.predictive_samples(future)["yhat"] if samples else None  # (horizon, samples)
    return fc["yhat"].to_numpy(), sample_paths


def _metrics(actual: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    err = actual - pred
    return {"mae": float(np.mean(np.abs(err))), "rmse": float(math.sqrt(np.mean(err ** 2))),
            "wape": float(np.sum(np.abs(err)) / max(1.0, np.sum(np.abs(actual)))),
            "end_error": float(abs(np.sum(err)))}


def backtest(series: Series, db: Session, user_id: int, prophet_ok: bool) -> dict[str, dict[str, float]]:
    """Rolling origin: train on everything before each origin, forecast 30 days, compare with what happened."""
    y = series.daily
    if len(y) < BACKTEST_MIN_DAYS:
        return {}
    results: dict[str, list[dict[str, float]]] = {"baseline": [], "baseline_schedule": [], "prophet_schedule": []}
    flows = _flows(db, user_id, y.index[-1].date())
    for k in range(BACKTEST_FOLDS, 0, -1):
        origin = len(y) - k * BACKTEST_HORIZON
        train, test = y.iloc[:origin], y.iloc[origin:origin + BACKTEST_HORIZON]
        # the schedule as it was knowable at the origin: recurring items detected from the training window only,
        # projected forward — never the payments that actually happened in the test window
        origin_day = train.index[-1].date()
        known = [r for r in detect_recurring(db, user_id, origin_day, until=origin_day) if r.cadence != "weekly"]
        sched_hist = _scheduled_history(flows, train.index, known, [], until=origin_day)
        future = pd.Series(0.0, index=test.index)
        for r in known:
            if r.active:
                for d in r.occurrences(test.index[0].date(), test.index[-1].date()):
                    future[pd.Timestamp(d)] += float(r.amount) if r.direction == "credit" else -float(r.amount)
        future_sched = future.to_numpy()
        actual = test.to_numpy()
        results["baseline"].append(_metrics(actual, baseline_forecast(train, len(test))))
        resid = train - sched_hist
        results["baseline_schedule"].append(_metrics(actual, future_sched + baseline_forecast(resid, len(test))))
        if prophet_ok:
            try:
                yhat, _ = prophet_fit_predict(resid, len(test))
                results["prophet_schedule"].append(_metrics(actual, future_sched + yhat))
            except Exception:  # pragma: no cover - environment specific
                log.exception("prophet failed during backtest")
                prophet_ok = False
    out = {}
    for name, folds in results.items():
        if folds:
            out[name] = {m: round(float(np.mean([f[m] for f in folds])), 2) for m in folds[0]} | {"folds": len(folds)}
    return out


def forecast(db: Session, user_id: int, today: date | None = None, run_backtest: bool = True) -> dict[str, Any]:
    from app.services.system import CAPABILITIES

    today = today or date.today()
    series = build_series(db, user_id, today, db.get(User, user_id))
    balance_now = float(liquid_balance(db, user_id))
    end = today + timedelta(days=HORIZON)
    sched_future, events = future_schedule(db, user_id, series.recurring, today + timedelta(days=1), end)
    resid = series.daily - series.scheduled
    prophet_available = CAPABILITIES.get("prophet", {}).get("ok", True)
    model_name, note = "prophet", None
    samples = None
    if len(resid) < MIN_PROPHET_DAYS:
        model_name = "baseline"
        note = (f"Using a simple model (recent averages plus your known schedule) until there are {MIN_PROPHET_DAYS} days of "
                f"history — you have {len(resid)}. Prophet takes over after that.")
        yhat = baseline_forecast(resid, HORIZON)
    else:
        try:
            if not prophet_available:
                raise RuntimeError("Prophet unavailable")
            yhat, samples = prophet_fit_predict(resid, HORIZON, samples=300)
        except Exception as exc:  # fallback keeps the page working on any machine
            log.warning("forecast falling back to baseline: %s", exc)
            model_name, note = "baseline", "Prophet couldn't run on your FinPilot server, so the seasonal baseline is shown."
            yhat = baseline_forecast(resid, HORIZON)
    prophet_ok = prophet_available and model_name == "prophet"
    if samples is None:
        # bootstrap residual noise around the point forecast for an honest band
        rng = np.random.default_rng(7)
        noise = resid.iloc[-180:].to_numpy() - float(resid.iloc[-180:].mean())
        samples = yhat[:, None] + rng.choice(noise, size=(HORIZON, 300), replace=True)
    paths = balance_now + np.cumsum(sched_future.to_numpy()[:, None] + samples, axis=0)
    p10, p50, p90 = (np.percentile(paths, q, axis=1) for q in (10, 50, 90))
    dates = [(today + timedelta(days=i + 1)).isoformat() for i in range(HORIZON)]
    # reconstruct the last 120 days of the liquid balance backwards from today
    hist_flows = series.daily.iloc[-120:]
    hist_bal, running = [], balance_now
    for d, v in zip(reversed(hist_flows.index), reversed(hist_flows.to_numpy())):
        hist_bal.append({"date": d.date().isoformat(), "balance": round(running, 2)})
        running -= v
    hist_bal.reverse()
    metrics = backtest(series, db, user_id, prophet_ok and model_name == "prophet") if run_backtest else {}
    net30 = float(np.sum(sched_future.to_numpy()[:30] + yhat[:30]))
    return {
        "model": model_name, "note": note, "generated_for": today.isoformat(), "balance_now": round(balance_now, 2),
        "history_days": len(series.daily), "backtest_min_days": BACKTEST_MIN_DAYS,
        "history": hist_bal,
        "projection": [{"date": d, "p10": round(float(a), 2), "p50": round(float(b), 2), "p90": round(float(c), 2)}
                       for d, a, b, c in zip(dates, p10, p50, p90)],
        "daily_net": [{"date": d, "value": round(float(s + y), 2)} for d, s, y in zip(dates, sched_future.to_numpy(), yhat)],
        "events": events,
        "net_next_30": round(net30, 2),
        "recurring": [{"merchant": r.merchant, "direction": r.direction, "cadence": r.cadence, "amount": float(r.amount),
                       "next_date": r.next_date.isoformat(), "category": r.category, "active": r.active} for r in series.recurring],
        "metrics": metrics,
    }


def lowest_point(projection: list[dict], days: int = 60, key: str = "p10") -> tuple[float, str]:
    window = projection[:days]
    point = min(window, key=lambda p: p[key])
    return point[key], point["date"]


def what_if(projection: list[dict], amount: float, on: date | None = None, days: int = 60) -> dict[str, Any]:
    """Subtracting a purchase shifts every sample path, hence every quantile, by the same amount."""
    on_iso = (on or date.fromisoformat(projection[0]["date"])).isoformat()
    shifted = [{**p, "p10": p["p10"] - amount, "p50": p["p50"] - amount, "p90": p["p90"] - amount} if p["date"] >= on_iso else p
               for p in projection]
    before = lowest_point(projection, days)
    after = lowest_point(shifted, days)
    return {"lowest_before": round(before[0], 2), "lowest_before_date": before[1], "lowest_after": round(after[0], 2),
            "lowest_after_date": after[1], "projection": shifted}


def to_decimal(x: float) -> Decimal:
    return Decimal(str(round(x, 2)))
