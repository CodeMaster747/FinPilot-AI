"""Model -> JSON helpers. Money goes out as numbers (display only; maths stays in Decimal server-side)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_text
from app.models import Account, Category, IngestedMessage, Transaction, User
from app.schemas.common import iso, num


def iso_local(value: datetime | None) -> str | None:
    """Financial event times are local wall-clock times: no 'Z'."""
    return value.isoformat(timespec="seconds") if value else None


class Lookups:
    def __init__(self, db: Session, user_id: int):
        self.cats = {c.id: c for c in db.scalars(select(Category).where(or_(Category.user_id.is_(None), Category.user_id == user_id))).all()}
        self.accts = {a.id: a for a in db.scalars(select(Account).where(Account.user_id == user_id)).all()}


def category_out(c: Category | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {"id": c.id, "name": c.name, "group": c.group, "kind": c.kind, "icon": c.icon, "essential": c.is_essential,
            "discretionary": c.is_discretionary}


def account_out(a: Account | None) -> dict[str, Any] | None:
    if a is None:
        return None
    return {"id": a.id, "name": a.name, "institution": a.institution, "kind": a.kind, "mask": a.mask}


def txn_out(t: Transaction, lk: Lookups) -> dict[str, Any]:
    signed = t.amount if t.direction == "credit" else -t.amount
    return {
        "id": t.id, "date": t.txn_date.isoformat(), "occurred_at": iso_local(t.occurred_at), "amount": num(t.amount),
        "signed_amount": num(signed), "direction": t.direction, "merchant": t.merchant_name, "description": t.description,
        "counterparty": t.counterparty, "category": category_out(lk.cats.get(t.category_id)), "category_source": t.category_source,
        "category_confidence": round(t.category_confidence or 0, 2), "account": account_out(lk.accts.get(t.account_id)),
        "origin": t.origin, "is_transfer": t.is_transfer, "status": t.status, "ref": t.ref_no, "needs_review": t.needs_review,
        "notes": t.notes, "items_count": len(t.items),
    }


def message_out(m: IngestedMessage, with_body: bool = False) -> dict[str, Any]:
    out = {
        "id": m.id, "channel": m.channel, "feed": m.feed, "sender": m.sender, "subject": m.subject,
        "received_at": iso_local(m.received_at), "kind": m.kind, "confidence": round(m.kind_confidence, 2), "parser": m.parser,
        "status": m.status, "role": m.match_role, "match_score": m.match_score, "transaction_id": m.transaction_id,
        "note": m.review_note or m.ignore_reason, "body_purged": m.body_purged_at is not None,
    }
    if with_body:
        out["body"] = decrypt_text(m.body_enc)
        out["fields"] = (m.fields or {}).get("fields", {})
        out["institution"] = (m.fields or {}).get("institution")
        out["purged_at"] = iso(m.body_purged_at)
    return out


def user_out(u: User) -> dict[str, Any]:
    return {"id": u.id, "email": u.email, "name": u.name, "is_demo": u.is_demo, "onboarded": u.onboarded,
            "preferences": u.preferences or {}, "data_end_date": u.data_end_date.isoformat() if u.data_end_date else None,
            "created_at": iso(u.created_at)}
