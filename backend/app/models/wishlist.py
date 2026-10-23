from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.money import Money
from app.db.base import Base, utcnow


class WishlistItem(Base):
    """Something the user wants to buy. The price is entered by hand or read from a product link."""

    __tablename__ = "wishlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(160))  # what it is
    max_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)  # "I'd pay up to…" (optional)
    price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)  # latest known price
    price_source: Mapped[str | None] = mapped_column(String(8), nullable=True)  # manual | link
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    store: Mapped[str | None] = mapped_column(String(120), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    fetch_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # ok | no_price | robots | blocked | error | not_inr
    fetch_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    bought_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class WishlistPricePoint(Base):
    """One observed price per item per day (from its link, or when the user updates it)."""

    __tablename__ = "wishlist_price_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("wishlist_items.id", ondelete="CASCADE"), index=True)
    price: Mapped[Decimal] = mapped_column(Money)
    observed_on: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(8), default="link")  # link | manual
