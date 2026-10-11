from datetime import date, timedelta
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import select

from app.db.session import session_scope
from app.models import CrawlRun, Product, ProductRecommendation, User
from app.services.picks import Snapshot, affordability, evaluate_price


def _demo():
    with session_scope() as db:
        return db.scalar(select(User.id).where(User.is_demo.is_(True)))


def test_crawler_obeys_robots_and_reads_jsonld(demo):
    with session_scope() as db:
        run = db.scalars(select(CrawlRun).order_by(CrawlRun.id.desc())).first()
        products = db.scalars(select(Product)).all()
    assert run.status == "done" and run.skipped_robots >= 1
    assert any("BlockedMart" in line and "disallowed" in line for line in run.log)
    assert len(products) > 150
    assert all(p.price > 0 and p.category for p in products)
    assert not any(p.path.startswith("/blockedmart/") for p in products)


def test_affordability_snapshot_is_conservative(demo):
    with session_scope() as db:
        user = db.get(User, _demo())
        s = affordability(db, user)
    assert s.buffer >= s.committed + s.essential - 1
    assert s.safe_to_spend <= s.liquid - s.buffer
    assert s.wants_left <= s.wants_budget


def test_picks_cover_interests_and_replenishment_saves_money(demo):
    with session_scope() as db:
        recs = db.execute(select(ProductRecommendation, Product).join(Product).where(ProductRecommendation.user_id == _demo())).all()
    assert len(recs) >= 6
    interests = {r.interest for r, _ in recs}
    assert any("wishlist" in i for i in interests) and any("goal" in i for i in interests)
    for r, p in recs:
        if r.interest.startswith("you buy"):
            assert "cheaper" in r.reasons[1] or "usually pay" in r.reasons[1]


def test_precision_at_10_beats_popularity_baseline(demo):
    from app.services.quality import picks_precision

    with session_scope() as db:
        result = picks_precision(db, db.get(User, _demo()))
    assert result is not None and result["evaluated"] >= 8
    assert result["picks"] >= 0.8 and result["picks"] > result["popularity_baseline"]


def _snap(safe, wants, surplus, buffer, emergency_ok=True):
    d = Decimal
    return Snapshot(d(100000), d(40000), d(20000), d(10000), d(surplus), d(buffer), d(buffer) * 3, d(safe) + d(buffer), d(0), None,
                    None, None, d(safe), d(wants), d(0), d(wants), emergency_ok, ["sms"])


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
