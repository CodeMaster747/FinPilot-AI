"""Budgets and goals."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.deps import DB, CurrentUser
from app.core.money import D
from app.jobs.runner import runner
from app.models import Budget, Category, Goal
from app.schemas.common import num
from app.services.metrics import budgets_status, goals_status

router = APIRouter(tags=["planning"])


class BudgetBody(BaseModel):
    category_id: int
    amount: float = Field(gt=0, lt=1e8)


class GoalBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target: float = Field(gt=0, lt=1e9)
    saved: float = Field(default=0, ge=0, lt=1e9)
    target_date: dt.date
    keywords: str = Field(default="", max_length=200)
    wishlist_item_id: int | None = None


class GoalPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    target: float | None = Field(default=None, gt=0)
    saved: float | None = Field(default=None, ge=0)
    target_date: dt.date | None = None
    status: str | None = Field(default=None, pattern="^(active|achieved|archived)$")
    add: float | None = Field(default=None, gt=0, description="Add money to the goal")


def _budget_json(b: dict) -> dict:
    return {**b, "budget": num(b["budget"]), "spent": num(b["spent"])}


def _goal_json(g: dict) -> dict:
    return {**g, "target": num(g["target"]), "saved": num(g["saved"]), "remaining": num(g["remaining"]),
            "monthly_needed": num(g["monthly_needed"]), "target_date": g["target_date"].isoformat()}


@router.get("/budgets")
def list_budgets(db: DB, user: CurrentUser) -> list[dict]:
    return [_budget_json(b) for b in budgets_status(db, user.id)]


@router.put("/budgets")
def upsert_budget(body: BudgetBody, db: DB, user: CurrentUser) -> dict:
    cat = db.get(Category, body.category_id)
    if cat is None or cat.kind != "expense":
        raise HTTPException(422, "Budgets can only be set on spending categories.")
    b = db.scalar(select(Budget).where(Budget.user_id == user.id, Budget.category_id == cat.id))
    if b is None:
        b = Budget(user_id=user.id, category_id=cat.id, amount=D(body.amount))
        db.add(b)
    else:
        b.amount = D(body.amount)
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"ok": True}


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: int, db: DB, user: CurrentUser) -> dict:
    b = db.get(Budget, budget_id)
    if b is None or b.user_id != user.id:
        raise HTTPException(404, "Budget not found")
    db.delete(b)
    return {"ok": True}


@router.get("/goals")
def list_goals(db: DB, user: CurrentUser) -> list[dict]:
    return [_goal_json(g) for g in goals_status(db, user.id)]


@router.post("/goals")
def create_goal(body: GoalBody, db: DB, user: CurrentUser) -> dict:
    from app.models import WishlistItem

    item_id = body.wishlist_item_id
    if item_id is not None:
        item = db.get(WishlistItem, item_id)
        if item is None or item.user_id != user.id:
            raise HTTPException(404, "Wishlist item not found")
    # keywords default to the goal's own name, so "what can I buy" answers can relate items to it
    g = Goal(user_id=user.id, name=body.name.strip(), target=D(body.target), saved=D(body.saved), target_date=body.target_date,
             keywords=(body.keywords or body.name).strip()[:200], wishlist_item_id=item_id)
    db.add(g)
    db.flush()
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"id": g.id}


@router.patch("/goals/{goal_id}")
def update_goal(goal_id: int, body: GoalPatch, db: DB, user: CurrentUser) -> dict:
    g = db.get(Goal, goal_id)
    if g is None or g.user_id != user.id:
        raise HTTPException(404, "Goal not found")
    if body.name:
        g.name = body.name.strip()
    if body.target:
        g.target = D(body.target)
    if body.saved is not None:
        g.saved = D(body.saved)
    if body.add:
        g.saved = g.saved + D(body.add)
    if body.target_date:
        g.target_date = body.target_date
    if body.status:
        g.status = body.status
    if g.saved >= g.target and g.status == "active":
        g.status = "achieved"
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"ok": True, "status": g.status}


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: int, db: DB, user: CurrentUser) -> dict:
    g = db.get(Goal, goal_id)
    if g is None or g.user_id != user.id:
        raise HTTPException(404, "Goal not found")
    db.delete(g)
    return {"ok": True}
