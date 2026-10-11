from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.core.config import APP_VERSION, get_settings
from app.core.deps import DB
from app.models import Job, User
from app.schemas.common import iso
from app.jobs.runner import live_progress
from app.services.system import CAPABILITIES

router = APIRouter(tags=["system"])

ACTIVE = ("queued", "running")


@router.get("/health")
def health() -> dict:
    from app.core.instance import INSTANCE_ID

    return {"status": "ok", "version": APP_VERSION, "instance": INSTANCE_ID}


@router.get("/system/capabilities")
def capabilities() -> dict:
    return CAPABILITIES


@router.get("/system/status")
def status(db: DB) -> dict:
    """Public: drives the 'Preparing demo data' banner on the login page and inside the app."""
    settings = get_settings()
    demo = db.scalar(select(User).where(User.email == settings.demo_email))
    bootstrap = db.scalar(select(Job).where(Job.kind == "bootstrap_demo").order_by(Job.id.desc()).limit(1))
    active = db.scalars(select(Job).where(Job.status.in_(ACTIVE)).order_by(Job.id)).all()
    return {
        "version": APP_VERSION,
        "demo_ready": bool(demo and demo.data_end_date and (bootstrap is None or bootstrap.status not in ACTIVE)),
        "bootstrap": None
        if bootstrap is None
        else {"status": bootstrap.status, "progress": live_progress(bootstrap)[0], "message": live_progress(bootstrap)[1]},
        "active_jobs": [
            {"id": j.id, "kind": j.kind, "status": j.status, "progress": live_progress(j)[0], "message": live_progress(j)[1],
             "user_id": j.user_id, "started_at": iso(j.started_at)}
            for j in active
        ],
        "store_url": settings.public_store_url,
    }
