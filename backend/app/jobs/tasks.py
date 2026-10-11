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


@job("crawl_all")
def crawl_all(ctx) -> dict:  # noqa: ANN001
    from sqlalchemy import select

    from app.db.session import session_scope
    from app.jobs.runner import runner
    from app.models import User
    from app.services.scraper import run_crawl

    result = run_crawl(trigger=ctx.params.get("trigger", "manual"), progress=ctx.progress)
    with session_scope() as db:
        users = [u.id for u in db.scalars(select(User)).all() if (u.preferences or {}).get("picks_enabled")]
    for uid in users:
        runner.enqueue("refresh_picks", user_id=uid)
    return result


@job("refresh_picks")
def refresh_picks_job(ctx) -> dict:  # noqa: ANN001
    from app.db.session import session_scope
    from app.models import User
    from app.services.picks import refresh_picks

    from app.services.insights import refresh_insights

    with session_scope() as db:
        user = db.get(User, ctx.user_id)
        result = refresh_picks(db, user)
        refresh_insights(db, user)
    return result


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

    runner.enqueue("bootstrap_demo")  # refreshes the demo persona if its data ended before today
    with session_scope() as db:
        ids = db.scalars(select(User.id).where(User.is_demo.is_(False))).all()
    for uid in ids:
        runner.enqueue("user_analytics", user_id=uid)
    return {"users": len(ids)}


@job("retention_purge")
def retention_purge(ctx) -> dict:  # noqa: ANN001
    from app.services.privacy import purge_expired_bodies

    return purge_expired_bodies()


@job("ingest_sample")
def ingest_sample(ctx) -> dict:  # noqa: ANN001
    from app.db.session import session_scope
    from app.jobs.runner import runner
    from app.models import ImportBatch, User
    from app.services.demo import load_sample

    kind = ctx.params["kind"]
    with session_scope() as db:
        user = db.get(User, ctx.user_id)
        result = load_sample(db, user, kind, progress=lambda f: ctx.progress(f * 100, f"Reading the sample {kind.upper()} inbox"))
        counts = result.get("counts", {})
        db.add(ImportBatch(user_id=user.id, kind=f"sample_{kind}", filename=f"Sample {kind} inbox", total=result.get("total", 0),
                           imported=counts.get("created", 0) + counts.get("transfer", 0) + counts.get("enriched", 0),
                           duplicates=counts.get("duplicate", 0), ignored=counts.get("ignored", 0) + counts.get("dropped", 0)))
    runner.enqueue("user_analytics", user_id=ctx.user_id)
    return result


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
