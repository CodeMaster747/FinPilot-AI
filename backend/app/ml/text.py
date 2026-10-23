"""Text normalisation shared by the ML models and the alias matcher."""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_AMOUNT = re.compile(r"(?i)(?:rs\.?|inr|₹)\s*[\d,]+(?:\.\d+)?")
_LONG_NUM = re.compile(r"\d{5,}")
_DIGITS = re.compile(r"\d")
_DLT = re.compile(r"^(?:[A-Z]{2}-)?([A-Z0-9]{6})(?:-([PSTG]))?$")


def normalize(text: str) -> str:
    """'SWIGGY*ORDER 8812 / swiggy@icici' -> 'swiggy order 8812 swiggy icici'."""
    return _NON_ALNUM.sub(" ", (text or "").lower()).strip()


def sender_tokens(channel: str, sender: str) -> str:
    sender = (sender or "").strip()
    if channel == "sms":
        m = _DLT.match(sender.upper())
        if m and any(c.isalpha() for c in m.group(1)):  # same rule as ingestion.extract.header_of
            return f"hdr_{m.group(1).lower()} sfx_{(m.group(2) or 'x').lower()}"
        return "hdr_phone" if any(c.isdigit() for c in sender[:4]) else f"hdr_{normalize(sender).replace(' ', '_')}"
    domain = sender.rsplit("@", 1)[-1].strip("> ").lower()
    return f"dom_{domain.replace('.', '_')}"


def message_text(channel: str, sender: str, subject: str | None, body: str) -> str:
    """Feature text for the message classifier: amounts/numbers abstracted so the model learns structure."""
    text = f"{subject or ''} \n {body}"
    text = _AMOUNT.sub(" amt ", text)
    text = _LONG_NUM.sub(" num ", text)
    text = _DIGITS.sub("0", text)
    return f"{sender_tokens(channel, sender)} {channel} {text}"
