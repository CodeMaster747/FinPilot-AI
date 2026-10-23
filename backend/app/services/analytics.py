"""Per-user analytics refresh, run after ingestion and nightly: one source of truth for every page."""

from __future__ import annotations

import logging
from typing import Any

from app.db.session import session_scope

log = logging.getLogger("finpilot.analytics")


def run_user_analytics(user_id: int, progress=None) -> dict[str, Any]:  # noqa: ANN001
    step = progress or (lambda pct, msg=None: None)
    out: dict[str, Any] = {}
    from app.services.anomaly import detect_anomalies
    from app.services.forecasting.service import refresh_forecast
    from app.models import User
    from app.services.insights import refresh_insights
    from app.services.subscriptions import refresh_subscriptions

    stages = [
        (10, "Looking for unusual transactions", "anomalies", lambda db: detect_anomalies(db, user_id)),
        (25, "Finding subscriptions", "subscriptions", lambda db: refresh_subscriptions(db, user_id)),
        (40, "Forecasting your cash flow", "forecast", lambda db: refresh_forecast(db, user_id)),
        (90, "Writing your insights", "insights", lambda db: refresh_insights(db, db.get(User, user_id))),
    ]
    for pct, label, key, fn in stages:
        step(pct, label)
        try:
            with session_scope() as db:
                out[key] = fn(db)
        except Exception as exc:  # one failing stage must not block the others
            log.exception("analytics stage %s failed", key)
            out[key] = {"error": str(exc)[:200]}
    return out
