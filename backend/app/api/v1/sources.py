"""Consent centre API: grant / pause / resume / revoke / purposes / delete data / history."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.deps import DB, CurrentUser
from app.jobs.runner import runner
from app.models import IngestedMessage
from app.schemas.common import iso
from app.services import consent

router = APIRouter(prefix="/sources", tags=["consent"])


class GrantBody(BaseModel):
    purposes: list[str]
    backfill_months: int = Field(default=12, ge=0, le=24)


class PurposesBody(BaseModel):
    purposes: list[str]


def _check(kind: str) -> None:
    if kind not in consent.KINDS:
        raise HTTPException(404, "Unknown source")


def source_out(db, user, kind: str) -> dict:  # noqa: ANN001
    src = consent.get_source(db, user, kind)
    base = {"kind": kind, "title": consent.NOTICES[kind]["title"], "status": "not_connected", "purposes": [],
            "backfill_months": None, "granted_at": None, "last_ingest_at": None, "counts": {}}
    if src is None:
        return base
    counts = dict(db.execute(select(IngestedMessage.status, func.count()).where(IngestedMessage.data_source_id == src.id)
                             .group_by(IngestedMessage.status)).all())
    return {**base, "id": src.id, "status": src.status, "purposes": src.purposes, "backfill_months": src.backfill_months,
            "granted_at": iso(src.granted_at), "paused_at": iso(src.paused_at), "revoked_at": iso(src.revoked_at),
            "last_ingest_at": iso(src.last_ingest_at), "notice_version": src.notice_version,
            "notice_current": src.notice_version == consent.NOTICE_VERSION,
            "counts": {"messages": sum(counts.values()), **counts}}


@router.get("")
def list_sources(db: DB, user: CurrentUser) -> dict:
    return {"sources": [source_out(db, user, k) for k in consent.KINDS], "notice_version": consent.NOTICE_VERSION}


@router.get("/history")
def history(db: DB, user: CurrentUser) -> list[dict]:
    return [{"id": e.id, "kind": e.source_kind, "event": e.event, "purposes": e.purposes, "notice_version": e.notice_version,
             "notice_hash": e.notice_hash[:12], "details": e.details, "at": iso(e.created_at)} for e in consent.history(db, user)]


@router.get("/{kind}/notice")
def get_notice(kind: str) -> dict:
    _check(kind)
    return consent.notice(kind)


@router.post("/{kind}/grant")
def grant(kind: str, body: GrantBody, request: Request, db: DB, user: CurrentUser) -> dict:
    _check(kind)
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
    if (user.preferences or {}).get("picks_enabled"):
        runner.enqueue("refresh_picks", user_id=user.id, db=db)  # Smart Picks may now use more or less data
    return source_out(db, user, kind)


@router.post("/{kind}/delete-data")
def delete_data(kind: str, request: Request, db: DB, user: CurrentUser) -> dict:
    _check(kind)
    counts = consent.delete_source_data(db, user, kind, request)
    db.commit()
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"deleted": counts, "source": source_out(db, user, kind)}
