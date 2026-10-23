from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Message kinds the classifier predicts.
KINDS = (
    "transaction",  # bank/card alert that moves money
    "refund",  # money coming back for a purchase
    "failed_or_reversed",  # failed payment / reversal of an earlier debit
    "otp",
    "promo",
    "bill_due",
    "statement",  # credit card statement
    "order_receipt",  # merchant receipt / order / payment confirmation (enriches a transaction)
    "subscription_notice",  # price change, trial ending, renewal notice
    "usage",  # usage signal for a subscription (e.g. class booked)
    "balance",  # balance-only alert
    "other",
)


def sms_external_id(sender: str, epoch_ms: int | None, body: str) -> str:
    """One identity per SMS whichever way it reaches FinPilot (the phone app, a backup file, pasted text):
    sender + the phone's own timestamp + text. Without a timestamp (pasted text), sender + text."""
    stamp = str(int(epoch_ms)) if epoch_ms is not None else "-"
    key = f"{(sender or '').strip().upper()}|{stamp}|{body or ''}"
    return "sms:" + hashlib.sha1(key.encode("utf-8")).hexdigest()


@dataclass
class RawMessage:
    channel: str  # sms | email
    sender: str
    received_at: datetime  # local wall-clock time
    body: str  # plain text (emails: text rendering of the HTML part)
    subject: str | None = None
    html: str | None = None
    external_id: str = ""
    truth: dict[str, Any] | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.external_id:
            key = f"{self.channel}|{self.sender}|{self.received_at.isoformat()}|{self.subject or ''}|{self.body}"
            self.external_id = hashlib.sha1(key.encode("utf-8")).hexdigest()
