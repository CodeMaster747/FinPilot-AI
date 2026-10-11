"""Forecast, subscriptions and tax endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.deps import DB, CurrentUser
from app.jobs.runner import runner
from app.models import Category, ForecastMetric, Job, Subscription
from app.schemas.common import iso
from app.schemas.serialize import category_out
from app.services.forecasting.engine import lowest_point, what_if
from app.services.forecasting.service import latest
from app.services.picks import safety_buffer
from app.services.tax import YEARS, tax_summary
from app.services.tax_export import export_csv, export_pdf

router = APIRouter(tags=["analysis"])

MODEL_LABELS = {"baseline": "Seasonal naive", "baseline_schedule": "Seasonal naive + known schedule",
                "prophet_schedule": "Prophet + known schedule"}


class TaxProfile(BaseModel):
    gross_salary: float | None = Field(default=None, ge=0)
    basic_salary: float | None = Field(default=None, ge=0)
    hra_received: float | None = Field(default=None, ge=0)
    employee_pf: float | None = Field(default=None, ge=0)
    professional_tax: float | None = Field(default=None, ge=0)
    education_loan_interest: float | None = Field(default=None, ge=0)
    home_loan_interest: float | None = Field(default=None, ge=0)
    tds_deducted: float | None = Field(default=None, ge=0)
    metro: bool | None = None
    city: str | None = Field(default=None, max_length=60)


class SubAction(BaseModel):
    action: str | None = Field(default=None, pattern="^(keep|cancel)$")


def _pending(db, user_id: int, kind: str) -> bool:  # noqa: ANN001
    return db.scalar(select(Job.id).where(Job.user_id == user_id, Job.kind == kind, Job.status.in_(("queued", "running"))).limit(1)) is not None


@router.get("/forecast")
def get_forecast(db: DB, user: CurrentUser) -> dict[str, Any]:
    fc = latest(db, user.id)
    if fc is None:
        if not _pending(db, user.id, "user_analytics"):
            runner.enqueue("user_analytics", user_id=user.id, db=db)
        return {"status": "computing"}
    p = fc.payload
    metrics = db.scalars(select(ForecastMetric).where(ForecastMetric.user_id == user.id)).all()
    low, low_date = lowest_point(p["projection"], 60)
    buffer = float(safety_buffer(db, user))
    return {
        "status": "ready", **p, "generated_at": iso(fc.generated_at),
        "lowest_60": {"amount": low, "date": low_date, "below_buffer": low < buffer, "buffer": buffer},
        "backtest": [{"model": m.model, "label": MODEL_LABELS.get(m.model, m.model), "mae": m.mae, "rmse": m.rmse, "wape": m.wape,
                      "folds": m.folds, "horizon_days": m.horizon_days,
                      "end_error": p.get("metrics", {}).get(m.model, {}).get("end_error")} for m in metrics],
    }


@router.get("/forecast/whatif")
def forecast_whatif(db: DB, user: CurrentUser, amount: float = Query(gt=0, lt=1e9), on: date | None = None) -> dict[str, Any]:
    fc = latest(db, user.id)
    if fc is None:
        raise HTTPException(409, "The forecast is still being computed.")
    res = what_if(fc.payload["projection"], amount, on)
    buffer = float(safety_buffer(db, user))
    return {**{k: v for k, v in res.items() if k != "projection"}, "buffer": buffer,
            "stays_above_buffer": res["lowest_after"] >= buffer, "projection": res["projection"]}


@router.get("/subscriptions")
def list_subscriptions(db: DB, user: CurrentUser) -> dict[str, Any]:
    subs = db.scalars(select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.annual_cost.desc())).all()
    cats = {c.id: c for c in db.scalars(select(Category)).all()}
    items = [{"id": s.id, "merchant": s.merchant_name, "category": category_out(cats.get(s.category_id)), "cadence": s.cadence,
              "amount": float(s.amount), "annual_cost": float(s.annual_cost), "first_seen": s.first_seen.isoformat(),
              "last_charged": s.last_charged.isoformat(), "next_expected": s.next_expected.isoformat() if s.next_expected else None,
              "charges": s.charge_count, "status": s.status, "flags": s.flags, "findings": s.findings, "evidence": s.evidence,
              "user_action": s.user_action} for s in subs]
    savings = sorted(({"merchant": s["merchant"], **f} for s in items for f in s["findings"] if s["user_action"] != "keep"),
                     key=lambda f: -f["saving"])
    seen, ranked = set(), []
    for f in savings:  # one suggestion per subscription, the biggest
        if f["merchant"] not in seen:
            seen.add(f["merchant"])
            ranked.append(f)
    active = [s for s in items if s["status"] in ("active", "dormant")]
    return {"items": items, "suggestions": ranked,
            "totals": {"monthly": round(sum(s["annual_cost"] for s in active) / 12, 2), "annual": round(sum(s["annual_cost"] for s in active), 2),
                       "potential_saving": round(sum(f["saving"] for f in ranked if f["type"] != "price_increase"), 2)}}


@router.post("/subscriptions/{sub_id}/action")
def subscription_action(sub_id: int, body: SubAction, db: DB, user: CurrentUser) -> dict:
    s = db.get(Subscription, sub_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(404, "Subscription not found")
    s.user_action = body.action
    return {"ok": True}


@router.get("/tax")
def get_tax(db: DB, user: CurrentUser, year: str = "2026-27") -> dict[str, Any]:
    if year not in YEARS:
        raise HTTPException(404, "Unsupported year")
    return {**tax_summary(db, user, year), "years": [{"id": k, "label": v["label"], "act": v["act"]} for k, v in YEARS.items()]}


@router.put("/tax/profile")
def update_tax_profile(body: TaxProfile, db: DB, user: CurrentUser) -> dict:
    profile = dict(user.tax_profile or {})
    for k, v in body.model_dump(exclude_none=True).items():
        profile[k] = v
    profile.pop("estimated", None)
    user.tax_profile = profile
    return {"ok": True, "profile": profile}


@router.get("/tax/export.csv")
def tax_csv(db: DB, user: CurrentUser, year: str = "2026-27") -> Response:
    if year not in YEARS:
        raise HTTPException(404, "Unsupported year")
    return Response(export_csv(db, user, year), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=finpilot-tax-{year}.csv"})


@router.get("/tax/export.pdf")
def tax_pdf(db: DB, user: CurrentUser, year: str = "2026-27") -> Response:
    if year not in YEARS:
        raise HTTPException(404, "Unsupported year")
    return Response(export_pdf(db, user, year), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=finpilot-tax-{year}.pdf"})
