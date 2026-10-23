from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import select

from app.db.session import session_scope
from app.models import User
from app.services import price_fetch
from app.services.affordability import Snapshot, affordability, evaluate_price

PRODUCT_JSONLD = """<html><head><title>Boat Rockerz 450</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"boAt Rockerz 450 Headphones",
"image":["https://cdn.example.in/rockerz.jpg"],"offers":{"@type":"Offer","price":"1,499.00","priceCurrency":"INR"}}</script>
</head><body>…</body></html>"""
PRODUCT_GRAPH = """<script type="application/ld+json">{"@graph":[{"@type":"BreadcrumbList"},{"@type":"Product","name":"Air Fryer",
"offers":[{"@type":"Offer","price":7499,"priceCurrency":"INR"},{"@type":"Offer","price":6999,"priceCurrency":"INR"}]}]}</script>"""
PRODUCT_META = """<html><head><meta property="og:title" content="Running Shoes"/>
<meta property="product:price:amount" content="4299"/><meta property="product:price:currency" content="INR"/></head></html>"""
PRODUCT_MICRODATA = """<div itemscope itemtype="https://schema.org/Product"><h1 itemprop="name">Kettle</h1>
<span itemprop="priceCurrency" content="INR">₹</span><span itemprop="price" content="1299.00">1,299</span></div>"""


def _demo():
    with session_scope() as db:
        return db.scalar(select(User.id).where(User.is_demo.is_(True)))


def test_price_from_jsonld_meta_and_microdata():
    r = price_fetch.parse_price(PRODUCT_JSONLD)
    assert r.status == "ok" and r.price == Decimal("1499.00") and "Rockerz" in r.title and r.image.endswith("rockerz.jpg")
    assert price_fetch.parse_price(PRODUCT_GRAPH).price == Decimal("6999.00")  # the lowest offer
    assert price_fetch.parse_price(PRODUCT_META).price == Decimal("4299.00")
    assert price_fetch.parse_price(PRODUCT_MICRODATA).price == Decimal("1299.00")
    assert price_fetch.parse_price("<html><title>Nothing</title></html>").status == "no_price"
    usd = PRODUCT_JSONLD.replace('"INR"', '"USD"')
    assert price_fetch.parse_price(usd).status == "not_inr"


def _client(routes: dict[str, tuple[int, str]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = routes.get(request.url.path, (404, "not found"))
        return httpx.Response(status, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_fetch_respects_robots_and_reports_blocking():
    allowed = _client({"/robots.txt": (200, "User-agent: *\nDisallow: /cart\n"), "/p/rockerz": (200, PRODUCT_JSONLD)})
    r = price_fetch.fetch_price("https://shop.example.in/p/rockerz", client=allowed)
    assert r.status == "ok" and r.price == Decimal("1499.00") and r.store == "shop.example.in"
    disallowed = _client({"/robots.txt": (200, "User-agent: *\nDisallow: /\n"), "/p/rockerz": (200, PRODUCT_JSONLD)})
    assert price_fetch.fetch_price("https://shop.example.in/p/rockerz", client=disallowed).status == "robots"
    blocked = _client({"/robots.txt": (404, ""), "/p/x": (403, "denied")})
    assert price_fetch.fetch_price("https://big.example.in/p/x", client=blocked).status == "blocked"


def test_links_to_local_addresses_are_refused():
    assert price_fetch.fetch_price("http://127.0.0.1:8000/api/v1/health").status == "invalid"
    assert price_fetch.fetch_price("http://192.168.1.1/admin").status == "invalid"
    assert price_fetch.fetch_price("file:///etc/passwd").status == "invalid"


def test_wishlist_for_a_new_user(new_user):
    c = new_user
    r = c.post("/api/v1/wishlist", json={"text": "Bluetooth speaker", "price": 2999})
    assert r.status_code == 200, r.text
    item_id = r.json()["item"]["id"]
    assert c.post("/api/v1/wishlist", json={"text": "No price yet"}).status_code == 200
    w = c.get("/api/v1/wishlist").json()
    tiers = {i["text"]: i["tier"] for i in w["items"]}
    assert tiers["No price yet"] == "needs_price"
    # a brand-new user: no income and no balance known, so nothing is "buy now" without saying why
    assert tiers["Bluetooth speaker"] in ("not_now", "save_up", "buy_now")
    assert w["snapshot"]["balance_known"] is False
    # tell FinPilot the take-home pay: now there is an income to plan with
    c.patch("/api/v1/auth/me", json={"preferences": {"take_home_monthly": 60000, "payday": 1}})
    w = c.get("/api/v1/wishlist").json()
    assert w["snapshot"]["income"] == 60000 and w["snapshot"]["income_source"] == "profile"
    speaker = next(i for i in w["items"] if i["id"] == item_id)
    assert speaker["tier"] == "buy_now" and speaker["reasons"]
    goal = c.post(f"/api/v1/wishlist/{item_id}/goal").json()
    assert goal["goal_id"]
    check = c.post("/api/v1/afford/check", json={"price": 200000, "label": "a laptop"}).json()
    assert check["verdict"]["tier"] in ("save_up", "not_now") and check["verdict"]["text"]
    assert c.patch(f"/api/v1/wishlist/{item_id}", json={"bought": True}).json()["active"] is False
    assert c.delete(f"/api/v1/wishlist/{item_id}").status_code == 200


def test_affordability_snapshot_is_conservative(demo):
    with session_scope() as db:
        user = db.get(User, _demo())
        s = affordability(db, user)
    assert s.balance_known
    assert s.buffer >= s.committed + s.essential - 1
    assert s.safe_to_spend <= s.liquid - s.buffer
    assert s.wants_left <= s.wants_budget


def test_demo_wishlist_has_real_tiers(demo_client):
    w = demo_client.get("/api/v1/wishlist").json()
    assert len(w["items"]) == 4
    assert all(i["tier"] in ("buy_now", "goal", "save_up", "not_now") for i in w["items"])


def _snap(safe, wants, surplus, buffer, emergency_ok=True, balance_known=True):
    d = Decimal
    return Snapshot(d(100000), d(40000), d(20000), d(10000), d(surplus), d(buffer), d(buffer) * 3, d(safe) + d(buffer), d(0), None,
                    None, None, d(safe), d(wants), d(0), d(wants), emergency_ok, balance_known=balance_known)


@settings(max_examples=300, deadline=None)
@given(price=st.integers(1, 300000), safe=st.integers(0, 400000), wants=st.integers(0, 60000), surplus=st.integers(-20000, 60000),
       buffer=st.integers(15000, 120000), start=st.integers(20000, 600000), drift=st.integers(-3000, 3000), emergency_ok=st.booleans())
def test_buy_now_never_breaks_the_buffer(price, safe, wants, surplus, buffer, start, drift, emergency_ok):
    today = date(2026, 10, 1)
    projection = [{"date": (today + timedelta(days=i)).isoformat(), "p10": start + drift * i - 5000, "p50": start + drift * i,
                   "p90": start + drift * i + 5000} for i in range(1, 61)]
    snap = _snap(safe, wants, surplus, buffer, emergency_ok)
    v = evaluate_price(Decimal(price), snap, projection)
    if v["tier"] == "buy_now":
        assert price <= min(safe, wants)
        assert v["impact"]["lowest_after"] >= buffer
        assert emergency_ok
    if v["tier"] == "save_up":
        assert 1 <= v["months"] <= 12 and surplus > 0


@settings(max_examples=200, deadline=None)
@given(price=st.integers(1, 100000), wants=st.integers(0, 60000))
def test_without_a_known_balance_only_the_wants_budget_decides(price, wants):
    snap = _snap(wants, wants, 10000, 15000, emergency_ok=False, balance_known=False)
    v = evaluate_price(Decimal(price), snap, None)
    assert (v["tier"] == "buy_now") == (price <= wants)


def test_a_redirect_to_a_local_address_is_refused_before_it_is_requested(monkeypatch):
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/api/v1/health"})

    monkeypatch.setattr(price_fetch, "_public_host", lambda host: host != "127.0.0.1")  # the shop counts as public
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(price_fetch._PrivateRedirect):
        price_fetch._get(client, "https://shop.example.in/p/x", check_hosts=True)
    assert requested == ["https://shop.example.in/p/x"]  # the local address itself was never requested
