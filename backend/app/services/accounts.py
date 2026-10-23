"""Accounts are discovered from the masked numbers in alerts (XX4521) — no bank login involved — or added by the
user (cash, wallets, an account whose bank sends no SMS).

Balances come from anchors: a bank alert that states the balance ("Avl Bal"), a card statement, a bank statement's
closing balance, or a balance the user typed in. Every posted transaction after the latest anchor moves it.
Credit cards carry a negative balance (what you owe)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, BalanceSnapshot, Transaction

KINDS = ("savings", "credit_card", "cash", "wallet")
GENERIC_INSTITUTION = "Bank"


def _compatible(acct: Account, institution: str | None, kind: str | None) -> bool:
    if kind and acct.kind != kind and {acct.kind, kind} & {"credit_card"}:
        return False  # card XX1234 and savings XX1234 at one bank are different accounts
    if institution and acct.institution not in (institution, GENERIC_INSTITUTION):
        return False  # same last four digits at two different banks
    return True


def resolve_account(db: Session, user_id: int, mask: str | None, institution: str | None, kind: str | None) -> Account | None:
    if not mask:
        return None
    kind = kind if kind in ("savings", "credit_card") else "savings"
    candidates = db.scalars(select(Account).where(Account.user_id == user_id, Account.mask == mask).order_by(Account.id)).all()
    for acct in candidates:
        if _compatible(acct, institution, kind):
            if institution and acct.institution == GENERIC_INSTITUTION:
                acct.institution = institution  # learnt the bank from a later alert
                if acct.name.startswith(f"{GENERIC_INSTITUTION} "):
                    acct.name = acct.name.replace(GENERIC_INSTITUTION, institution, 1)
            return acct
    bank = institution or GENERIC_INSTITUTION
    acct = Account(user_id=user_id, name=f"{bank} {'Credit Card' if kind == 'credit_card' else 'Account'} ••{mask}",
                   institution=bank, kind=kind, mask=mask, is_liquid=kind != "credit_card")
    db.add(acct)
    db.flush()
    return acct


def set_balance(db: Session, user_id: int, account: Account, balance: Decimal, as_of: datetime, source: str = "manual",
                message_id: int | None = None) -> BalanceSnapshot:
    """Anchor an account's balance at a moment in time (credit cards: pass what you owe as a positive amount)."""
    value = -abs(balance) if account.kind == "credit_card" else balance
    snap = BalanceSnapshot(user_id=user_id, account_id=account.id, balance=value, as_of=as_of, source=source, message_id=message_id)
    db.add(snap)
    db.flush()
    return snap


def _latest_snapshot(db: Session, account_id: int) -> BalanceSnapshot | None:
    return db.scalar(select(BalanceSnapshot).where(BalanceSnapshot.account_id == account_id)
                     .order_by(BalanceSnapshot.as_of.desc(), BalanceSnapshot.id.desc()).limit(1))


def account_balances(db: Session, user_id: int) -> list[dict]:
    """Latest balance per account: the latest anchor plus net movements after it. Without any anchor, a savings
    account shows its opening balance plus every movement seen; a card shows spends minus payments seen."""
    out = []
    for acct in db.scalars(select(Account).where(Account.user_id == user_id).order_by(Account.id)).all():
        snap = _latest_snapshot(db, acct.id)
        if snap is not None:
            net = _net_since(db, acct.id, snap.as_of)
            label = {"manual": "set by you", "statement": "statement", "alert": "bank alert"}.get(snap.source, "bank alert")
            out.append({"account": acct, "balance": snap.balance + net, "as_of": snap.as_of, "source": label, "known": True})
            continue
        if acct.kind == "credit_card":
            spent = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == acct.id, Transaction.direction == "debit", Transaction.status == "posted")) or Decimal(0)
            paid = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == acct.id, Transaction.direction == "credit", Transaction.status == "posted")) or Decimal(0)
            outstanding = max(Decimal(spent) - Decimal(paid), Decimal(0))
            out.append({"account": acct, "balance": -outstanding, "as_of": None, "source": "card spends seen", "known": True})
            continue
        net = _net_since(db, acct.id, None)
        known = acct.opening_date is not None
        out.append({"account": acct, "balance": acct.opening_balance + net, "as_of": None,
                    "source": "opening balance" if known else "movements only", "known": known})
    return out


def balance_known(db: Session, user_id: int) -> bool:
    """True once at least one money account has a real balance anchor (alert, statement, or entered by the user)."""
    return any(r["known"] and r["account"].kind != "credit_card" for r in account_balances(db, user_id))


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
    """Cash you can actually use: balances of money accounts minus what's owed on cards."""
    total = Decimal(0)
    for row in account_balances(db, user_id):
        if row["account"].kind == "credit_card" or row["known"]:
            total += row["balance"]
    return total
