def test_auth_flow(client):
    r = client.post("/api/v1/auth/register", json={"name": "Asha", "email": "asha@test.dev", "password": "short"})
    assert r.status_code == 422
    r = client.post("/api/v1/auth/register", json={"name": "Asha", "email": "asha@test.dev", "password": "longenough"})
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me").json()["email"] == "asha@test.dev"
    assert client.post("/api/v1/auth/refresh").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "asha@test.dev", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "ASHA@test.dev", "password": "longenough"}).status_code == 200


def test_csrf_header_required(client):
    client.headers.pop("X-Requested-With")
    assert client.post("/api/v1/auth/login", json={"email": "x@y.z", "password": "12345678"}).status_code == 403


def test_transactions_and_remembered_rule(demo_client):
    c = demo_client
    page = c.get("/api/v1/transactions", params={"q": "Ola", "page_size": 5}).json()
    assert page["total"] > 0
    txn = page["items"][0]
    cats = {x["name"]: x["id"] for x in c.get("/api/v1/categories").json()}
    r = c.patch(f"/api/v1/transactions/{txn['id']}", json={"category_id": cats["Travel"], "remember": True})
    assert r.status_code == 200
    again = c.get("/api/v1/transactions", params={"q": "Ola", "page_size": 200}).json()["items"]
    assert all(t["category"]["name"] == "Travel" for t in again if t["merchant"] == txn["merchant"])
    rules = c.get("/api/v1/rules").json()
    assert any(rule["value"] == txn["merchant"].lower() for rule in rules)
    # restore: other tests measure the automatic categoriser against ground truth
    c.patch(f"/api/v1/transactions/{txn['id']}", json={"category_id": cats[txn["category"]["name"]], "remember": True})
    for rule in rules:
        if rule["value"] == txn["merchant"].lower():
            c.delete(f"/api/v1/rules/{rule['id']}")


def test_transaction_detail_shows_evidence(demo_client):
    items = demo_client.get("/api/v1/transactions", params={"q": "Swiggy", "page_size": 20}).json()["items"]
    detail = demo_client.get(f"/api/v1/transactions/{items[0]['id']}").json()
    roles = {e["role"] for e in detail["evidence"]}
    assert "primary" in roles


def test_writes_that_queue_jobs_do_not_block(new_user):
    """Regression: a request that flushed rows and then queued a job from a second connection waited on
    its own SQLite write lock for the 30 s busy timeout and failed. Jobs now join the request's transaction."""
    import time

    c = new_user
    t0 = time.perf_counter()
    r = c.post("/api/v1/transactions", json={"date": "2026-10-01", "amount": 250, "direction": "debit", "merchant": "Saravana Stores"})
    assert r.status_code == 200, r.text
    assert c.post("/api/v1/wishlist", json={"text": "Mirrorless camera", "max_price": 80000}).status_code == 200
    assert c.patch("/api/v1/auth/me", json={"preferences": {"picks_enabled": True, "buffer_floor": 20000}}).status_code == 200
    assert time.perf_counter() - t0 < 10
    listed = c.get("/api/v1/transactions", params={"q": "Saravana"}).json()
    assert listed["total"] == 1


def test_preferences_are_validated(new_user):
    assert new_user.patch("/api/v1/auth/me", json={"preferences": {"emergency_months": 99}}).status_code == 422
    assert new_user.patch("/api/v1/auth/me", json={"preferences": {"picks_enabled": "yes"}}).status_code == 422
    assert new_user.patch("/api/v1/auth/me", json={"preferences": {"buffer_floor": 25000}}).json()["preferences"]["buffer_floor"] == 25000


def test_failed_logins_are_rate_limited(client):
    from app.api.v1 import auth

    auth._attempts.clear()  # earlier tests may have recorded a failed login
    try:
        for _ in range(10):
            assert client.post("/api/v1/auth/login", json={"email": "nobody@test.dev", "password": "wrong-pass"}).status_code == 401
        assert client.post("/api/v1/auth/login", json={"email": "nobody@test.dev", "password": "wrong-pass"}).status_code == 429
    finally:
        auth._attempts.clear()


def test_delete_account_removes_everything(new_user):
    c = new_user
    c.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions", "picks"], "backfill_months": 1})
    job_id = c.post("/api/v1/ingest/sms/sample").json()["job_id"]
    assert c.get(f"/api/v1/jobs/{job_id}").json()["status"] == "done"
    assert c.post("/api/v1/goals", json={"name": "Bike", "target": 50000, "target_date": "2027-06-30"}).status_code == 200
    assert c.get("/api/v1/transactions").json()["total"] > 0
    assert c.request("DELETE", "/api/v1/settings/account", json={"confirm": "nope"}).status_code == 422
    r = c.request("DELETE", "/api/v1/settings/account", json={"confirm": "DELETE"})
    assert r.status_code == 200, r.text
    assert c.get("/api/v1/auth/me").status_code == 401
