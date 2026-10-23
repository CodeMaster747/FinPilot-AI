"""Feeding the consented sources with real messages: the phone app's SMS sync, and file imports."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import DB, CurrentUser
from app.jobs.runner import runner
from app.models import ImportBatch, User
from app.services import consent
from app.services.ingestion import device, importers

router = APIRouter(prefix="/ingest", tags=["capture"])
SESSION_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def refuse_demo(user: User) -> None:
    if user.is_demo:
        raise HTTPException(403, "The demo account only holds sample data. Create your own account to connect your real "
                                 "SMS and email.")


class DeviceSms(BaseModel):
    address: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1, max_length=4000)
    date_ms: int = Field(gt=0)


class DeviceUpload(BaseModel):
    session: str = Field(min_length=8, max_length=64)  # one per sync run, made up by the app
    messages: list[DeviceSms] = Field(default_factory=list, max_length=1000)
    final: bool = False
    cursor_ms: int | None = Field(default=None, gt=0)  # newest message the phone looked at (uploaded or not)
    phone: dict[str, int] | None = None  # what the phone read and filtered out itself (counts only)
    device: dict[str, str | int] | None = None  # maker and Android version, to tailor permission help


@router.post("/sms/device")
def upload_device_sms(body: DeviceUpload, db: DB, user: CurrentUser) -> dict:
    """The FinPilot Android app uploads financial SMS read from the phone's inbox (already filtered on the phone)."""
    refuse_demo(user)
    consent.require_active(db, user, "sms")
    if not SESSION_RE.match(body.session):
        raise HTTPException(422, "Invalid sync session id")
    try:
        total = device.append_chunk(user.id, body.session, [m.model_dump() for m in body.messages]) if body.messages else None
    except ValueError as exc:
        raise HTTPException(413, str(exc)) from exc
    if not body.final:
        return {"received": len(body.messages), "session_total": total}
    path = device.stage_path(user.id, body.session)
    if total is None:
        total = sum(1 for _ in path.open(encoding="utf-8")) if path.exists() else 0
    batch = ImportBatch(user_id=user.id, kind="sms_device", filename="SMS from your phone", total=total, status="queued")
    db.add(batch)
    db.flush()
    phone = {k: v for k, v in (body.phone or {}).items() if isinstance(v, int)}
    device_info = {k: v for k, v in (body.device or {}).items() if k in ("manufacturer", "model", "sdk", "app_version")}
    job_id = runner.enqueue("ingest_device", user_id=user.id, db=db, params={
        "path": str(path), "batch_id": batch.id, "cursor_ms": body.cursor_ms, "phone": phone, "device": device_info,
        "session": body.session})
    return {"job_id": job_id, "messages": total}


@router.post("/{kind}/import")
async def import_file(kind: str, db: DB, user: CurrentUser, file: UploadFile = File(...)) -> dict:
    if kind not in consent.KINDS:
        raise HTTPException(404, "Unknown source")
    refuse_demo(user)
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
