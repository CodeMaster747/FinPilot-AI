"""Message kind = ML prediction, then safety rules that the model can never override."""

from __future__ import annotations

import re

from app.ml import message_classifier, registry
from app.services.ingestion.types import RawMessage

OTP = re.compile(r"(?i)\b(otp|one[- ]time password|verification code)\b")
# Completed money movements. Real alerts often end with "Never share your OTP"; those must not be mistaken for an
# OTP. An OTP itself only announces a payment ("OTP to pay Rs 500", "for txn of INR 2,000").
MOVES_MONEY = re.compile(r"(?i)\b(debited|credited|deposited|withdrawn|spent|sent|paid|received|transferred)\b")


AMOUNT = re.compile(r"(?i)(?:rs\.?|inr|₹)\s?[:.]?\s?\d")
REFUND = re.compile(r"(?i)\b(refund|refunded|cashback|cash back)\b")
CREDIT_VERB = re.compile(r"(?i)\b(credited|received|deposited)\b")
FAILED = re.compile(r"(?i)\b(failed|declined|could not be (?:completed|processed)|unsuccessful)\b")
# a completed movement on the user's account, in the past tense ("Rs 60 paid to…", "Debited INR…")
MOVED = re.compile(r"(?i)\b(debited|credited|spent|paid|sent|received|withdrawn|transferred|deducted|deposited)\b")


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
        elif msg.channel == "sms" and kind in ("balance", "other") and AMOUNT.search(text) and MOVED.search(text) \
                and not FAILED.search(text):
            # bank alerts that also quote a balance ("Rs 60 paid to … Balance: Rs 1,230") are transactions first
            kind, p = "transaction", max(p, 0.6)
        if kind == "transaction" and REFUND.search(text) and CREDIT_VERB.search(text):
            kind = "refund"  # money coming back: it nets against the purchase instead of counting as income
        out.append((kind, round(p, 3)))
    return out
