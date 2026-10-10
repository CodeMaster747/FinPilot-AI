"""Decides what is never read: personal chats, promotional SMS headers, non-financial senders.
Messages rejected here are not stored anywhere (data minimisation)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.seed.reference import EMAIL_ALLOWLIST_DOMAINS
from app.services.ingestion.extract import sender_name
from app.services.ingestion.types import RawMessage

DLT = re.compile(r"^[A-Z]{2}-([A-Z0-9]{6})(?:-([PSTG]))?$")
PHONE = re.compile(r"^\+?\d[\d\s-]{6,}$")
FINANCIAL = re.compile(
    r"(?i)(rs\.?\s?\d|inr\s?\d|₹\s?\d|\bdebited\b|\bcredited\b|\bspent\b|\bupi\b|\ba/c\b|\bbill\b|\bpayment\b|\brefund|"
    r"\botp\b|\bstatement\b|\bbalance\b|\border\b|\breceipt\b|\binvoice\b|\bemi\b|\bpremium\b|\bsip\b|\bsubscription\b|"
    r"\btrial\b|\brenew|\bbooked\b|\bclass\b|\bsession\b|\bworkout\b|\bfare\b|\bbooking\b)"
)


@dataclass
class Decision:
    keep: bool
    reason: str | None = None


def prefilter(msg: RawMessage, extra_domains: tuple[str, ...] = ()) -> Decision:
    if msg.channel == "sms":
        sender = (msg.sender or "").strip()
        if PHONE.match(sender):
            return Decision(False, "Personal number — never read")
        m = DLT.match(sender.upper())
        if m and m.group(2) == "P":
            return Decision(False, "Promotional sender (-P header) — dropped unread")
        if not FINANCIAL.search(msg.body or ""):
            return Decision(False, "No financial content")
        return Decision(True)
    _, domain = sender_name(msg.sender)
    allowed = EMAIL_ALLOWLIST_DOMAINS + tuple(extra_domains)
    if not any(domain == d or domain.endswith("." + d) for d in allowed):
        return Decision(False, "Sender is not on the financial allowlist — never read")
    if not FINANCIAL.search(f"{msg.subject or ''} {msg.body or ''}"):
        return Decision(False, "No financial content")
    return Decision(True)
