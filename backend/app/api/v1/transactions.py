from __future__ import annotations

import csv
import io
import datetime as dt
from datetime import date, datetime, time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.core.deps import DB, CurrentUser
from app.core.money import D
from app.jobs.runner import runner
from app.models import Account, Category, IngestedMessage, Receipt, Transaction
from app.schemas.serialize import Lookups, message_out, txn_out
from app.services.categorization import Categorizer

router = APIRouter(prefix="/transactions", tags=["transactions"])


class ManualTxn(BaseModel):
    date: dt.date
    amount: float = Field(gt=0, lt=10_00_00_000)
    direction: str = Field(pattern="^(debit|credit)$")
    merchant: str = Field(min_length=1, max_length=120)
    category_id: int | None = None
    account_id: int | None = None
    notes: str | None = Field(default=None, max_length=500)


class TxnPatch(BaseModel):
    category_id: int | None = None
    merchant: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=500)
    remember: bool = False


class BulkPatch(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    category_id: int


def _filtered(user_id: int, q: str | None, category_id: int | None, account_id: int | None, start: date | None,
              end: date | None, direction: str | None, origin: str | None, review: bool | None, include_transfers: bool):
    stmt = select(Transaction).where(Transaction.user_id == user_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Transaction.merchant_name.ilike(like), Transaction.description.ilike(like), Transaction.notes.ilike(like)))
    if category_id:
        stmt = stmt.where(Transaction.category_id == category_id)
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if start:
        stmt = stmt.where(Transaction.txn_date >= start)
    if end:
        stmt = stmt.where(Transaction.txn_date <= end)
    if direction:
        stmt = stmt.where(Transaction.direction == direction)
    if origin:
        stmt = stmt.where(Transaction.origin == origin)
    if review is not None:
        stmt = stmt.where(Transaction.needs_review.is_(review))
    if not include_transfers:
        stmt = stmt.where(Transaction.is_transfer.is_(False))
    return stmt


@router.get("")
def list_transactions(db: DB, user: CurrentUser, q: str | None = None, category_id: int | None = None, account_id: int | None = None,
                      start: date | None = None, end: date | None = None, direction: str | None = None, origin: str | None = None,
                      review: bool | None = None, include_transfers: bool = True, page: int = Query(1, ge=1),
                      page_size: int = Query(50, ge=1, le=200)) -> dict:
    stmt = _filtered(user.id, q, category_id, account_id, start, end, direction, origin, review, include_transfers)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    sub = stmt.where(Transaction.status == "posted", Transaction.is_transfer.is_(False)).subquery()
    sums = db.execute(select(sub.c.direction, func.sum(sub.c.amount)).group_by(sub.c.direction)).all() if total else []
    rows = db.scalars(stmt.order_by(Transaction.txn_date.desc(), Transaction.occurred_at.desc(), Transaction.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    lk = Lookups(db, user.id)
    totals = {d: float(v or 0) for d, v in sums}
    return {"items": [txn_out(t, lk) for t in rows], "total": total, "page": page, "page_size": page_size,
            "totals": {"in": totals.get("credit", 0.0), "out": totals.get("debit", 0.0)}}


@router.get("/export.csv")
def export_csv(db: DB, user: CurrentUser, q: str | None = None, category_id: int | None = None, start: date | None = None,
               end: date | None = None) -> StreamingResponse:
    stmt = _filtered(user.id, q, category_id, None, start, end, None, None, None, True)
    lk = Lookups(db, user.id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "merchant", "description", "category", "direction", "amount", "account", "origin", "transfer", "status", "notes"])
    for t in db.scalars(stmt.order_by(Transaction.txn_date)).all():
        c, a = lk.cats.get(t.category_id), lk.accts.get(t.account_id)
        w.writerow([t.txn_date.isoformat(), t.merchant_name, t.description, c.name if c else "", t.direction, f"{t.amount:.2f}",
                    a.name if a else "", t.origin, "yes" if t.is_transfer else "", t.status, t.notes or ""])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=finpilot-transactions.csv"})


@router.get("/{txn_id}")
def get_transaction(txn_id: int, db: DB, user: CurrentUser) -> dict:
    t = db.get(Transaction, txn_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, "Transaction not found")
    out = txn_out(t, Lookups(db, user.id))
    out["items"] = [{"description": i.description, "quantity": i.quantity, "amount": float(i.amount), "source": i.source} for i in t.items]
    evidence = db.scalars(select(IngestedMessage).where(IngestedMessage.transaction_id == t.id).order_by(IngestedMessage.received_at)).all()
    out["evidence"] = [message_out(m) for m in evidence]
    out["receipts"] = [{"id": r.id, "filename": r.filename, "kind": r.kind} for r in
                       db.scalars(select(Receipt).where(Receipt.transaction_id == t.id)).all()]
    if t.transfer_group:
        other = db.scalar(select(Transaction).where(Transaction.transfer_group == t.transfer_group, Transaction.id != t.id))
        out["transfer_partner"] = txn_out(other, Lookups(db, user.id)) if other else None
    return out


@router.post("")
def create_transaction(body: ManualTxn, db: DB, user: CurrentUser) -> dict:
    if body.account_id and (db.get(Account, body.account_id) is None or db.get(Account, body.account_id).user_id != user.id):
        raise HTTPException(404, "Account not found")
    res = Categorizer(db, user.id).categorize(body.merchant)
    txn = Transaction(user_id=user.id, account_id=body.account_id, txn_date=body.date, occurred_at=datetime.combine(body.date, time(12)),
                      amount=D(body.amount), direction=body.direction, description=body.merchant, merchant_id=res.merchant_id,
                      merchant_name=res.merchant_name if res.merchant_id else body.merchant.strip(),
                      category_id=body.category_id or res.category_id, category_source="user" if body.category_id else res.source,
                      category_confidence=1.0 if body.category_id else res.confidence, origin="manual", notes=body.notes)
    db.add(txn)
    db.flush()
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return txn_out(txn, Lookups(db, user.id))


@router.patch("/{txn_id}")
def update_transaction(txn_id: int, body: TxnPatch, db: DB, user: CurrentUser) -> dict:
    from app.api.v1.review import apply_category

    t = db.get(Transaction, txn_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, "Transaction not found")
    if body.merchant:
        t.merchant_name = body.merchant.strip()
    if body.notes is not None:
        t.notes = body.notes or None
    if body.category_id:
        cat = db.get(Category, body.category_id)
        if cat is None:
            raise HTTPException(404, "Category not found")
        apply_category(db, user.id, t, cat, body.remember)
    return txn_out(t, Lookups(db, user.id))


@router.post("/bulk")
def bulk_update(body: BulkPatch, db: DB, user: CurrentUser) -> dict:
    cat = db.get(Category, body.category_id)
    if cat is None:
        raise HTTPException(404, "Category not found")
    rows = db.scalars(select(Transaction).where(Transaction.user_id == user.id, Transaction.id.in_(body.ids))).all()
    for t in rows:
        t.category_id, t.category_source, t.category_confidence, t.needs_review = cat.id, "user", 1.0, False
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"updated": len(rows)}


@router.delete("/{txn_id}")
def delete_transaction(txn_id: int, db: DB, user: CurrentUser) -> dict:
    t = db.get(Transaction, txn_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, "Transaction not found")
    db.delete(t)
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"ok": True}
