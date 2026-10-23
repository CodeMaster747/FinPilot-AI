"""The Android app's path: Bearer tokens from a WebView origin, and SMS read on the phone and uploaded."""

import uuid

from conftest import sign_up_phone
from realistic import inbox, phone_upload, sms_backup_xml


def _sync(c, messages, session=None, chunk=5):
    session = session or uuid.uuid4().hex
    for i in range(0, len(messages), chunk):
        part = messages[i:i + chunk]
        r = c.post("/api/v1/ingest/sms/device", json={"session": session, "messages": part, "final": False})
        assert r.status_code == 200, r.text
    r = c.post("/api/v1/ingest/sms/device", json={
        "session": session, "messages": [], "final": True, "cursor_ms": max(m["date_ms"] for m in messages),
        "phone": {"read": 14, "skipped_personal": 1, "skipped_promo": 1, "skipped_otp": 1},
        "device": {"manufacturer": "Xiaomi", "sdk": 35}})
    assert r.status_code == 200, r.text
    job = c.get(f"/api/v1/jobs/{r.json()['job_id']}").json()
    assert job["status"] == "done", job
    return job["result"]["counts"]


def test_phone_signs_in_with_bearer_tokens(phone):
    tokens = sign_up_phone(phone)
    assert {"access_token", "refresh_token", "expires_in"} <= tokens.keys()
    assert "fp_at" not in phone.cookies  # no cookies for the app
    me = phone.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.headers["access-control-allow-origin"] == "http://localhost"
    # no X-Requested-With needed: a Bearer token can't be sent by a forged cross-site form
    assert phone.patch("/api/v1/auth/me", json={"preferences": {"take_home_monthly": 50000}}).status_code == 200
    r = phone.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200 and r.json()["access_token"]
    assert phone.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401  # rotated
    fresh = r.json()
    assert phone.post("/api/v1/auth/logout", json={"refresh_token": fresh["refresh_token"]}).status_code == 200
    assert phone.post("/api/v1/auth/refresh", json={"refresh_token": fresh["refresh_token"]}).status_code == 401
    phone.headers.pop("Authorization")
    assert phone.get("/api/v1/auth/me").status_code == 401


def test_signing_out_after_deleting_the_account_is_harmless(phone):
    # The app signs out right after "Delete my account"; the refresh token's row is already gone by then.
    tokens = sign_up_phone(phone)
    assert phone.request("DELETE", "/api/v1/settings/account", json={"confirm": "DELETE"}).status_code == 200
    assert phone.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 200
    assert phone.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_cors_preflight_allows_only_the_app(phone):
    ok = phone.options("/api/v1/auth/login", headers={"Origin": "http://localhost", "Access-Control-Request-Method": "POST",
                                                     "Access-Control-Request-Headers": "authorization,content-type,x-finpilot-client"})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost"
    evil = phone.options("/api/v1/auth/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in evil.headers


def test_web_cookie_requests_still_need_the_csrf_header(client):
    client.headers.pop("X-Requested-With")
    assert client.post("/api/v1/auth/login", json={"email": "x@y.z", "password": "12345678"}).status_code == 403


def test_sms_from_the_phone_becomes_transactions(phone):
    sign_up_phone(phone)
    assert phone.get("/api/v1/sources/sms/sync-state").json()["status"] == "not_connected"
    phone.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 3})
    state = phone.get("/api/v1/sources/sms/sync-state").json()
    assert state["status"] == "active" and state["cursor_ms"] is None and state["backfill_start_ms"] > 0
    uploads = phone_upload()
    counts = _sync(phone, uploads)
    assert counts["uploaded"] == len(uploads) and counts["transactions"] >= 8
    assert counts["skipped_otp"] == 1  # what the phone reported it filtered itself
    txns = phone.get("/api/v1/transactions", params={"page_size": 100}).json()
    merchants = {t["merchant"] for t in txns["items"]}
    assert {"Swiggy", "Netflix", "Zepto", "Bharat Petroleum"} <= merchants
    salary = next(t for t in txns["items"] if t["direction"] == "credit" and t["category"]["name"] == "Salary")
    assert "Zentrix" not in salary["merchant"]  # never the demo persona's employer
    assert salary["amount"] == 85000
    # sync state moved forward, and capture health is there for the Connections page
    state = phone.get("/api/v1/sources/sms/sync-state").json()
    assert state["cursor_ms"] == max(m["date_ms"] for m in uploads) and state["last"]["transactions"] >= 8
    assert state["device"]["manufacturer"] == "Xiaomi"
    # accounts were discovered and balances anchored from "Avl bal" in the alerts
    accounts = phone.get("/api/v1/accounts").json()
    assert any(a["mask"] == "4821" and a["balance_known"] for a in accounts)
    # syncing the same messages again (the app re-reads a short overlap) adds nothing
    again = _sync(phone, uploads)
    assert again["transactions"] == 0 and again["already_had"] == len(uploads) - again["not_financial"]


def test_backup_file_and_phone_sync_store_each_sms_once(phone):
    sign_up_phone(phone, "Arjun Mehta")
    phone.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 3})
    r = phone.post("/api/v1/ingest/sms/import", files={"file": ("sms-backup.xml", sms_backup_xml(), "text/xml")})
    assert r.status_code == 200, r.text
    first = phone.get(f"/api/v1/jobs/{r.json()['job_id']}").json()["result"]["counts"]
    assert first["created"] + first.get("transfer", 0) >= 8
    before = phone.get("/api/v1/transactions").json()["total"]
    counts = _sync(phone, phone_upload())
    assert counts["transactions"] == 0
    assert phone.get("/api/v1/transactions").json()["total"] == before


def test_otp_and_promotions_are_never_stored_even_if_uploaded(phone):
    """Defence in depth: if an old app version uploaded everything, the server still drops OTPs, -P promos and chats."""
    sign_up_phone(phone, "Kavya Nair")
    phone.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 3})
    everything = [{k: m[k] for k in ("address", "body", "date_ms")} for m in inbox()]
    _sync(phone, everything)
    stored = phone.get("/api/v1/review").json()
    texts = [m.get("body", "") for m in stored.get("messages", [])]
    assert not any("OTP" in t or "Pre-approved" in t or "dinner" in t for t in texts)
    page = phone.get("/api/v1/transactions", params={"page_size": 100}).json()["items"]
    assert not any(t["amount"] == 4999 for t in page) and not any(t["amount"] == 500000 for t in page)


def test_status_only_shows_my_own_jobs(phone, new_user):
    sign_up_phone(phone, "Someone Else")
    mine = {j["user_id"] for j in phone.get("/api/v1/system/status").json()["active_jobs"]}
    me = phone.get("/api/v1/auth/me").json()["id"]
    assert mine <= {me, None}
