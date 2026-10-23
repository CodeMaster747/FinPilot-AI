from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DB
from app.services.affordability import affordability, evaluate_price, snapshot_projection, verdict_text
from app.services.smart_pick import search_products

router = APIRouter(tags=["smart-pick"])


class SearchBody(BaseModel):
    query: str = Field(min_length=2, max_length=160)


@router.post("/smart-pick/search")
def search(body: SearchBody, db: DB, user: CurrentUser) -> dict:
    try:
        products = search_products(body.query.strip())
    except RuntimeError as exc:
        message = str(exc)
        raise HTTPException(503 if "not configured" in message else 502, message) from exc

    snapshot = affordability(db, user)
    projection = snapshot_projection(db, user, snapshot)
    for product in products:
        price = product["price"]
        verdict = evaluate_price(Decimal(str(price)), snapshot, projection) if price else None
        product["affordability"] = verdict["tier"] if verdict else "needs_price"
        product["affordability_text"] = verdict_text(verdict, Decimal(str(price)), snapshot) if verdict else "Price unavailable; check the retailer listing."
    order = {"buy_now": 0, "save_up": 1, "not_now": 2, "needs_price": 3}
    products.sort(key=lambda p: (order.get(p["affordability"], 4), p["price"] or float("inf")))
    return {"query": body.query.strip(), "products": products, "checked_at": datetime.now().astimezone().isoformat()}
