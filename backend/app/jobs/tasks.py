"""Importing this module registers every background job with the runner."""

from __future__ import annotations

from app.jobs.runner import job
from app.services import system  # noqa: F401  (system_warmup)


@job("bootstrap_demo")
def bootstrap_demo(ctx) -> dict:  # noqa: ANN001
    from app.services.demo import ensure_demo

    return ensure_demo(force=bool(ctx.params.get("force")), progress=ctx.progress)


@job("user_analytics")
def user_analytics(ctx) -> dict:  # noqa: ANN001
    from app.services.analytics import run_user_analytics

    return run_user_analytics(ctx.user_id, progress=ctx.progress)


@job("refresh_insights")
def refresh_insights_job(ctx) -> dict:  # noqa: ANN001
    """Cheap refresh after a wishlist change (the forecast and subscriptions don't change)."""
    from app.db.session import session_scope
    from app.models import User
    from app.services.insights import refresh_insights

    with session_scope() as db:
        return refresh_insights(db, db.get(User, ctx.user_id))


@job("wishlist_prices")
def wishlist_prices(ctx) -> dict:  # noqa: ANN001
    from app.db.session import session_scope
    from app.services.wishlist import check_all_prices

    with session_scope() as db:
        return check_all_prices(db, ctx.user_id)


@job("quality_report")
def quality_report(ctx) -> dict:  # noqa: ANN001
    from app.services import quality

    report = quality.compute(ctx.user_id)
    return {"ok": True, "challenge_kind_accuracy": report["parsing"]["challenge"]["kind_accuracy"]}


@job("nightly_all_users")
def nightly_all_users(ctx) -> dict:  # noqa: ANN001
    from sqlalchemy import select

    from app.db.session import session_scope
    from app.jobs.runner import runner
    from app.models import User
    from app.services.ingestion.pipeline import finalize_stale_receipts

    runner.enqueue("bootstrap_demo")  # refreshes the demo persona if its data ended before today
    with session_scope() as db:
        ids = db.scalars(select(User.id).where(User.is_demo.is_(False))).all()
    finalized = 0
    for uid in ids:
        with session_scope() as db:
            finalized += finalize_stale_receipts(db, db.get(User, uid))
        runner.enqueue("user_analytics", user_id=uid)
    return {"users": len(ids), "receipts_finalized": finalized}


@job("retention_purge")
def retention_purge(ctx) -> dict:  # noqa: ANN001
    from app.services.privacy import purge_expired_bodies

    return purge_expired_bodies()


@job("ingest_file")
def ingest_file(ctx) -> dict:  # noqa: ANN001
    from pathlib import Path

    from app.db.session import session_scope
    from app.jobs.runner import runner
    from app.models import ImportBatch, User
    from app.services import consent
    from app.services.ingestion import importers
    from app.services.ingestion.pipeline import ingest

    kind, path = ctx.params["kind"], Path(ctx.params["path"])
    data = path.read_bytes()
    path.unlink(missing_ok=True)
    msgs = importers.parse_sms_file(ctx.params["filename"], data) if kind == "sms" else importers.parse_email_file(ctx.params["filename"], data)
    with session_scope() as db:
        user = db.get(User, ctx.user_id)
        source = consent.require_active(db, user, kind)
        msgs = consent.within_backfill(source, msgs)
        report = ingest(db, user, source, msgs, feed="import", progress=lambda f: ctx.progress(f * 100, "Reading your file"))
        batch = db.get(ImportBatch, ctx.params["batch_id"])
        if batch:
            c = report.counts
            batch.status = "done"
            batch.imported = c.get("created", 0) + c.get("transfer", 0) + c.get("enriched", 0)
            batch.duplicates = c.get("duplicate", 0) + c.get("already_imported", 0)
            batch.ignored = c.get("ignored", 0) + c.get("dropped", 0)
    runner.enqueue("user_analytics", user_id=ctx.user_id)
    return report.as_dict()


@job("ingest_device")
def ingest_device(ctx) -> dict:  # noqa: ANN001
    """SMS read on the user's phone and uploaded by the app (already filtered on the phone)."""
    from app.services.ingestion.device import run_device_batch

    return run_device_batch(ctx.user_id, ctx.params, progress=ctx.progress)


@job("imap_sync")
def imap_sync(ctx) -> dict:  # noqa: ANN001
    from app.services.ingestion.imap_sync import sync_user

    return sync_user(ctx.user_id, progress=ctx.progress)


@job("imap_sync_all")
def imap_sync_all(ctx) -> dict:  # noqa: ANN001
    from sqlalchemy import select

    from app.db.session import session_scope
    from app.jobs.runner import runner
    from app.models import DataSource, MailboxConnection

    with session_scope() as db:
        ids = db.scalars(select(MailboxConnection.user_id).join(DataSource, DataSource.id == MailboxConnection.data_source_id)
                         .where(DataSource.status == "active", MailboxConnection.secret_enc.is_not(None))).all()
    for uid in ids:
        runner.enqueue("imap_sync", user_id=uid)
    return {"mailboxes": len(ids)}
