"""Categorisation cascade: user rules -> curated alias map -> ML classifier -> 'Misc' (flagged for review).

Money coming in is never filed as spending: credits go to Salary, Interest or Other Income, a person sending you
money over UPI is a transfer, and only a refund or cashback from a merchant keeps the merchant's expense category
(so it nets against what you spent there)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ml import categorizer, registry
from app.ml.text import normalize
from app.models import Category, CategoryRule, Merchant, MerchantAlias

ML_THRESHOLD = 0.45
SALARY = re.compile(r"(?i)\b(salary|sal\b|sal cr|payroll|wages|stipend|pay ?out|monthly pay)")
INTEREST = re.compile(r"(?i)\b(interest|int\.? ?pd|int\.? ?cr|int credit|sb int|savings int)")
REFUND = re.compile(r"(?i)\b(refund|refunded|reversal|reversed|cashback|cash back|chargeback)")
DIVIDEND = re.compile(r"(?i)\b(dividend|div\b|redemption|maturity)")


@dataclass
class CatResult:
    category_id: int
    category_name: str
    source: str  # rule | alias | ml
    confidence: float
    merchant_id: int | None
    merchant_name: str


def display_name(text: str | None) -> str:
    text = (text or "").strip()
    if "@" in text and " " not in text:  # bare VPA
        text = text.split("@")[0]
    text = re.sub(r"[*_/]+", " ", text)
    text = re.sub(r"(?i)\s*-\s*(salary|sal|payroll|wages)\b.*$", "", text)  # a NEFT narration: "ACME LTD-SALARY OCT"
    text = re.sub(r"\s+\d{3,}\b", "", text)
    text = re.sub(r"(?i)\b(pvt|ltd|private|limited|india|systems|technologies)\b\.?", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -.")
    return text.title()[:60] or "Unknown"


class Categorizer:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        cats = db.scalars(select(Category).where(or_(Category.user_id.is_(None), Category.user_id == user_id))).all()
        self.by_name = {c.name: c for c in cats}
        self.by_id = {c.id: c for c in cats}
        self.rules = db.scalars(
            select(CategoryRule).where(CategoryRule.user_id == user_id).order_by(CategoryRule.priority, CategoryRule.id)
        ).all()
        rows = db.execute(
            select(MerchantAlias.pattern, MerchantAlias.user_id, Merchant.id, Merchant.name, Merchant.category_id)
            .join(Merchant, Merchant.id == MerchantAlias.merchant_id)
            .where(or_(MerchantAlias.user_id.is_(None), MerchantAlias.user_id == user_id))
        ).all()
        # user aliases first, then longest pattern first ('swiggy instamart' beats 'swiggy')
        self.aliases = sorted(rows, key=lambda r: (r.user_id is None, -len(r.pattern)))
        self._model = None

    @property
    def model(self):  # noqa: ANN201
        if self._model is None:
            self._model = registry.load("categorizer")
        return self._model

    def category(self, name: str) -> Category:
        return self.by_name[name]

    def match_alias(self, text: str):  # noqa: ANN201
        padded = f" {normalize(text)} "
        for row in self.aliases:
            if f" {row.pattern} " in padded:
                return row
        return None

    def categorize(self, *texts: str | None, direction: str | None = None, hint: str | None = None,
                   channel: str | None = None) -> CatResult:
        """`texts` name the counterparty (payee, VPA); `hint` is the whole message, used only to tell kinds of income apart."""
        joined = " ".join(t for t in texts if t)
        norm = normalize(joined)
        alias = self.match_alias(joined)
        if direction == "credit":
            return self._categorize_credit(texts, joined, norm, alias, hint or joined, channel)
        for rule in self.rules:
            value = normalize(rule.value)
            if not value:
                continue
            hit = (value == norm) if rule.op == "equals" else (f" {value} " in f" {norm} ")
            if hit:
                cat = self.by_id[rule.category_id]
                return CatResult(cat.id, cat.name, "rule", 1.0, alias.id if alias else None,
                                 alias.name if alias else display_name(texts[0] if texts else joined))
        if alias and alias.category_id:
            cat = self.by_id[alias.category_id]
            return CatResult(cat.id, cat.name, "alias", 0.97, alias.id, alias.name)
        label, p = categorizer.predict(self.model, [joined])[0]
        name = display_name(next((t for t in texts if t), joined))
        if p >= ML_THRESHOLD and label in self.by_name:
            cat = self.by_name[label]
            return CatResult(cat.id, cat.name, "ml", round(p, 3), None, name)
        misc = self.by_name["Misc"]
        return CatResult(misc.id, misc.name, "ml", round(p, 3), None, name)

    def _named(self, name: str, texts: tuple, joined: str, alias, source: str = "system", confidence: float = 0.9) -> CatResult:  # noqa: ANN001
        cat = self.by_name[name]
        merchant = alias.name if alias else display_name(next((t for t in texts if t), joined))
        return CatResult(cat.id, cat.name, source, confidence, alias.id if alias else None, merchant)

    def _categorize_credit(self, texts: tuple, joined: str, norm: str, alias, hint: str, channel: str | None) -> CatResult:  # noqa: ANN001
        for rule in self.rules:  # the user's own rules still win
            value = normalize(rule.value)
            if value and ((value == norm) if rule.op == "equals" else (f" {value} " in f" {norm} ")):
                cat = self.by_id[rule.category_id]
                return CatResult(cat.id, cat.name, "rule", 1.0, alias.id if alias else None,
                                 alias.name if alias else display_name(texts[0] if texts else joined))
        alias_cat = self.by_id.get(alias.category_id) if alias and alias.category_id else None
        if alias_cat is not None and alias_cat.kind == "income":
            return CatResult(alias_cat.id, alias_cat.name, "alias", 0.97, alias.id, alias.name)
        if SALARY.search(hint):
            return self._named("Salary", texts, joined, alias)
        if INTEREST.search(hint):
            return self._named("Interest", texts, joined, alias)
        if DIVIDEND.search(hint) or (alias_cat is not None and alias_cat.name == "Investments"):
            return self._named("Other Income", texts, joined, alias)
        if alias_cat is not None and alias_cat.kind == "expense":
            # merchants send money back only as refunds or cashback: it nets against what was spent there
            return CatResult(alias_cat.id, alias_cat.name, "alias", 0.9, alias.id, alias.name)
        if REFUND.search(hint):
            return self._named("Other Income", texts, joined, alias)
        if (channel == "upi" or "upi" in hint.lower()) and alias is None:
            return self._named("Transfers", texts, joined, alias, confidence=0.75)  # money from a person
        return self._named("Other Income", texts, joined, alias, confidence=0.7)

    def merchant_for(self, text: str) -> tuple[int | None, str | None]:
        alias = self.match_alias(text)
        return (alias.id, alias.name) if alias else (None, None)
