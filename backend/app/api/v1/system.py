from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import or_, select

from app.core.config import APP_VERSION, get_settings
from app.core.deps import DB, CurrentUser, OptionalUser
from app.jobs.runner import live_progress
from app.models import Job, User
from app.schemas.common import iso
from app.services.system import CAPABILITIES

router = APIRouter(tags=["system"])

ACTIVE = ("queued", "running")


@router.get("/health")
def health() -> dict:
    """Also used by the phone app's "Test connection" when pairing."""
    from app.core.instance import INSTANCE_ID

    return {"status": "ok", "app": "FinPilot AI", "version": APP_VERSION, "instance": INSTANCE_ID}


@router.get("/system/capabilities")
def capabilities() -> dict:
    return CAPABILITIES


@router.get("/system/status")
def status(db: DB, user: OptionalUser) -> dict:
    """Drives the 'Preparing the demo' note on the login page and the activity banner inside the app.
    Signed-in users see only their own background jobs (plus app-wide ones)."""
    settings = get_settings()
    demo = db.scalar(select(User).where(User.email == settings.demo_email))
    bootstrap = db.scalar(select(Job).where(Job.kind == "bootstrap_demo").order_by(Job.id.desc()).limit(1))
    active: list[Job] = []
    if user is not None:
        active = db.scalars(select(Job).where(Job.status.in_(ACTIVE), or_(Job.user_id == user.id, Job.user_id.is_(None)))
                            .order_by(Job.id)).all()
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
    }


@router.get("/system/pairing")
def pairing(user: CurrentUser) -> dict:
    """Addresses the phone app can use to reach this server, with a QR code to scan from the app."""
    from app.core.network import PAIRING, qr_svg

    info = PAIRING.as_dict()
    info["qr_svg"] = qr_svg(PAIRING.best_url) if PAIRING.best_url else None
    info["lan_enabled"] = get_settings().lan
    return info
