"""Smart Picks: recommendations, product detail, check-a-price, wishlist, stores and crawl runs."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DB, CurrentUser
from app.core.money import D, fmt_inr
from app.jobs.runner import runner
from app.models import CrawlRun, Goal, Product, ProductPriceHistory, ProductRecommendation, ProductSource, WishlistItem
from app.schemas.common import iso
from app.services.picks import DISCLAIMER, affordability, evaluate_price, snapshot_projection

router = APIRouter(tags=["picks"])


class StatusBody(BaseModel):
    status: str = Field(pattern="^(new|saved|dismissed|bought)$")


class CheckBody(BaseModel):
    price: float = Field(gt=0, lt=1e9)
    label: str | None = Field(default=None, max_length=120)


class WishBody(BaseModel):
    text: str = Field(min_length=2, max_length=160)
    max_price: float | None = Field(default=None, gt=0)


def product_out(p: Product, db, history_days: int = 30) -> dict[str, Any]:  # noqa: ANN001
    settings = get_settings()
    src = db.get(ProductSource, p.source_id)
    hist = db.execute(select(ProductPriceHistory.observed_on, ProductPriceHistory.price).where(
        ProductPriceHistory.product_id == p.id, ProductPriceHistory.observed_on >= date.today() - timedelta(days=history_days))
        .order_by(ProductPriceHistory.observed_on)).all()
    prices = [float(x[1]) for x in hist]
    return {"id": p.id, "title": p.title, "brand": p.brand, "category": p.category, "price": float(p.price), "mrp": float(p.mrp),
            "discount_pct": round(float((p.mrp - p.price) / p.mrp * 100), 0) if p.mrp else 0, "rating": p.rating,
            "rating_count": p.rating_count, "store": src.name if src else "", "url": f"{settings.public_store_url}{p.path}",
            "image": f"{settings.public_store_url}{p.image_path}" if p.image_path else None, "tags": p.tags,
            "history": [{"date": d.isoformat(), "price": float(v)} for d, v in hist],
            "low_30": min(prices) if prices else float(p.price), "median_30": sorted(prices)[len(prices) // 2] if prices else float(p.price)}


def _verdict_text(v: dict[str, Any], price: Decimal) -> str:
    if v["tier"] == "buy_now":
        return f"You can buy this now — {fmt_inr(price)} fits your safe-to-spend and this month's wants budget."
    if v["tier"] == "save_up":
        return f"Save {fmt_inr(Decimal(str(v['monthly'])))}/month for {v['months']} month(s) and you can buy it without touching your buffer."
    return "Not right now — it would cut into money you need for bills, goals or your safety buffer."


@router.get("/picks")
def get_picks(db: DB, user: CurrentUser) -> dict[str, Any]:
    prefs = user.preferences or {}
    last_run = db.scalar(select(CrawlRun).order_by(CrawlRun.id.desc()).limit(1))
    base = {"enabled": bool(prefs.get("picks_enabled")), "disclaimer": DISCLAIMER,
            "last_crawl": {"at": iso(last_run.finished_at or last_run.started_at), "status": last_run.status,
                           "products": last_run.products_upserted} if last_run else None}
    if not base["enabled"]:
        return {**base, "picks": [], "snapshot": None}
    snap = affordability(db, user)
    recs = db.execute(select(ProductRecommendation, Product).join(Product).where(
        ProductRecommendation.user_id == user.id, ProductRecommendation.status != "dismissed")
        .order_by(ProductRecommendation.id)).all()
    picks = [{"id": r.id, "tier": r.tier, "score": r.score, "reasons": r.reasons, "impact": r.impact, "interest": r.interest,
              "status": r.status, "generated_at": iso(r.generated_at), "product": product_out(p, db)} for r, p in recs]
    pending = db.scalar(select(ProductRecommendation.id).limit(1)) is None and last_run is None
    return {**base, "snapshot": snap.as_json(), "picks": picks, "preparing": pending,
            "counts": {t: sum(1 for x in picks if x["tier"] == t) for t in ("buy_now", "goal", "save_up")}}


@router.post("/picks/{rec_id}/status")
def set_status(rec_id: int, body: StatusBody, db: DB, user: CurrentUser) -> dict:
    r = db.get(ProductRecommendation, rec_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Pick not found")
    r.status = body.status
    return {"ok": True}


@router.post("/picks/{rec_id}/goal")
def pick_to_goal(rec_id: int, db: DB, user: CurrentUser) -> dict:
    r = db.get(ProductRecommendation, rec_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Pick not found")
    p = db.get(Product, r.product_id)
    months = int((r.impact or {}).get("months") or 3)
    target_date = date.today() + timedelta(days=30 * max(1, months))
    g = Goal(user_id=user.id, name=p.title[:120], target=p.price, saved=Decimal(0), target_date=target_date,
             keywords=" ".join(p.tags or [])[:200], product_id=p.id)
    db.add(g)
    r.status = "saved"
    db.flush()
    return {"goal_id": g.id, "target_date": target_date.isoformat()}


@router.get("/picks/products/{product_id}")
def product_detail(product_id: int, db: DB, user: CurrentUser) -> dict[str, Any]:
    p = db.get(Product, product_id)
    if p is None:
        raise HTTPException(404, "Product not found")
    snap = affordability(db, user)
    v = evaluate_price(p.price, snap, snapshot_projection(db, user, snap))
    return {"product": product_out(p, db, 90), "verdict": {**v, "text": _verdict_text(v, p.price)}, "snapshot": snap.as_json()}


@router.post("/picks/check")
def check_price(body: CheckBody, db: DB, user: CurrentUser) -> dict[str, Any]:
    price = D(body.price)
    snap = affordability(db, user)
    v = evaluate_price(price, snap, snapshot_projection(db, user, snap))
    return {"price": float(price), "label": body.label, "verdict": {**v, "text": _verdict_text(v, price)}, "snapshot": snap.as_json()}


@router.get("/picks/stores")
def stores(db: DB, user: CurrentUser) -> dict[str, Any]:
    settings = get_settings()
    sources = db.scalars(select(ProductSource).order_by(ProductSource.id)).all()
    runs = db.scalars(select(CrawlRun).order_by(CrawlRun.id.desc()).limit(5)).all()
    return {
        "store_url": settings.public_store_url,
        "sources": [{"id": s.id, "name": s.name, "slug": s.slug, "url": f"{settings.public_store_url}{s.base_path}", "enabled": s.enabled,
                     "robots_allowed": s.robots_allowed, "products": s.product_count, "last_crawled_at": iso(s.last_crawled_at),
                     "interval_hours": s.crawl_interval_hours} for s in sources],
        "runs": [{"id": r.id, "trigger": r.trigger, "status": r.status, "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
                  "pages_fetched": r.pages_fetched, "products": r.products_upserted, "prices_changed": r.prices_changed,
                  "skipped_robots": r.skipped_robots, "errors": r.errors, "log": r.log} for r in runs],
    }


@router.post("/picks/crawl")
def crawl_now(db: DB, user: CurrentUser) -> dict:
    return {"job_id": runner.enqueue("crawl_all", params={"trigger": "manual"})}


@router.get("/products")
def search_products(db: DB, user: CurrentUser, q: str = Query(min_length=2), limit: int = Query(10, le=30)) -> list[dict]:
    like = f"%{q.strip()}%"
    rows = db.scalars(select(Product).where(Product.stale.is_(False), Product.title.ilike(like)).order_by(Product.price).limit(limit)).all()
    return [product_out(p, db, 0) for p in rows]


@router.get("/wishlist")
def wishlist(db: DB, user: CurrentUser) -> list[dict]:
    rows = db.scalars(select(WishlistItem).where(WishlistItem.user_id == user.id, WishlistItem.active.is_(True)).order_by(WishlistItem.id)).all()
    return [{"id": w.id, "text": w.text, "max_price": float(w.max_price) if w.max_price else None} for w in rows]


@router.post("/wishlist")
def add_wish(body: WishBody, db: DB, user: CurrentUser) -> dict:
    w = WishlistItem(user_id=user.id, text=body.text.strip(), max_price=D(body.max_price) if body.max_price else None)
    db.add(w)
    db.flush()
    runner.enqueue("refresh_picks", user_id=user.id, db=db)
    return {"id": w.id}


@router.delete("/wishlist/{wish_id}")
def delete_wish(wish_id: int, db: DB, user: CurrentUser) -> dict:
    w = db.get(WishlistItem, wish_id)
    if w is None or w.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(w)
    runner.enqueue("refresh_picks", user_id=user.id, db=db)
    return {"ok": True}
