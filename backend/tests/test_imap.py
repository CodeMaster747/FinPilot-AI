"""Mailbox sync against a fake IMAP server that behaves like Gmail (X-GM-RAW search, \\All folder) or a plain
IMAP server (SINCE search, header filtering)."""

import imaplib
import re
from datetime import date, datetime, time, timedelta
from email.utils import parseaddr, parsedate_to_datetime

import pytest
from sqlalchemy import select

from app.db.session import session_scope
from app.models import MailboxConnection
from app.services.ingestion import imap_sync
from test_consent import SWIGGY_RECEIPT, SWIGGY_SMS, _ms, eml, job_result, phone_sync

PASSWORD = "abcd efgh ijkl mnop"


class FakeMailbox:
    def __init__(self):
        self.messages: dict[int, bytes] = {}
        self.uidvalidity = 7001

    def add(self, raw: bytes) -> int:
        uid = max(self.messages, default=100) + 1
        self.messages[uid] = raw
        return uid


class FakeIMAP:
    box = FakeMailbox()
    fetched_full: list[int] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.gmail = host == "imap.gmail.com"

    def login(self, user, password):
        if password.replace(" ", "") != PASSWORD.replace(" ", ""):
            raise imaplib.IMAP4.error("b'[AUTHENTICATIONFAILED] Invalid credentials (Failure)'")
        return "OK", [b"Logged in"]

    def list(self):
        if self.gmail:
            return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\All \\HasNoChildren) "/" "[Gmail]/All Mail"']
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"']

    def select(self, mailbox, readonly=False):
        assert readonly, "FinPilot must open mailboxes read-only"
        return "OK", [str(len(self.box.messages)).encode()]

    def response(self, code):
        return code, [str(self.box.uidvalidity).encode()]

    def _from(self, raw: bytes) -> str:
        m = re.search(rb"^From: (.+)$", raw, re.M)
        return parseaddr(m.group(1).decode())[1].lower() if m else ""

    def _date(self, raw: bytes) -> date:
        m = re.search(rb"^Date: (.+)$", raw, re.M)
        return parsedate_to_datetime(m.group(1).decode()).date()

    def uid(self, command, *args):
        if command == "SEARCH":
            if args[0] == "X-GM-RAW":
                query = args[1].strip('"')
                terms = re.search(r"from:\((.*)\)", query).group(1).split(" OR ")
                after = datetime.strptime(re.search(r"after:(\S+)", query).group(1), "%Y/%m/%d").date()
                hits = [u for u, raw in self.box.messages.items()
                        if any(self._from(raw) == t or self._from(raw).endswith("@" + t) or self._from(raw).endswith("." + t)
                               for t in terms) and self._date(raw) >= after]
            else:
                since = datetime.strptime(args[2], "%d-%b-%Y").date()
                hits = [u for u, raw in self.box.messages.items() if self._date(raw) >= since]
            return "OK", [" ".join(map(str, sorted(hits))).encode()]
        if command == "FETCH":
            uids = [int(u) for u in args[0].split(",")]
            out = []
            for u in uids:
                raw = self.box.messages[u]
                if "HEADER.FIELDS" in args[1]:
                    header = re.search(rb"^From: .+$", raw, re.M).group(0) + b"\r\n\r\n"
                    out.append((f"{u} (UID {u} BODY[HEADER.FIELDS (FROM)] {{{len(header)}}}".encode(), header))
                else:
                    assert "PEEK" in args[1], "FinPilot must not mark emails as read"
                    FakeIMAP.fetched_full.append(u)
                    out.append((f"{u} (UID {u} BODY[] {{{len(raw)}}}".encode(), raw))
                out.append(b")")
            return "OK", out
        raise AssertionError(command)

    def logout(self):
        return "BYE", [b""]

    def shutdown(self):
        pass


@pytest.fixture
def fake_imap(monkeypatch):
    FakeIMAP.box = FakeMailbox()
    FakeIMAP.fetched_full = []
    monkeypatch.setattr(imap_sync.imaplib, "IMAP4_SSL", FakeIMAP)
    return FakeIMAP


def _when(days_ago: int, hh: int = 13, mm: int = 6) -> datetime:
    return datetime.combine(date.today() - timedelta(days=days_ago), time(hh, mm))


def test_gmail_sync_reads_only_financial_senders(new_user, fake_imap):
    c = new_user
    for kind in ("sms", "email"):
        c.post(f"/api/v1/sources/{kind}/grant", json={"purposes": ["transactions"], "backfill_months": 3})
    job_result(c, phone_sync(c, [{"address": "VM-HDFCBK-S", "body": SWIGGY_SMS, "date_ms": _ms(0, 13)}]))
    receipt = fake_imap.box.add(eml("Swiggy <noreply@swiggy.in>", "Your Swiggy order", SWIGGY_RECEIPT, _when(0)))
    alert = fake_imap.box.add(eml("HDFC Bank InstaAlerts <alerts@hdfcbank.bank.in>", "Account update",
                                  "<p>Dear Customer, Rs.2,450.00 has been debited from account **6612 to VPA zomato@hdfcbank ZOMATO "
                                  f"on {date.today():%d-%m-%y}. Your UPI transaction reference number is 627612345703.</p>", _when(1)))
    newsletter = fake_imap.box.add(eml("Friends <hello@socialnetwork.example>", "Party pics", "<p>See the photos</p>", _when(1)))
    old = fake_imap.box.add(eml("Swiggy <noreply@swiggy.in>", "Older order", SWIGGY_RECEIPT.replace("7781234", "1111111"), _when(200)))

    wrong = c.post("/api/v1/sources/email/mailbox", json={"provider": "gmail", "email": "me@gmail.com", "password": "nope-nope"})
    assert wrong.status_code == 422 and "app password" in wrong.json()["detail"]
    r = c.post("/api/v1/sources/email/mailbox", json={"provider": "gmail", "email": "me@gmail.com", "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["mailbox"]["folder"] == "[Gmail]/All Mail"
    counts = job_result(c, r)["counts"]
    assert set(fake_imap.fetched_full) == {receipt, alert}  # never downloaded the newsletter or mail outside the window
    assert newsletter not in fake_imap.fetched_full and old not in fake_imap.fetched_full
    assert counts["emails"] == 2 and counts["linked"] == 1 and counts["transactions"] == 1
    swiggy = c.get("/api/v1/transactions", params={"q": "Swiggy"}).json()["items"][0]
    assert c.get(f"/api/v1/transactions/{swiggy['id']}").json()["items_count"] == 1
    with session_scope() as db:
        box = db.scalar(select(MailboxConnection))
        assert box.secret_enc and PASSWORD.encode() not in box.secret_enc  # stored encrypted
    status = c.get("/api/v1/sources/email/mailbox").json()["mailbox"]
    assert status["username"] == "me@gmail.com" and "password" not in status and status["last_error"] is None

    # the next sync continues from the last UID: only the new email is downloaded, nothing is duplicated
    fake_imap.fetched_full.clear()
    later = fake_imap.box.add(eml("Zepto <no-reply@zepto.co>", "Order delivered", "<p>Grand Total ₹386.00</p>", _when(0, 18)))
    job_result(c, c.post("/api/v1/sources/email/sync"))
    assert fake_imap.fetched_full == [later]
    assert c.get("/api/v1/transactions", params={"q": "Swiggy"}).json()["total"] == 1

    # revoking email access deletes the stored app password
    c.post("/api/v1/sources/email/revoke")
    assert c.get("/api/v1/sources/email/mailbox").json()["mailbox"] is None
    assert c.post("/api/v1/sources/email/sync").status_code == 409


def test_other_imap_providers_filter_by_sender_before_downloading(new_user, fake_imap):
    c = new_user
    c.post("/api/v1/sources/email/grant", json={"purposes": ["transactions"], "backfill_months": 1})
    bank = fake_imap.box.add(eml("Axis Bank Alerts <alerts@axisbank.com>", "Transaction alert",
                                 f"<p>Dear Customer, INR 2,150.00 spent on your Axis Bank Credit Card XX7766 at DMART on "
                                 f"{date.today():%d-%m-%Y} 18:30:12. Available limit INR 1,02,850.00.</p>", _when(2)))
    chat = fake_imap.box.add(eml("A Friend <friend@example.org>", "hi", "<p>dinner?</p>", _when(2)))
    r = c.post("/api/v1/sources/email/mailbox", json={"provider": "custom", "host": "mail.example.org", "email": "me@example.org",
                                                      "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert job_result(c, r)["counts"]["transactions"] == 1
    assert fake_imap.fetched_full == [bank] and chat not in fake_imap.fetched_full


def test_outlook_is_explained_not_attempted(new_user):
    c = new_user
    c.post("/api/v1/sources/email/grant", json={"purposes": ["transactions"], "backfill_months": 1})
    r = c.post("/api/v1/sources/email/mailbox", json={"provider": "custom", "host": "outlook.office365.com", "email": "me@outlook.com",
                                                      "password": PASSWORD})
    assert r.status_code == 422 and "Microsoft" in r.json()["detail"]
