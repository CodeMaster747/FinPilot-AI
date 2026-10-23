"""SMS read on the user's Android phone by the FinPilot app.

The phone has already dropped personal chats, promotional (-P) senders and OTPs before uploading — they never leave
the device. The app uploads the rest in chunks of one "sync session"; the last chunk starts one pipeline run over
the whole session, in date order (so a reversal always finds the payment it reverses).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.timeutil import local_from_epoch_ms
from app.db.base import utcnow
from app.schemas.common import iso
from app.services.ingestion.types import RawMessage, sms_external_id

MAX_SESSION_MESSAGES = 50_000  # unfinished sessions are deleted after a day by the retention job


def stage_dir() -> Path:
    folder = get_settings().uploads_dir / "imports"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def stage_path(user_id: int, session: str) -> Path:
    return stage_dir() / f"device-{user_id}-{session}.jsonl"


def append_chunk(user_id: int, session: str, messages: list[dict[str, Any]]) -> int:
    """Append a chunk to the session's staging file; returns the session's message count so far."""
    path = stage_path(user_id, session)
    with path.open("a", encoding="utf-8") as fh:
        for m in messages:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    with path.open(encoding="utf-8") as fh:
        n = sum(1 for _ in fh)
    if n > MAX_SESSION_MESSAGES:
        path.unlink(missing_ok=True)
        raise ValueError(f"Too many messages in one sync (over {MAX_SESSION_MESSAGES:,}). Choose a shorter period.")
    return n


def to_raw(item: dict[str, Any]) -> RawMessage:
    address, body, ms = str(item["address"]).strip(), str(item["body"]), int(item["date_ms"])
    return RawMessage("sms", address, local_from_epoch_ms(ms), body, external_id=sms_external_id(address, ms, body))


def _merge_counts(total: dict[str, int] | None, add: dict[str, int]) -> dict[str, int]:
    out = dict(total or {})
    for k, v in add.items():
        out[k] = out.get(k, 0) + int(v or 0)
    return out


def run_device_batch(user_id: int, params: dict[str, Any], progress=None) -> dict[str, Any]:  # noqa: ANN001
    from app.db.session import session_scope
    from app.jobs.runner import runner
    from app.models import ImportBatch, User
    from app.services import consent
    from app.services.ingestion.pipeline import ingest

    path = Path(params["path"])
    items = []
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            items = [json.loads(line) for line in fh if line.strip()]
        path.unlink(missing_ok=True)
    msgs = [to_raw(it) for it in items]
    step = progress or (lambda pct, msg=None: None)
    with session_scope() as db:
        user = db.get(User, user_id)
        source = consent.require_active(db, user, "sms")
        in_window = consent.within_backfill(source, msgs)
        report = ingest(db, user, source, in_window, feed="device", finalize_pending=False,
                        progress=lambda f: step(f * 100, "Reading your SMS"))
        c = report.counts
        server = {
            "uploaded": len(msgs),
            "outside_window": len(msgs) - len(in_window),
            "transactions": c.get("created", 0) + c.get("transfer", 0),
            "linked": c.get("duplicate", 0) + c.get("enriched", 0) + c.get("reversed", 0),
            "review": c.get("review", 0),
            "notes": c.get("informational", 0) + c.get("pending", 0),
            "not_financial": c.get("ignored", 0) + c.get("dropped", 0),
            "already_had": c.get("already_imported", 0),
        }
        phone = {k: int(v) for k, v in (params.get("phone") or {}).items() if isinstance(v, (int, float))}
        state = dict(source.sync_state or {})
        cursor = params.get("cursor_ms")
        if cursor is not None:
            state["cursor_ms"] = max(int(cursor), int(state.get("cursor_ms") or 0))
        state["last_sync_at"] = iso(utcnow())
        state["last"] = {**phone, **server}
        state["totals"] = _merge_counts(state.get("totals"), {**phone, **server})
        if params.get("device"):
            state["device"] = params["device"]
        source.sync_state = state
        batch = db.get(ImportBatch, params.get("batch_id")) if params.get("batch_id") else None
        if batch is not None:
            batch.status = "done"
            batch.total = len(msgs)
            batch.imported = server["transactions"] + c.get("enriched", 0)
            batch.duplicates = c.get("duplicate", 0) + c.get("already_imported", 0)
            batch.ignored = server["not_financial"]
    if msgs:
        runner.enqueue("user_analytics", user_id=user_id)
    return {"counts": {**phone, **server}}
