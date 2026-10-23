from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, Float, ForeignKey, Index, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.money import Money
from app.db.base import Base, utcnow


class DataSource(Base):
    """A consent-gated source (SMS or Email). Nothing is read from it unless status == 'active'."""

    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("user_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # sms | email
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | paused | revoked
    purposes: Mapped[list[str]] = mapped_column(JSON, default=list)
    notice_version: Mapped[str] = mapped_column(String(20))
    backfill_months: Mapped[int] = mapped_column(default=12)
    granted_at: Mapped[datetime] = mapped_column(default=utcnow)
    paused_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_ingest_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # phone sync cursor and the last sync's counts (SMS), shown as "capture health" on Connections
    sync_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class MailboxConnection(Base):
    """An IMAP mailbox the user connected with an app password (stored encrypted, deleted on revoke)."""

    __tablename__ = "mailbox_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(16))  # gmail | yahoo | zoho | icloud | custom
    host: Mapped[str] = mapped_column(String(120))
    port: Mapped[int] = mapped_column(default=993)
    username: Mapped[str] = mapped_column(String(255))
    secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    folder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uidvalidity: Mapped[int | None] = mapped_column(nullable=True)
    last_uid: Mapped[int | None] = mapped_column(nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_counts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ConsentEvent(Base):
    """Append-only audit log of every consent decision."""

    __tablename__ = "consent_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    data_source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(8))
    event: Mapped[str] = mapped_column(String(20))  # granted | paused | resumed | revoked | purposes_changed | data_deleted
    purposes: Mapped[list[str]] = mapped_column(JSON, default=list)
    notice_version: Mapped[str] = mapped_column(String(20))
    notice_hash: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class IngestedMessage(Base):
    """A financial SMS/email that passed the pre-filter. Non-financial messages are never stored."""

    __tablename__ = "ingested_messages"
    __table_args__ = (
        UniqueConstraint("data_source_id", "external_id"),
        Index("ix_ingested_messages_user_received", "user_id", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(8))  # sms | email
    feed: Mapped[str] = mapped_column(String(12))  # device | imap | import | sample (demo persona only)
    external_id: Mapped[str] = mapped_column(String(128))
    sender: Mapped[str] = mapped_column(String(160))
    received_at: Mapped[datetime]
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    body_purged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    kind_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    parser: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(14))  # linked | enriched | ignored | needs_review | informational
    ignore_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    match_role: Mapped[str | None] = mapped_column(String(16), nullable=True)  # primary|enrichment|transfer_pair|duplicate
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class UpcomingPayment(Base):
    __tablename__ = "upcoming_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    payee: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16))  # bill | card_due
    amount: Mapped[Decimal] = mapped_column(Money)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="upcoming")  # upcoming | paid | missed
    message_id: Mapped[int | None] = mapped_column(ForeignKey("ingested_messages.id", ondelete="CASCADE"), nullable=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    balance: Mapped[Decimal] = mapped_column(Money)
    as_of: Mapped[datetime]
    message_id: Mapped[int | None] = mapped_column(ForeignKey("ingested_messages.id", ondelete="CASCADE"), nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="alert")  # alert (bank message) | manual | statement
