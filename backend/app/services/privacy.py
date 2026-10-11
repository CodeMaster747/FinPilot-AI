"""Retention: raw message bodies are deleted after the user's retention period; extracted fields stay."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.db.base import utcnow
from app.db.session import session_scope
from app.models import IngestedMessage, User


def purge_expired_bodies() -> dict:
    purged = 0
    with session_scope() as db:
        for user in db.scalars(select(User)).all():
            days = int((user.preferences or {}).get("retention_days", 90))
            cutoff = utcnow() - timedelta(days=days)
            rows = db.scalars(select(IngestedMessage).where(
                IngestedMessage.user_id == user.id, IngestedMessage.body_enc.is_not(None),
                IngestedMessage.received_at < cutoff)).all()
            for row in rows:
                row.body_enc, row.body_purged_at = None, utcnow()
            purged += len(rows)
    return {"purged": purged}
