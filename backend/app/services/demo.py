"""Demo bootstrap: a seeded persona whose 24 months of data end *today*, ingested through the real
consent-gated pipeline. Runs on first start and again automatically whenever the data goes stale."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import session_scope
from app.ml.train import ensure_models
from app.models import Budget, Category, CategoryRule, Goal, User, WishlistItem
from app.seed import demo_profile
from app.services import consent
from app.services.reference_data import ensure_reference_data

log = logging.getLogger("finpilot.demo")


def create_user(db, email: str, name: str, password: str, is_demo: bool = False) -> User:  # noqa: ANN001
    user = User(email=email.lower().strip(), name=name.strip(), password_hash=hash_password(password), is_demo=is_demo,
                preferences=dict(demo_profile.PREFERENCES) | {"picks_enabled": is_demo})
    db.add(user)
    db.flush()
    return user


def _personalise(db, user: User, today: date) -> None:  # noqa: ANN001
    cats = {c.name: c for c in db.scalars(select(Category).where(Category.user_id.is_(None))).all()}
    for name, amount in demo_profile.BUDGETS.items():
        db.add(Budget(user_id=user.id, category_id=cats[name].id, amount=amount))
    for g in demo_profile.goals(today):
        db.add(Goal(user_id=user.id, **g))
    for w in demo_profile.WISHLIST:
        db.add(WishlistItem(user_id=user.id, **w))
    for value, cat in demo_profile.RULES:
        db.add(CategoryRule(user_id=user.id, match_field="merchant", op="contains", value=value, category_id=cats[cat].id))
    user.tax_profile = dict(demo_profile.TAX_PROFILE)
    user.onboarded = True


def months_ago(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


def load_sample(db, user: User, kind: str, today: date | None = None, cutoff: datetime | None = None,
                progress=None) -> dict[str, Any]:  # noqa: ANN001
    """Run the persona's sample inbox (kind='sms') or mailbox (kind='email') through the pipeline."""
    from app.seed.emails import render_emails
    from app.seed.persona import build_persona
    from app.seed.sms import render_sms
    from app.services.ingestion.pipeline import ingest

    source = consent.require_active(db, user, kind)
    today = today or date.today()
    persona = build_persona(today, cutoff=cutoff or datetime.now())
    messages = render_sms(persona) if kind == "sms" else render_emails(persona)
    start = months_ago(today, max(1, min(24, source.backfill_months or 24)))
    messages = [m for m in messages if m.received_at.date() >= start]
    report = ingest(db, user, source, messages, feed="sample", progress=progress)
    return report.as_dict()


def ensure_demo(force: bool = False, progress=None) -> dict[str, Any]:  # noqa: ANN001
    settings = get_settings()
    step = progress or (lambda pct, msg: None)
    with session_scope() as db:
        ensure_reference_data(db)
    step(3, "Training models")
    ensure_models()
    today = date.today()
    with session_scope() as db:
        demo = db.scalar(select(User).where(User.email == settings.demo_email))
        if demo is not None and demo.data_end_date == today and not force:
            return {"status": "fresh", "user_id": demo.id}
        if demo is not None:
            step(5, "Refreshing demo data to today")
            db.delete(demo)
            db.flush()
        demo = create_user(db, settings.demo_email, settings.demo_name, settings.demo_password, is_demo=True)
        _personalise(db, demo, today)
        for kind in ("sms", "email"):
            consent.grant(db, demo, kind, ["transactions", "picks"], 24)
        user_id = demo.id
    cutoff = datetime.now()
    results = {}
    for i, kind in enumerate(("sms", "email")):  # SMS first: bank alerts own transactions, emails enrich them
        with session_scope() as db:
            demo = db.get(User, user_id)
            base = 10 + i * 40
            results[kind] = load_sample(db, demo, kind, today, cutoff,
                                        progress=lambda f, b=base, k=kind: step(b + f * 40, f"Reading sample {k.upper()}"))
    step(92, "Preparing sample receipts")
    from app.seed.persona import build_persona
    from app.seed.receipt_images import generate_samples

    from app.seed.import_samples import write_samples

    persona = build_persona(today, cutoff=cutoff)
    generate_samples(persona, get_settings().data_dir / "samples" / "receipts")
    write_samples(persona, get_settings().data_dir / "samples" / "imports")
    with session_scope() as db:
        u = db.get(User, user_id)
        u.data_end_date = today
        u.preferences = {**(u.preferences or {}), "demo_generated_at": cutoff.isoformat(timespec="seconds")}
    step(96, "Scheduling analytics")
    from app.jobs.runner import runner

    runner.enqueue("user_analytics", user_id=user_id)
    runner.enqueue("crawl_all", params={"trigger": "bootstrap"})
    runner.enqueue("quality_report", user_id=user_id)
    log.info("demo ready: %s", results)
    return {"status": "created", "user_id": user_id, **results}
