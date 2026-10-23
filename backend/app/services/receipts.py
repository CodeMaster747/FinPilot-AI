"""Receipt & bill field extraction from OCR output (tesseract.js runs in the browser) or PDF text.

Every field is {value, confidence, bbox}; confidence below 0.8 is highlighted for the user to check.
Heuristics: merchant = most confident top-region line (matched against the alias map); total = keyword
anchors (GRAND TOTAL / NET PAYABLE / TOTAL) -> rightmost amount, cross-checked against the item sum; date =
multi-format regex; GSTIN = format regex; line items = description + trailing amount rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import D
from app.ml.text import normalize
from app.models import Merchant, MerchantAlias, Receipt, Transaction, TransactionItem, UpcomingPayment, User
from app.services.categorization import Categorizer, display_name

AMOUNT = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})|\d+\.\d{2}|\d{2,7})(?![\d])")
GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
IGNORE_MERCHANT = re.compile(r"(?i)(gst|invoice|bill|tax|date|time|phone|ph[:.]|tel|cashier|receipt|address|road|street|nagar|www|@|"
                             r"thank|visit|no\.|order|table|token|customer)")
TOTAL_KEYS = [(re.compile(r"(?i)grand\s*total"), 1.0), (re.compile(r"(?i)net\s*(?:payable|amount|amt)"), 0.97),
              (re.compile(r"(?i)amount\s*payable|total\s*payable|bill\s*amount|total\s*amount"), 0.95),
              (re.compile(r"(?i)\btotal\b"), 0.9)]
NOT_TOTAL = re.compile(r"(?i)sub\s*-?\s*total|total\s*(qty|quantity|items?|savings|discount)|you\s*saved|tax\s*total")
ITEM_EXCLUDE = re.compile(r"(?i)(total|tax|gst|cgst|sgst|igst|cash|change|card|upi|amount|round|discount|saved|balance|paid|tender|"
                          r"invoice|bill no|date|time|qty|mrp\s*$|hsn)")
DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b"), "dmY"), (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2})\b"), "dmy"),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "Ymd"), (re.compile(r"\b(\d{1,2})[ -]([A-Za-z]{3})[a-z]*[ -,]+(\d{2,4})\b"), "dMy"),
]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DUE_KEYS = re.compile(r"(?i)(due\s*date|pay\s*by|payment\s*due|last\s*date(?:\s*(?:of|for)\s*payment)?|due\s*on)")


@dataclass
class Line:
    text: str
    conf: float
    bbox: dict[str, float] | None
    y: float


def _lines(raw: list[dict[str, Any]]) -> list[Line]:
    out = []
    for i, ln in enumerate(raw):
        text = re.sub(r"\s+", " ", str(ln.get("text", ""))).strip()
        if not text:
            continue
        conf = float(ln.get("confidence", ln.get("conf", 80)) or 0)
        conf = conf / 100 if conf > 1 else conf
        bbox = ln.get("bbox")
        y = float(bbox["y0"]) if bbox else float(i)
        out.append(Line(text, max(0.0, min(1.0, conf)), bbox, y))
    out.sort(key=lambda ln: ln.y)
    return out


def _amounts(text: str) -> list[Decimal]:
    vals = []
    for m in AMOUNT.finditer(text.replace("₹", " ").replace("Rs.", " ").replace("Rs", " ")):
        try:
            vals.append(D(m.group(1)))
        except ValueError:
            continue
    return vals


def _date(text: str, future_days: int = 1) -> date | None:
    today = date.today()
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            try:
                if kind == "dmY":
                    d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                elif kind == "dmy":
                    d = date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
                elif kind == "Ymd":
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                else:
                    mon = MONTHS.get(m.group(2)[:3].lower())
                    if not mon:
                        continue
                    y = int(m.group(3))
                    d = date(y + 2000 if y < 100 else y, mon, int(m.group(1)))
            except ValueError:
                continue
            if today - timedelta(days=3 * 365) <= d <= today + timedelta(days=future_days):
                return d
    return None


def field(value: Any, conf: float, line: Line | None = None) -> dict[str, Any]:
    return {"value": value, "confidence": round(conf, 2), "bbox": line.bbox if line else None}


def extract_fields(db: Session, user: User, raw_lines: list[dict[str, Any]], full_text: str | None = None) -> dict[str, Any]:
    lines = _lines(raw_lines)
    if not lines and full_text:
        lines = _lines([{"text": t, "confidence": 90} for t in full_text.splitlines()])
    text = "\n".join(ln.text for ln in lines)
    out: dict[str, Any] = {}
    cat = Categorizer(db, user.id)
    n = len(lines)
    top = lines[: max(3, n // 3)]
    best, best_score = None, -1.0
    for idx, ln in enumerate(top):
        letters = sum(c.isalpha() for c in ln.text)
        if letters < 3 or IGNORE_MERCHANT.search(ln.text) or GSTIN.search(ln.text):
            continue
        alias = cat.match_alias(ln.text)
        score = ln.conf + (0.4 if alias else 0) + (0.15 if ln.text.isupper() else 0) - 0.06 * idx
        if score > best_score:
            best, best_score = (ln, alias), score
    if best:
        ln, alias = best
        out["merchant"] = field(alias.name if alias else display_name(ln.text), min(0.99, ln.conf * (1.0 if alias else 0.75)), ln)
        out["merchant_raw"] = ln.text
    for ln in lines:
        if DUE_KEYS.search(ln.text):
            continue  # a bill's due date is not the date it was issued
        d = _date(ln.text)
        if d:
            out["date"] = field(d.isoformat(), ln.conf, ln)
            break
    for i, ln in enumerate(lines):  # bills: "Due Date: 25/10/2026" (the date may sit on the next line)
        if DUE_KEYS.search(ln.text):
            d = _date(ln.text[DUE_KEYS.search(ln.text).end():], future_days=120) or (
                _date(lines[i + 1].text, future_days=120) if i + 1 < n else None)
            if d:
                out["due_date"] = field(d.isoformat(), ln.conf, ln)
                break
    total_line, total_val, total_conf = None, None, 0.0
    for prio_rx, weight in TOTAL_KEYS:
        for ln in reversed(lines):
            if prio_rx.search(ln.text) and not NOT_TOTAL.search(ln.text):
                vals = _amounts(ln.text)
                if vals:
                    total_line, total_val, total_conf = ln, vals[-1], ln.conf * weight
                    break
        if total_line:
            break
    if total_line is None:
        bottom = lines[int(n * 0.6):]
        cands = [(v, ln) for ln in bottom for v in _amounts(ln.text)]
        if cands:
            total_val, total_line = max(cands, key=lambda x: x[0])
            total_conf = total_line.conf * 0.55
    m = GSTIN.search(text)
    if m:
        ln = next((x for x in lines if m.group(0) in x.text), None)
        out["gstin"] = field(m.group(0), ln.conf if ln else 0.8, ln)
    for key in ("cgst", "sgst", "igst"):
        ln = next((x for x in lines if key in x.text.lower()), None)
        if ln and _amounts(ln.text):
            out[key] = field(str(_amounts(ln.text)[-1]), ln.conf, ln)
    items = []
    end_idx = lines.index(total_line) if total_line in lines else n
    start_idx = lines.index(best[0]) + 1 if best else 0
    for ln in lines[start_idx:end_idx]:
        if ITEM_EXCLUDE.search(ln.text) or GSTIN.search(ln.text) or _date(ln.text):
            continue
        mm = re.match(r"^(?P<desc>[A-Za-z][A-Za-z0-9 &'().,/%+-]{2,50}?)\s+(?:(?P<qty>\d+(?:\.\d+)?)\s*(?:x|@|nos|pcs|kg)?\s+)?"
                      r"(?:[\d,]+\.\d{2}\s+)?(?P<amt>\d[\d,]*\.\d{2})$", ln.text)
        if mm:
            items.append({"description": mm.group("desc").strip(" .:-"), "quantity": float(mm.group("qty") or 1),
                          "amount": str(D(mm.group("amt"))), "confidence": round(ln.conf, 2), "bbox": ln.bbox})
    if items:
        out["items"] = items
    if total_val is not None:
        item_sum = sum((D(i["amount"]) for i in items), Decimal(0))
        taxes = sum((D(out[k]["value"]) for k in ("cgst", "sgst", "igst") if k in out), Decimal(0))
        if items and (abs(item_sum - total_val) <= total_val * Decimal("0.02") or abs(item_sum + taxes - total_val) <= total_val * Decimal("0.02")):
            total_conf = max(total_conf, 0.97)  # items add up: strong evidence the total is right
        out["total"] = field(str(total_val), total_conf, total_line)
    return out


def suggest_match(db: Session, user: User, fields: dict[str, Any]) -> Transaction | None:
    if "total" not in fields:
        return None
    amount = D(fields["total"]["value"])
    day = date.fromisoformat(fields["date"]["value"]) if "date" in fields else date.today()
    cands = db.scalars(select(Transaction).where(
        Transaction.user_id == user.id, Transaction.direction == "debit", Transaction.is_transfer.is_(False),
        Transaction.amount >= amount * Decimal("0.99"), Transaction.amount <= amount * Decimal("1.01"),
        Transaction.txn_date >= day - timedelta(days=3), Transaction.txn_date <= day + timedelta(days=3))).all()
    linked = set(db.scalars(select(Receipt.transaction_id).where(Receipt.user_id == user.id, Receipt.transaction_id.is_not(None))).all())
    name = normalize((fields.get("merchant") or {}).get("value", ""))
    best, score = None, 0.0
    for t in cands:
        if t.id in linked:
            continue
        s = (1.0 if t.amount == amount else 0.8) + fuzz.partial_ratio(name, normalize(f"{t.merchant_name} {t.description}")) / 100 \
            - abs((t.txn_date - day).days) * 0.1
        if s > score:
            best, score = t, s
    return best


def commit(db: Session, user: User, receipt: Receipt, merchant: str, when: date, total: Decimal, items: list[dict[str, Any]],
           category_id: int | None, link_id: int | None) -> Transaction:
    cat = Categorizer(db, user.id)
    ocr_merchant = (receipt.fields or {}).get("merchant_raw") or ""
    # learning: if the user corrected the merchant, remember the OCR text as an alias for it
    if ocr_merchant and normalize(merchant) != normalize((receipt.fields or {}).get("merchant", {}).get("value", "")):
        m = db.scalar(select(Merchant).where(Merchant.name == merchant, Merchant.user_id.is_(None))) or db.scalar(
            select(Merchant).where(Merchant.name == merchant, Merchant.user_id == user.id))
        if m is None:  # a merchant the user named: private to them
            res = cat.categorize(merchant)
            m = Merchant(user_id=user.id, name=merchant, category_id=category_id or res.category_id)
            db.add(m)
            db.flush()
        pattern = normalize(ocr_merchant)
        if pattern and db.scalar(select(MerchantAlias).where(MerchantAlias.user_id == user.id, MerchantAlias.pattern == pattern)) is None:
            db.add(MerchantAlias(user_id=user.id, pattern=pattern, merchant_id=m.id, source="user"))
    txn = db.get(Transaction, link_id) if link_id else None
    if txn is not None and txn.user_id != user.id:
        txn = None
    if txn is None:
        res = cat.categorize(merchant)
        txn = Transaction(user_id=user.id, account_id=None, txn_date=when, occurred_at=datetime.combine(when, time(12)), amount=total,
                          direction="debit", description=f"{merchant} (scanned receipt)", merchant_id=res.merchant_id,
                          merchant_name=res.merchant_name if res.merchant_id else merchant, category_id=category_id or res.category_id,
                          category_source="user" if category_id else res.source, category_confidence=1.0 if category_id else res.confidence,
                          origin="receipt", notes="Created from a scanned receipt")
        db.add(txn)
        db.flush()
    elif category_id and category_id != txn.category_id:
        txn.category_id, txn.category_source = category_id, "user"
    if items and not any(i.source == "receipt" for i in txn.items):
        for it in items[:40]:
            txn.items.append(TransactionItem(description=str(it["description"])[:200], quantity=float(it.get("quantity", 1)),
                                             amount=D(it["amount"]), source="receipt"))
    receipt.transaction_id, receipt.status = txn.id, "committed"
    return txn


def save_as_bill(db: Session, user: User, receipt: Receipt, payee: str, amount: Decimal, due: date) -> UpcomingPayment:
    """An unpaid bill (a PDF electricity or broadband bill, say): it is money that will go out, not a payment yet.
    It appears in the forecast and is marked paid when the matching payment arrives."""
    up = db.scalar(select(UpcomingPayment).where(UpcomingPayment.user_id == user.id, UpcomingPayment.amount == amount,
                                                 UpcomingPayment.due_date == due))
    if up is None:
        up = UpcomingPayment(user_id=user.id, payee=payee[:120], kind="bill", amount=amount, due_date=due)
        db.add(up)
        db.flush()
    paid = db.scalar(select(Transaction).where(
        Transaction.user_id == user.id, Transaction.direction == "debit", Transaction.amount == amount,
        Transaction.txn_date >= due - timedelta(days=25), Transaction.txn_date <= due + timedelta(days=3)).limit(1))
    if paid is not None:
        up.status, up.transaction_id = "paid", paid.id
    receipt.status = "committed"
    return up
