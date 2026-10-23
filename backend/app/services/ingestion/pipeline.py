"""The capture pipeline: pre-filter -> classify -> extract -> reconcile -> categorise -> side outputs.

One purchase can be announced several times (bank SMS, bank email, merchant receipt). Bank alerts own
the transaction; a second alert for the same payment on another channel is linked as a duplicate;
receipts and order emails *enrich* the transaction with line items instead of creating a new one.
Own-account transfers and card bill payments are paired and excluded from spending.
"""

from __future__ import annotations

import re
import threading
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_text
from app.core.money import D, fmt_inr
from app.db.base import utcnow
from app.ml.text import normalize
from app.models import (
    Account,
    BalanceSnapshot,
    DataSource,
    IngestedMessage,
    Transaction,
    TransactionItem,
    UpcomingPayment,
    User,
)
from app.services.accounts import resolve_account, set_balance
from app.services.categorization import Categorizer
from app.services.ingestion.classify import classify
from app.services.ingestion.extract import Extraction, extract, sender_name
from app.services.ingestion.prefilter import prefilter
from app.services.ingestion.types import RawMessage

LOW_CONFIDENCE = 0.6
NOT_STORED = ("otp", "promo", "other")
AUTOPAY = re.compile(r"(?i)\b(autopay|auto[- ]pay|mandate|e-?mandate|standing instruction|auto[- ]?debit|recurring payment|"
                     r"si (?:txn|transaction))\b")
AUTOPAY_NOTE = "Auto-debit (UPI AutoPay / mandate)"


def keeps(kind: str, p: float, ex: Extraction) -> bool:
    """Whether a classified message is stored. OTPs, promotions and "other" are not — except that a message with an
    amount, a direction and an account/card/UPI marker is never thrown away unread: if the model thinks it's a
    promotion or "other", a person decides (Review). OTPs are never stored, whatever they look like."""
    if kind not in NOT_STORED:
        return True
    looks_like_money = bool(ex.get("amount") and ex.get("direction"))
    names_account = bool(ex.get("mask") or ex.get("ref") or ex.get("vpa"))
    return kind != "otp" and looks_like_money and (p < LOW_CONFIDENCE or names_account)


@dataclass
class Outcome:
    status: str  # created | duplicate | enriched | transfer | reversed | informational | ignored | dropped | review | pending
    detail: str
    kind: str | None = None
    confidence: float | None = None
    transaction_id: int | None = None
    message_id: int | None = None
    fields: dict[str, Any] | None = None


@dataclass
class IngestReport:
    total: int = 0
    counts: Counter = field(default_factory=Counter)
    outcomes: list[Outcome] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"total": self.total, "counts": dict(self.counts)}


def _when(ex: Extraction, received: datetime) -> tuple[date, datetime]:
    d = date.fromisoformat(ex.get("date")) if ex.get("date") else received.date()
    t = ex.get("time")
    if t:
        try:
            parts = [int(x) for x in t.split(":")]
            return d, datetime.combine(d, time(*parts[:3]))
        except ValueError:
            pass
    if d == received.date():
        return d, received
    return d, datetime.combine(d, time(12, 0))


class Pipeline:
    def __init__(self, db: Session, user: User, source: DataSource, feed: str, finalize_pending: bool = True):
        self.db = db
        self.user = user
        self.source = source
        self.feed = feed
        self.finalize_pending = finalize_pending
        self.cat = Categorizer(db, user.id)
        self.report = IngestReport()
        self.own_accounts: dict[str, Account] = {}
        self._load_accounts()
        name_tokens = [t for t in normalize(user.name).split() if len(t) > 2]
        self.user_tokens = set(name_tokens)
        self.extra_domains = tuple((user.preferences or {}).get("extra_email_domains") or ())

    def _load_accounts(self) -> None:
        for acct in self.db.scalars(select(Account).where(Account.user_id == self.user.id)).all():
            if acct.mask:
                self.own_accounts[acct.mask] = acct

    # -- entry point -----------------------------------------------------------------------------
    def run(self, messages: list[RawMessage], progress=None) -> IngestReport:  # noqa: ANN001
        msgs = sorted(messages, key=lambda m: m.received_at)
        self.report.total = len(msgs)
        kept: list[RawMessage] = []
        for m in msgs:
            decision = prefilter(m, self.extra_domains)
            if decision.keep:
                kept.append(m)
            else:
                self.report.counts["dropped"] += 1
                self.report.outcomes.append(Outcome("dropped", decision.reason or "Not financial"))
        ids = [m.external_id for m in kept]
        seen: set[str] = set()
        for i in range(0, len(ids), 500):
            seen.update(self.db.scalars(select(IngestedMessage.external_id).where(
                IngestedMessage.data_source_id == self.source.id, IngestedMessage.external_id.in_(ids[i:i + 500]))).all())
        fresh = []
        for m in kept:
            if m.external_id in seen:
                self.report.counts["already_imported"] += 1
                self.report.outcomes.append(Outcome("duplicate", "Already imported earlier"))
            else:
                seen.add(m.external_id)
                fresh.append(m)
        kinds = classify(fresh)
        for i, (m, (kind, p)) in enumerate(zip(fresh, kinds)):
            outcome = self.process(m, kind, p)
            self.report.counts[outcome.status] += 1
            self.report.outcomes.append(outcome)
            if i and i % 250 == 0:
                self.db.commit()  # keep SQLite's single write lock short during big imports
            if progress and i % 100 == 0:
                progress(i / max(1, len(fresh)))
        self.finish()
        self.source.last_ingest_at = utcnow()
        self.db.flush()
        return self.report

    # -- per message -----------------------------------------------------------------------------
    def process(self, m: RawMessage, kind: str, p: float) -> Outcome:
        ex = extract(m, kind)
        if not keeps(kind, p, ex):
            label = {"otp": "One-time password", "promo": "Promotional message", "other": "Not a financial record"}[kind]
            return Outcome("ignored", f"{label} — not stored", kind, p, fields=ex.to_json())
        row = IngestedMessage(
            user_id=self.user.id, data_source_id=self.source.id, channel=m.channel, feed=self.feed,
            external_id=m.external_id, sender=m.sender[:160], received_at=m.received_at, subject=(m.subject or None),
            body_enc=encrypt_text(m.body), kind=kind, kind_confidence=p, parser=ex.parser, fields=ex.to_json(),
            status="informational",
        )
        self.db.add(row)
        self.db.flush()
        if kind in NOT_STORED or (p < LOW_CONFIDENCE and kind in ("transaction", "refund")):
            row.status = "needs_review"
            row.review_note = f"Unsure what this message is (looks like '{kind}', {p:.0%} confident). Please confirm."
            return Outcome("review", row.review_note, kind, p, message_id=row.id, fields=ex.to_json())
        handler = {
            "transaction": self.on_transaction, "refund": self.on_refund, "failed_or_reversed": self.on_failed,
            "balance": self.on_balance, "bill_due": self.on_due, "statement": self.on_due, "order_receipt": self.on_receipt,
        }.get(kind)
        if handler is None:  # subscription_notice, usage: evidence for the subscriptions module
            return Outcome("informational", "Saved as subscription evidence", kind, p, message_id=row.id, fields=ex.to_json())
        outcome = handler(row, m, ex)
        outcome.kind, outcome.confidence, outcome.message_id, outcome.fields = kind, p, row.id, ex.to_json()
        return outcome

    # -- transactions ----------------------------------------------------------------------------
    def on_transaction(self, row: IngestedMessage, m: RawMessage, ex: Extraction) -> Outcome:
        amount, direction = ex.get("amount"), ex.get("direction")
        if not amount or not direction:
            row.status = "needs_review"
            row.review_note = "Couldn't read the amount or whether money came in or went out."
            return Outcome("review", row.review_note)
        amount = D(amount)
        acct = resolve_account(self.db, self.user.id, ex.get("mask"), ex.institution, ex.account_kind)
        if acct and acct.mask:
            self.own_accounts[acct.mask] = acct
        txn_date, occurred = _when(ex, m.received_at)
        ref, payee, vpa = ex.get("ref"), ex.get("payee"), ex.get("vpa")

        same = self.find_same(acct, amount, direction, txn_date, occurred, ref, payee or vpa or "", m.channel)
        if same is not None:
            txn, score = same
            row.transaction_id, row.status, row.match_role, row.match_score = txn.id, "linked", "duplicate", score
            if txn.account_id is None and acct:
                txn.account_id = acct.id
            if not txn.ref_no and ref:
                txn.ref_no = ref
            self._snapshot(acct, ex, occurred, row)
            return Outcome("duplicate", f"Same payment already recorded from {txn.origin.upper()} — linked as evidence",
                           transaction_id=txn.id)

        cat = self.cat.categorize(payee, vpa, direction=direction, hint=m.body, channel=ex.channel)
        needs_review = cat.category_name == "Misc" or min(ex.conf("amount"), ex.conf("direction")) < 0.8
        txn = Transaction(
            user_id=self.user.id, account_id=acct.id if acct else None, txn_date=txn_date, occurred_at=occurred,
            amount=amount, direction=direction, description=(payee or vpa or "Unknown")[:255],
            merchant_id=cat.merchant_id, merchant_name=cat.merchant_name, counterparty=vpa, category_id=cat.category_id,
            category_source=cat.source, category_confidence=cat.confidence, origin=m.channel, ref_no=ref,
            needs_review=needs_review,
        )
        if direction == "debit" and AUTOPAY.search(m.body):
            txn.notes = AUTOPAY_NOTE  # subscriptions are often paid this way, whatever the merchant's category
        self.db.add(txn)
        self.db.flush()
        row.transaction_id, row.status, row.match_role, row.match_score = txn.id, "linked", "primary", 1.0
        self._snapshot(acct, ex, occurred, row)
        paired = self.pair_transfer(txn, ex, m)
        enriched = self.retry_pending(txn)
        self.mark_paid(txn)
        if paired:
            return Outcome("transfer", f"Recorded as a {paired} — not counted as spending", transaction_id=txn.id)
        detail = f"{'Paid' if direction == 'debit' else 'Received'} {fmt_inr(amount, True)} · {cat.merchant_name} · {cat.category_name}"
        if enriched:
            detail += " · matched a receipt"
        return Outcome("created", detail, transaction_id=txn.id)

    def find_same(self, acct: Account | None, amount: Decimal, direction: str, txn_date: date, occurred: datetime,
                  ref: str | None, payee: str, channel: str) -> tuple[Transaction, float] | None:
        q = select(Transaction).where(
            Transaction.user_id == self.user.id, Transaction.amount == amount, Transaction.direction == direction,
            Transaction.txn_date >= txn_date - timedelta(days=1), Transaction.txn_date <= txn_date + timedelta(days=1))
        best = None
        for c in self.db.scalars(q).all():
            if acct and c.account_id and c.account_id != acct.id:
                continue
            if ref and c.ref_no:
                if ref == c.ref_no:
                    return c, 1.0
                continue  # distinct references => distinct payments (e.g. a genuine double charge)
            # banks send one alert per payment per channel: two SMS can never be the same payment
            same_channel = self.db.scalar(select(IngestedMessage.id).where(
                IngestedMessage.transaction_id == c.id, IngestedMessage.channel == channel,
                IngestedMessage.match_role.in_(("primary", "duplicate"))).limit(1))
            if same_channel is not None:
                continue
            minutes = abs((c.occurred_at - occurred).total_seconds()) / 60 if c.occurred_at else 999
            time_score = 1.0 if minutes <= 15 else 0.6 if minutes <= 180 else 0.2
            name_score = fuzz.token_set_ratio(normalize(payee), normalize(f"{c.description} {c.merchant_name}")) / 100
            score = 0.55 * time_score + 0.45 * name_score
            if score >= 0.6 and (best is None or score > best[1]):
                best = (c, round(score, 2))
        return best

    def _snapshot(self, acct: Account | None, ex: Extraction, as_of: datetime, row: IngestedMessage) -> None:
        if acct and acct.kind != "credit_card" and ex.get("balance"):
            self.db.add(BalanceSnapshot(user_id=self.user.id, account_id=acct.id, balance=D(ex.get("balance")),
                                        as_of=as_of, message_id=row.id, source="alert"))

    def _transfer_signal(self, txn: Transaction, text: str, acct: Account | None, channel: str | None) -> str | None:
        """'card' for card bill payments, 'self' for own-account transfers, 'maybe' for account-to-account moves."""
        own_masks = {k for k, a in self.own_accounts.items() if not acct or a.id != acct.id}
        squashed = text.replace(" ", "")
        mentions_own = any(f" {mk} " in f" {text} " or f"xx{mk}" in squashed for mk in own_masks)
        if (txn.direction == "debit" and "credit card" in text) or channel == "card_payment" or (
                acct is not None and acct.kind == "credit_card" and txn.direction == "credit" and "payment" in text and "received" in text):
            return "card"
        if txn.direction == "debit" and mentions_own:
            return "self"
        if txn.direction == "credit" and self.user_tokens and self.user_tokens <= set(text.split()):
            return "self"
        if channel in ("imps", "neft") and ("a c" in text or "xx" in text):
            return "maybe"
        return None

    def pair_transfer(self, txn: Transaction, ex: Extraction, m: RawMessage) -> str | None:
        acct = self.db.get(Account, txn.account_id) if txn.account_id else None
        signal = self._transfer_signal(txn, normalize(f"{txn.description} {m.body[:300]}"), acct, ex.channel)
        if signal is None:
            return None
        # the other leg: same amount, opposite direction, another account, within two days, not already paired
        partner = None
        cands = self.db.scalars(select(Transaction).where(
            Transaction.user_id == self.user.id, Transaction.id != txn.id, Transaction.amount == txn.amount,
            Transaction.direction != txn.direction, Transaction.status == "posted",
            Transaction.txn_date >= txn.txn_date - timedelta(days=2), Transaction.txn_date <= txn.txn_date + timedelta(days=2))).all()
        cands.sort(key=lambda c: abs(((c.occurred_at or datetime.combine(c.txn_date, time(12))) - (txn.occurred_at or datetime.combine(txn.txn_date, time(12)))).total_seconds()))
        for c in cands:
            if acct is not None and c.account_id == acct.id:
                continue
            if c.transfer_group is not None and self.db.scalar(select(Transaction.id).where(
                    Transaction.transfer_group == c.transfer_group, Transaction.id != c.id).limit(1)) is not None:
                continue
            c_acct = self.db.get(Account, c.account_id) if c.account_id else None
            c_signal = c.is_transfer or self._transfer_signal(c, normalize(c.description), c_acct, None)
            if signal in ("card", "self") or c_signal:
                partner = c
                break
        if partner is None and signal == "maybe":
            return None
        card = signal == "card" or (partner is not None and (
            (acct is not None and acct.kind == "credit_card")
            or (partner.account_id and self.db.get(Account, partner.account_id).kind == "credit_card")))
        cat = self.cat.category("Credit Card Payment" if card else "Transfers")
        group = (partner.transfer_group if partner is not None and partner.transfer_group else None) or uuid.uuid4().hex[:12]
        for t in [txn] + ([partner] if partner is not None else []):
            t.is_transfer, t.transfer_group = True, group
            t.category_id, t.category_source, t.category_confidence, t.needs_review = cat.id, "system", 1.0, False
            t.merchant_name = "Card bill payment" if card else "Own account transfer"
        return "card bill payment" if card else "transfer between your own accounts"

    # -- refunds, failures, balances, dues ------------------------------------------------------
    def on_refund(self, row: IngestedMessage, m: RawMessage, ex: Extraction) -> Outcome:
        amount = ex.get("amount")
        if not amount:
            row.status, row.review_note = "needs_review", "Refund message without a readable amount."
            return Outcome("review", row.review_note)
        if m.channel == "email" and ex.institution is None:
            # a merchant's refund notice (not the bank's) announces a credit that arrives later: wait, then enrich
            return self.on_receipt(row, m, ex, refund=True)
        ex.set("direction", "credit", 0.95)
        earlier = self._refund_recorded_from_email(D(amount), _when(ex, m.received_at)[0], m.channel)
        if earlier is not None:  # the user already recorded this refund from the merchant's email (Review → create)
            row.transaction_id, row.status, row.match_role, row.match_score = earlier.id, "linked", "duplicate", 0.8
            return Outcome("duplicate", f"Refund {fmt_inr(earlier.amount, True)} was already recorded from the merchant's email — "
                                        "linked as evidence", transaction_id=earlier.id)
        outcome = self.on_transaction(row, m, ex)
        if outcome.transaction_id:
            txn = self.db.get(Transaction, outcome.transaction_id)
            orig = None
            if ex.get("refund_of_ref"):  # "refund of UPI/6275…": the bank names the payment being refunded
                orig = self.db.scalar(select(Transaction).where(
                    Transaction.user_id == self.user.id, Transaction.direction == "debit", Transaction.ref_no == ex.get("refund_of_ref")))
                if orig is not None:
                    txn.merchant_id, txn.merchant_name, txn.description = orig.merchant_id, orig.merchant_name, f"Refund — {orig.merchant_name}"
            if orig is None:
                orig = self.db.scalar(select(Transaction).where(
                    Transaction.user_id == self.user.id, Transaction.direction == "debit", Transaction.merchant_name == txn.merchant_name,
                    Transaction.amount >= txn.amount, Transaction.txn_date >= txn.txn_date - timedelta(days=60),
                    Transaction.txn_date <= txn.txn_date).order_by(Transaction.txn_date.desc()).limit(1))
            if orig:
                txn.notes = f"Refund for {orig.merchant_name} purchase on {orig.txn_date:%d %b %Y}"
                txn.category_id, txn.category_source = orig.category_id, "system"
            outcome.detail = f"Refund {fmt_inr(txn.amount, True)} from {txn.merchant_name} — nets against spending"
        return outcome

    def _refund_recorded_from_email(self, amount: Decimal, day: date, channel: str) -> Transaction | None:
        """A credit created from a refund email, with no bank alert attached yet, within 10 days."""
        if channel != "sms":
            return None
        for t in self.db.scalars(select(Transaction).where(
                Transaction.user_id == self.user.id, Transaction.direction == "credit", Transaction.amount == amount,
                Transaction.origin == "email", Transaction.txn_date >= day - timedelta(days=10),
                Transaction.txn_date <= day + timedelta(days=10))).all():
            has_sms = self.db.scalar(select(IngestedMessage.id).where(IngestedMessage.transaction_id == t.id,
                                                                      IngestedMessage.channel == "sms").limit(1))
            if has_sms is None:
                return t
        return None

    def on_failed(self, row: IngestedMessage, m: RawMessage, ex: Extraction) -> Outcome:
        low = m.body.lower()
        if "revers" in low and ("ref" in low or ex.get("ref")):
            ref, amount = ex.get("ref"), ex.get("amount")
            q = select(Transaction).where(Transaction.user_id == self.user.id, Transaction.direction == "debit")
            orig = self.db.scalar(q.where(Transaction.ref_no == ref)) if ref else None
            if orig is None and amount:
                orig = self.db.scalar(q.where(Transaction.amount == D(amount),
                                              Transaction.txn_date >= m.received_at.date() - timedelta(days=7)).order_by(Transaction.id.desc()))
            if orig:
                orig.status = "reversed"
                row.transaction_id, row.status, row.match_role = orig.id, "linked", "reversal"
                return Outcome("reversed", f"{fmt_inr(orig.amount, True)} to {orig.merchant_name} was reversed — excluded from spending",
                               transaction_id=orig.id)
        row.ignore_reason = "Payment failed — no money moved"
        return Outcome("informational", row.ignore_reason)

    def on_balance(self, row: IngestedMessage, m: RawMessage, ex: Extraction) -> Outcome:
        acct = resolve_account(self.db, self.user.id, ex.get("mask"), ex.institution, ex.account_kind or "savings")
        if acct and ex.get("balance") and acct.kind != "credit_card":
            self.db.add(BalanceSnapshot(user_id=self.user.id, account_id=acct.id, balance=D(ex.get("balance")),
                                        as_of=m.received_at, message_id=row.id, source="alert"))
            return Outcome("informational", f"Balance of {acct.name}: {fmt_inr(D(ex.get('balance')), True)}")
        return Outcome("informational", "Balance alert noted")

    def on_due(self, row: IngestedMessage, m: RawMessage, ex: Extraction) -> Outcome:
        amount = ex.get("amount") or ex.get("total")
        due = ex.get("due_date")
        payee = ex.get("payee") or ex.get("merchant") or "Bill"
        if not amount or not due:
            row.review_note = "Bill reminder without a readable amount or due date."
            return Outcome("informational", row.review_note)
        amount, due_d = D(amount), date.fromisoformat(due)
        kind = "card_due" if row.kind == "statement" else "bill"
        if kind == "card_due" and ex.get("mask"):
            card = resolve_account(self.db, self.user.id, ex.get("mask"), ex.institution, "credit_card")
            if card is not None and card.kind == "credit_card":
                set_balance(self.db, self.user.id, card, D(ex.get("total") or amount), m.received_at, "statement", row.id)
        existing = self.db.scalar(select(UpcomingPayment).where(
            UpcomingPayment.user_id == self.user.id, UpcomingPayment.due_date == due_d, UpcomingPayment.amount == amount))
        if existing is None:
            self.db.add(UpcomingPayment(user_id=self.user.id, payee=payee[:120], kind=kind, amount=amount, due_date=due_d,
                                        message_id=row.id))
            self.db.flush()
            self._match_due_to_payment(amount, due_d, payee)
        return Outcome("informational", f"{'Card bill' if kind == 'card_due' else 'Bill'} due: {payee} {fmt_inr(amount, True)} on {due_d:%d %b}")

    def _match_due_to_payment(self, amount: Decimal, due: date, payee: str) -> None:
        up = self.db.scalar(select(UpcomingPayment).where(UpcomingPayment.user_id == self.user.id, UpcomingPayment.amount == amount,
                                                           UpcomingPayment.due_date == due))
        if up is None:
            return
        txn = self.db.scalar(select(Transaction).where(
            Transaction.user_id == self.user.id, Transaction.direction == "debit", Transaction.amount == amount,
            Transaction.txn_date >= due - timedelta(days=25), Transaction.txn_date <= due + timedelta(days=3)).limit(1))
        if txn is not None:
            up.status, up.transaction_id = "paid", txn.id

    def mark_paid(self, txn: Transaction) -> None:
        if txn.direction != "debit":
            return
        for up in self.db.scalars(select(UpcomingPayment).where(
                UpcomingPayment.user_id == self.user.id, UpcomingPayment.status == "upcoming", UpcomingPayment.amount == txn.amount,
                UpcomingPayment.due_date >= txn.txn_date - timedelta(days=3), UpcomingPayment.due_date <= txn.txn_date + timedelta(days=25))).all():
            up.status, up.transaction_id = "paid", txn.id
            break

    # -- receipts (enrichment) -------------------------------------------------------------------
    def on_receipt(self, row: IngestedMessage, m: RawMessage, ex: Extraction, refund: bool = False) -> Outcome:
        if not ex.get("amount"):
            row.review_note = "Receipt without a total amount — kept for reference."
            return Outcome("informational", row.review_note)
        same = None if refund else self.find_same_receipt(row, ex)
        if same is not None:  # the same order's receipt arrived again (e.g. forwarded or re-sent)
            row.transaction_id, row.status, row.match_role, row.match_score = same.id, "linked", "duplicate", 1.0
            return Outcome("duplicate", f"Same receipt (order {ex.get('order_id')}) is already attached to {same.merchant_name} "
                                        f"{fmt_inr(same.amount, True)} — not counted again", transaction_id=same.id)
        target = self.find_receipt_target(row, ex, refund)
        if target is None:
            row.status = "pending"
            return Outcome("pending", "Receipt saved — waiting for the matching bank alert")
        txn, score = target
        if score < 0.7:
            row.status, row.transaction_id, row.match_role, row.match_score = "needs_review", txn.id, "suggested", score
            row.review_note = f"Is this the receipt for {txn.merchant_name} {fmt_inr(txn.amount, True)} on {txn.txn_date:%d %b}?"
            return Outcome("review", row.review_note, transaction_id=txn.id)
        self.enrich(txn, row, ex, score)
        items = len(ex.get("items") or [])
        return Outcome("enriched", f"Added to {txn.merchant_name} {fmt_inr(txn.amount, True)}" + (f" — {items} line items" if items else ""),
                       transaction_id=txn.id)

    def find_same_receipt(self, row: IngestedMessage, ex: Extraction) -> Transaction | None:
        order_id = ex.get("order_id")
        if not order_id:
            return None
        # same kind only: a refund notice shares the order number with its purchase receipt but is a different event
        recent = self.db.scalars(select(IngestedMessage).where(
            IngestedMessage.user_id == self.user.id, IngestedMessage.match_role == "enrichment", IngestedMessage.id != row.id,
            IngestedMessage.kind == row.kind, IngestedMessage.received_at >= row.received_at - timedelta(days=60))).all()
        for other in recent:
            if ((other.fields or {}).get("fields", {}).get("order_id") or {}).get("value") == order_id and other.transaction_id:
                return self.db.get(Transaction, other.transaction_id)
        return None

    def find_receipt_target(self, row: IngestedMessage, ex: Extraction, refund: bool = False) -> tuple[Transaction, float] | None:
        amount = D(ex.get("amount"))
        day = row.received_at.date()
        q = select(Transaction).where(
            Transaction.user_id == self.user.id, Transaction.direction == ("credit" if refund else "debit"),
            Transaction.is_transfer.is_(False), Transaction.txn_date >= day - timedelta(days=4), Transaction.txn_date <= day + timedelta(days=1),
            Transaction.amount >= amount * Decimal("0.99"), Transaction.amount <= amount * Decimal("1.01"))
        names = [n for n in (ex.get("merchant"), ex.get("scheme")) if n]
        best = None
        for txn in self.db.scalars(q).all():
            taken = self.db.scalar(select(IngestedMessage.id).where(
                IngestedMessage.transaction_id == txn.id, IngestedMessage.match_role == "enrichment").limit(1))
            if taken is not None:
                continue
            hay = normalize(f"{txn.merchant_name} {txn.description} {txn.counterparty or ''}")
            name_score = max((fuzz.partial_ratio(normalize(n), hay) / 100 for n in names), default=0.0)
            if name_score < 0.55:
                merchant_id, _ = self.cat.merchant_for(" ".join(names))
                if merchant_id and merchant_id == txn.merchant_id:
                    name_score = 1.0
            amount_score = 1.0 if txn.amount == amount else 0.7
            hours = abs((txn.occurred_at - row.received_at).total_seconds()) / 3600 if txn.occurred_at else 48
            time_score = 1.0 if hours <= 6 else 0.6 if hours <= 48 else 0.3
            score = round(0.45 * amount_score + 0.4 * name_score + 0.15 * time_score, 2)
            if best is None or score > best[1]:
                best = (txn, score)
        if best is None or best[1] < 0.5:
            return None
        return best

    def enrich(self, txn: Transaction, row: IngestedMessage, ex: Extraction, score: float) -> None:
        items = ex.get("items") or []
        if items and not txn.items:
            for it in items[:40]:
                txn.items.append(TransactionItem(description=str(it["description"])[:200], quantity=float(it.get("quantity", 1)),
                                                 amount=D(it["amount"]), source="email"))
        notes = []
        if ex.get("order_id"):
            notes.append(f"Order #{ex.get('order_id')}")
        if ex.get("scheme"):
            notes.append(ex.get("scheme"))
        if ex.get("policy"):
            notes.append(f"Policy {ex.get('policy')}")
        if notes and not txn.notes:
            txn.notes = " · ".join(notes)
        if txn.category_source == "ml" and ex.get("merchant"):
            merchant_id, merchant_name = self.cat.merchant_for(ex.get("merchant"))
            if merchant_id:
                cat = self.cat.categorize(merchant_name)
                txn.merchant_id, txn.merchant_name, txn.category_id, txn.category_source = merchant_id, merchant_name, cat.category_id, "alias"
                txn.needs_review = False
        row.transaction_id, row.status, row.match_role, row.match_score = txn.id, "enriched", "enrichment", score

    def retry_pending(self, txn: Transaction) -> bool:
        pending = self.db.scalars(select(IngestedMessage).where(
            IngestedMessage.user_id == self.user.id, IngestedMessage.status == "pending",
            IngestedMessage.received_at >= datetime.combine(txn.txn_date - timedelta(days=1), time(0)),
            IngestedMessage.received_at <= datetime.combine(txn.txn_date + timedelta(days=4), time(23, 59)))).all()
        for row in pending:
            ex = Extraction(parser=row.parser or "", fields=(row.fields or {}).get("fields", {}))
            target = self.find_receipt_target(row, ex, refund=row.kind == "refund")
            if target and target[0].id == txn.id and target[1] >= 0.7:
                self.enrich(txn, row, ex, target[1])
                return True
        return False

    def finish(self) -> None:
        """After a batch: retry receipts still waiting; receipts with no bank alert after 3 days (or after a
        complete historical import) become transactions themselves (e.g. paid by cash or an unconnected card)."""
        cutoff = utcnow() - timedelta(days=3)
        pending = self.db.scalars(select(IngestedMessage).where(
            IngestedMessage.user_id == self.user.id, IngestedMessage.status == "pending")).all()
        for row in pending:
            ex = Extraction(parser=row.parser or "", fields=(row.fields or {}).get("fields", {}))
            target = self.find_receipt_target(row, ex, refund=row.kind == "refund")
            if target and target[1] >= 0.7:
                self.enrich(target[0], row, ex, target[1])
                continue
            if not self.finalize_pending and row.received_at > cutoff:
                continue
            cat = self.cat.categorize(ex.get("merchant"))
            txn = Transaction(
                user_id=self.user.id, account_id=None, txn_date=row.received_at.date(), occurred_at=row.received_at,
                amount=D(ex.get("amount")), direction="credit" if row.kind == "refund" else "debit",
                description=f"{ex.get('merchant') or 'Receipt'} (from receipt)", merchant_id=cat.merchant_id,
                merchant_name=cat.merchant_name, category_id=cat.category_id, category_source=cat.source,
                category_confidence=cat.confidence, origin=row.channel, needs_review=True,
                notes="Created from a receipt — no matching bank alert was found")
            self.db.add(txn)
            self.db.flush()
            for it in (ex.get("items") or [])[:40]:
                txn.items.append(TransactionItem(description=str(it["description"])[:200], quantity=float(it.get("quantity", 1)),
                                                 amount=D(it["amount"]), source="email"))
            row.transaction_id, row.status, row.match_role = txn.id, "linked", "primary"
            self.report.counts["created_from_receipt"] += 1


_LOCKS: dict[int, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def user_lock(user_id: int) -> threading.RLock:
    """One ingestion at a time per user: the phone's SMS sync, a mailbox sync and a file import never interleave
    (each checks what is already stored before adding, which only works if they take turns)."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(user_id, threading.RLock())


def ingest(db: Session, user: User, source: DataSource, messages: list[RawMessage], feed: str,
           finalize_pending: bool = True, progress=None) -> IngestReport:  # noqa: ANN001
    """`finalize_pending`: True for one-off historical imports (a receipt with no bank alert by the end of the import
    becomes its own transaction). Continuous feeds (phone SMS, mailbox sync) pass False, so a receipt that arrives
    before its bank SMS waits up to 3 days for it instead of being counted twice."""
    with user_lock(user.id):
        report = Pipeline(db, user, source, feed, finalize_pending).run(messages, progress)
        db.commit()  # visible to the next ingestion before the lock is released
        return report


def finalize_stale_receipts(db: Session, user: User) -> int:
    """Nightly: receipts that waited more than 3 days without a matching bank alert become transactions."""
    source = db.scalar(select(DataSource).where(DataSource.user_id == user.id, DataSource.kind == "email"))
    if source is None:
        return 0
    with user_lock(user.id):
        pipe = Pipeline(db, user, source, "nightly", finalize_pending=False)
        pipe.finish()
        db.commit()
        return pipe.report.counts.get("created_from_receipt", 0)


def sender_display(sender: str) -> str:
    name, _ = sender_name(sender)
    return name
