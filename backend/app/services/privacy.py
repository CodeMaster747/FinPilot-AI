"""Retention: raw message bodies are deleted after the user's retention period (extracted fields stay), and
uploads left half-way (an SMS sync the app never finished, a statement never mapped) are deleted after a day."""

from __future__ import annotations

import time
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings

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
    return {"purged": purged, "stale_uploads": purge_stale_uploads()}


def purge_stale_uploads(max_age_hours: int = 24) -> int:
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    uploads = get_settings().uploads_dir
    for pattern in ("imports/device-*.jsonl", "csv/*"):
        for path in uploads.glob(pattern):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
    return removed
