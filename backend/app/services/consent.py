"""Per-source consent: versioned notices, separate purposes, and an append-only audit trail.

Modelled on the consent principles of India's DPDP Act 2023 (free, specific, informed, unambiguous,
withdrawable as easily as given). This is a design basis, not a compliance claim.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models import ConsentEvent, DataSource, IngestedMessage, MailboxConnection, Transaction, TransactionItem, User
from app.services.metrics import months_ago

NOTICE_VERSION = "2026-11"
PURPOSES = {
    "transactions": "Record my transactions, bills and subscriptions from these messages, and use them for my balance, forecast, "
                    "budgets, insights and affordability checks (required to connect).",
}
NOTICES: dict[str, dict[str, Any]] = {
    "sms": {
        "title": "Bank & payment SMS",
        "reads": [
            "On your Android phone, the FinPilot app reads your SMS inbox — only messages from business sender IDs "
            "(banks, cards, wallets and billers, e.g. VM-HDFCBK-S) — for the period you choose, then new ones each time you open the app.",
            "Transaction alerts, bill reminders, card statements and balance alerts from those senders.",
        ],
        "never_reads": [
            "Messages from personal phone numbers (your chats) — filtered out on your phone and never uploaded.",
            "OTPs and promotional messages (sender IDs ending in -P) — filtered out on your phone and never uploaded.",
        ],
        "stores": [
            "Extracted fields: amount, date, merchant, masked account number (e.g. XX4521), reference number.",
            "The original alert text, encrypted, for 90 days so you can check what was read — then deleted.",
        ],
        "never": ["Send, delete or change messages", "Store OTPs", "Share data with anyone", "Use your data for advertising"],
    },
    "email": {
        "title": "Receipts & bank emails",
        "reads": [
            "Signs in to your mailbox (Gmail, Yahoo, Zoho, iCloud or another IMAP server) with an app password you create — "
            "never your normal password.",
            "Opens only emails from banks, card issuers, merchants, billers and subscription services on the financial allowlist "
            "(plus sender domains you add), for the period you choose, then new ones every 30 minutes.",
        ],
        "never_reads": ["Any email from a sender that is not on the allowlist — it is never opened or downloaded.", "Attachments."],
        "stores": [
            "Extracted fields: amount, merchant, order number, line items, due dates.",
            "The email text, encrypted, for 90 days — then deleted.",
            "Your app password, encrypted — deleted as soon as you disconnect or revoke.",
        ],
        "never": ["Send, delete, move or mark email as read", "Read personal mail", "Share data with anyone",
                  "Use your data for advertising"],
    },
}
KINDS = ("sms", "email")


def notice(kind: str) -> dict[str, Any]:
    return {"kind": kind, "version": NOTICE_VERSION, **NOTICES[kind], "purposes": PURPOSES, "hash": notice_hash(kind)}


def notice_hash(kind: str) -> str:
    payload = json.dumps({"v": NOTICE_VERSION, "notice": NOTICES[kind], "purposes": PURPOSES}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _event(db: Session, user: User, source: DataSource | None, kind: str, event: str, purposes: list[str],
           request: Request | None, details: dict[str, Any] | None = None) -> None:
    db.add(ConsentEvent(
        user_id=user.id, data_source_id=source.id if source else None, source_kind=kind, event=event,
        purposes=purposes, notice_version=NOTICE_VERSION, notice_hash=notice_hash(kind), details=details or {},
        ip=request.client.host if request and request.client else None,
        user_agent=(request.headers.get("user-agent", "")[:255] if request else None),
    ))


def get_source(db: Session, user: User, kind: str) -> DataSource | None:
    return db.scalar(select(DataSource).where(DataSource.user_id == user.id, DataSource.kind == kind))


def grant(db: Session, user: User, kind: str, purposes: list[str], backfill_months: int,
          request: Request | None = None) -> DataSource:
    if kind not in KINDS:
        raise HTTPException(404, "Unknown data source")
    purposes = [p for p in purposes if p in PURPOSES]
    if "transactions" not in purposes:
        raise HTTPException(400, "The 'record transactions' purpose is required to connect this source.")
    src = get_source(db, user, kind)
    if src is None:
        src = DataSource(user_id=user.id, kind=kind)
        db.add(src)
    src.status, src.purposes, src.notice_version = "active", purposes, NOTICE_VERSION
    src.backfill_months, src.granted_at, src.paused_at, src.revoked_at = backfill_months, utcnow(), None, None
    src.sync_state = None  # a new grant (maybe with a different window) reads the window again; duplicates are skipped
    db.flush()
    _event(db, user, src, kind, "granted", purposes, request, {"backfill_months": backfill_months})
    return src


def backfill_start(source: DataSource) -> date:
    """The earliest message date this grant allows: the chosen window back from the day permission was given."""
    granted = source.granted_at.date()
    return months_ago(granted, source.backfill_months) if source.backfill_months else granted


def within_backfill(source: DataSource, messages: list) -> list:  # list[RawMessage]
    start = backfill_start(source)
    return [m for m in messages if m.received_at.date() >= start]


def require_active(db: Session, user: User, kind: str) -> DataSource:
    src = get_source(db, user, kind)
    if src is None or src.status != "active":
        state = "not connected" if src is None else src.status
        raise HTTPException(409, f"{NOTICES[kind]['title']} is {state}. Grant permission on the Connections page first.")
    return src


def set_status(db: Session, user: User, kind: str, status: str, request: Request | None = None) -> DataSource:
    src = get_source(db, user, kind)
    if src is None:
        raise HTTPException(404, "Source not connected")
    event = {"paused": "paused", "active": "resumed", "revoked": "revoked"}[status]
    if src.status == "revoked" and status != "revoked":
        raise HTTPException(409, "This source was revoked — grant permission again to reconnect.")
    src.status = status
    if status == "paused":
        src.paused_at = utcnow()
    elif status == "revoked":
        src.revoked_at = utcnow()
        if kind == "email":  # revoking means FinPilot can no longer sign in to the mailbox at all
            for box in db.scalars(select(MailboxConnection).where(MailboxConnection.data_source_id == src.id)).all():
                db.delete(box)
    _event(db, user, src, kind, event, src.purposes, request)
    return src


def update_purposes(db: Session, user: User, kind: str, purposes: list[str], request: Request | None = None) -> DataSource:
    src = get_source(db, user, kind)
    if src is None:
        raise HTTPException(404, "Source not connected")
    purposes = [p for p in purposes if p in PURPOSES]
    if "transactions" not in purposes:
        raise HTTPException(400, "To stop recording transactions, pause or revoke the source instead.")
    src.purposes = purposes
    _event(db, user, src, kind, "purposes_changed", purposes, request)
    return src


def delete_source_data(db: Session, user: User, kind: str, request: Request | None = None) -> dict[str, int]:
    """Delete every message from this source and every transaction that exists only because of it."""
    src = get_source(db, user, kind)
    if src is None:
        raise HTTPException(404, "Source not connected")
    msgs = db.scalars(select(IngestedMessage).where(IngestedMessage.data_source_id == src.id)).all()
    msg_ids = {m.id for m in msgs}
    linked_txn_ids = {m.transaction_id for m in msgs if m.transaction_id}
    deleted_txns = detached = 0
    for txn_id in linked_txn_ids:
        others = db.scalar(
            select(IngestedMessage.id).where(IngestedMessage.transaction_id == txn_id, IngestedMessage.id.notin_(msg_ids)).limit(1)
        )
        txn = db.get(Transaction, txn_id)
        if txn is None:
            continue
        if others is None and txn.origin == kind:
            db.delete(txn)
            deleted_txns += 1
        else:
            if kind == "email":
                db.execute(delete(TransactionItem).where(TransactionItem.transaction_id == txn_id, TransactionItem.source == "email"))
            detached += 1
    db.execute(delete(IngestedMessage).where(IngestedMessage.data_source_id == src.id))
    src.sync_state = None
    counts = {"messages": len(msgs), "transactions_deleted": deleted_txns, "transactions_kept": detached}
    _event(db, user, src, kind, "data_deleted", src.purposes, request, counts)
    return counts


def history(db: Session, user: User) -> list[ConsentEvent]:
    return db.scalars(select(ConsentEvent).where(ConsentEvent.user_id == user.id).order_by(ConsentEvent.id.desc())).all()
