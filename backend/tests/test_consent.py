import uuid
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage
from email.utils import format_datetime

from app.core.timeutil import app_zone

SWIGGY_SMS = f"Sent Rs.412.00\nFrom HDFC Bank A/C *4521\nTo BUNDL TECHNOLOGIES\nOn {date.today():%d/%m/%y}\nRef 111122223333\nNot You?"


def _ms(days_ago: int = 0, hh: int = 13) -> int:
    d = datetime.combine(date.today() - timedelta(days=days_ago), time(hh, 5))
    return int(d.replace(tzinfo=app_zone()).timestamp() * 1000)


def phone_sync(c, messages: list[dict]):
    """What the Android app does: upload a sync session, then finish it (jobs run inline in tests)."""
    return c.post("/api/v1/ingest/sms/device", json={"session": uuid.uuid4().hex, "messages": messages, "final": True,
                                                     "cursor_ms": max((m["date_ms"] for m in messages), default=None)})


def job_result(c, r) -> dict:
    assert r.status_code == 200, r.text
    job = c.get(f"/api/v1/jobs/{r.json()['job_id']}").json()
    assert job["status"] == "done", job
    return job["result"]


def eml(sender: str, subject: str, html: str, when: datetime | None = None, message_id: str | None = None) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, "me@example.com", subject
    msg["Date"] = format_datetime((when or datetime.now()).replace(tzinfo=app_zone()))
    msg["Message-ID"] = message_id or f"<{uuid.uuid4().hex}@mail.test>"
    msg.set_content("This email needs HTML.")
    msg.add_alternative(html, subtype="html")
    return bytes(msg)


SWIGGY_RECEIPT = ("<p>Order No: 7781234</p><table class='items'><tr><th>Item</th><th>Qty</th><th>Price</th></tr>"
                  "<tr><td>Biryani</td><td>1</td><td>₹412.00</td></tr></table><p>Order Total: ₹412.00</p>")


def test_nothing_is_read_without_consent(new_user):
    assert phone_sync(new_user, [{"address": "VM-HDFCBK-S", "body": SWIGGY_SMS, "date_ms": _ms()}]).status_code == 409


def test_grant_requires_the_transactions_purpose(new_user):
    r = new_user.post("/api/v1/sources/sms/grant", json={"purposes": ["marketing"], "backfill_months": 3})
    assert r.status_code == 400


def test_pause_revoke_and_history(new_user):
    c = new_user
    assert c.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 3}).status_code == 200
    assert job_result(c, phone_sync(c, [{"address": "VM-HDFCBK-S", "body": SWIGGY_SMS, "date_ms": _ms()}]))["counts"]["transactions"] == 1
    c.post("/api/v1/sources/sms/pause")
    assert phone_sync(c, [{"address": "VM-HDFCBK-S", "body": SWIGGY_SMS.replace("111122223333", "999"), "date_ms": _ms()}]).status_code == 409
    c.post("/api/v1/sources/sms/revoke")
    # revoked means revoked: neither resume nor pause→resume brings it back without a new grant
    assert c.post("/api/v1/sources/sms/resume").status_code == 409
    assert c.post("/api/v1/sources/sms/pause").status_code == 409
    events = [e["event"] for e in c.get("/api/v1/sources/history").json()]
    assert events[:3] == ["revoked", "paused", "granted"]


def test_backfill_window_is_enforced_on_every_feed(new_user):
    c = new_user
    c.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 1})
    old = {"address": "VM-HDFCBK-S", "body": SWIGGY_SMS.replace("111122223333", "444455556666"), "date_ms": _ms(days_ago=90)}
    new = {"address": "VM-HDFCBK-S", "body": SWIGGY_SMS, "date_ms": _ms()}
    counts = job_result(c, phone_sync(c, [old, new]))["counts"]
    assert counts["outside_window"] == 1 and counts["transactions"] == 1


def test_delete_data_removes_only_that_source(new_user):
    c = new_user
    c.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 3})
    c.post("/api/v1/sources/email/grant", json={"purposes": ["transactions"], "backfill_months": 3})
    job_result(c, phone_sync(c, [{"address": "VM-HDFCBK-S", "body": SWIGGY_SMS, "date_ms": _ms()}]))
    txn_id = c.get("/api/v1/transactions", params={"q": "Swiggy"}).json()["items"][0]["id"]
    r = c.post("/api/v1/ingest/email/import", files={"file": ("receipt.eml", eml("Swiggy <noreply@swiggy.in>", "Your Swiggy order", SWIGGY_RECEIPT), "message/rfc822")})
    assert job_result(c, r)["counts"]["enriched"] == 1
    assert c.get(f"/api/v1/transactions/{txn_id}").json()["items_count"] == 1
    out = c.post("/api/v1/sources/email/delete-data").json()
    assert out["deleted"]["messages"] == 1 and out["deleted"]["transactions_deleted"] == 0
    detail = c.get(f"/api/v1/transactions/{txn_id}").json()
    assert detail["items_count"] == 0 and all(e["channel"] == "sms" for e in detail["evidence"])
    out = c.post("/api/v1/sources/sms/delete-data").json()
    assert out["deleted"]["transactions_deleted"] == 1
    assert c.get(f"/api/v1/transactions/{txn_id}").status_code == 404


def test_import_sms_backup_file(new_user):
    c = new_user
    c.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 3})
    xml = ('<?xml version="1.0"?><smses count="2">'
           f'<sms address="VM-HDFCBK-S" date="{_ms(1)}" type="1" body="{SWIGGY_SMS}" />'
           f'<sms address="+919876543210" date="{_ms(1, 14)}" type="1" body="dinner at 8?" /></smses>')
    r = c.post("/api/v1/ingest/sms/import", files={"file": ("backup.xml", xml.encode(), "text/xml")})
    counts = job_result(c, r)["counts"]
    assert counts["created"] == 1 and counts["dropped"] == 1


def test_phone_sms_then_receipt_email_make_one_transaction(new_user):
    c = new_user
    for kind in ("sms", "email"):
        c.post(f"/api/v1/sources/{kind}/grant", json={"purposes": ["transactions"], "backfill_months": 1})
    job_result(c, phone_sync(c, [{"address": "VM-HDFCBK-S", "body": SWIGGY_SMS, "date_ms": _ms(0, 13)}]))
    page = c.get("/api/v1/transactions", params={"q": "Swiggy"}).json()
    assert page["total"] == 1 and page["items"][0]["merchant"] == "Swiggy"
    mail = eml("Swiggy <noreply@swiggy.in>", "Your Swiggy order", SWIGGY_RECEIPT, message_id="<order-7781234@swiggy.in>")
    first = job_result(c, c.post("/api/v1/ingest/email/import", files={"file": ("r.eml", mail, "message/rfc822")}))
    assert first["counts"]["enriched"] == 1
    again = job_result(c, c.post("/api/v1/ingest/email/import", files={"file": ("r.eml", mail, "message/rfc822")}))
    assert again["counts"].get("already_imported") == 1  # the same email imported twice is stored once
    detail = c.get(f"/api/v1/transactions/{page['items'][0]['id']}").json()
    assert len(detail["items"]) == 1 and c.get("/api/v1/transactions", params={"q": "Swiggy"}).json()["total"] == 1


def test_the_demo_account_cannot_connect_real_sources(demo_client):
    c = demo_client
    assert c.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 3}).status_code == 403
    assert phone_sync(c, [{"address": "VM-HDFCBK-S", "body": SWIGGY_SMS, "date_ms": _ms()}]).status_code == 403
    r = c.post("/api/v1/ingest/sms/import", files={"file": ("b.xml", b"<smses></smses>", "text/xml")})
    assert r.status_code == 403
    r = c.post("/api/v1/sources/email/mailbox", json={"provider": "gmail", "email": "x@gmail.com", "password": "abcd efgh ijkl mnop"})
    assert r.status_code == 403
