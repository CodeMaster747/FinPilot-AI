from datetime import date

from sqlalchemy import func, select

from app.db.session import session_scope
from app.ml.evaluate_pipeline import evaluate_capture
from app.models import Anomaly, IngestedMessage, Transaction, User


def _demo_id():
    with session_scope() as db:
        return db.scalar(select(User.id).where(User.is_demo.is_(True)))


def test_capture_matches_ground_truth(demo):
    r = evaluate_capture(_demo_id(), date.today())
    assert r["captured"] == r["truth_transactions"]
    assert r["dedup_precision"] >= 0.98
    assert r["dedup_recall"] >= 0.95
    assert r["transfer_recall"] >= 0.98
    assert r["false_transfers"] == 0
    assert r["category_accuracy"] >= 0.95
    assert r["receipts_linked_correctly"] >= 0.95
    assert r["reversal_detected"] == 1


def test_no_transaction_comes_from_otp_or_promo(demo):
    with session_scope() as db:
        bad = db.scalar(select(func.count()).select_from(IngestedMessage).where(
            IngestedMessage.kind.in_(("otp", "promo")), IngestedMessage.transaction_id.is_not(None)))
        stored = db.scalar(select(func.count()).select_from(IngestedMessage).where(IngestedMessage.kind.in_(("otp", "promo", "other"))))
    assert bad == 0
    assert stored == 0  # minimisation: not even stored


def test_transfers_and_card_payments_are_not_spending(demo):
    with session_scope() as db:
        rows = db.scalars(select(Transaction).where(Transaction.user_id == _demo_id(), Transaction.is_transfer.is_(True))).all()
    assert rows and all(t.merchant_name in ("Own account transfer", "Card bill payment") for t in rows)
    groups = {}
    for t in rows:
        groups.setdefault(t.transfer_group, []).append(t)
    paired = [g for g in groups.values() if len(g) == 2]
    assert len(paired) >= 0.9 * len(groups)


def test_planted_anomalies_found_without_noise(demo):
    with session_scope() as db:
        rows = db.execute(select(Anomaly.detector, Transaction.merchant_name).join(Transaction).where(Anomaly.user_id == _demo_id())).all()
    found = {(d, m) for d, m in rows}
    assert ("duplicate", "Zomato") in found
    assert any(m == "Croma" for _, m in found)
    assert any(m.lower().startswith("quickfix") for _, m in found)
    assert {m for _, m in found} <= {"Zomato", "Croma", "Quickfix Appliances"}


def test_refund_emails_attach_to_the_refund_not_the_purchase(demo):
    """Regression: a refund email shares its order number with the purchase receipt, but it belongs to the credit."""
    with session_scope() as db:
        refunds = db.scalars(select(IngestedMessage).where(IngestedMessage.user_id == _demo_id(), IngestedMessage.kind == "refund",
                                                           IngestedMessage.channel == "email", IngestedMessage.transaction_id.is_not(None))).all()
        assert refunds
        assert all(db.get(Transaction, m.transaction_id).direction == "credit" for m in refunds)
    r = evaluate_capture(_demo_id(), date.today())
    assert r["dedup_precision"] == 1.0 and r["dedup_recall"] == 1.0
