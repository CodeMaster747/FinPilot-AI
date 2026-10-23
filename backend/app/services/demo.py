"""The demo account: a seeded persona (Aarav Sharma) whose 24 months of messages end *today*, ingested through the
real consent-gated pipeline. It exists for presentations, is labelled as sample data everywhere, and can't connect
real sources. Real accounts never see any of this data. Rebuilt on first start and whenever it goes stale."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.ml.text import normalize
from app.ml.train import ensure_models
from app.models import Budget, Category, CategoryRule, Goal, Merchant, MerchantAlias, User, WishlistItem, WishlistPricePoint
from app.seed import demo_profile
from app.seed.reference import PERSONA_MERCHANTS
from app.services import consent
from app.services.metrics import months_ago
from app.services.reference_data import ensure_reference_data
from app.services.users import create_user

log = logging.getLogger("finpilot.demo")


def _persona_merchants(db, user: User, cats: dict[str, Category]) -> None:  # noqa: ANN001
    """The persona's employer and loan are the demo account's own merchants, never global ones."""
    for spec in PERSONA_MERCHANTS:
        merchant = db.scalar(select(Merchant).where(Merchant.user_id.is_(None), Merchant.name == spec.name))
        if merchant is None:
            merchant = Merchant(user_id=user.id, name=spec.name, category_id=cats[spec.category].id)
            db.add(merchant)
            db.flush()
        for pattern in {normalize(a) for a in (*spec.aliases, spec.name)}:
            db.add(MerchantAlias(user_id=user.id, pattern=pattern, merchant_id=merchant.id, source="seed"))


def _personalise(db, user: User, today: date) -> None:  # noqa: ANN001
    cats = {c.name: c for c in db.scalars(select(Category).where(Category.user_id.is_(None))).all()}
    _persona_merchants(db, user, cats)
    for name, amount in demo_profile.BUDGETS.items():
        db.add(Budget(user_id=user.id, category_id=cats[name].id, amount=amount))
    for g in demo_profile.goals(today):
        db.add(Goal(user_id=user.id, **g))
    for w in demo_profile.WISHLIST:
        item = WishlistItem(user_id=user.id, text=w["text"], max_price=w["max_price"], price=w["price"], price_source="manual")
        db.add(item)
        db.flush()
        db.add(WishlistPricePoint(item_id=item.id, price=w["price"], observed_on=today, source="manual"))
    for value, cat in demo_profile.RULES:
        db.add(CategoryRule(user_id=user.id, match_field="merchant", op="contains", value=value, category_id=cats[cat].id))
    user.tax_profile = dict(demo_profile.TAX_PROFILE)
    user.onboarded = True


def load_sample(db, user: User, kind: str, today: date | None = None, cutoff: datetime | None = None,
                progress=None) -> dict[str, Any]:  # noqa: ANN001
    """Run the persona's inbox (kind='sms') or mailbox (kind='email') through the pipeline. Demo account only."""
    from app.seed.emails import render_emails
    from app.seed.persona import build_persona
    from app.seed.sms import render_sms
    from app.services.ingestion.pipeline import ingest

    if not user.is_demo:
        raise ValueError("Sample messages can only be loaded into the demo account.")
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
        demo = create_user(db, settings.demo_email, settings.demo_name, settings.demo_password, is_demo=True,
                           preferences=dict(demo_profile.PREFERENCES))
        _personalise(db, demo, today)
        for kind in ("sms", "email"):
            consent.grant(db, demo, kind, ["transactions"], 24)
        user_id = demo.id
    cutoff = datetime.now()
    results = {}
    for i, kind in enumerate(("sms", "email")):  # SMS first: bank alerts own transactions, emails enrich them
        with session_scope() as db:
            demo = db.get(User, user_id)
            base = 10 + i * 40
            results[kind] = load_sample(db, demo, kind, today, cutoff,
                                        progress=lambda f, b=base, k=kind: step(b + f * 40, f"Reading sample {k.upper()}"))
    with session_scope() as db:
        u = db.get(User, user_id)
        u.data_end_date = today
        u.preferences = {**(u.preferences or {}), "demo_generated_at": cutoff.isoformat(timespec="seconds")}
    step(96, "Scheduling analytics")
    from app.jobs.runner import runner

    runner.enqueue("user_analytics", user_id=user_id)
    runner.enqueue("quality_report", user_id=user_id)
    log.info("demo ready: %s", results)
    return {"status": "created", "user_id": user_id, **results}
