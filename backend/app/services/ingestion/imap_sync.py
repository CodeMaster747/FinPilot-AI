"""Reads financial emails from the user's mailbox over IMAP, signed in with an app password.

Only senders on the financial allowlist are searched for and downloaded; nothing is ever sent, moved, deleted or
marked as read (messages are fetched with BODY.PEEK). The first sync reads the consented backfill window; later
syncs continue from the last UID seen (re-reading a short overlap is harmless: duplicates are skipped).
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
import socket
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from email import policy
from typing import Any

from app.services.ingestion.senders import gmail_from_terms, sender_allowed

log = logging.getLogger("finpilot.imap")

PROVIDERS: dict[str, dict[str, Any]] = {
    "gmail": {"label": "Gmail", "host": "imap.gmail.com", "port": 993,
              "help": "Create an app password at myaccount.google.com/apppasswords (2-Step Verification must be on)."},
    "yahoo": {"label": "Yahoo Mail", "host": "imap.mail.yahoo.com", "port": 993,
              "help": "Yahoo Account Security → Generate app password."},
    "zoho": {"label": "Zoho Mail (India)", "host": "imap.zoho.in", "port": 993,
             "help": "Zoho Accounts → Security → App passwords. Make sure IMAP access is on in Zoho Mail settings."},
    "zoho_com": {"label": "Zoho Mail (global)", "host": "imap.zoho.com", "port": 993,
                 "help": "Zoho Accounts → Security → App passwords. Make sure IMAP access is on in Zoho Mail settings."},
    "icloud": {"label": "iCloud Mail", "host": "imap.mail.me.com", "port": 993,
               "help": "appleid.apple.com → Sign-In and Security → App-Specific Passwords."},
    "custom": {"label": "Other (IMAP)", "host": None, "port": 993, "help": "Use your provider's IMAP server and an app password."},
}
UNSUPPORTED = {
    "outlook.com": "Outlook.com and Hotmail no longer allow app passwords for IMAP (Microsoft requires its own sign-in). "
                   "Forward bank emails to a Gmail address, or import them as .eml/.mbox files.",
    "hotmail.com": "Outlook.com and Hotmail no longer allow app passwords for IMAP (Microsoft requires its own sign-in). "
                   "Forward bank emails to a Gmail address, or import them as .eml/.mbox files.",
    "live.com": "Outlook.com and Hotmail no longer allow app passwords for IMAP (Microsoft requires its own sign-in). "
                "Forward bank emails to a Gmail address, or import them as .eml/.mbox files.",
}
TIMEOUT = 30
SEARCH_CHUNK = 25
FETCH_BATCH = 25
INGEST_BATCH = 100
OVERLAP_DAYS = 2
UID_RE = re.compile(rb"UID (\d+)")


class MailboxError(Exception):
    """A problem the user can act on (wrong password, server unreachable…); the message is shown as is."""


def provider_for_email(address: str) -> str | None:
    domain = address.rsplit("@", 1)[-1].lower()
    if domain in ("gmail.com", "googlemail.com"):
        return "gmail"
    if domain.startswith("yahoo.") or domain in ("ymail.com", "rocketmail.com"):
        return "yahoo"
    if domain in ("icloud.com", "me.com", "mac.com"):
        return "icloud"
    if domain in ("zoho.in", "zohomail.in"):
        return "zoho"
    if domain in ("zoho.com", "zohomail.com"):
        return "zoho_com"
    return None


def connect(host: str, port: int, username: str, password: str, provider: str = "custom") -> imaplib.IMAP4_SSL:
    try:
        conn = imaplib.IMAP4_SSL(host, port, timeout=TIMEOUT)
    except socket.gaierror as exc:
        raise MailboxError(f"Couldn't find the mail server “{host}”. Check the server name, and that the computer running FinPilot is online.") from exc
    except (OSError, TimeoutError) as exc:
        raise MailboxError(f"Couldn't reach {host} — check that the computer running FinPilot is online, then try again.") from exc
    try:
        conn.login(username, password.replace(" ", "") if provider in ("gmail", "yahoo") else password)
    except imaplib.IMAP4.error as exc:
        try:
            conn.shutdown()
        except Exception:  # noqa: BLE001
            pass
        detail = str(exc).replace("b'", "").replace("'", "")[:160]
        if provider == "gmail":
            raise MailboxError("Gmail didn't accept that password. Use an app password — create one at "
                               "myaccount.google.com/apppasswords (2-Step Verification must be on) and paste its 16 letters. "
                               "Your normal Gmail password won't work.") from exc
        raise MailboxError(f"The mail server rejected the sign-in. Check the address and use an app password. (Server said: {detail})") from exc
    except (OSError, TimeoutError) as exc:
        raise MailboxError(f"The connection to {host} dropped while signing in — try again.") from exc
    return conn


def _decode(value: bytes | str) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def find_folder(conn: imaplib.IMAP4_SSL, provider: str) -> str:
    """Gmail: the "All Mail" folder (bank alerts are often archived by filters), found by its \\All flag so it works
    whatever the account's language. Other providers: the inbox."""
    if provider != "gmail":
        return "INBOX"
    typ, data = conn.list()
    if typ == "OK":
        for raw in data or []:
            line = _decode(raw) if raw else ""
            if "\\All" in line:
                m = re.search(r'"([^"]+)"\s*$', line) or re.search(r"\s(\S+)\s*$", line)
                if m:
                    return m.group(1)
    return "INBOX"


def _quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def select_folder(conn: imaplib.IMAP4_SSL, folder: str) -> int | None:
    typ, _ = conn.select(_quote(folder), readonly=True)
    if typ != "OK":
        raise MailboxError(f"Couldn't open the mail folder “{folder}”.")
    _, data = conn.response("UIDVALIDITY")
    try:
        return int(_decode(data[0])) if data and data[0] else None
    except (TypeError, ValueError):
        return None


def _chunks(items: list, n: int) -> Iterator[list]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


def search_uids(conn: imaplib.IMAP4_SSL, provider: str, since: date, extra: tuple[str, ...], min_uid: int | None) -> list[int]:
    uids: set[int] = set()
    if provider == "gmail":
        for chunk in _chunks(gmail_from_terms(extra), SEARCH_CHUNK):
            terms = [t for t in chunk if "@" not in t] + [t for t in chunk if "@" in t]
            query = f"from:({' OR '.join(terms)}) after:{since:%Y/%m/%d}"
            typ, data = conn.uid("SEARCH", "X-GM-RAW", _quote(query))
            if typ == "OK" and data and data[0]:
                uids.update(int(x) for x in data[0].split())
    else:
        typ, data = conn.uid("SEARCH", None, "SINCE", since.strftime("%d-%b-%Y"))
        candidates = [int(x) for x in data[0].split()] if typ == "OK" and data and data[0] else []
        if min_uid:
            candidates = [u for u in candidates if u > min_uid]
        for batch in _chunks(candidates, 200):
            typ, resp = conn.uid("FETCH", ",".join(map(str, batch)), "(UID BODY.PEEK[HEADER.FIELDS (FROM)])")
            for part in resp or []:
                if not isinstance(part, tuple):
                    continue
                m = UID_RE.search(part[0])
                header = email.message_from_bytes(part[1], policy=policy.default)
                address = email.utils.parseaddr(str(header.get("From", "")))[1]
                if m and sender_allowed(address, extra):
                    uids.add(int(m.group(1)))
    if min_uid:
        uids = {u for u in uids if u > min_uid}
    return sorted(uids)


def fetch_raw(conn: imaplib.IMAP4_SSL, uids: list[int]) -> Iterator[tuple[int, bytes]]:
    for batch in _chunks(uids, FETCH_BATCH):
        typ, resp = conn.uid("FETCH", ",".join(map(str, batch)), "(UID BODY.PEEK[])")
        if typ != "OK":
            raise MailboxError("The mail server stopped answering while downloading — FinPilot will try again later.")
        for part in resp or []:
            if isinstance(part, tuple):
                m = UID_RE.search(part[0])
                if m:
                    yield int(m.group(1)), part[1]


def test_login(provider: str, host: str, port: int, username: str, password: str) -> str:
    """Sign in and open the folder FinPilot will read; returns that folder's name."""
    conn = connect(host, port, username, password, provider)
    try:
        folder = find_folder(conn, provider)
        select_folder(conn, folder)
        return folder
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


@dataclass
class SyncResult:
    fetched: int
    counts: dict[str, int]


def sync_user(user_id: int, progress=None) -> dict[str, Any]:  # noqa: ANN001
    from sqlalchemy import select

    from app.core.crypto import decrypt_text
    from app.db.base import utcnow
    from app.db.session import session_scope
    from app.jobs.runner import runner
    from app.models import DataSource, MailboxConnection, User
    from app.services import consent
    from app.services.ingestion.importers import email_to_raw
    from app.services.ingestion.pipeline import ingest

    step = progress or (lambda pct, msg=None: None)
    with session_scope() as db:
        user = db.get(User, user_id)
        box = db.scalar(select(MailboxConnection).where(MailboxConnection.user_id == user_id))
        if user is None or user.is_demo or box is None or box.secret_enc is None:
            return {"skipped": "No mailbox connected"}
        src = db.get(DataSource, box.data_source_id)
        if src is None or src.status != "active":
            return {"skipped": "Email is not active"}
        password = decrypt_text(box.secret_enc)
        provider, host, port, username = box.provider, box.host, box.port, box.username
        folder, last_uid, old_validity = box.folder, box.last_uid, box.uidvalidity
        start = consent.backfill_start(src)
        since = start if last_uid is None or box.last_synced_at is None else max(start, box.last_synced_at.date() - timedelta(days=OVERLAP_DAYS))
        extra = tuple((user.preferences or {}).get("extra_email_domains") or ())
    step(5, "Signing in to your mailbox")
    totals: dict[str, int] = {}
    fetched = 0
    newest_uid = last_uid
    validity = old_validity
    try:
        conn = connect(host, port, username, password, provider)
        try:
            folder = folder or find_folder(conn, provider)
            validity = select_folder(conn, folder)
            if old_validity is not None and validity != old_validity:
                last_uid, since = None, start  # the server renumbered the folder: read the window again
            step(15, "Looking for bank and shop emails")
            uids = search_uids(conn, provider, since, extra, last_uid)
            batch: list = []

            def flush(msgs: list) -> None:
                with session_scope() as db:
                    u, s = db.get(User, user_id), db.get(DataSource, src.id)
                    if s is None or s.status != "active":
                        raise MailboxError("Email access was paused or revoked during the sync.")
                    report = ingest(db, u, s, consent.within_backfill(s, msgs), feed="imap", finalize_pending=False)
                    for k, v in report.counts.items():
                        totals[k] = totals.get(k, 0) + v

            for i, (uid, raw) in enumerate(fetch_raw(conn, uids)):
                parsed = email.message_from_bytes(raw, policy=policy.default)
                msg = email_to_raw(parsed)
                if msg is not None:
                    batch.append(msg)
                fetched += 1
                newest_uid = max(newest_uid or 0, uid)
                if len(batch) >= INGEST_BATCH:
                    flush(batch)
                    batch = []
                if i % 10 == 0:
                    step(15 + 80 * (i + 1) / max(1, len(uids)), f"Reading emails ({i + 1} of {len(uids)})")
            if batch:
                flush(batch)
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass
    except MailboxError as exc:
        log.warning("mailbox sync for user %s (%s) failed: %s", user_id, host, exc)
        with session_scope() as db:
            box = db.scalar(select(MailboxConnection).where(MailboxConnection.user_id == user_id))
            if box is not None:
                box.last_error = str(exc)[:255]
        raise
    except (imaplib.IMAP4.error, OSError) as exc:
        message = f"The mail server returned an error ({exc.__class__.__name__}). FinPilot will try again in 30 minutes."
        log.warning("mailbox sync for user %s (%s) failed: %r", user_id, host, exc)
        with session_scope() as db:
            box = db.scalar(select(MailboxConnection).where(MailboxConnection.user_id == user_id))
            if box is not None:
                box.last_error = message[:255]
        raise MailboxError(message) from exc
    counts = {"emails": fetched, "transactions": totals.get("created", 0) + totals.get("transfer", 0),
              "linked": totals.get("duplicate", 0) + totals.get("enriched", 0), "waiting": totals.get("pending", 0),
              "review": totals.get("review", 0), "not_financial": totals.get("ignored", 0) + totals.get("dropped", 0),
              "already_had": totals.get("already_imported", 0)}
    with session_scope() as db:
        box = db.scalar(select(MailboxConnection).where(MailboxConnection.user_id == user_id))
        if box is not None:
            box.folder, box.uidvalidity, box.last_uid = folder, validity, newest_uid
            box.last_synced_at, box.last_error = utcnow(), None
            box.last_counts = counts
    log.info("mailbox sync for user %s (%s, %s): %s", user_id, host, folder, counts)
    if fetched:
        runner.enqueue("user_analytics", user_id=user_id)
    step(100, "Done")
    return {"counts": counts}
