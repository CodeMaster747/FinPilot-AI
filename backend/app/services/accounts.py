"""Accounts are discovered from the masked numbers in alerts (XX4521) — no bank login involved."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, BalanceSnapshot, Transaction


def resolve_account(db: Session, user_id: int, mask: str | None, institution: str | None, kind: str | None) -> Account | None:
    if not mask:
        return None
    acct = db.scalar(select(Account).where(Account.user_id == user_id, Account.mask == mask))
    if acct:
        return acct
    kind = kind if kind in ("savings", "credit_card") else "savings"
    bank = institution or "Bank"
    acct = Account(user_id=user_id, name=f"{bank} {'Credit Card' if kind == 'credit_card' else 'Account'} ••{mask}",
                   institution=bank, kind=kind, mask=mask, is_liquid=kind != "credit_card")
    db.add(acct)
    db.flush()
    return acct


def account_balances(db: Session, user_id: int) -> list[dict]:
    """Latest balance per account: last balance snapshot from alerts + net movements after it.
    Credit cards report outstanding = card spends - payments/refunds since the account was seen."""
    out = []
    for acct in db.scalars(select(Account).where(Account.user_id == user_id).order_by(Account.id)).all():
        if acct.kind == "credit_card":
            spent = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == acct.id, Transaction.direction == "debit", Transaction.status == "posted")) or Decimal(0)
            paid = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == acct.id, Transaction.direction == "credit", Transaction.status == "posted")) or Decimal(0)
            outstanding = max(Decimal(spent) - Decimal(paid), Decimal(0))
            out.append({"account": acct, "balance": -outstanding, "as_of": None, "source": "card outstanding"})
            continue
        snap = db.scalar(select(BalanceSnapshot).where(BalanceSnapshot.account_id == acct.id)
                         .order_by(BalanceSnapshot.as_of.desc()).limit(1))
        if snap is None:
            net = _net_since(db, acct.id, None)
            out.append({"account": acct, "balance": acct.opening_balance + net, "as_of": None, "source": "transactions"})
            continue
        net = _net_since(db, acct.id, snap.as_of)
        out.append({"account": acct, "balance": snap.balance + net, "as_of": snap.as_of, "source": "bank alert"})
    return out


def _net_since(db: Session, account_id: int, since: datetime | None) -> Decimal:
    q = select(Transaction.direction, func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.account_id == account_id, Transaction.status == "posted")
    if since is not None:
        q = q.where(Transaction.occurred_at > since)
    net = Decimal(0)
    for direction, total in db.execute(q.group_by(Transaction.direction)).all():
        net += Decimal(total) if direction == "credit" else -Decimal(total)
    return net


def liquid_balance(db: Session, user_id: int) -> Decimal:
    """Cash you can actually use: savings balances minus what's owed on cards."""
    total = Decimal(0)
    for row in account_balances(db, user_id):
        total += row["balance"]
    return total
