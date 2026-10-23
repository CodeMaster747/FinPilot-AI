"""Accounts (with balances derived from alerts), categories, rules and job status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.core.deps import DB, CurrentUser
from app.core.money import D
from app.core.timeutil import now_local
from app.jobs.runner import live_progress, runner
from app.models import Account, Category, CategoryRule, Job, Transaction
from app.schemas.common import iso, num
from app.schemas.serialize import account_out, category_out, iso_local
from app.services.accounts import account_balances, set_balance

router = APIRouter(tags=["accounts"])


class AccountBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="savings", pattern="^(savings|credit_card|cash|wallet)$")
    institution: str | None = Field(default=None, max_length=80)
    mask: str | None = Field(default=None, pattern=r"^\d{3,4}$")
    balance: float | None = Field(default=None, gt=-1e9, lt=1e9, description="Current balance (cards: amount you owe)")


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: str | None = Field(default=None, pattern="^(savings|credit_card|cash|wallet)$")
    balance: float | None = Field(default=None, gt=-1e9, lt=1e9, description="Current balance (cards: amount you owe)")


class RuleBody(BaseModel):
    value: str = Field(min_length=2, max_length=120)
    category_id: int
    match_field: str = Field(default="merchant", pattern="^(merchant|description)$")
    op: str = Field(default="contains", pattern="^(contains|equals)$")


def _account_rows(db, user_id: int) -> list[dict]:  # noqa: ANN001
    return [{**account_out(r["account"]), "balance": num(r["balance"]) if r["known"] else None, "movement": num(r["balance"]),
             "balance_known": r["known"], "as_of": iso_local(r["as_of"]), "balance_source": r["source"]}
            for r in account_balances(db, user_id)]


@router.get("/accounts")
def accounts(db: DB, user: CurrentUser) -> list[dict]:
    return _account_rows(db, user.id)


@router.post("/accounts")
def create_account(body: AccountBody, db: DB, user: CurrentUser) -> dict:
    """Accounts appear by themselves from bank SMS; add one by hand for cash, a wallet, or a bank that sends no alerts."""
    a = Account(user_id=user.id, name=body.name.strip(), institution=(body.institution or body.name).strip()[:80], kind=body.kind,
                mask=body.mask, is_liquid=body.kind != "credit_card")
    db.add(a)
    db.flush()
    if body.balance is not None:
        set_balance(db, user.id, a, D(body.balance), now_local(), "manual")
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return next(r for r in _account_rows(db, user.id) if r["id"] == a.id)


@router.patch("/accounts/{account_id}")
def update_account(account_id: int, body: AccountPatch, db: DB, user: CurrentUser) -> dict:
    a = db.get(Account, account_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Account not found")
    if body.name:
        a.name = body.name.strip()
    if body.kind:
        a.kind, a.is_liquid = body.kind, body.kind != "credit_card"
    if body.balance is not None:
        # "my balance right now is X": later transactions move it from here
        set_balance(db, user.id, a, D(body.balance), now_local(), "manual")
        runner.enqueue("user_analytics", user_id=user.id, db=db)
    db.flush()
    return next(r for r in _account_rows(db, user.id) if r["id"] == a.id)


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: DB, user: CurrentUser) -> dict:
    a = db.get(Account, account_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Account not found")
    used = db.scalar(select(Transaction.id).where(Transaction.account_id == a.id).limit(1))
    if used is not None:
        raise HTTPException(409, "This account has transactions. Rename it instead, or delete those transactions first.")
    db.delete(a)
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"ok": True}


@router.get("/categories")
def categories(db: DB, user: CurrentUser) -> list[dict]:
    rows = db.scalars(select(Category).where(or_(Category.user_id.is_(None), Category.user_id == user.id))
                      .order_by(Category.sort, Category.name)).all()
    return [category_out(c) for c in rows]


@router.get("/rules")
def rules(db: DB, user: CurrentUser) -> list[dict]:
    rows = db.scalars(select(CategoryRule).where(CategoryRule.user_id == user.id).order_by(CategoryRule.priority, CategoryRule.id)).all()
    cats = {c.id: c for c in db.scalars(select(Category)).all()}
    return [{"id": r.id, "value": r.value, "match_field": r.match_field, "op": r.op, "category": category_out(cats.get(r.category_id)),
             "created_at": iso(r.created_at)} for r in rows]


@router.post("/rules")
def add_rule(body: RuleBody, db: DB, user: CurrentUser) -> dict:
    if db.get(Category, body.category_id) is None:
        raise HTTPException(404, "Category not found")
    rule = CategoryRule(user_id=user.id, value=body.value.lower().strip(), category_id=body.category_id,
                        match_field=body.match_field, op=body.op, priority=10)
    db.add(rule)
    db.flush()
    return {"id": rule.id}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: DB, user: CurrentUser) -> dict:
    r = db.get(CategoryRule, rule_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Rule not found")
    db.delete(r)
    return {"ok": True}


@router.get("/jobs/{job_id}")
def job_status(job_id: int, db: DB, user: CurrentUser) -> dict:
    j = db.get(Job, job_id)
    if j is None or (j.user_id not in (None, user.id)):
        raise HTTPException(404, "Job not found")
    progress, message = live_progress(j)
    return {"id": j.id, "kind": j.kind, "status": j.status, "progress": progress, "message": message, "result": j.result,
            "error": (j.error or "").splitlines()[-1] if j.error else None, "finished_at": iso(j.finished_at)}
