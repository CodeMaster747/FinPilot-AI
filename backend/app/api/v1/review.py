"""One review queue for everything the app wasn't sure about: unclear messages, suggested receipt
matches, and uncategorised transactions. Corrections can be remembered as rules."""

from __future__ import annotations

import datetime as dt
from datetime import date, datetime, time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.deps import DB, CurrentUser
from app.core.money import D
from app.jobs.runner import runner
from app.models import Category, CategoryRule, IngestedMessage, Receipt, Transaction
from app.schemas.serialize import Lookups, message_out, txn_out
from app.services.categorization import Categorizer
from app.services.ingestion.extract import Extraction
from app.services.ingestion.pipeline import Pipeline

router = APIRouter(prefix="/review", tags=["review"])


class MessageResolution(BaseModel):
    action: str = Field(pattern="^(create|link|ignore)$")
    amount: float | None = None
    direction: str | None = Field(default=None, pattern="^(debit|credit)$")
    payee: str | None = Field(default=None, max_length=120)
    date: dt.date | None = None
    category_id: int | None = None
    transaction_id: int | None = None


class TxnResolution(BaseModel):
    category_id: int
    remember: bool = True


@router.get("")
def queue(db: DB, user: CurrentUser) -> dict:
    lk = Lookups(db, user.id)
    msgs = db.scalars(select(IngestedMessage).where(IngestedMessage.user_id == user.id, IngestedMessage.status == "needs_review")
                      .order_by(IngestedMessage.received_at.desc()).limit(100)).all()
    items = []
    for m in msgs:
        out = message_out(m, with_body=True)
        if m.transaction_id:
            t = db.get(Transaction, m.transaction_id)
            out["suggested_transaction"] = txn_out(t, lk) if t else None
        items.append(out)
    txns = db.scalars(select(Transaction).where(Transaction.user_id == user.id, Transaction.needs_review.is_(True))
                      .order_by(Transaction.txn_date.desc()).limit(100)).all()
    receipts = db.scalar(select(func.count()).select_from(Receipt).where(Receipt.user_id == user.id, Receipt.status == "parsed"))
    return {"messages": items, "transactions": [txn_out(t, lk) for t in txns],
            "counts": {"messages": len(items), "transactions": len(txns), "receipts": receipts or 0}}


@router.post("/messages/{message_id}")
def resolve_message(message_id: int, body: MessageResolution, db: DB, user: CurrentUser) -> dict:
    m = db.get(IngestedMessage, message_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(404, "Message not found")
    if body.action == "ignore":
        m.status, m.review_note = "ignored", "Dismissed during review"
        if m.match_role == "suggested":
            m.transaction_id, m.match_role = None, None
        return {"ok": True}
    if body.action == "link":
        txn = db.get(Transaction, body.transaction_id or m.transaction_id or 0)
        if txn is None or txn.user_id != user.id:
            raise HTTPException(404, "Transaction not found")
        from app.models import DataSource

        source = db.get(DataSource, m.data_source_id)
        pipe = Pipeline(db, user, source, feed=m.feed)
        ex = Extraction(parser=m.parser or "", fields=(m.fields or {}).get("fields", {}))
        pipe.enrich(txn, m, ex, 1.0)
        return {"ok": True, "transaction_id": txn.id}
    # create a transaction from the corrected fields
    fields = (m.fields or {}).get("fields", {})
    amount = body.amount if body.amount is not None else (float(fields["amount"]["value"]) if fields.get("amount") else None)
    direction = body.direction or (fields.get("direction") or {}).get("value")
    if not amount or not direction:
        raise HTTPException(422, "Enter the amount and whether money came in or went out.")
    payee = body.payee or (fields.get("payee") or {}).get("value") or (fields.get("merchant") or {}).get("value") or "Unknown"
    when = body.date or (date.fromisoformat(fields["date"]["value"]) if fields.get("date") else m.received_at.date())
    cat = Categorizer(db, user.id)
    res = cat.categorize(payee)
    category_id = body.category_id or res.category_id
    txn = Transaction(user_id=user.id, txn_date=when, occurred_at=datetime.combine(when, time(12, 0)), amount=D(amount),
                      direction=direction, description=payee[:255], merchant_id=res.merchant_id, merchant_name=res.merchant_name,
                      category_id=category_id, category_source="user" if body.category_id else res.source,
                      category_confidence=1.0, origin=m.channel)
    db.add(txn)
    db.flush()
    m.transaction_id, m.status, m.match_role, m.review_note = txn.id, "linked", "primary", "Confirmed during review"
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"ok": True, "transaction": txn_out(txn, Lookups(db, user.id))}


@router.post("/transactions/{txn_id}")
def resolve_transaction(txn_id: int, body: TxnResolution, db: DB, user: CurrentUser) -> dict:
    txn = db.get(Transaction, txn_id)
    cat = db.get(Category, body.category_id)
    if txn is None or txn.user_id != user.id or cat is None:
        raise HTTPException(404, "Not found")
    updated = apply_category(db, user.id, txn, cat, body.remember)
    return {"ok": True, "updated": updated}


def apply_category(db, user_id: int, txn: Transaction, cat: Category, remember: bool) -> int:  # noqa: ANN001
    """Recategorise; optionally remember it as a rule and apply it to every payment to the same merchant."""
    txn.category_id, txn.category_source, txn.category_confidence, txn.needs_review = cat.id, "user", 1.0, False
    updated = 1
    if remember and txn.merchant_name:
        exists = db.scalar(select(CategoryRule).where(CategoryRule.user_id == user_id, CategoryRule.value == txn.merchant_name.lower()))
        if exists is None:
            db.add(CategoryRule(user_id=user_id, match_field="merchant", op="contains", value=txn.merchant_name.lower(),
                                category_id=cat.id, priority=10))
        else:
            exists.category_id = cat.id
        for other in db.scalars(select(Transaction).where(Transaction.user_id == user_id, Transaction.merchant_name == txn.merchant_name,
                                                          Transaction.id != txn.id, Transaction.is_transfer.is_(False))).all():
            other.category_id, other.category_source, other.category_confidence, other.needs_review = cat.id, "rule", 1.0, False
            updated += 1
    runner.enqueue("user_analytics", user_id=user_id, db=db)
    return updated
