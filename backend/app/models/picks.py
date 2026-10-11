from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.money import Money
from app.db.base import Base, utcnow


class ProductSource(Base):
    __tablename__ = "product_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    base_path: Mapped[str] = mapped_column(String(80))  # e.g. "/techkart/" on the demo store host
    enabled: Mapped[bool] = mapped_column(default=True)
    crawl_interval_hours: Mapped[int] = mapped_column(Integer, default=6)
    robots_allowed: Mapped[bool | None] = mapped_column(nullable=True)
    last_crawled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    product_count: Mapped[int] = mapped_column(Integer, default=0)


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(12))  # schedule | manual | bootstrap
    status: Mapped[str] = mapped_column(String(12), default="running")
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    products_upserted: Mapped[int] = mapped_column(Integer, default=0)
    prices_changed: Mapped[int] = mapped_column(Integer, default=0)
    skipped_robots: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    log: Mapped[list[str]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("source_id", "path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("product_sources.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str] = mapped_column(String(200), default="")
    price: Mapped[Decimal] = mapped_column(Money)
    mrp: Mapped[Decimal] = mapped_column(Money)
    rating: Mapped[float] = mapped_column(Float, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    availability: Mapped[str] = mapped_column(String(20), default="InStock")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    first_seen: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(default=utcnow)
    stale: Mapped[bool] = mapped_column(default=False)


class ProductPriceHistory(Base):
    __tablename__ = "product_price_history"
    __table_args__ = (UniqueConstraint("product_id", "observed_on"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    price: Mapped[Decimal] = mapped_column(Money)
    observed_on: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(10), default="crawl")  # crawl | backfill


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(160))
    max_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AffordabilitySnapshot(Base):
    __tablename__ = "affordability_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    computed_at: Mapped[datetime] = mapped_column(default=utcnow)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ProductRecommendation(Base):
    __tablename__ = "product_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    tier: Mapped[str] = mapped_column(String(10))  # buy_now | save_up
    score: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    impact: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    interest: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(10), default="new")  # new | saved | dismissed | bought
    batch: Mapped[str] = mapped_column(String(32), index=True)
    generated_at: Mapped[datetime] = mapped_column(default=utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
