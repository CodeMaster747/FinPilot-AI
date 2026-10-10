from sqlalchemy import select

from app.db.session import session_scope
from app.models import Subscription, User


def test_planted_subscription_findings(demo):
    with session_scope() as db:
        uid = db.scalar(select(User.id).where(User.is_demo.is_(True)))
        subs = {s.merchant_name: s for s in db.scalars(select(Subscription).where(Subscription.user_id == uid)).all()}
    flags = {name: {f["type"] for f in s.findings} for name, s in subs.items()}
    assert "dormant" in flags["Cult.fit"] and subs["Cult.fit"].status == "dormant"
    assert "price_increase" in flags["Netflix"]
    assert "trial_converted" in flags["Audible"]
    assert "overlap" in flags["Spotify"] and "overlap" not in flags["YouTube Premium"]  # keep the one that includes more
    assert subs["Amazon Prime"].cadence == "annual" and subs["JioHotstar"].cadence == "quarterly"
