"""Decides what is never read: personal chats, promotional SMS headers, non-financial senders.
Messages rejected here are not stored anywhere (data minimisation)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.ingestion.senders import sender_allowed
from app.services.ingestion.types import RawMessage

DLT = re.compile(r"^(?:[A-Z]{2}-)?([A-Z0-9]{6})(?:-([PSTG]))?$")
PHONE = re.compile(r"^\+?\d[\d\s-]{6,}$")
FINANCIAL = re.compile(
    r"(?i)(rs\.?\s?\d|inr\s?\d|₹\s?\d|\bdebited\b|\bcredited\b|\bspent\b|\bupi\b|\ba/c\b|\bbill\b|\bpayment\b|\brefund|"
    r"\botp\b|\bstatement\b|\bbalance\b|\border\b|\breceipt\b|\binvoice\b|\bemi\b|\bpremium\b|\bsip\b|\bsubscription\b|"
    r"\btrial\b|\brenew|\bbooked\b|\bclass\b|\bsession\b|\bworkout\b|\bfare\b|\bbooking\b)"
)


def email_address(sender: str) -> str:
    """'Swiggy <noreply@swiggy.in>' -> 'noreply@swiggy.in'."""
    m = re.search(r"<([^>]+)>", sender or "")
    return (m.group(1) if m else (sender or "")).strip().lower()


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
    if not sender_allowed(email_address(msg.sender), tuple(extra_domains)):
        return Decision(False, "Sender is not on the financial allowlist — never read")
    if not FINANCIAL.search(f"{msg.subject or ''} {msg.body or ''}"):
        return Decision(False, "No financial content")
    return Decision(True)
