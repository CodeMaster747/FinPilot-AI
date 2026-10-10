"""Data export, account deletion, demo reset and the system/model-quality report."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import APP_VERSION
from app.core.deps import DB, CurrentUser
from app.db.base import utcnow
from app.jobs.runner import runner
from app.models import (
    Account,
    Budget,
    ConsentEvent,
    DataSource,
    ForecastMetric,
    Goal,
    Subscription,
    Transaction,
    WishlistItem,
)
from app.schemas.common import iso
from app.schemas.serialize import Lookups, txn_out, user_out
from app.services import quality
from app.services.system import CAPABILITIES

router = APIRouter(tags=["settings"])


class DeleteAccount(BaseModel):
    confirm: str


@router.get("/settings/export")
def export_all(db: DB, user: CurrentUser) -> Response:
    lk = Lookups(db, user.id)
    data: dict[str, Any] = {
        "exported_at": iso(utcnow()),
        "app": f"FinPilot AI {APP_VERSION}",
        "user": user_out(user),
        "accounts": [{"name": a.name, "institution": a.institution, "kind": a.kind, "mask": a.mask}
                     for a in db.scalars(select(Account).where(Account.user_id == user.id)).all()],
        "transactions": [txn_out(t, lk) for t in db.scalars(select(Transaction).where(Transaction.user_id == user.id)
                                                            .order_by(Transaction.txn_date)).all()],
        "data_sources": [{"kind": s.kind, "status": s.status, "purposes": s.purposes, "granted_at": iso(s.granted_at)}
                         for s in db.scalars(select(DataSource).where(DataSource.user_id == user.id)).all()],
        "consent_history": [{"kind": e.source_kind, "event": e.event, "purposes": e.purposes, "notice_version": e.notice_version,
                             "at": iso(e.created_at)} for e in db.scalars(select(ConsentEvent).where(ConsentEvent.user_id == user.id)).all()],
        "budgets": [{"category_id": b.category_id, "amount": float(b.amount)} for b in db.scalars(select(Budget).where(Budget.user_id == user.id)).all()],
        "goals": [{"name": g.name, "target": float(g.target), "saved": float(g.saved), "target_date": g.target_date.isoformat()}
                  for g in db.scalars(select(Goal).where(Goal.user_id == user.id)).all()],
        "subscriptions": [{"merchant": s.merchant_name, "cadence": s.cadence, "amount": float(s.amount)}
                          for s in db.scalars(select(Subscription).where(Subscription.user_id == user.id)).all()],
        "wishlist": [{"text": w.text} for w in db.scalars(select(WishlistItem).where(WishlistItem.user_id == user.id)).all()],
    }
    return Response(json.dumps(data, indent=2, default=str), media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename=finpilot-export-{date.today().isoformat()}.json"})


@router.delete("/settings/account")
def delete_account(body: DeleteAccount, db: DB, user: CurrentUser, response: Response) -> dict:
    if body.confirm != "DELETE":
        raise HTTPException(422, "Type DELETE to confirm.")
    if user.is_demo:
        raise HTTPException(409, "The demo account can be reset, not deleted.")
    db.delete(user)
    response.delete_cookie("fp_at", path="/")
    response.delete_cookie("fp_rt", path="/api/v1/auth")
    return {"ok": True}


@router.post("/settings/reset-demo")
def reset_demo(user: CurrentUser) -> dict:
    if not user.is_demo:
        raise HTTPException(403, "Only the demo account can be reset.")
    return {"job_id": runner.enqueue("bootstrap_demo", params={"force": True})}


@router.get("/system/quality")
def system_quality(db: DB, user: CurrentUser) -> dict[str, Any]:
    report = quality.load()
    metrics = db.scalars(select(ForecastMetric).where(ForecastMetric.user_id == user.id)).all()
    return {"capabilities": CAPABILITIES, "report": report, "picks": quality.picks_precision(db, user),
            "forecast_backtest": [{"model": m.model, "mae": m.mae, "rmse": m.rmse, "wape": m.wape, "folds": m.folds} for m in metrics]}
