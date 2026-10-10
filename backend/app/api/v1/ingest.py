"""Feeding the consented sources: sample inbox, file import, and the live simulator."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import DB, CurrentUser
from app.jobs.runner import runner
from app.models import ImportBatch, Transaction
from app.schemas.serialize import Lookups, txn_out
from app.seed.emails import html_to_text
from app.services import consent
from app.services.ingestion import importers, simulator
from app.services.ingestion.pipeline import Pipeline
from app.services.ingestion.types import RawMessage

router = APIRouter(prefix="/ingest", tags=["capture"])


class SimulateBody(BaseModel):
    channel: str = Field(pattern="^(sms|email)$")
    sender: str = Field(min_length=1, max_length=160)
    body: str | None = Field(default=None, max_length=8000)
    subject: str | None = Field(default=None, max_length=255)
    html: str | None = Field(default=None, max_length=20000)


@router.post("/{kind}/sample")
def load_sample(kind: str, db: DB, user: CurrentUser) -> dict:
    if kind not in consent.KINDS:
        raise HTTPException(404, "Unknown source")
    consent.require_active(db, user, kind)
    job_id = runner.enqueue("ingest_sample", user_id=user.id, params={"kind": kind}, db=db)
    return {"job_id": job_id}


@router.post("/{kind}/import")
async def import_file(kind: str, db: DB, user: CurrentUser, file: UploadFile = File(...)) -> dict:
    if kind not in consent.KINDS:
        raise HTTPException(404, "Unknown source")
    consent.require_active(db, user, kind)
    data = await file.read()
    try:
        msgs = importers.parse_sms_file(file.filename or "", data) if kind == "sms" else importers.parse_email_file(file.filename or "", data)
    except importers.ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    if not msgs:
        raise HTTPException(422, "No messages found in that file.")
    folder = get_settings().uploads_dir / "imports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}-{kind}"
    path.write_bytes(data)
    batch = ImportBatch(user_id=user.id, kind=f"{kind}_file", filename=(file.filename or "upload")[:200], total=len(msgs), status="queued")
    db.add(batch)
    db.flush()
    db.commit()
    job_id = runner.enqueue("ingest_file", user_id=user.id, params={"kind": kind, "path": str(path),
                                                                   "filename": file.filename or "", "batch_id": batch.id})
    return {"job_id": job_id, "messages": len(msgs)}


@router.get("/simulator/templates")
def simulator_templates(db: DB, user: CurrentUser) -> list[dict]:
    return simulator.templates(db, user)


@router.post("/simulate")
def simulate(body: SimulateBody, db: DB, user: CurrentUser) -> dict:
    """Runs one message through exactly the same pipeline as imports and the sample inbox."""
    source = consent.require_active(db, user, body.channel)
    text = body.body or (html_to_text(body.html) if body.html else "")
    if not text.strip():
        raise HTTPException(422, "The message is empty.")
    msg = RawMessage(channel=body.channel, sender=body.sender.strip(), received_at=datetime.now().replace(microsecond=0),
                     body=text, subject=body.subject, html=body.html, external_id=f"sim:{uuid.uuid4().hex}")
    report = Pipeline(db, user, source, feed="simulator", finalize_pending=False).run([msg])
    outcome = report.outcomes[0] if report.outcomes else None
    txn = db.get(Transaction, outcome.transaction_id) if outcome and outcome.transaction_id else None
    db.commit()
    if outcome and outcome.status in ("created", "transfer", "reversed", "enriched"):
        runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {
        "status": outcome.status if outcome else "dropped",
        "detail": outcome.detail if outcome else "",
        "kind": outcome.kind if outcome else None,
        "confidence": outcome.confidence if outcome else None,
        "fields": (outcome.fields or {}).get("fields") if outcome and outcome.fields else None,
        "parser": (outcome.fields or {}).get("parser") if outcome and outcome.fields else None,
        "message_id": outcome.message_id if outcome else None,
        "transaction": txn_out(txn, Lookups(db, user.id)) if txn else None,
    }
