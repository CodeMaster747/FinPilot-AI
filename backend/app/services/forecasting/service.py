"""Persist forecasts + backtest metrics; serve the latest one and what-if checks."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Forecast, ForecastMetric
from app.services.forecasting.engine import forecast


def refresh_forecast(db: Session, user_id: int, today: date | None = None) -> dict[str, Any]:
    fc = forecast(db, user_id, today)
    db.execute(delete(Forecast).where(Forecast.user_id == user_id))
    db.add(Forecast(user_id=user_id, model=fc["model"], horizon_days=len(fc["projection"]), payload=fc, note=fc["note"]))
    if fc["metrics"]:
        db.execute(delete(ForecastMetric).where(ForecastMetric.user_id == user_id))
        for name, m in fc["metrics"].items():
            db.add(ForecastMetric(user_id=user_id, model=name, horizon_days=30, folds=int(m["folds"]), mae=m["mae"],
                                  rmse=m["rmse"], wape=m["wape"]))
    db.flush()
    return {"model": fc["model"], "net_next_30": fc["net_next_30"]}


def latest(db: Session, user_id: int) -> Forecast | None:
    return db.scalar(select(Forecast).where(Forecast.user_id == user_id).order_by(Forecast.id.desc()).limit(1))
