"""Accounts (with balances derived from alerts), categories, rules and job status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.core.deps import DB, CurrentUser
from app.jobs.runner import live_progress
from app.models import Account, Category, CategoryRule, Job
from app.schemas.common import iso, num
from app.schemas.serialize import account_out, category_out, iso_local
from app.services.accounts import account_balances

router = APIRouter(tags=["accounts"])


class AccountPatch(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class RuleBody(BaseModel):
    value: str = Field(min_length=2, max_length=120)
    category_id: int
    match_field: str = Field(default="merchant", pattern="^(merchant|description)$")
    op: str = Field(default="contains", pattern="^(contains|equals)$")


@router.get("/accounts")
def accounts(db: DB, user: CurrentUser) -> list[dict]:
    return [{**account_out(r["account"]), "balance": num(r["balance"]), "as_of": iso_local(r["as_of"]), "balance_source": r["source"]}
            for r in account_balances(db, user.id)]


@router.patch("/accounts/{account_id}")
def rename_account(account_id: int, body: AccountPatch, db: DB, user: CurrentUser) -> dict:
    a = db.get(Account, account_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Account not found")
    a.name = body.name.strip()
    return account_out(a)


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
