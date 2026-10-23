"""Consent centre API: grant / pause / resume / revoke / delete data / history, plus the two real feeds:
the phone app's SMS sync state and the connected IMAP mailbox."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.v1.ingest import refuse_demo
from app.core.crypto import encrypt_text
from app.core.deps import DB, CurrentUser
from app.core.timeutil import app_zone
from app.jobs.runner import runner
from app.models import IngestedMessage, MailboxConnection
from app.schemas.common import iso
from app.services import consent
from app.services.ingestion import imap_sync

router = APIRouter(prefix="/sources", tags=["consent"])


class GrantBody(BaseModel):
    purposes: list[str]
    backfill_months: int = Field(default=6, ge=0, le=24)


class PurposesBody(BaseModel):
    purposes: list[str]


class MailboxBody(BaseModel):
    provider: str = Field(pattern="^(gmail|yahoo|zoho|zoho_com|icloud|custom)$")
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=4, max_length=200)
    host: str | None = Field(default=None, max_length=120)
    port: int | None = Field(default=None, ge=1, le=65535)


def _check(kind: str) -> None:
    if kind not in consent.KINDS:
        raise HTTPException(404, "Unknown source")


def _mailbox_out(box: MailboxConnection | None) -> dict[str, Any] | None:
    if box is None:
        return None
    return {"provider": box.provider, "provider_label": imap_sync.PROVIDERS.get(box.provider, {}).get("label", box.provider),
            "username": box.username, "host": box.host, "folder": box.folder, "last_synced_at": iso(box.last_synced_at),
            "last_error": box.last_error, "last_counts": box.last_counts or {}}


def _sms_sync(src) -> dict[str, Any]:  # noqa: ANN001
    state = dict(src.sync_state or {})
    start = consent.backfill_start(src)
    start_ms = int(datetime.combine(start, time(0), tzinfo=app_zone()).astimezone(timezone.utc).timestamp() * 1000)
    return {"cursor_ms": state.get("cursor_ms"), "backfill_start_ms": start_ms, "last_sync_at": state.get("last_sync_at"),
            "last": state.get("last") or {}, "totals": state.get("totals") or {}, "device": state.get("device")}


def source_out(db, user, kind: str) -> dict:  # noqa: ANN001
    src = consent.get_source(db, user, kind)
    base = {"kind": kind, "title": consent.NOTICES[kind]["title"], "status": "not_connected", "purposes": [],
            "backfill_months": None, "granted_at": None, "last_ingest_at": None, "counts": {}}
    if src is None:
        return base
    counts = dict(db.execute(select(IngestedMessage.status, func.count()).where(IngestedMessage.data_source_id == src.id)
                             .group_by(IngestedMessage.status)).all())
    out = {**base, "id": src.id, "status": src.status, "purposes": src.purposes, "backfill_months": src.backfill_months,
           "granted_at": iso(src.granted_at), "paused_at": iso(src.paused_at), "revoked_at": iso(src.revoked_at),
           "last_ingest_at": iso(src.last_ingest_at), "notice_version": src.notice_version,
           "notice_current": src.notice_version == consent.NOTICE_VERSION,
           "counts": {"messages": sum(counts.values()), **counts}}
    if kind == "sms":
        out["sync"] = _sms_sync(src)
    else:
        out["mailbox"] = _mailbox_out(db.scalar(select(MailboxConnection).where(MailboxConnection.data_source_id == src.id)))
    return out


@router.get("")
def list_sources(db: DB, user: CurrentUser) -> dict:
    return {"sources": [source_out(db, user, k) for k in consent.KINDS], "notice_version": consent.NOTICE_VERSION,
            "is_demo": user.is_demo}


@router.get("/history")
def history(db: DB, user: CurrentUser) -> list[dict]:
    return [{"id": e.id, "kind": e.source_kind, "event": e.event, "purposes": e.purposes, "notice_version": e.notice_version,
             "notice_hash": e.notice_hash[:12], "details": e.details, "at": iso(e.created_at)} for e in consent.history(db, user)]


@router.get("/email/providers")
def providers() -> dict:
    return {"providers": [{"id": k, **v} for k, v in imap_sync.PROVIDERS.items()]}


@router.get("/{kind}/notice")
def get_notice(kind: str) -> dict:
    _check(kind)
    return consent.notice(kind)


@router.post("/{kind}/grant")
def grant(kind: str, body: GrantBody, request: Request, db: DB, user: CurrentUser) -> dict:
    _check(kind)
    refuse_demo(user)
    consent.grant(db, user, kind, body.purposes, body.backfill_months, request)
    return source_out(db, user, kind)


@router.post("/{kind}/pause")
def pause(kind: str, request: Request, db: DB, user: CurrentUser) -> dict:
    _check(kind)
    consent.set_status(db, user, kind, "paused", request)
    return source_out(db, user, kind)


@router.post("/{kind}/resume")
def resume(kind: str, request: Request, db: DB, user: CurrentUser) -> dict:
    _check(kind)
    consent.set_status(db, user, kind, "active", request)
    return source_out(db, user, kind)


@router.post("/{kind}/revoke")
def revoke(kind: str, request: Request, db: DB, user: CurrentUser) -> dict:
    _check(kind)
    consent.set_status(db, user, kind, "revoked", request)
    return source_out(db, user, kind)


@router.put("/{kind}/purposes")
def purposes(kind: str, body: PurposesBody, request: Request, db: DB, user: CurrentUser) -> dict:
    _check(kind)
    consent.update_purposes(db, user, kind, body.purposes, request)
    return source_out(db, user, kind)


@router.post("/{kind}/delete-data")
def delete_data(kind: str, request: Request, db: DB, user: CurrentUser) -> dict:
    _check(kind)
    counts = consent.delete_source_data(db, user, kind, request)
    db.commit()
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"deleted": counts, "source": source_out(db, user, kind)}


# -- the phone app's SMS sync ------------------------------------------------------------------------
@router.get("/sms/sync-state")
def sms_sync_state(db: DB, user: CurrentUser) -> dict:
    """Where the phone app should start reading (it re-reads a short overlap; duplicates are skipped)."""
    src = consent.get_source(db, user, "sms")
    if src is None:
        return {"status": "not_connected"}
    return {"status": src.status, **_sms_sync(src)}


# -- the connected mailbox -----------------------------------------------------------------------------
@router.get("/email/mailbox")
def get_mailbox(db: DB, user: CurrentUser) -> dict:
    return {"mailbox": _mailbox_out(db.scalar(select(MailboxConnection).where(MailboxConnection.user_id == user.id)))}


@router.post("/email/mailbox")
def connect_mailbox(body: MailboxBody, db: DB, user: CurrentUser) -> dict:
    """Check the app password by signing in once, store it encrypted, and start the first sync."""
    refuse_demo(user)
    src = consent.require_active(db, user, "email")
    address = body.email.strip().lower()
    domain = address.rsplit("@", 1)[-1]
    if domain in imap_sync.UNSUPPORTED:
        raise HTTPException(422, imap_sync.UNSUPPORTED[domain])
    preset = imap_sync.PROVIDERS[body.provider]
    host = (body.host or "").strip() if body.provider == "custom" else preset["host"]
    port = body.port or preset["port"]
    if not host:
        raise HTTPException(422, "Enter your mail server's IMAP address (for example imap.example.com).")
    try:
        folder = imap_sync.test_login(body.provider, host, port, address, body.password)
    except imap_sync.MailboxError as exc:
        raise HTTPException(422, str(exc)) from exc
    box = db.scalar(select(MailboxConnection).where(MailboxConnection.user_id == user.id))
    if box is None:
        box = MailboxConnection(user_id=user.id, data_source_id=src.id, provider=body.provider, host=host, port=port, username=address)
        db.add(box)
    box.data_source_id, box.provider, box.host, box.port, box.username = src.id, body.provider, host, port, address
    box.secret_enc = encrypt_text(body.password.replace(" ", "") if body.provider in ("gmail", "yahoo") else body.password)
    box.folder, box.uidvalidity, box.last_uid, box.last_synced_at, box.last_error = folder, None, None, None, None
    db.flush()
    job_id = runner.enqueue("imap_sync", user_id=user.id, db=db)
    return {"mailbox": _mailbox_out(box), "job_id": job_id}


@router.post("/email/sync")
def sync_mailbox(db: DB, user: CurrentUser) -> dict:
    refuse_demo(user)
    consent.require_active(db, user, "email")
    box = db.scalar(select(MailboxConnection).where(MailboxConnection.user_id == user.id))
    if box is None:
        raise HTTPException(404, "No mailbox connected yet.")
    return {"job_id": runner.enqueue("imap_sync", user_id=user.id, db=db)}


@router.delete("/email/mailbox")
def disconnect_mailbox(db: DB, user: CurrentUser) -> dict:
    box = db.scalar(select(MailboxConnection).where(MailboxConnection.user_id == user.id))
    if box is not None:
        db.delete(box)
    return {"ok": True}
