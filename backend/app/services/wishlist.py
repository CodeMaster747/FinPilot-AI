"""The wishlist: things the user wants, each judged against their real finances.

Tiers: buy_now (fits safe-to-spend and this month's wants budget without the forecast dipping below the buffer),
goal (linked to a savings goal: follow the goal's plan), save_up (affordable within 12 months of surplus),
not_now, and needs_price (no price yet). Prices of linked items are re-checked once a day.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import fmt_inr
from app.db.base import utcnow
from app.models import Goal, User, WishlistItem, WishlistPricePoint
from app.schemas.common import iso
from app.services.affordability import Snapshot, affordability, evaluate_price, snapshot_projection, verdict_text
from app.services.price_fetch import PriceResult, fetch_price

log = logging.getLogger("finpilot.wishlist")
TIER_ORDER = {"buy_now": 0, "goal": 1, "save_up": 2, "not_now": 3, "needs_price": 4}


def record_price(db: Session, item: WishlistItem, price: Decimal, source: str, today: date | None = None) -> None:
    """At most one price point per item per day (the latest wins)."""
    today = today or date.today()
    point = db.scalar(select(WishlistPricePoint).where(WishlistPricePoint.item_id == item.id, WishlistPricePoint.observed_on == today))
    if point is None:
        db.add(WishlistPricePoint(item_id=item.id, price=price, observed_on=today, source=source))
    else:
        point.price, point.source = price, source
    item.price, item.price_source = price, source


def apply_fetch(db: Session, item: WishlistItem, result: PriceResult) -> None:
    item.fetch_status, item.fetch_note, item.last_checked_at = result.status, (result.note or None), utcnow()
    item.store = result.store or item.store
    if result.image and not item.image_url:
        item.image_url = result.image[:1000]
    if result.status == "ok" and result.price is not None:
        record_price(db, item, result.price, "link")


def refresh_item(db: Session, item: WishlistItem) -> PriceResult:
    result = fetch_price(item.url or "")
    apply_fetch(db, item, result)
    db.flush()
    return result


def check_all_prices(db: Session, user_id: int | None = None) -> dict[str, int]:
    """Daily job: re-read the price of every active item that has a link."""
    q = select(WishlistItem).where(WishlistItem.active.is_(True), WishlistItem.url.is_not(None))
    if user_id is not None:
        q = q.where(WishlistItem.user_id == user_id)
    counts: dict[str, int] = {}
    for item in db.scalars(q).all():
        try:
            status = refresh_item(db, item).status
        except Exception:  # noqa: BLE001 - one bad page must not stop the others
            log.exception("price check failed for wishlist item %s", item.id)
            status = "error"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _history(db: Session, item_id: int, days: int = 90) -> list[dict[str, Any]]:
    since = date.today() - timedelta(days=days)
    rows = db.execute(select(WishlistPricePoint.observed_on, WishlistPricePoint.price).where(
        WishlistPricePoint.item_id == item_id, WishlistPricePoint.observed_on >= since).order_by(WishlistPricePoint.observed_on)).all()
    return [{"date": d.isoformat(), "price": float(p)} for d, p in rows]


def _reasons(item: WishlistItem, tier: str, v: dict[str, Any] | None, snap: Snapshot, goal: Goal | None,
             history: list[dict[str, Any]], today: date) -> list[str]:
    reasons: list[str] = []
    price = item.price
    if price is None:
        return [item.fetch_note or "Add a price (or a product link) to see whether it fits your budget."]
    if tier == "buy_now" and snap.wants_known:
        reasons.append(f"{fmt_inr(price)} is {float(price / max(snap.wants_left, Decimal(1)) * 100):.0f}% of what's left in this month's "
                       "wants budget")
    elif tier == "buy_now":
        reasons.append(f"{fmt_inr(price)} fits within what's safe to spend ({fmt_inr(snap.safe_to_spend)}) after bills, goals and "
                       "your buffer")
    elif tier == "goal" and goal is not None:
        months_left = max(1, (goal.target_date.year - today.year) * 12 + goal.target_date.month - today.month)
        reasons.append(f"Your “{goal.name}” goal: {fmt_inr(goal.saved)} of {fmt_inr(goal.target)} saved, "
                       f"{fmt_inr(max(Decimal(0), goal.target - goal.saved) / months_left)}/month until {goal.target_date:%b %Y}")
    elif tier == "save_up" and v:
        reasons.append(f"Save {fmt_inr(Decimal(str(v['monthly'])))}/month for {v['months']} month(s) to buy it without touching "
                       "your buffer")
    elif tier == "not_now":
        reasons.append(verdict_text(v or {"tier": "not_now"}, price, snap))
    if item.max_price is not None and price > item.max_price:
        reasons.append(f"Above the {fmt_inr(item.max_price)} you wanted to pay")
    prices = [h["price"] for h in history]
    if len(prices) >= 2:
        low = min(prices)
        first = prices[0]
        if float(price) <= low and float(price) < first:
            reasons.append(f"Lowest price since you added it (was {fmt_inr(Decimal(str(first)))})")
        elif float(price) > first * 1.03:
            reasons.append(f"Up {((float(price) / first) - 1) * 100:.0f}% since you added it")
    if v and v.get("impact"):
        imp = v["impact"]
        reasons.append(f"Lowest projected balance would be {fmt_inr(Decimal(str(imp['lowest_after'])))} (buffer {fmt_inr(snap.buffer)})"
                       if imp["stays_above_buffer"] else "Would take your projected balance below the safety buffer if bought today")
    return reasons


def item_out(item: WishlistItem, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": item.id, "text": item.text, "price": float(item.price) if item.price is not None else None,
            "price_source": item.price_source, "max_price": float(item.max_price) if item.max_price is not None else None,
            "url": item.url, "store": item.store, "image_url": item.image_url, "fetch_status": item.fetch_status,
            "fetch_note": item.fetch_note, "last_checked_at": iso(item.last_checked_at), "created_at": iso(item.created_at),
            "bought_at": iso(item.bought_at), "active": item.active, "history": history or []}


def evaluate(db: Session, user: User, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    snap = affordability(db, user, today)
    projection = snapshot_projection(db, user, snap)
    goals = {g.wishlist_item_id: g for g in db.scalars(select(Goal).where(Goal.user_id == user.id, Goal.status == "active")).all()
             if g.wishlist_item_id}
    items = db.scalars(select(WishlistItem).where(WishlistItem.user_id == user.id, WishlistItem.active.is_(True))
                       .order_by(WishlistItem.id)).all()
    out = []
    for item in items:
        history = _history(db, item.id)
        goal = goals.get(item.id)
        v = None
        if item.price is None:
            tier = "needs_price"
        else:
            v = evaluate_price(item.price, snap, projection)
            tier = "goal" if goal is not None and v["tier"] != "buy_now" else v["tier"]
        out.append({**item_out(item, history), "tier": tier, "goal_id": goal.id if goal else None,
                    "months": v["months"] if v else None, "monthly": v["monthly"] if v else None,
                    "impact": (v or {}).get("impact"), "reasons": _reasons(item, tier, v, snap, goal, history, today)})
    out.sort(key=lambda x: (TIER_ORDER[x["tier"]], x["price"] or 0))
    return {"snapshot": snap.as_json(), "items": out,
            "counts": {t: sum(1 for x in out if x["tier"] == t) for t in TIER_ORDER}}
