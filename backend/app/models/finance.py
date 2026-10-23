from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.money import Money
from app.db.base import Base, utcnow


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    institution: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))  # savings | credit_card | cash
    mask: Mapped[str | None] = mapped_column(String(8), nullable=True)
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    opening_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_liquid: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(60))
    group: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(12))  # income | expense | transfer
    is_essential: Mapped[bool] = mapped_column(default=False)
    is_discretionary: Mapped[bool] = mapped_column(default=False)
    is_sensitive: Mapped[bool] = mapped_column(default=False)  # never used for interest inference
    color: Mapped[str] = mapped_column(String(16), default="#64748b")
    icon: Mapped[str] = mapped_column(String(32), default="circle")
    sort: Mapped[int] = mapped_column(Integer, default=100)


class Merchant(Base):
    """Global merchants come from the curated reference list (user_id NULL); merchants a user names themselves
    (e.g. by correcting a scanned receipt) are private to that user."""

    __tablename__ = "merchants"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    interest_tags: Mapped[list[str]] = mapped_column(JSON, default=list)


class MerchantAlias(Base):
    __tablename__ = "merchant_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    pattern: Mapped[str] = mapped_column(String(120), index=True)  # lower-case token / VPA prefix
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(12), default="seed")  # seed | user


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    match_field: Mapped[str] = mapped_column(String(20), default="merchant")  # merchant | description
    op: Mapped[str] = mapped_column(String(12), default="contains")  # contains | equals
    value: Mapped[str] = mapped_column(String(120))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_date", "user_id", "txn_date"),
        Index("ix_transactions_user_cat_date", "user_id", "category_id", "txn_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    txn_date: Mapped[date] = mapped_column(Date)
    occurred_at: Mapped[datetime | None] = mapped_column(nullable=True)
    amount: Mapped[Decimal] = mapped_column(Money)  # always positive; see direction
    direction: Mapped[str] = mapped_column(String(6))  # debit | credit
    description: Mapped[str] = mapped_column(String(255), default="")
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id", ondelete="SET NULL"), nullable=True)
    merchant_name: Mapped[str] = mapped_column(String(120), default="")
    counterparty: Mapped[str | None] = mapped_column(String(160), nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    category_source: Mapped[str] = mapped_column(String(12), default="system")  # rule|alias|ml|user|system
    category_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    origin: Mapped[str] = mapped_column(String(12), default="manual")  # sms|email|receipt|csv|manual
    is_transfer: Mapped[bool] = mapped_column(default=False)
    transfer_group: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="posted")  # posted | reversed
    ref_no: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    needs_review: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    items: Mapped[list[TransactionItem]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", lazy="selectin"
    )


class TransactionItem(Base):
    __tablename__ = "transaction_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float] = mapped_column(Float, default=1)
    amount: Mapped[Decimal] = mapped_column(Money)
    source: Mapped[str] = mapped_column(String(12), default="email")  # email | receipt

    transaction: Mapped[Transaction] = relationship(back_populates="items")


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    file_path: Mapped[str] = mapped_column(String(512))
    kind: Mapped[str] = mapped_column(String(8), default="image")  # image | pdf
    status: Mapped[str] = mapped_column(String(12), default="parsed")  # parsed | committed | discarded
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    words: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    image_size: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # csv | sms_file | email_file | sample_sms | sample_email
    filename: Mapped[str] = mapped_column(String(200), default="")
    total: Mapped[int] = mapped_column(Integer, default=0)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    ignored: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="done")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    amount: Mapped[Decimal] = mapped_column(Money)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    target: Mapped[Decimal] = mapped_column(Money)
    saved: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    target_date: Mapped[date] = mapped_column(Date)
    wishlist_item_id: Mapped[int | None] = mapped_column(ForeignKey("wishlist_items.id", ondelete="SET NULL"), nullable=True)
    keywords: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | achieved | archived
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    merchant_name: Mapped[str] = mapped_column(String(120))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    cadence: Mapped[str] = mapped_column(String(12))  # weekly | monthly | quarterly | annual
    amount: Mapped[Decimal] = mapped_column(Money)
    first_seen: Mapped[date] = mapped_column(Date)
    last_charged: Mapped[date] = mapped_column(Date)
    next_expected: Mapped[date | None] = mapped_column(Date, nullable=True)
    charge_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | dormant | ended
    annual_cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    user_action: Mapped[str | None] = mapped_column(String(16), nullable=True)  # keep | cancel
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"))
    detector: Mapped[str] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(8))  # low | medium | high
    explanation: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(12), default="open")  # open | dismissed | confirmed
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(120))
    severity: Mapped[int] = mapped_column(Integer, default=50)  # 0-100
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    link: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dismissed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(16))  # prophet | baseline
    horizon_days: Mapped[int] = mapped_column(Integer, default=90)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(default=utcnow)


class ForecastMetric(Base):
    __tablename__ = "forecast_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(16))
    horizon_days: Mapped[int] = mapped_column(Integer)
    folds: Mapped[int] = mapped_column(Integer)
    mae: Mapped[float] = mapped_column(Float)
    rmse: Mapped[float] = mapped_column(Float)
    wape: Mapped[float] = mapped_column(Float)
    generated_at: Mapped[datetime] = mapped_column(default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    text: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
