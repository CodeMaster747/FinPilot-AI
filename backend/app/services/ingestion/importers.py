"""File imports — the manual, no-setup way to feed your own messages in.

SMS:   'SMS Backup & Restore' XML (Android), CSV (date, sender, message), or pasted text.
Email: .eml files or an .mbox archive (e.g. a Google Takeout export of a label).
XML is parsed with defusedxml (safe against entity-expansion attacks).
"""

from __future__ import annotations

import csv
import email
import io
import mailbox
import re
import tempfile
from datetime import datetime
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path

from defusedxml.ElementTree import fromstring

from app.seed.emails import html_to_text
from app.services.ingestion.types import RawMessage

MAX_BYTES = 25 * 1024 * 1024


class ImportError_(ValueError):
    pass


def _parse_when(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"\d{12,14}", value):
        return datetime.fromtimestamp(int(value) / 1000)
    if re.fullmatch(r"\d{9,10}", value):
        return datetime.fromtimestamp(int(value))
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d %b %Y %H:%M:%S", "%d %b %Y %I:%M:%S %p", "%b %d, %Y %I:%M:%S %p",
                "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        return None


# -- SMS -------------------------------------------------------------------------------------------
def parse_sms_backup_xml(data: bytes) -> list[RawMessage]:
    try:
        root = fromstring(data)
    except Exception as exc:  # noqa: BLE001 - surface any XML problem as a friendly error
        raise ImportError_(f"Not a valid SMS backup XML file ({exc.__class__.__name__}).") from exc
    out = []
    for el in root.iter("sms"):
        if el.get("type") not in (None, "1"):  # inbox only; sent messages are the user's own
            continue
        when = _parse_when(el.get("date")) or _parse_when(el.get("readable_date")) or datetime.now()
        out.append(RawMessage("sms", el.get("address", "").strip(), when, el.get("body", "")))
    return out


def parse_sms_csv(data: bytes) -> list[RawMessage]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportError_("The CSV file has no header row.")
    cols = {c.lower().strip(): c for c in reader.fieldnames}

    def pick(*names: str) -> str | None:
        return next((cols[n] for n in names if n in cols), None)

    sender_col = pick("address", "sender", "from", "number", "sender id")
    body_col = pick("body", "message", "text", "sms", "content")
    date_col = pick("date", "time", "timestamp", "datetime", "received", "date time")
    if not body_col:
        raise ImportError_("Couldn't find a message column (expected 'body' or 'message').")
    out = []
    for row in reader:
        body = (row.get(body_col) or "").strip()
        if not body:
            continue
        when = _parse_when(row.get(date_col)) if date_col else None
        out.append(RawMessage("sms", (row.get(sender_col) or "UNKNOWN").strip() if sender_col else "UNKNOWN",
                              when or datetime.now(), body))
    return out


SENDER_LINE = re.compile(r"^(?:from\s*:\s*|\[)?([A-Z]{2}-[A-Z0-9]{6}(?:-[PSTG])?|\+?\d{10,13})\]?:?\s*$", re.I)


def parse_sms_text(text: str) -> list[RawMessage]:
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.rstrip() for ln in block.strip().splitlines()]
        if not lines:
            continue
        sender, when = "UNKNOWN", None
        if SENDER_LINE.match(lines[0]):
            sender = SENDER_LINE.match(lines[0]).group(1).upper()
            lines = lines[1:]
        if lines and re.match(r"(?i)^date\s*:", lines[0]):
            when = _parse_when(lines[0].split(":", 1)[1])
            lines = lines[1:]
        body = "\n".join(lines).strip()
        if body:
            out.append(RawMessage("sms", sender, when or datetime.now(), body))
    return out


def parse_sms_file(filename: str, data: bytes) -> list[RawMessage]:
    if len(data) > MAX_BYTES:
        raise ImportError_("File is larger than 25 MB.")
    name = (filename or "").lower()
    if name.endswith(".xml") or data.lstrip()[:5] in (b"<?xml", b"<smse"):
        return parse_sms_backup_xml(data)
    if name.endswith(".csv"):
        return parse_sms_csv(data)
    return parse_sms_text(data.decode("utf-8", errors="replace"))


# -- Email -----------------------------------------------------------------------------------------
def email_to_raw(msg: email.message.EmailMessage) -> RawMessage | None:
    sender = str(msg.get("From", "") or "")
    subject = str(msg.get("Subject", "") or "")
    try:
        when = parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
        if when is not None and when.tzinfo is not None:
            when = when.astimezone().replace(tzinfo=None)
    except (TypeError, ValueError):
        when = None
    html = text = None
    try:
        part = msg.get_body(preferencelist=("html", "plain"))
        if part is not None:
            content = part.get_content()
            if part.get_content_type() == "text/html":
                html, text = content, html_to_text(content)
            else:
                text = content
    except (KeyError, LookupError):
        payload = msg.get_payload(decode=True)
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload or "")
    if not (text or "").strip():
        return None
    ext = str(msg.get("Message-ID", "") or "").strip("<> ")
    return RawMessage("email", sender, when or datetime.now(), text or "", subject=subject, html=html,
                      external_id=f"mid:{ext}" if ext else "")


def parse_email_file(filename: str, data: bytes) -> list[RawMessage]:
    if len(data) > MAX_BYTES:
        raise ImportError_("File is larger than 25 MB.")
    name = (filename or "").lower()
    if name.endswith(".mbox") or data.startswith(b"From "):
        with tempfile.NamedTemporaryFile(suffix=".mbox", delete=False) as tmp:
            tmp.write(data)
            path = Path(tmp.name)
        try:
            out = []
            for item in mailbox.mbox(str(path)):
                parsed = email.message_from_bytes(item.as_bytes(), policy=policy.default)
                raw = email_to_raw(parsed)
                if raw:
                    out.append(raw)
            return out
        finally:
            path.unlink(missing_ok=True)
    parsed = email.message_from_bytes(data, policy=policy.default)
    raw = email_to_raw(parsed)
    if raw is None:
        raise ImportError_("That doesn't look like an email file (.eml) — no readable body found.")
    return [raw]
