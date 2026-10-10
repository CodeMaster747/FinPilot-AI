"""Idempotently installs system categories and the curated merchant alias map."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.text import normalize
from app.models import Category, Merchant, MerchantAlias
from app.seed.reference import CATEGORIES, MERCHANTS


def ensure_reference_data(db: Session) -> None:
    existing = {c.name: c for c in db.scalars(select(Category).where(Category.user_id.is_(None))).all()}
    for i, spec in enumerate(CATEGORIES):
        cat = existing.get(spec.name)
        if cat is None:
            cat = Category(name=spec.name, user_id=None)
            db.add(cat)
            existing[spec.name] = cat
        cat.group, cat.kind, cat.is_essential = spec.group, spec.kind, spec.essential
        cat.is_discretionary, cat.is_sensitive, cat.icon, cat.sort = spec.discretionary, spec.sensitive, spec.icon, i
    db.flush()
    merchants = {m.name: m for m in db.scalars(select(Merchant)).all()}
    have = {(a.pattern, a.merchant_id) for a in db.scalars(select(MerchantAlias).where(MerchantAlias.user_id.is_(None))).all()}
    for spec in MERCHANTS:
        merchant = merchants.get(spec.name)
        if merchant is None:
            merchant = Merchant(name=spec.name)
            db.add(merchant)
            merchants[spec.name] = merchant
        merchant.category_id = existing[spec.category].id
        merchant.interest_tags = list(spec.tags)
        db.flush()
        for pattern in {normalize(a) for a in (*spec.aliases, spec.name)}:
            if pattern and (pattern, merchant.id) not in have:
                db.add(MerchantAlias(pattern=pattern, merchant_id=merchant.id, source="seed"))
                have.add((pattern, merchant.id))
    db.flush()
