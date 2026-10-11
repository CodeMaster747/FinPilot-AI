from datetime import date

SWIGGY_SMS = f"Sent Rs.412.00\nFrom HDFC Bank A/C *4521\nTo BUNDL TECHNOLOGIES\nOn {date.today():%d/%m/%y}\nRef 111122223333\nNot You?"


def _sim(c, channel, sender, body=None, html=None, subject=None):
    return c.post("/api/v1/ingest/simulate", json={"channel": channel, "sender": sender, "body": body, "html": html, "subject": subject})


def test_nothing_is_read_without_consent(new_user):
    assert _sim(new_user, "sms", "VM-HDFCBK-S", SWIGGY_SMS).status_code == 409


def test_grant_requires_the_transactions_purpose(new_user):
    r = new_user.post("/api/v1/sources/sms/grant", json={"purposes": ["picks"], "backfill_months": 3})
    assert r.status_code == 400


def test_pause_revoke_and_history(new_user):
    c = new_user
    assert c.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 3}).status_code == 200
    assert _sim(c, "sms", "VM-HDFCBK-S", SWIGGY_SMS).json()["status"] == "created"
    c.post("/api/v1/sources/sms/pause")
    assert _sim(c, "sms", "VM-HDFCBK-S", SWIGGY_SMS.replace("111122223333", "999")).status_code == 409
    c.post("/api/v1/sources/sms/revoke")
    assert c.post("/api/v1/sources/sms/resume").status_code == 409
    events = [e["event"] for e in c.get("/api/v1/sources/history").json()]
    assert events[:3] == ["revoked", "paused", "granted"]


def test_delete_data_removes_only_that_source(new_user):
    c = new_user
    c.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 3})
    c.post("/api/v1/sources/email/grant", json={"purposes": ["transactions"], "backfill_months": 3})
    created = _sim(c, "sms", "VM-HDFCBK-S", SWIGGY_SMS).json()
    html = ("<p>Order No: 1</p><table class='items'><tr><th>Item</th><th>Qty</th><th>Price</th></tr>"
            "<tr><td>Biryani</td><td>1</td><td>₹412.00</td></tr></table><p>Order Total: ₹412.00</p>")
    enriched = _sim(c, "email", "Swiggy <noreply@swiggy.in>", html=html, subject="Your Swiggy order").json()
    assert enriched["status"] == "enriched"
    txn_id = created["transaction"]["id"]
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
           f'<sms address="VM-HDFCBK-S" date="1790000000000" type="1" body="{SWIGGY_SMS}" />'
           '<sms address="+919876543210" date="1790000100000" type="1" body="dinner at 8?" /></smses>')
    r = c.post("/api/v1/ingest/sms/import", files={"file": ("backup.xml", xml.encode(), "text/xml")})
    assert r.status_code == 200, r.text
    job = c.get(f"/api/v1/jobs/{r.json()['job_id']}").json()
    assert job["status"] == "done", job
    assert job["result"]["counts"]["created"] == 1 and job["result"]["counts"]["dropped"] == 1


def test_smart_picks_only_use_sources_allowed_for_them(new_user):
    c = new_user
    c.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 3})
    c.post("/api/v1/ingest/sms/sample")
    assert c.patch("/api/v1/auth/me", json={"preferences": {"picks_enabled": True}}).status_code == 200
    snap = c.get("/api/v1/picks").json()["snapshot"]
    assert snap["complete"] is False and "sms" not in snap["origins"]
    assert snap["income"] == 0 and snap["safe_to_spend"] == 0  # SMS data is not used for Smart Picks
    assert all(p["tier"] != "buy_now" for p in c.get("/api/v1/picks").json()["picks"])
    assert c.put("/api/v1/sources/sms/purposes", json={"purposes": ["transactions", "picks"]}).status_code == 200
    snap = c.get("/api/v1/picks").json()["snapshot"]
    assert snap["complete"] is True and "sms" in snap["origins"] and snap["income"] > 0


def test_simulated_sms_then_receipt_email_make_one_transaction(new_user):
    c = new_user
    for kind in ("sms", "email"):
        c.post(f"/api/v1/sources/{kind}/grant", json={"purposes": ["transactions"], "backfill_months": 1})
    sms = next(t for t in c.get("/api/v1/ingest/simulator/templates").json() if t["id"] == "upi_swiggy")
    r = c.post("/api/v1/ingest/simulate", json={"channel": "sms", "sender": sms["sender"], "body": sms["body"]}).json()
    assert r["status"] == "created" and r["transaction"]["merchant"] == "Swiggy"
    receipt = next(t for t in c.get("/api/v1/ingest/simulator/templates").json() if t["id"] == "swiggy_receipt")
    payload = {"channel": "email", "sender": receipt["sender"], "subject": receipt["subject"], "html": receipt["html"]}
    first = c.post("/api/v1/ingest/simulate", json=payload).json()
    assert first["status"] == "enriched" and first["transaction"]["id"] == r["transaction"]["id"]
    again = c.post("/api/v1/ingest/simulate", json=payload).json()  # the same receipt delivered twice
    assert again["status"] == "duplicate" and again["transaction"]["id"] == r["transaction"]["id"]
    detail = c.get(f"/api/v1/transactions/{r['transaction']['id']}").json()
    assert len(detail["items"]) == 2 and c.get("/api/v1/transactions", params={"q": "Swiggy"}).json()["total"] == 1
