"""Wishlist and "Can I afford it?" — real items judged against the user's real finances."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.deps import DB, CurrentUser
from app.core.money import D
from app.db.base import utcnow
from app.models import Goal, WishlistItem
from app.services.affordability import DISCLAIMER, affordability, evaluate_price, snapshot_projection, verdict_text
from app.services.price_fetch import validate_url
from app.services.wishlist import evaluate, item_out, record_price, refresh_item

router = APIRouter(tags=["wishlist"])


class CheckBody(BaseModel):
    price: float = Field(gt=0, lt=1e9)
    label: str | None = Field(default=None, max_length=120)


class WishBody(BaseModel):
    text: str | None = Field(default=None, max_length=160)
    url: str | None = Field(default=None, max_length=1000)
    price: float | None = Field(default=None, gt=0, lt=1e9)
    max_price: float | None = Field(default=None, gt=0, lt=1e9)


class WishPatch(BaseModel):
    text: str | None = Field(default=None, min_length=2, max_length=160)
    url: str | None = Field(default=None, max_length=1000)
    price: float | None = Field(default=None, gt=0, lt=1e9)
    max_price: float | None = Field(default=None, ge=0, lt=1e9)
    bought: bool | None = None


def _own(db, user, item_id: int) -> WishlistItem:  # noqa: ANN001
    item = db.get(WishlistItem, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "Wishlist item not found")
    return item


def _queue_analytics(db, user) -> None:  # noqa: ANN001
    from app.jobs.runner import runner

    runner.enqueue("refresh_insights", user_id=user.id, db=db)


@router.get("/wishlist")
def wishlist(db: DB, user: CurrentUser) -> dict[str, Any]:
    return {"disclaimer": DISCLAIMER, **evaluate(db, user)}


@router.post("/wishlist")
def add_item(body: WishBody, db: DB, user: CurrentUser) -> dict[str, Any]:
    url = None
    if body.url and body.url.strip():
        try:
            url = validate_url(body.url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    text = (body.text or "").strip()
    if not text and not url:
        raise HTTPException(422, "Say what you want, or paste a product link.")
    item = WishlistItem(user_id=user.id, text=(text or "Item from a link")[:160], url=url,
                        max_price=D(body.max_price) if body.max_price else None)
    db.add(item)
    db.flush()
    if body.price:
        record_price(db, item, D(body.price), "manual")
    fetch = None
    if url:
        result = refresh_item(db, item)
        fetch = {"status": result.status, "note": result.note}
        if not text and result.title:
            item.text = result.title[:160]
    _queue_analytics(db, user)
    return {"item": item_out(item), "fetch": fetch}


@router.patch("/wishlist/{item_id}")
def update_item(item_id: int, body: WishPatch, db: DB, user: CurrentUser) -> dict[str, Any]:
    item = _own(db, user, item_id)
    if body.text is not None:
        item.text = body.text.strip()
    if body.max_price is not None:
        item.max_price = D(body.max_price) if body.max_price else None
    if body.url is not None:
        if body.url.strip():
            try:
                item.url = validate_url(body.url)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            refresh_item(db, item)
        else:
            item.url = item.fetch_status = item.fetch_note = None
    if body.price is not None:
        record_price(db, item, D(body.price), "manual")
    if body.bought is not None:
        item.active = not body.bought
        item.bought_at = utcnow() if body.bought else None
    _queue_analytics(db, user)
    return item_out(item)


@router.post("/wishlist/{item_id}/refresh")
def refresh_price(item_id: int, db: DB, user: CurrentUser) -> dict[str, Any]:
    item = _own(db, user, item_id)
    if not item.url:
        raise HTTPException(422, "This item has no product link to check.")
    result = refresh_item(db, item)
    return {"item": item_out(item), "fetch": {"status": result.status, "note": result.note}}


@router.delete("/wishlist/{item_id}")
def delete_item(item_id: int, db: DB, user: CurrentUser) -> dict:
    db.delete(_own(db, user, item_id))
    _queue_analytics(db, user)
    return {"ok": True}


@router.post("/wishlist/{item_id}/goal")
def item_to_goal(item_id: int, db: DB, user: CurrentUser) -> dict[str, Any]:
    """Turn a wishlist item into a savings goal, timed by the save-up plan."""
    item = _own(db, user, item_id)
    if item.price is None:
        raise HTTPException(422, "Add a price first, so the goal knows how much to save.")
    existing = db.scalar(select(Goal).where(Goal.user_id == user.id, Goal.wishlist_item_id == item.id, Goal.status == "active"))
    if existing is not None:
        return {"goal_id": existing.id, "target_date": existing.target_date.isoformat()}
    snap = affordability(db, user)
    v = evaluate_price(item.price, snap, snapshot_projection(db, user, snap))
    months = int(v.get("months") or 3)
    target_date = date.today() + timedelta(days=30 * max(1, months))
    g = Goal(user_id=user.id, name=item.text[:120], target=item.price, saved=Decimal(0), target_date=target_date,
             keywords=item.text[:200], wishlist_item_id=item.id)
    db.add(g)
    db.flush()
    from app.jobs.runner import runner

    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"goal_id": g.id, "target_date": target_date.isoformat()}


@router.post("/afford/check")
def check_price(body: CheckBody, db: DB, user: CurrentUser) -> dict[str, Any]:
    price = D(body.price)
    snap = affordability(db, user)
    v = evaluate_price(price, snap, snapshot_projection(db, user, snap))
    return {"price": float(price), "label": body.label, "verdict": {**v, "text": verdict_text(v, price, snap)}, "snapshot": snap.as_json()}
