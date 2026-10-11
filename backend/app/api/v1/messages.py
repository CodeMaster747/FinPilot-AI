from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.core.deps import DB, CurrentUser
from app.models import IngestedMessage, Transaction
from app.schemas.serialize import Lookups, message_out, txn_out

router = APIRouter(prefix="/messages", tags=["capture"])


@router.get("")
def list_messages(db: DB, user: CurrentUser, channel: str | None = None, kind: str | None = None, status: str | None = None,
                  transaction_id: int | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> dict:
    q = select(IngestedMessage).where(IngestedMessage.user_id == user.id)
    if channel:
        q = q.where(IngestedMessage.channel == channel)
    if kind:
        q = q.where(IngestedMessage.kind == kind)
    if status:
        q = q.where(IngestedMessage.status == status)
    if transaction_id:
        q = q.where(IngestedMessage.transaction_id == transaction_id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(IngestedMessage.received_at.desc(), IngestedMessage.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [message_out(m) for m in rows], "total": total, "page": page}


@router.get("/{message_id}")
def get_message(message_id: int, db: DB, user: CurrentUser) -> dict:
    m = db.get(IngestedMessage, message_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(404, "Message not found")
    out = message_out(m, with_body=True)
    if m.transaction_id:
        txn = db.get(Transaction, m.transaction_id)
        out["transaction"] = txn_out(txn, Lookups(db, user.id)) if txn else None
    return out
