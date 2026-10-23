"""Product discovery through SerpApi Google Shopping, with FinPilot affordability ranking."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import get_settings

SERPAPI_URL = "https://serpapi.com/search.json"


def _price(value: Any) -> float | None:
    if isinstance(value, (float, int)):
        return float(value) if value > 0 else None
    text = re.sub(r"[^\d.]", "", str(value or "").replace(",", ""))
    try:
        parsed = Decimal(text)
        return float(parsed) if parsed > 0 else None
    except (InvalidOperation, ValueError):
        return None


def search_products(query: str, api_key: str | None = None) -> list[dict[str, Any]]:
    key = api_key if api_key is not None else get_settings().serpapi_api_key
    if not key:
        raise RuntimeError("Smart Pick search is not configured yet. Set SERPAPI_API_KEY on the server.")
    try:
        response = httpx.get(SERPAPI_URL, params={
            "engine": "google_shopping", "q": query, "gl": "in", "hl": "en", "google_domain": "google.co.in",
            "api_key": key,
        }, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("Product search is temporarily unavailable. Please try again shortly.") from exc
    if payload.get("error"):
        raise RuntimeError("Product search provider returned an error. Please try again later.")

    products = []
    for item in payload.get("shopping_results", [])[:20]:
        products.append({
            "title": str(item.get("title") or "Product")[:240],
            "price": _price(item.get("extracted_price") or item.get("price")),
            "url": item.get("product_link") or item.get("link"),
            "store": item.get("source"),
            "rating": item.get("rating"),
            "reviews": item.get("reviews"),
            "image": item.get("thumbnail"),
            "delivery": item.get("delivery"),
            "snippet": item.get("snippet"),
        })
    return products
