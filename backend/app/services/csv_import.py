"""Bank-statement CSV import with column mapping. Rows are reconciled against transactions that already
arrived by SMS/email, so importing a statement never double-counts."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import D
from app.ml.text import normalize
from app.models import Account, ImportBatch, Transaction, User
from app.services.categorization import Categorizer

DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d-%b-%Y", "%d-%b-%y", "%d.%m.%Y"]


def read_rows(data: bytes) -> tuple[list[str], list[list[str]]]:
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("The file is empty.")
    # bank statements often have a preamble: the header is the first row that names a date column
    header_idx = next((i for i, r in enumerate(rows[:15]) if any("date" in c.lower() for c in r)), 0)
    header = [c.strip() for c in rows[header_idx]]
    return header, [r + [""] * (len(header) - len(r)) for r in rows[header_idx + 1:]]


def guess_mapping(header: list[str]) -> dict[str, str | None]:
    low = [h.lower() for h in header]

    def find(*keys: str) -> str | None:
        for k in keys:
            for h, l in zip(header, low):
                if k in l:
                    return h
        return None

    return {
        "date": find("txn date", "transaction date", "value date", "date"),
        "description": find("narration", "description", "particulars", "details", "remarks"),
        "debit": find("withdrawal", "debit", "dr"),
        "credit": find("deposit", "credit", "cr"),
        "amount": None if find("withdrawal", "debit") else find("amount"),
        "reference": find("ref", "chq", "cheque"),
    }


def parse_date(value: str) -> date | None:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(value: str) -> Decimal | None:
    v = re.sub(r"[^\d.\-]", "", (value or "").replace(",", ""))
    if not v or v in ("-", "."):
        return None
    try:
        return D(v)
    except (ValueError, InvalidOperation):
        return None


@dataclass
class Result:
    imported: int = 0
    duplicates: int = 0
    skipped: int = 0


def commit_csv(db: Session, user: User, filename: str, header: list[str], rows: list[list[str]], mapping: dict[str, Any],
               account_id: int | None) -> Result:
    idx = {k: header.index(v) for k, v in mapping.items() if v and v in header}
    if "date" not in idx or "description" not in idx or not ({"amount", "debit", "credit"} & idx.keys()):
        raise ValueError("Map at least the date, description and amount (or debit/credit) columns.")
    acct = db.get(Account, account_id) if account_id else None
    if acct is not None and acct.user_id != user.id:
        raise ValueError("Unknown account")
    cat = Categorizer(db, user.id)
    res = Result()
    for r in rows:
        d = parse_date(r[idx["date"]])
        desc = r[idx["description"]].strip()
        amount, direction = None, None
        if "amount" in idx:
            a = parse_amount(r[idx["amount"]])
            if a is not None:
                amount, direction = abs(a), ("credit" if a > 0 else "debit")
        else:
            dr = parse_amount(r[idx["debit"]]) if "debit" in idx else None
            cr = parse_amount(r[idx["credit"]]) if "credit" in idx else None
            if dr:
                amount, direction = abs(dr), "debit"
            elif cr:
                amount, direction = abs(cr), "credit"
        if not d or not amount or not desc:
            res.skipped += 1
            continue
        ref = r[idx["reference"]].strip() if "reference" in idx else None
        # reconcile: the same payment may already have arrived as an SMS/email alert
        cands = db.scalars(select(Transaction).where(
            Transaction.user_id == user.id, Transaction.amount == amount, Transaction.direction == direction,
            Transaction.txn_date >= d - timedelta(days=1), Transaction.txn_date <= d + timedelta(days=1))).all()
        dup = None
        for c in cands:
            if acct and c.account_id and c.account_id != acct.id:
                continue
            if ref and c.ref_no and ref in c.ref_no:
                dup = c
                break
            if fuzz.partial_ratio(normalize(desc), normalize(f"{c.description} {c.merchant_name} {c.counterparty or ''}")) >= 60 or len(cands) == 1:
                dup = c
                break
        if dup is not None:
            res.duplicates += 1
            continue
        c = cat.categorize(desc)
        db.add(Transaction(user_id=user.id, account_id=acct.id if acct else None, txn_date=d, occurred_at=datetime.combine(d, time(12)),
                           amount=amount, direction=direction, description=desc[:255], merchant_id=c.merchant_id, merchant_name=c.merchant_name,
                           category_id=c.category_id, category_source=c.source, category_confidence=c.confidence, origin="csv", ref_no=ref or None,
                           needs_review=c.category_name == "Misc"))
        res.imported += 1
    db.add(ImportBatch(user_id=user.id, kind="csv", filename=filename[:200], total=len(rows), imported=res.imported,
                       duplicates=res.duplicates, ignored=res.skipped))
    db.flush()
    return res
