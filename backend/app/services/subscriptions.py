"""Subscription discovery from payment intervals + evidence from email (price notices, trials, usage).

Findings, each with ₹/year at stake:
- price_increase  — the plan got more expensive (matched to the price-change email when there is one)
- dormant         — still paying, but no usage signal for months (e.g. no gym class booked)
- overlap         — two music services, or 3+ video services
- trial_converted — a free trial quietly became a paid plan
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.money import fmt_inr
from app.ml.text import normalize
from app.models import Category, IngestedMessage, Subscription, Transaction
from app.services.recurring import Recurring, detect_recurring

SUBSCRIPTION_CATEGORIES = {"Subscriptions", "Sports & Fitness", "Entertainment", "Education", "Phone & Internet"}
# auto-debits in these categories are loans, investments and rent — commitments, not subscriptions
NOT_SUBSCRIPTIONS = {"Loan EMI", "Investments", "Insurance", "Rent", "Utilities", "Credit Card Payment", "Transfers"}
MUSIC = {"spotify", "youtube premium", "apple music", "jiosaavn", "gaana", "amazon music"}
VIDEO = {"netflix", "jiohotstar", "amazon prime", "sonyliv", "zee5", "disney hotstar"}
ANNUAL_FACTOR = {"weekly": Decimal(52), "monthly": Decimal(12), "bimonthly": Decimal(6), "quarterly": Decimal(4), "annual": Decimal(1)}


def _evidence(db: Session, user_id: int, merchant: str) -> list[IngestedMessage]:
    rows = db.scalars(select(IngestedMessage).where(IngestedMessage.user_id == user_id,
                                                    IngestedMessage.kind.in_(("subscription_notice", "usage")))).all()
    key = normalize(merchant)
    out = []
    for r in rows:
        service = ((r.fields or {}).get("fields", {}).get("service") or {}).get("value") or r.sender
        if fuzz.partial_ratio(normalize(service), key) >= 80 or fuzz.partial_ratio(key, normalize(r.sender)) >= 80:
            out.append(r)
    return out


def _price_change(rec: Recurring) -> tuple[Decimal, Decimal, date] | None:
    amounts, dates = rec.amounts, rec.dates
    for i in range(len(amounts) - 1, 0, -1):
        if amounts[i] != amounts[i - 1]:
            if amounts[i] > amounts[i - 1] and all(a == amounts[i] for a in amounts[i:]):
                return amounts[i - 1], amounts[i], dates[i]
            return None
    return None


def refresh_subscriptions(db: Session, user_id: int, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    keep = {s.merchant_name: s.user_action for s in db.scalars(select(Subscription).where(Subscription.user_id == user_id)).all()
            if s.user_action}
    cats = {c.name: c for c in db.scalars(select(Category).where(Category.user_id.is_(None))).all()}
    from app.services.ingestion.pipeline import AUTOPAY_NOTE

    autopay = set(db.scalars(select(Transaction.merchant_name).where(Transaction.user_id == user_id,
                                                                   Transaction.notes == AUTOPAY_NOTE).distinct()).all())
    recs = [r for r in detect_recurring(db, user_id, today) if r.direction == "debit" and (
        r.category in SUBSCRIPTION_CATEGORIES or (r.merchant in autopay and r.category not in NOT_SUBSCRIPTIONS))]
    db.execute(delete(Subscription).where(Subscription.user_id == user_id))
    active_names = {normalize(r.merchant) for r in recs if r.active}
    annual_by = {normalize(r.merchant): r.amount * ANNUAL_FACTOR[r.cadence] for r in recs if r.active}
    display = {normalize(r.merchant): r.merchant for r in recs}
    keep_music = max((n for n in active_names & MUSIC), key=lambda n: annual_by[n], default=None)
    keep_video = max((n for n in active_names & VIDEO), key=lambda n: annual_by[n], default=None)
    created = []
    for r in recs:
        annual = (r.amount * ANNUAL_FACTOR[r.cadence]).quantize(Decimal("0.01"))
        findings: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        notices = _evidence(db, user_id, r.merchant)
        change = _price_change(r)
        if change:
            old, new, since = change
            delta = ((new - old) * ANNUAL_FACTOR[r.cadence]).quantize(Decimal("0.01"))
            notice = next((n for n in notices if n.kind == "subscription_notice"
                           and ((n.fields or {}).get("fields", {}).get("notice") or {}).get("value") == "price_change"), None)
            findings.append({"type": "price_increase", "saving": float(delta), "title": f"Price went up {((new - old) / old * 100):.0f}%",
                             "detail": f"{r.merchant} rose from {fmt_inr(old)} to {fmt_inr(new)} per {r.cadence.replace('ly', '')} on "
                                       f"{since:%d %b %Y} — {fmt_inr(delta)} more a year." + (" You were notified by email." if notice else ""),
                             "message_id": notice.id if notice else None})
        usage = sorted((n for n in notices if n.kind == "usage"), key=lambda n: n.received_at)
        if usage and r.active:
            last_use = usage[-1].received_at.date()
            idle_days = (today - last_use).days
            if idle_days >= 60:
                paid_since = sum((a for a, d in zip(r.amounts, r.dates) if d > last_use), Decimal(0))
                findings.append({"type": "dormant", "saving": float(annual), "title": "Paying but not using",
                                 "detail": f"No {r.merchant} activity since {last_use:%d %b %Y} ({idle_days // 30} months), "
                                           f"but you've paid {fmt_inr(paid_since)} since then.", "message_id": usage[-1].id})
            evidence.append({"type": "usage", "count": len(usage), "last": usage[-1].received_at.date().isoformat()})
        trial = next((n for n in notices if n.kind == "subscription_notice"
                      and ((n.fields or {}).get("fields", {}).get("notice") or {}).get("value") == "trial"), None)
        if trial and r.first >= trial.received_at.date() - timedelta(days=3):
            findings.append({"type": "trial_converted", "saving": float(annual), "title": "Free trial became paid",
                             "detail": f"Your {r.merchant} free trial converted to a paid plan on {r.first:%d %b %Y} — "
                                       f"{fmt_inr(r.amount)}/month ({fmt_inr(annual)} a year).", "message_id": trial.id})
        key = normalize(r.merchant)
        if key in MUSIC and len(active_names & MUSIC) >= 2 and key != keep_music:
            findings.append({"type": "overlap", "saving": float(annual), "title": "Two music services",
                             "detail": f"{display[keep_music]} already includes music, so {r.merchant} duplicates it — "
                                       f"dropping {r.merchant} saves {fmt_inr(annual)} a year."})
        if key in VIDEO and len(active_names & VIDEO) >= 3 and key != keep_video:
            findings.append({"type": "overlap", "saving": float(annual), "title": f"{len(active_names & VIDEO)} video services",
                             "detail": f"You pay for {len(active_names & VIDEO)} video services. Rotating instead of keeping {r.merchant} "
                                       f"all year saves up to {fmt_inr(annual)}."})
        status = "active" if r.active else "ended"
        if any(f["type"] == "dormant" for f in findings):
            status = "dormant"
        sub = Subscription(user_id=user_id, merchant_name=r.merchant, category_id=cats[r.category].id if r.category in cats else None,
                           cadence=r.cadence, amount=r.amount, first_seen=r.first, last_charged=r.last,
                           next_expected=r.next_date if r.active else None, charge_count=r.count, status=status, annual_cost=annual,
                           flags=sorted({f["type"] for f in findings}), findings=findings, evidence=evidence,
                           user_action=keep.get(r.merchant))
        db.add(sub)
        created.append(sub)
    db.flush()
    return {"subscriptions": len(created), "findings": sum(len(s.findings) for s in created)}
