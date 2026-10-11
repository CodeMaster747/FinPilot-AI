"""Insight engine: ranked, severity-scored observations built from the same metric functions as the
dashboard. Wording varies (stable per insight and period) so the feed reads naturally."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.money import fmt_inr
from app.models import Anomaly, IngestedMessage, Insight, Product, ProductRecommendation, Subscription, Transaction, UpcomingPayment, User
from app.services import metrics
from app.services.forecasting.engine import lowest_point
from app.services.forecasting.service import latest as latest_forecast


def _pick(key: str, options: list[str]) -> str:
    return options[int(hashlib.md5(key.encode()).hexdigest(), 16) % len(options)]


class Builder:
    def __init__(self, today: date):
        self.today = today
        self.items: list[dict[str, Any]] = []

    def add(self, kind: str, key: str, severity: int, title: str, body: str, link: str | None = None, **data: Any) -> None:
        self.items.append({"kind": kind, "key": f"{kind}:{key}", "severity": max(0, min(100, severity)), "title": title,
                           "body": body, "link": link, "data": data})


def generate(db: Session, user: User, today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    b = Builder(today)
    month = metrics.month_start(today)
    period = f"{today:%Y-%m}"

    # 1) spending spikes: month-to-date vs the same days of the previous three months
    cur = metrics.by_category(metrics.rows(db, user.id, month, today))
    past: dict[str, list[Decimal]] = {}
    for k in (1, 2, 3):
        m = metrics.add_months(month, -k)
        end = min(m + timedelta(days=today.day - 1), metrics.add_months(m, 1) - timedelta(days=1))
        for cat, v in metrics.by_category(metrics.rows(db, user.id, m, end)).items():
            past.setdefault(cat, []).append(v)
    for cat, v in (cur.items() if today.day >= 7 else []):
        hist = past.get(cat, [])
        usual = sum(hist, Decimal(0)) / 3 if hist else Decimal(0)
        if usual >= 1000 and v >= usual * Decimal("1.5") and v - usual >= 2000:
            pct = float((v - usual) / usual * 100)
            b.add("spend_spike", f"{cat}:{period}", 50 + min(20, int(pct / 10)),
                  _pick(cat + period, [f"{cat} is running hot", f"More on {cat.lower()} this month", f"{cat} spending jumped"]),
                  _pick(cat, [f"You've spent {fmt_inr(v)} on {cat.lower()} so far this month — {pct:.0f}% more than usual by this date ({fmt_inr(usual)}).",
                              f"{cat}: {fmt_inr(v)} this month against a typical {fmt_inr(usual)} by day {today.day} ({pct:+.0f}%)."]),
                  "/transactions", category=cat, amount=float(v), usual=float(usual))

    # 2) budgets burning faster than the month
    for st in metrics.budgets_status(db, user.id, today):
        if st["over"]:
            b.add("budget", f"{st['category']}:{period}", 80, f"{st['category']} budget exceeded",
                  f"You've spent {fmt_inr(st['spent'])} of your {fmt_inr(st['budget'])} {st['category'].lower()} budget ({st['pct']:.0f}%).",
                  "/budgets", pct=st["pct"])
        elif st["over_pace"] and st["pct"] >= 50:
            b.add("budget", f"{st['category']}:{period}", 60, f"{st['category']} budget is ahead of pace",
                  _pick(st["category"], [f"{st['pct']:.0f}% of your {st['category'].lower()} budget is gone by day {today.day} of the month.",
                                         f"At this rate you'll pass your {st['category'].lower()} budget before month end — {st['pct']:.0f}% used already."]),
                  "/budgets", pct=st["pct"])

    # 3) savings rate trend (last complete month vs the six before)
    series = metrics.monthly_series(db, user.id, 8, today)[:-1]
    if len(series) >= 4 and series[-1]["income"]:
        last, prev = series[-1], [s["savings_rate"] for s in series[:-1] if s["income"]]
        avg = sum(prev) / len(prev) if prev else 0
        delta = last["savings_rate"] - avg
        month_name = f"{date.fromisoformat(last['month']):%B}"
        if last["savings_rate"] < 0:
            lm_start = date.fromisoformat(last["month"])
            cats = metrics.by_category(metrics.rows(db, user.id, lm_start, metrics.add_months(lm_start, 1) - timedelta(days=1)))
            top = next(iter(cats.items()), None)
            cause = f" The biggest item was {top[0].lower()} at {fmt_inr(top[1])}." if top else ""
            b.add("savings_rate", period, 70, f"Spent more than you earned in {month_name}",
                  f"Spending was {abs(last['savings_rate']):.0f}% higher than income in {month_name}, against an average savings rate of "
                  f"{avg:.0f}%.{cause}", "/dashboard", rate=last["savings_rate"])
        elif abs(delta) >= 5:
            up = delta > 0
            b.add("savings_rate", period, 45 if up else 65, "Savings rate " + ("up" if up else "down"),
                  f"In {month_name} you kept {last['savings_rate']:.0f}% of your income, "
                  f"{'up' if up else 'down'} from a {avg:.0f}% average.", "/dashboard", rate=last["savings_rate"])

    # 4) forecast warning
    fc = latest_forecast(db, user.id)
    from app.services.picks import safety_buffer

    buffer = safety_buffer(db, user, today)
    if fc is not None:
        low, low_date = lowest_point(fc.payload["projection"], 45)
        if low < float(buffer):
            b.add("forecast", period, 90, "Balance could run low",
                  f"Your projected balance could fall to {fmt_inr(Decimal(str(low)))} around {date.fromisoformat(low_date):%d %b} "
                  f"— below your {fmt_inr(buffer)} safety buffer.", "/forecast", low=low)
        net = fc.payload.get("net_next_30", 0)
        b.add("forecast_summary", period, 30, "Next 30 days",
              f"Expected net cash flow over the next 30 days: {fmt_inr(Decimal(str(net)))}, with "
              f"{len([e for e in fc.payload.get('events', []) if e['date'] <= (today + timedelta(days=30)).isoformat()])} scheduled payments.",
              "/forecast", net=net)

    # 5) bills due in the next 7 days
    soon = db.scalars(select(UpcomingPayment).where(UpcomingPayment.user_id == user.id, UpcomingPayment.status == "upcoming",
                                                    UpcomingPayment.due_date >= today, UpcomingPayment.due_date <= today + timedelta(days=7))
                      .order_by(UpcomingPayment.due_date)).all()
    if soon:
        total = sum((u.amount for u in soon), Decimal(0))
        listing = ", ".join(f"{u.payee} {fmt_inr(u.amount)} ({u.due_date:%d %b})" for u in soon[:4])
        b.add("bills", f"{today.isoformat()}", 70, f"{fmt_inr(total)} due this week", f"Coming up: {listing}.", "/forecast", total=float(total))

    # 6) anomalies
    n_anom = db.scalar(select(func.count(func.distinct(Anomaly.transaction_id))).where(Anomaly.user_id == user.id, Anomaly.status == "open")) or 0
    if n_anom:
        first = db.scalar(select(Anomaly).where(Anomaly.user_id == user.id, Anomaly.status == "open").order_by(Anomaly.severity.desc(), Anomaly.id))
        b.add("anomaly", str(n_anom), 85, f"{n_anom} unusual transaction{'s' if n_anom > 1 else ''} to check",
              first.explanation if first else "", "/transactions?anomalies=1", count=n_anom)

    # 7) subscription waste
    for s in db.scalars(select(Subscription).where(Subscription.user_id == user.id, Subscription.user_action.is_(None))).all():
        for f in s.findings:
            if f["type"] in ("dormant", "trial_converted", "price_increase"):
                sev = {"dormant": 75, "trial_converted": 65, "price_increase": 50}[f["type"]]
                b.add("subscription", f"{s.merchant_name}:{f['type']}", sev, f"{s.merchant_name}: {f['title'].lower()}", f["detail"],
                      "/subscriptions", saving=f["saving"])

    # 8) 50/30/20 for the last complete month
    lm = metrics.add_months(month, -1)
    rs = metrics.rows(db, user.id, lm, month - timedelta(days=1))
    inc = metrics.income(rs)
    if inc:
        needs = -sum((r.amount for r in rs if r.kind == "expense" and not r.discretionary), Decimal(0))
        wants = -sum((r.amount for r in rs if r.kind == "expense" and r.discretionary), Decimal(0))
        n, w = float(needs / inc * 100), float(wants / inc * 100)
        s = 100 - n - w
        if s < 0:
            b.add("rule_50_30_20", f"{lm:%Y-%m}", 35, f"{lm:%B}: needs {n:.0f}% + wants {w:.0f}% of income",
                  f"Needs took {n:.0f}% of income and wants {w:.0f}% — nothing was left to save. The 50/30/20 guideline keeps wants "
                  f"near 30% so that a fifth of income is saved.", "/dashboard", needs=n, wants=w, save=s)
        else:
            verdict = "right on the 50/30/20 guideline" if n <= 55 and w <= 33 else "above the 50/30/20 guideline on " + ("needs" if n > 55 else "wants")
            b.add("rule_50_30_20", f"{lm:%Y-%m}", 35, f"{lm:%B}: {n:.0f}/{w:.0f}/{s:.0f} split",
                  f"Needs took {n:.0f}% of income, wants {w:.0f}% and {s:.0f}% was left to save — {verdict}.", "/dashboard",
                  needs=n, wants=w, save=s)

    # 9) goals pace
    for g in metrics.goals_status(db, user.id, today):
        if g["remaining"] > 0 and g["months_left"] <= 6:
            b.add("goal", f"{g['id']}:{period}", 50, f"“{g['name']}”: {g['pct']:.0f}% there",
                  f"Put aside {fmt_inr(g['monthly_needed'])}/month to reach {fmt_inr(g['target'])} by {g['target_date']:%b %Y}.", "/budgets")

    # 10) Smart Picks: price drops on picks that now fit
    for rec, prod in db.execute(select(ProductRecommendation, Product).join(Product).where(
            ProductRecommendation.user_id == user.id, ProductRecommendation.tier == "buy_now",
            ProductRecommendation.status.in_(("new", "saved")))).all():
        drop = next((r for r in rec.reasons if r.startswith("Lowest price in 30 days") or "below its usual price" in r), None)
        if drop:
            b.add("price_drop", f"{prod.id}:{today.isoformat()}", 55, f"Price drop: {prod.title}",
                  f"Now {fmt_inr(prod.price)} ({drop.lower()}) — and it fits your budget ({rec.interest}).", "/picks", product_id=prod.id)
    n_picks = db.scalar(select(func.count()).select_from(ProductRecommendation).where(
        ProductRecommendation.user_id == user.id, ProductRecommendation.status == "new")) or 0
    if n_picks:
        b.add("picks", period, 30, f"{n_picks} Smart Picks within your budget",
              "Products matching your wishlist, goals and regular purchases — each checked against your forecast.", "/picks")

    # 11) review queue
    to_review = (db.scalar(select(func.count()).select_from(IngestedMessage).where(IngestedMessage.user_id == user.id, IngestedMessage.status == "needs_review")) or 0) \
        + (db.scalar(select(func.count()).select_from(Transaction).where(Transaction.user_id == user.id, Transaction.needs_review.is_(True))) or 0)
    if to_review:
        b.add("review", str(to_review), 40, f"{to_review} item{'s' if to_review > 1 else ''} to review",
              "A few messages or transactions need a quick confirmation.", "/review")

    # 12) tax season
    if today.month in (1, 2, 3):
        b.add("tax", period, 55, "Tax-saving deadline: 31 March",
              "Check how much of your deductions you've used before the financial year ends.", "/tax")
    return sorted(b.items, key=lambda x: -x["severity"])


def refresh_insights(db: Session, user: User, today: date | None = None) -> dict[str, Any]:
    items = generate(db, user, today)
    dismissed = set(db.scalars(select(Insight.key).where(Insight.user_id == user.id, Insight.dismissed.is_(True))).all())
    db.execute(delete(Insight).where(Insight.user_id == user.id, Insight.dismissed.is_(False)))
    for it in items:
        if it["key"] in dismissed:
            continue
        db.add(Insight(user_id=user.id, kind=it["kind"], key=it["key"], severity=it["severity"], title=it["title"][:200], body=it["body"],
                       data=it["data"], link=it["link"]))
    db.flush()
    return {"insights": len(items)}
