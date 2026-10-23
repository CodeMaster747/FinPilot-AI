"""Four complementary anomaly detectors over reconciled spending (transfers and reversals excluded).

- robust z-score per category (median + MAD): out-of-pattern amounts
- Isolation Forest over [log amount, day of month, category, merchant frequency]: unusual combinations
- duplicate charges: two separate payments, same merchant and amount, within 2 hours
- new merchant + large amount: first-ever payment to a merchant that is unusually big
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.money import fmt_inr
from app.models import Anomaly, Category, Transaction

NEW_MERCHANT_AFTER_DAYS = 60
WINDOW_DAYS = 180


def _spending(db: Session, user_id: int) -> list[tuple[Transaction, Category]]:
    rows = db.execute(
        select(Transaction, Category).join(Category, Category.id == Transaction.category_id).where(
            Transaction.user_id == user_id, Transaction.direction == "debit", Transaction.status == "posted",
            Transaction.is_transfer.is_(False), Category.kind == "expense")
        .order_by(Transaction.txn_date, Transaction.id)
    ).all()
    return [(t, c) for t, c in rows]


def detect_anomalies(db: Session, user_id: int, today: date | None = None) -> dict:
    today = today or date.today()
    since = today - timedelta(days=WINDOW_DAYS)
    rows = _spending(db, user_id)
    if len(rows) < 20:
        return {"flagged": 0}
    found: dict[tuple[int, str], tuple[float, str, str]] = {}

    def flag(txn: Transaction, detector: str, score: float, severity: str, text: str) -> None:
        if txn.txn_date >= since:
            found[(txn.id, detector)] = (score, severity, text)

    # 1) robust z-score against the merchant's own history (else the category's): only prior payments
    by_cat: dict[int, list[Transaction]] = defaultdict(list)
    by_merchant: dict[str, list[Transaction]] = defaultdict(list)
    cat_names = {c.id: c.name for _, c in rows}
    for t, c in rows:
        by_cat[c.id].append(t)
        by_merchant[t.merchant_name].append(t)
    for t, c in rows:
        if t.txn_date < since:
            continue
        own = [x for x in by_merchant[t.merchant_name] if x.txn_date < t.txn_date]
        base = own if len(own) >= 4 else [x for x in by_cat[c.id] if x.txn_date < t.txn_date]
        if len(base) < 8 and base is not own:
            continue
        amounts = np.array([float(x.amount) for x in base])
        med = float(np.median(amounts))
        mad = float(np.median(np.abs(amounts - med))) or max(med * 0.1, 1.0)
        p90 = float(np.percentile(amounts, 90))
        z = 0.6745 * (float(t.amount) - med) / mad
        if z > 8 and float(t.amount) >= 2000 and float(t.amount) > 2.5 * p90:
            what = f"your usual {t.merchant_name} payment" if base is own else f"your typical {cat_names[c.id]} payment"
            flag(t, "robust_z", round(z, 1), "high" if float(t.amount) >= 20000 else "medium",
                 f"{fmt_inr(t.amount)} at {t.merchant_name} is {float(t.amount) / med:.0f}× {what} ({fmt_inr(Decimal(str(round(med))))}).")

    # 2) Isolation Forest
    merchant_freq: dict[str, int] = defaultdict(int)
    for t, _ in rows:
        merchant_freq[t.merchant_name] += 1
    cat_index = {cid: i for i, cid in enumerate(sorted(by_cat))}
    X = np.array([[math.log1p(float(t.amount)), t.txn_date.day / 31, cat_index[c.id] / max(1, len(cat_index)),
                   math.log1p(merchant_freq[t.merchant_name])] for t, c in rows])
    forest = IsolationForest(n_estimators=200, contamination=0.01, random_state=7).fit(X)
    scores = forest.decision_function(X)
    for (t, c), s, pred in zip(rows, scores, forest.predict(X)):
        if pred == -1 and float(t.amount) >= 3000:
            flag(t, "isolation_forest", round(float(-s), 3), "medium",
                 f"Unusual combination: {fmt_inr(t.amount)} to {t.merchant_name} ({c.name}) doesn't fit your usual pattern.")

    # 3) duplicate charges (distinct payments: reconciliation already merged alerts for the same payment)
    by_key: dict[tuple[str, Decimal], list[Transaction]] = defaultdict(list)
    for t, c in rows:
        if c.name != "Cash Withdrawal":  # two same-sized ATM withdrawals are normal
            by_key[(t.merchant_name, t.amount)].append(t)
    for (merchant, amount), txns in by_key.items():
        txns.sort(key=lambda t: (t.occurred_at or t.txn_date, t.id))
        for a, b in zip(txns, txns[1:]):
            if a.occurred_at and b.occurred_at:
                gap = (b.occurred_at - a.occurred_at).total_seconds() / 3600
            else:
                gap = abs((b.txn_date - a.txn_date).days) * 24
            if gap <= 2 and (not a.ref_no or not b.ref_no or a.ref_no != b.ref_no):
                when = f"{gap * 60:.0f} minutes" if gap < 1 else f"{gap:.1f} hours"
                flag(b, "duplicate", 1.0, "high", f"{fmt_inr(amount)} was charged twice by {merchant} within {when}. Check whether one should be refunded.")

    # 4) first-ever payment to a merchant that is unusually large — only once there's enough history for "first ever"
    # to mean something (right after the first SMS backfill, every merchant is "new")
    seen: set[str] = set()
    typical = float(np.median([float(t.amount) for t, _ in rows]))
    history_start = rows[0][0].txn_date
    for t, c in rows:
        established = (t.txn_date - history_start).days >= NEW_MERCHANT_AFTER_DAYS
        if established and t.merchant_name not in seen and float(t.amount) >= max(5000.0, 8 * typical):
            flag(t, "new_merchant", round(float(t.amount) / typical, 1), "high" if float(t.amount) >= 20000 else "medium",
                 f"First ever payment to {t.merchant_name} — {fmt_inr(t.amount)}, much larger than your usual spends.")
        seen.add(t.merchant_name)

    keep = {(a.transaction_id, a.detector): a for a in db.scalars(select(Anomaly).where(
        Anomaly.user_id == user_id, Anomaly.status != "open")).all()}
    db.execute(delete(Anomaly).where(Anomaly.user_id == user_id, Anomaly.status == "open"))
    added = 0
    for (txn_id, detector), (score, severity, text) in found.items():
        if (txn_id, detector) in keep:
            continue
        db.add(Anomaly(user_id=user_id, transaction_id=txn_id, detector=detector, score=float(score), severity=severity,
                       explanation=text[:300]))
        added += 1
    db.flush()
    return {"flagged": added}
