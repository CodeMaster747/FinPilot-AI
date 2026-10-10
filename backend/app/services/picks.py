"""Smart Picks: products the user can afford, judged against their real finances.

Affordability (computed from sources where the user granted the 'picks' purpose, plus uploads/manual):
  income     = median monthly income credits (last 6 complete months)
  committed  = recurring outflows (rent, EMIs, SIPs, insurance, subscriptions, bills) per month
  essential  = median monthly essential spending outside those recurring items (3 months)
  goals      = what active goals need per month
  surplus    = income - committed - essential - goals
  buffer     = max(user floor, one month of committed + essential)
  safe_to_spend = max(0, min(liquid - buffer - dues before next income - goals, lowest 60-day forecast (p10) - buffer))
  wants_left = monthly wants budget (30% of income unless set) - discretionary spending so far this month

Tiers: buy_now (fits safe_to_spend and wants_left, forecast never dips below the buffer, emergency fund in
place unless it's an everyday replenishment); goal (matches an active goal: follow the goal's plan);
save_up (affordable within 12 months of surplus); everything else is never shown.
"""

from __future__ import annotations

import math
import statistics
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.money import fmt_inr
from app.db.base import utcnow
from app.ml.text import normalize
from app.models import (
    AffordabilitySnapshot,
    Category,
    Goal,
    Merchant,
    Product,
    ProductPriceHistory,
    ProductRecommendation,
    Transaction,
    TransactionItem,
    User,
    WishlistItem,
)
from app.services import metrics
from app.services.accounts import liquid_balance
from app.services.forecasting.engine import lowest_point, what_if
from app.services.forecasting.service import latest as latest_forecast
from app.services.recurring import detect_recurring

DISCLAIMER = ("Smart Picks are estimates to help you plan, not financial advice. FinPilot has no affiliate links and no paid "
              "placements — products are ranked only by how well they fit you and your budget.")
COMMITTED_CATEGORIES = {"Rent", "Loan EMI", "Investments", "Insurance", "Subscriptions", "Phone & Internet", "Utilities",
                        "Sports & Fitness", "Education"}
REPLENISH_CATEGORIES = {"Groceries", "Personal Care"}


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
    origins: list[str]
    explain: list[str] = field(default_factory=list)
    complete: bool = True  # every source with transactions may be used (else balance & forecast checks are skipped)

    def as_json(self) -> dict[str, Any]:
        out = {}
        for k, v in self.__dict__.items():
            out[k] = float(v) if isinstance(v, Decimal) else v.isoformat() if isinstance(v, date) else v
        return out


def _commitments(db: Session, user_id: int, today: date, origins: set[str] | None = None):  # noqa: ANN202
    recurring = [r for r in detect_recurring(db, user_id, today, origins=origins) if r.active]
    committed_recs = [r for r in recurring if r.direction == "debit" and r.category in COMMITTED_CATEGORIES]
    committed = sum((r.monthly_equivalent for r in committed_recs), Decimal(0))
    recurring_merchants = {r.merchant for r in committed_recs}
    essential = metrics.median_monthly(db, user_id, 3, lambda r: r.kind == "expense" and r.essential and r.amount < 0
                                       and r.merchant not in recurring_merchants, today, origins)
    return recurring, committed_recs, committed, recurring_merchants, essential


def safety_buffer(db: Session, user: User, today: date | None = None) -> Decimal:
    """The one safety-buffer rule used everywhere: max(the user's floor, one month of must-pays)."""
    _, _, committed, _, essential = _commitments(db, user.id, today or date.today())
    return max(Decimal(str((user.preferences or {}).get("buffer_floor", 15000))), committed + essential)


def affordability(db: Session, user: User, today: date | None = None, for_picks: bool = True) -> Snapshot:
    """What the user can afford. ``for_picks`` applies purpose limitation: only sources allowed for Smart Picks
    (plus uploads and manual entries) are used, and the balance and forecast, which are built from every source,
    are only used when every source with transactions is allowed. The coach and dashboard answer the user's own
    questions about their money, so they use everything (for_picks=False)."""
    today = today or date.today()
    prefs = user.preferences or {}
    origins = metrics.picks_origins(db, user.id) if for_picks else None
    used = set(db.scalars(select(Transaction.origin).where(Transaction.user_id == user.id).distinct()).all())
    complete = origins is None or used <= origins
    income = metrics.median_monthly(db, user.id, 6, lambda r: r.kind == "income" and r.amount > 0, today, origins)
    recurring, committed_recs, committed, recurring_merchants, essential = _commitments(db, user.id, today, origins)
    goal_rows = metrics.goals_status(db, user.id, today)
    goals = sum((g["monthly_needed"] for g in goal_rows), Decimal(0))
    surplus = income - committed - essential - goals
    must_pay = committed + essential
    buffer = max(Decimal(str(prefs.get("buffer_floor", 15000))), must_pay)
    emergency_target = must_pay * Decimal(str(prefs.get("emergency_months", 3)))
    liquid = liquid_balance(db, user.id) if complete else Decimal(0)
    salary = [r for r in recurring if r.direction == "credit" and r.category == "Salary"]
    next_income = min((r.next_date for r in salary), default=None)
    horizon_end = next_income or today + timedelta(days=30)
    dues = Decimal(0)
    for r in committed_recs:
        dues += r.amount * len(r.occurrences(today + timedelta(days=1), horizon_end))
    fc = latest_forecast(db, user.id) if complete else None
    f_low, f_date = (None, None)
    if fc is not None:
        low, f_date = lowest_point(fc.payload["projection"], 60)
        f_low = Decimal(str(round(low, 2)))
    safe_a = liquid - buffer - dues - goals
    safe = max(Decimal(0), min(safe_a, f_low - buffer) if f_low is not None else safe_a) if complete else Decimal(0)
    wants_budget = Decimal(str(prefs["wants_budget"])) if prefs.get("wants_budget") else (income * Decimal("0.30")).quantize(Decimal("1"))
    month_rows = metrics.rows(db, user.id, today.replace(day=1), today, origins)
    wants_spent = -sum((r.amount for r in month_rows if r.kind == "expense" and r.discretionary and r.merchant not in recurring_merchants),
                       Decimal(0))
    wants_left = max(Decimal(0), wants_budget - wants_spent)
    snap = Snapshot(income, committed, essential, goals, surplus, buffer, emergency_target, liquid, dues, next_income, f_low, f_date,
                    safe.quantize(Decimal("1")), wants_budget, wants_spent, wants_left, complete and liquid >= emergency_target,
                    sorted(origins if origins is not None else used | {"manual", "receipt", "csv"}), complete=complete)
    snap.explain = [
        f"Typical monthly income {fmt_inr(income)} (median of the last 6 months).",
        f"Committed {fmt_inr(committed)}/month: rent, EMIs, SIPs, insurance, subscriptions and bills.",
        f"Essential spending {fmt_inr(essential)}/month and goal savings {fmt_inr(goals)}/month.",
        f"Safety buffer {fmt_inr(buffer)} — one month of must-pays — is never counted as spendable.",
        f"Safe to spend now: {fmt_inr(snap.safe_to_spend)}; wants budget left this month: {fmt_inr(wants_left)}.",
    ]
    if not complete:
        snap.explain.append("Your balance and forecast come from sources you haven't allowed for Smart Picks, so they aren't used "
                            "here — and nothing is marked “buy now” until they are.")
    return snap


def snapshot_projection(db: Session, user: User, snap: Snapshot) -> list[dict] | None:
    """The forecast for what-if checks, but only when this snapshot may use it."""
    if not snap.complete:
        return None
    fc = latest_forecast(db, user.id)
    return fc.payload["projection"] if fc else None


def save_snapshot(db: Session, user: User, snap: Snapshot) -> None:
    db.add(AffordabilitySnapshot(user_id=user.id, computed_at=utcnow(), inputs={"origins": snap.origins},
                                 outputs=snap.as_json()))


@dataclass
class Interest:
    text: str
    weight: float
    source: str  # wishlist | goal | replenish | merchant | category
    label: str
    max_price: Decimal | None = None
    goal_id: int | None = None
    typical_price: Decimal | None = None


def interests(db: Session, user: User, origins: set[str], today: date) -> list[Interest]:
    prefs = user.preferences or {}
    excluded = set(prefs.get("excluded_interest_categories", [])) | {"Healthcare"}
    out: list[Interest] = []
    for w in db.scalars(select(WishlistItem).where(WishlistItem.user_id == user.id, WishlistItem.active.is_(True))).all():
        out.append(Interest(w.text, 3.0, "wishlist", f"your wishlist: “{w.text}”", w.max_price))
    for g in db.scalars(select(Goal).where(Goal.user_id == user.id, Goal.status == "active")).all():
        if g.keywords.strip():
            out.append(Interest(f"{g.name} {g.keywords}", 2.5, "goal", f"your goal “{g.name}”", g.target, g.id))
    since = today - timedelta(days=180)
    rows = db.execute(select(TransactionItem, Transaction, Category).join(Transaction, Transaction.id == TransactionItem.transaction_id)
                      .join(Category, Category.id == Transaction.category_id).where(
        Transaction.user_id == user.id, Transaction.txn_date >= since, Transaction.direction == "debit")).all()
    counts: Counter[str] = Counter()
    prices: dict[str, list[Decimal]] = defaultdict(list)
    for item, txn, cat in rows:
        if txn.origin not in origins or cat.is_sensitive or cat.name in excluded or item.description.lower().startswith("delivery"):
            continue
        counts[item.description] += 1
        prices[item.description].append(item.amount / Decimal(str(item.quantity or 1)))
    # premium consumables bought again and again (whey protein, coffee beans...) — not everyday staples
    regular = [(d, n, statistics.median(prices[d])) for d, n in counts.items() if n >= 3 and statistics.median(prices[d]) >= 400]
    for desc, n, typical in sorted(regular, key=lambda x: -x[1] * float(x[2]))[:5]:
        out.append(Interest(desc, 2.2, "replenish", f"you buy “{desc}” regularly ({n}× in 6 months)", typical_price=typical))
    tag_weight: Counter[str] = Counter()
    for m_tags, txn_origin in db.execute(select(Merchant.interest_tags, Transaction.origin).join(Transaction, Transaction.merchant_id == Merchant.id)
                                         .where(Transaction.user_id == user.id, Transaction.txn_date >= since)).all():
        if txn_origin in origins:
            for t in m_tags or []:
                tag_weight[t] += 1
    for tag, n in tag_weight.most_common(6):
        if n >= 3 and tag not in ("groceries",):
            out.append(Interest(tag, 1.2, "merchant", f"your spending on {tag}"))
    return out


def _doc(p: Product) -> str:
    return normalize(f"{p.title} {p.brand} {p.category} {' '.join(p.tags or [])} {p.title}")


def _price_stats(db: Session, product_ids: list[int], today: date) -> dict[int, tuple[Decimal, Decimal]]:
    """30-day median and 30-day minimum price per product."""
    rows = db.execute(select(ProductPriceHistory.product_id, ProductPriceHistory.price).where(
        ProductPriceHistory.product_id.in_(product_ids), ProductPriceHistory.observed_on >= today - timedelta(days=30))).all()
    by: dict[int, list[Decimal]] = defaultdict(list)
    for pid, price in rows:
        by[pid].append(price)
    return {pid: (statistics.median(v), min(v)) for pid, v in by.items()}


def evaluate_price(price: Decimal, snap: Snapshot, projection: list[dict] | None, replenish: bool = False) -> dict[str, Any]:
    limit = min(snap.safe_to_spend, snap.wants_left)
    impact = None
    stays = True
    if projection:
        w = what_if(projection, float(price))
        stays = w["lowest_after"] >= float(snap.buffer)
        impact = {"lowest_before": w["lowest_before"], "lowest_after": w["lowest_after"], "date": w["lowest_after_date"],
                  "buffer": float(snap.buffer), "stays_above_buffer": stays}
    if price <= limit and stays and (snap.emergency_ok or replenish):
        return {"tier": "buy_now", "months": 0, "monthly": 0.0, "impact": impact}
    capacity = max(snap.surplus, Decimal(0))
    gap = max(price - limit, Decimal(0))
    if capacity > 0:
        months = max(1, math.ceil(gap / capacity))
        if months <= 12:
            return {"tier": "save_up", "months": months, "monthly": float((gap / months).quantize(Decimal("1"))), "impact": impact}
    return {"tier": "not_now", "months": None, "monthly": None, "impact": impact}


def refresh_picks(db: Session, user: User, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    prefs = user.preferences or {}
    if not prefs.get("picks_enabled"):
        return {"skipped": "Smart Picks is turned off"}
    snap = affordability(db, user, today)
    save_snapshot(db, user, snap)
    products = db.scalars(select(Product).where(Product.stale.is_(False), Product.availability == "InStock")).all()
    if not products:
        return {"skipped": "No products crawled yet"}
    origins = set(snap.origins)
    ints = interests(db, user, origins, today)
    if not ints:
        return {"picks": 0, "interests": 0}
    projection = snapshot_projection(db, user, snap)
    docs = [_doc(p) for p in products]
    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True).fit(docs + [normalize(i.text) for i in ints])
    pm = vec.transform(docs)
    stats = _price_stats(db, [p.id for p in products], today)
    previous = {r.product_id: r.status for r in db.scalars(select(ProductRecommendation).where(ProductRecommendation.user_id == user.id)).all()}
    bought = {normalize(d) for d in db.scalars(select(TransactionItem.description).join(Transaction).where(
        Transaction.user_id == user.id, Transaction.txn_date >= today - timedelta(days=30))).all()}
    goals = {g.id: g for g in db.scalars(select(Goal).where(Goal.user_id == user.id, Goal.status == "active")).all()}
    candidates: dict[int, dict[str, Any]] = {}
    for it in ints:
        sims = (pm @ vec.transform([normalize(it.text)]).T).toarray().ravel()
        for idx in np.argsort(-sims)[:30]:
            sim = float(sims[idx])
            if sim < 0.12:
                break
            p = products[idx]
            if previous.get(p.id) in ("dismissed", "bought"):
                continue
            if it.max_price is not None and it.source == "wishlist" and p.price > it.max_price:
                continue
            replenish = it.source == "replenish"
            if replenish:
                if fuzz.token_set_ratio(normalize(p.title), normalize(it.text)) < 70 or not it.typical_price:
                    continue
                if p.price > it.typical_price * Decimal("1.05"):
                    continue  # replenishment picks must save money, never cost more
            elif normalize(p.title) in bought:
                continue
            relevance = min(1.0, sim * it.weight / 2.2)
            if p.id in candidates and candidates[p.id]["relevance"] >= relevance:
                continue
            candidates[p.id] = {"product": p, "interest": it, "relevance": relevance}
    picks = []
    for pid, c in candidates.items():
        p, it = c["product"], c["interest"]
        median30, min30 = stats.get(pid, (p.price, p.price))
        verdict = evaluate_price(p.price, snap, projection, replenish=it.source == "replenish")
        tier = verdict["tier"]
        goal = goals.get(it.goal_id) if it.goal_id else None
        if goal is not None and tier != "buy_now" and p.price <= goal.target * Decimal("1.1"):
            tier = "goal"
        if tier == "not_now":
            continue
        discount = float(max(Decimal(0), (median30 - p.price) / median30)) if median30 else 0.0
        bayes = (p.rating * p.rating_count + 4.0 * 50) / (p.rating_count + 50)
        value = 0.5 * min(1.0, discount / 0.3) + 0.5 * max(0.0, min(1.0, (bayes - 3.0) / 2.0))
        limit = min(snap.safe_to_spend, snap.wants_left)
        headroom = float(1 - p.price / limit) if tier == "buy_now" and limit else (1 - (verdict["months"] or 12) / 12) * 0.5
        score = 0.45 * c["relevance"] + 0.25 * max(0.0, headroom) + 0.2 * value + (0.1 if goal else 0.0)
        reasons = [f"Matches {it.label}"]
        if it.source == "replenish" and it.typical_price:
            diff = it.typical_price - p.price
            if diff >= 10:
                reasons.append(f"{fmt_inr(diff)} cheaper than the {fmt_inr(it.typical_price)} you usually pay")
                score += 0.15
            else:
                reasons.append(f"About what you usually pay ({fmt_inr(it.typical_price)})")
        if tier == "buy_now":
            reasons.append(f"{fmt_inr(p.price)} is {float(p.price / max(snap.wants_left, Decimal(1)) * 100):.0f}% of what's left in this month's wants budget")
        elif tier == "goal" and goal is not None:
            months_left = max(1, (goal.target_date.year - today.year) * 12 + goal.target_date.month - today.month)
            reasons.append(f"Fits your “{goal.name}” goal: {fmt_inr(goal.saved)} of {fmt_inr(goal.target)} saved, "
                           f"{fmt_inr((goal.target - goal.saved) / months_left)}/month until {goal.target_date:%b %Y}")
        else:
            reasons.append(f"Save {fmt_inr(Decimal(str(verdict['monthly'])))}/month for {verdict['months']} month(s) to buy it without touching your buffer")
        if p.price <= min30 and discount > 0.03:
            reasons.append("Lowest price in 30 days")
        elif discount >= 0.08:
            reasons.append(f"{discount * 100:.0f}% below its usual price")
        if p.rating_count >= 100 and p.rating >= 4.2:
            reasons.append(f"Rated {p.rating}★ by {p.rating_count:,} buyers")
        if verdict["impact"]:
            imp = verdict["impact"]
            reasons.append(f"Lowest projected balance stays {fmt_inr(Decimal(str(imp['lowest_after'])))} (buffer {fmt_inr(snap.buffer)})"
                           if imp["stays_above_buffer"] else "Would take your projected balance below the buffer if bought today")
        picks.append({"product": p, "tier": tier, "score": round(score, 4), "reasons": reasons, "impact": verdict["impact"] or {},
                      "interest": it.label, "months": verdict["months"], "monthly": verdict["monthly"]})
    picks.sort(key=lambda x: -x["score"])
    cap = int(prefs.get("picks_weekly_cap", 12))
    # round-robin across interests so every wishlist item, goal and regular purchase is represented
    by_interest: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pk in picks:
        by_interest[pk["interest"]].append(pk)
    order = sorted(by_interest, key=lambda k: -max(x["score"] for x in by_interest[k]))
    chosen: list[dict[str, Any]] = []
    for rnd in range(3):
        for key in order:
            group = by_interest[key]
            if rnd < len(group) and len(chosen) < cap and (rnd == 0 or not key.startswith("you buy")):
                chosen.append(group[rnd])
    chosen.sort(key=lambda x: (-{"buy_now": 2, "goal": 1, "save_up": 0}[x["tier"]], -x["score"]))
    batch = uuid.uuid4().hex[:12]
    keep_status = {pid: s for pid, s in previous.items() if s in ("saved", "dismissed", "bought")}
    db.execute(delete(ProductRecommendation).where(ProductRecommendation.user_id == user.id, ProductRecommendation.status.notin_(("saved",))))
    saved_ids = set(db.scalars(select(ProductRecommendation.product_id).where(ProductRecommendation.user_id == user.id)).all())
    for pk in chosen:
        if pk["product"].id in saved_ids:
            continue
        db.add(ProductRecommendation(user_id=user.id, product_id=pk["product"].id, tier=pk["tier"], score=pk["score"], reasons=pk["reasons"],
                                     impact={**pk["impact"], "months": pk["months"], "monthly": pk["monthly"]}, interest=pk["interest"][:80],
                                     status=keep_status.get(pk["product"].id, "new"), batch=batch))
    db.flush()
    return {"picks": len(chosen), "candidates": len(candidates), "interests": len(ints),
            "tiers": dict(Counter(pk["tier"] for pk in chosen)), "safe_to_spend": float(snap.safe_to_spend)}
