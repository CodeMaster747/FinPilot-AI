"""Message kind = ML prediction, then safety rules that the model can never override."""

from __future__ import annotations

import re

from app.ml import message_classifier, registry
from app.services.ingestion.types import RawMessage

OTP = re.compile(r"(?i)\b(otp|one[- ]time password|verification code)\b")
MOVES_MONEY = re.compile(r"(?i)\b(debited|credited|deposited|withdrawn)\b")


def classify(msgs: list[RawMessage]) -> list[tuple[str, float]]:
    if not msgs:
        return []
    preds = message_classifier.predict(registry.load("message_classifier"), msgs)
    out = []
    for msg, (kind, p) in zip(msgs, preds):
        text = f"{msg.subject or ''} {msg.body}"
        # An OTP is never a transaction, whatever the model thinks: it only *announces* a payment.
        if OTP.search(text) and not MOVES_MONEY.search(text):
            kind, p = "otp", max(p, 0.99)
        out.append((kind, round(p, 3)))
    return out
