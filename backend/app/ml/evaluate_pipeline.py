"""End-to-end capture evaluation against the persona's ground truth (dedup, transfers, categories)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime

from sqlalchemy import select

from app.db.session import session_scope
from app.models import Category, IngestedMessage, Transaction


def evaluate_capture(user_id: int, end: date, cutoff: datetime | None = None, seed: int = 7) -> dict:
    from app.seed.emails import render_emails
    from app.seed.persona import build_persona
    from app.seed.sms import render_sms

    if cutoff is None:
        with session_scope() as db:
            from app.models import User

            stamp = ((db.get(User, user_id).preferences or {}).get("demo_generated_at"))
        cutoff = datetime.fromisoformat(stamp) if stamp else None
    persona = build_persona(end, seed=seed, cutoff=cutoff)
    truth = persona.by_id()
    msgs = render_sms(persona) + render_emails(persona)
    by_ext = {m.external_id: m for m in msgs}
    with session_scope() as db:
        rows = db.execute(select(IngestedMessage.external_id, IngestedMessage.transaction_id, IngestedMessage.match_role)
                          .where(IngestedMessage.user_id == user_id)).all()
        txns = {t.id: t for t in db.scalars(select(Transaction).where(Transaction.user_id == user_id)).all()}
        cats = {c.id: c.name for c in db.scalars(select(Category)).all()}
    truth_to_db: dict[str, set[int]] = defaultdict(set)
    db_to_truth: dict[int, set[str]] = defaultdict(set)
    for ext, txn_id, role in rows:
        m = by_ext.get(ext)
        if m is None or not m.truth or not m.truth.get("txn_id") or not txn_id or role == "reversal":
            continue
        tid = m.truth["txn_id"]
        truth_to_db[tid].add(txn_id)
        db_to_truth[txn_id].add(tid)
    expected = [t for t in truth.values() if t.kind != "reversal"]
    captured = [t for t in expected if t.id in truth_to_db]
    one_to_one = sum(1 for t in captured if len(truth_to_db[t.id]) == 1)
    pure = sum(1 for ids in db_to_truth.values() if len(ids) == 1)
    transfer_truth = [t for t in captured if t.kind in ("transfer_out", "transfer_in", "card_payment", "card_payment_in")]
    transfer_ok = sum(1 for t in transfer_truth if all(txns[i].is_transfer for i in truth_to_db[t.id]))
    false_transfer = sum(1 for t in captured if t.kind not in ("transfer_out", "transfer_in", "card_payment", "card_payment_in")
                         and any(txns[i].is_transfer for i in truth_to_db[t.id]))
    cat_cases = [t for t in captured if t.kind in ("spend", "income", "refund") and len(truth_to_db[t.id]) == 1]
    cat_ok = sum(1 for t in cat_cases if cats.get(txns[next(iter(truth_to_db[t.id]))].category_id) == t.category)
    misses = Counter(cats.get(txns[next(iter(truth_to_db[t.id]))].category_id) + " <- " + t.category
                     for t in cat_cases if cats.get(txns[next(iter(truth_to_db[t.id]))].category_id) != t.category)
    receipts = [m for m in msgs if m.truth and m.truth["kind"] == "order_receipt" and m.truth.get("txn_id")]
    linked = {ext: txn_id for ext, txn_id, role in rows if role == "enrichment"}
    receipt_ok = sum(1 for m in receipts if m.external_id in linked and m.truth["txn_id"] in db_to_truth.get(linked[m.external_id], set()))
    reversed_ok = sum(1 for t in truth.values() if "reversed" in t.tags and any(txns[i].status == "reversed" for i in truth_to_db.get(t.id, ())))
    return {
        "truth_transactions": len(expected),
        "captured": len(captured),
        "db_transactions": len(txns),
        "dedup_recall": round(one_to_one / max(1, len(captured)), 4),  # each real payment -> exactly one record
        "dedup_precision": round(pure / max(1, len(db_to_truth)), 4),  # each record -> exactly one real payment
        "transfer_recall": round(transfer_ok / max(1, len(transfer_truth)), 4),
        "false_transfers": false_transfer,
        "category_accuracy": round(cat_ok / max(1, len(cat_cases)), 4),
        "category_misses": dict(misses.most_common(8)),
        "receipts_linked_correctly": round(receipt_ok / max(1, len(receipts)), 4),
        "receipts": len(receipts),
        "reversal_detected": reversed_ok,
    }
