"""Facts the user tells us during onboarding (take-home pay, payday, rent and landlord) and how they are applied."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.text import normalize
from app.models import Category, CategoryRule, Transaction, User

RENT_RULE_PRIORITY = 5  # rules created from the profile; user rules from Review use 10


def _rent_category(db: Session) -> Category:
    return db.scalar(select(Category).where(Category.user_id.is_(None), Category.name == "Rent"))


def apply_rent_rule(db: Session, user: User, payee: str | None) -> int:
    """Payments to the landlord (name or UPI ID) are Rent — now and for every past and future payment."""
    rent = _rent_category(db)
    for old in db.scalars(select(CategoryRule).where(CategoryRule.user_id == user.id, CategoryRule.category_id == rent.id,
                                                    CategoryRule.priority == RENT_RULE_PRIORITY)).all():
        db.delete(old)
    if not payee or not normalize(payee):
        return 0
    value = payee.lower().strip()
    db.add(CategoryRule(user_id=user.id, match_field="merchant", op="contains", value=value, category_id=rent.id,
                        priority=RENT_RULE_PRIORITY))
    needle = f" {normalize(value)} "
    updated = 0
    for t in db.scalars(select(Transaction).where(Transaction.user_id == user.id, Transaction.direction == "debit",
                                                  Transaction.is_transfer.is_(False))).all():
        text = f" {normalize(' '.join(filter(None, [t.merchant_name, t.counterparty, t.description])))} "
        if needle in text:
            t.category_id, t.category_source, t.category_confidence, t.needs_review = rent.id, "rule", 1.0, False
            updated += 1
    db.flush()
    return updated
