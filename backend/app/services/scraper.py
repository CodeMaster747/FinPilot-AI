"""Polite crawler for product catalogues (pointed at the bundled demo storefronts).

- robots.txt is honoured for every URL (Protego: wildcard-aware, reads Crawl-delay and Sitemap lines)
- products are discovered through the sitemap index, never by brute-force link following
- data comes from schema.org Product/Offer JSON-LD, so no per-site CSS selectors are needed
- identifying User-Agent, per-request delay, retries with backoff, page cap, readable log
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from defusedxml.ElementTree import fromstring
from protego import Protego
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.money import D
from app.db.base import utcnow
from app.db.session import session_scope
from app.demo_store.catalog import SHOPS, find_sku, price_on
from app.models import CrawlRun, Product, ProductPriceHistory, ProductSource
from app.services.jsonld import extract_jsonld, of_type

log = logging.getLogger("finpilot.crawler")
USER_AGENT = "FinPilotBot/1.0 (+https://localhost/finpilot; offline demo crawler)"
PAGE_CAP = 600
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_client_factory: Callable[[], httpx.Client] | None = None


def set_client_factory(factory: Callable[[], httpx.Client] | None) -> None:
    """Tests inject an in-process client for the store app."""
    global _client_factory
    _client_factory = factory


def _client() -> httpx.Client:
    if _client_factory is not None:
        return _client_factory()
    return httpx.Client(base_url=get_settings().store_base_url, timeout=10, headers={"User-Agent": USER_AGENT},
                        follow_redirects=True)


def ensure_sources() -> None:
    with session_scope() as db:
        have = {s.slug for s in db.scalars(select(ProductSource)).all()}
        for slug, meta in SHOPS.items():
            if slug not in have:
                db.add(ProductSource(name=meta["name"], slug=slug, base_path=f"/{slug}/"))


class Crawl:
    def __init__(self, run_id: int, client: httpx.Client, progress: Callable[[float, str], None] | None):
        self.run_id = run_id
        self.client = client
        self.progress = progress or (lambda pct, msg: None)
        self.lines: list[str] = []
        self.stats = {"pages_fetched": 0, "products_upserted": 0, "prices_changed": 0, "skipped_robots": 0, "errors": 0}
        self.delay = 1.0
        self._last = 0.0

    def note(self, line: str) -> None:
        self.lines.append(line)
        log.info(line)

    def get(self, url: str) -> httpx.Response | None:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            try:
                self._last = time.monotonic()
                r = self.client.get(url, headers={"User-Agent": USER_AGENT})
                self.stats["pages_fetched"] += 1
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return r
            except httpx.HTTPError as exc:
                if attempt == 2:
                    self.stats["errors"] += 1
                    self.note(f"Error fetching {urlparse(url).path}: {exc.__class__.__name__}")
                    return None
                time.sleep(1.0 * (attempt + 1))
        self.stats["errors"] += 1
        return None

    def run(self) -> dict[str, Any]:
        r = self.get("/robots.txt")
        robots = Protego.parse(r.text if r is not None and r.status_code == 200 else "")
        self.delay = 0.0 if get_settings().testing else max(0.1, float(robots.crawl_delay(USER_AGENT) or 1.0))
        sitemaps = list(robots.sitemaps)
        self.note(f"robots.txt read — Crawl-delay {self.delay}s, {len(sitemaps)} sitemap index(es)")
        children: list[str] = []
        for sm in sitemaps:
            resp = self.get(sm)
            if resp is None or resp.status_code != 200:
                continue
            root = fromstring(resp.content)
            children += [el.text.strip() for el in root.iter(f"{NS}loc") if el.text]
        with session_scope() as db:
            sources = {s.slug: (s.id, s.name) for s in db.scalars(select(ProductSource).where(ProductSource.enabled.is_(True))).all()}
        today = date.today()
        total_sources = max(1, len(sources))
        for n, (slug, (source_id, name)) in enumerate(sources.items()):
            sitemap_url = next((c for c in children if urlparse(c).path == f"/{slug}/sitemap.xml"), None)
            if sitemap_url is None:
                self.note(f"{name}: no sitemap listed — skipped")
                continue
            if not robots.can_fetch(sitemap_url, USER_AGENT):
                self.stats["skipped_robots"] += 1
                self.note(f"{name}: disallowed by robots.txt — skipped without fetching")
                self._mark_source(source_id, robots_allowed=False, count=None)
                continue
            resp = self.get(sitemap_url)
            if resp is None or resp.status_code != 200:
                continue
            urls = [el.text.strip() for el in fromstring(resp.content).iter(f"{NS}loc") if el.text]
            seen: set[str] = set()
            changed_here = 0
            for i, url in enumerate(urls):
                if self.stats["pages_fetched"] >= PAGE_CAP:
                    self.note("Page cap reached — stopping early")
                    break
                if not robots.can_fetch(url, USER_AGENT):
                    self.stats["skipped_robots"] += 1
                    continue
                page = self.get(url)
                if page is None or page.status_code != 200:
                    continue
                product = next(iter(of_type(extract_jsonld(page.text), "Product")), None)
                if product is None:
                    continue
                path = urlparse(url).path
                changed = self._upsert(source_id, path, product, today)
                seen.add(path)
                changed_here += changed
                self.progress(((n + (i + 1) / max(1, len(urls))) / total_sources) * 100, f"Crawling {name}")
            self._finish_source(source_id, seen)
            self.note(f"{name}: {len(seen)} products read, {changed_here} price change(s)")
        return self.stats

    def _upsert(self, source_id: int, path: str, data: dict[str, Any], today: date) -> int:
        offer = data.get("offers") or {}
        offer = offer[0] if isinstance(offer, list) else offer
        if (offer.get("priceCurrency") or "INR") != "INR" or not offer.get("price"):
            return 0
        price = D(offer["price"])
        spec = offer.get("priceSpecification") or {}
        mrp = D(spec.get("price")) if isinstance(spec, dict) and spec.get("price") else price
        brand = data.get("brand") or {}
        rating = data.get("aggregateRating") or {}
        cat_parts = [p.strip() for p in str(data.get("category") or "Other").split(">")]
        image = urlparse(str(data.get("image") or "")).path
        changed = 0
        with session_scope() as db:
            prod = db.scalar(select(Product).where(Product.source_id == source_id, Product.path == path))
            if prod is None:
                prod = Product(source_id=source_id, path=path, first_seen=utcnow())
                db.add(prod)
            prod.sku, prod.title = str(data.get("sku") or path)[:40], str(data.get("name") or "Product")[:200]
            prod.brand = (brand.get("name") if isinstance(brand, dict) else str(brand))[:80]
            prod.category = cat_parts[0][:40]
            prod.description = str(data.get("description") or "")[:2000]
            prod.image_path, prod.price, prod.mrp = image, price, max(mrp, price)
            prod.rating = float(rating.get("ratingValue") or 0)
            prod.rating_count = int(rating.get("reviewCount") or 0)
            prod.availability = str(offer.get("availability") or "InStock").rsplit("/", 1)[-1]
            prod.tags = [t.strip() for t in str(data.get("keywords") or "").split(",") if t.strip()] + cat_parts[1:]
            prod.last_seen, prod.stale = utcnow(), False
            db.flush()
            last = db.scalar(select(ProductPriceHistory).where(ProductPriceHistory.product_id == prod.id)
                             .order_by(ProductPriceHistory.observed_on.desc()).limit(1))
            if last is None or last.observed_on < today:
                if last is not None and last.price != price:
                    changed = 1
                db.add(ProductPriceHistory(product_id=prod.id, price=price, observed_on=today, source="crawl"))
            elif last.price != price:
                last.price, changed = price, 1
        self.stats["products_upserted"] += 1
        self.stats["prices_changed"] += changed
        return changed

    def _mark_source(self, source_id: int, robots_allowed: bool, count: int | None) -> None:
        with session_scope() as db:
            src = db.get(ProductSource, source_id)
            src.robots_allowed, src.last_crawled_at = robots_allowed, utcnow()
            if count is not None:
                src.product_count = count

    def _finish_source(self, source_id: int, seen: set[str]) -> None:
        with session_scope() as db:
            for prod in db.scalars(select(Product).where(Product.source_id == source_id)).all():
                if prod.path not in seen:
                    prod.stale = True
        self._mark_source(source_id, robots_allowed=True, count=len(seen))


def run_crawl(trigger: str = "manual", progress: Callable[[float, str], None] | None = None) -> dict[str, Any]:
    ensure_sources()
    with session_scope() as db:
        run = CrawlRun(trigger=trigger, status="running")
        db.add(run)
        db.flush()
        run_id = run.id
    crawl = Crawl(run_id, _client(), progress)
    status = "done"
    try:
        stats = crawl.run()
    except Exception as exc:  # pragma: no cover - logged and surfaced in the crawl log
        log.exception("crawl failed")
        crawl.note(f"Crawl failed: {exc}")
        stats, status = crawl.stats, "failed"
    finally:
        crawl.client.close()
    with session_scope() as db:
        run = db.get(CrawlRun, run_id)
        run.status, run.finished_at, run.log = status, utcnow(), crawl.lines[-200:]
        for k, v in stats.items():
            setattr(run, k, v)
    backfilled = backfill_history()
    return {**stats, "status": status, "backfilled": backfilled}


def backfill_history(days: int = 90) -> int:
    """First boot only: fill past prices from the store's published schedule so charts have history.
    Rows are marked source='backfill' (they are not observations)."""
    added = 0
    today = date.today()
    with session_scope() as db:
        counts = dict(db.execute(select(ProductPriceHistory.product_id, func.count()).group_by(ProductPriceHistory.product_id)).all())
        for prod in db.scalars(select(Product)).all():
            if counts.get(prod.id, 0) >= 30:
                continue
            item = find_sku(prod.sku)
            if item is None:
                continue
            have = set(db.scalars(select(ProductPriceHistory.observed_on).where(ProductPriceHistory.product_id == prod.id)).all())
            for k in range(days, 0, -1):
                d = today - timedelta(days=k)
                if d not in have:
                    db.add(ProductPriceHistory(product_id=prod.id, price=D(price_on(item, d)), observed_on=d, source="backfill"))
                    added += 1
    return added
