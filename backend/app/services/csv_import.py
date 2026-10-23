"""Bank-statement import (CSV, Excel .xlsx and older .xls, as Indian banks export them) with column mapping.
Rows are reconciled against transactions that already arrived by SMS/email, so importing a statement never
double-counts. A mapped balance column becomes the account's balance."""

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

DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d-%b-%Y", "%d-%b-%y", "%d.%m.%Y",
                "%d.%m.%y", "%d %b %y", "%d/%b/%Y", "%b %d, %Y", "%d %B %Y", "%Y/%m/%d"]
HEADER_HINTS = ("narration", "description", "particulars", "details", "remarks", "debit", "withdrawal", "credit", "deposit",
                "amount", "balance", "chq", "ref")
XLSX_MAGIC, XLS_MAGIC = b"PK\x03\x04", b"\xd0\xcf\x11\xe0"


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float):
        return f"{value:.2f}" if value != int(value) else str(int(value))
    return str(value).strip()


def _excel_rows(data: bytes) -> list[list[str]]:
    if data.startswith(XLSX_MAGIC):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    import xlrd

    book = xlrd.open_workbook(file_contents=data)
    sheet = book.sheet_by_index(0)
    rows = []
    for r in range(sheet.nrows):
        out = []
        for c in range(sheet.ncols):
            cell = sheet.cell(r, c)
            if cell.ctype == xlrd.XL_CELL_DATE:
                out.append(_cell(xlrd.xldate_as_datetime(cell.value, book.datemode)))
            else:
                out.append(_cell(cell.value))
        rows.append(out)
    return rows


def _text_rows(data: bytes) -> list[list[str]]:
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), dialect)]


def read_rows(data: bytes) -> tuple[list[str], list[list[str]]]:
    """(header, data rows) from a CSV or Excel statement. Bank statements start with a preamble (name, address,
    period…); the header is the first row naming a date column and at least one money or description column."""
    try:
        rows = _excel_rows(data) if data.startswith((XLSX_MAGIC, XLS_MAGIC)) else _text_rows(data)
    except Exception as exc:  # noqa: BLE001 - corrupt or password-protected workbook
        raise ValueError("Couldn't read that file. Export the statement as CSV or Excel (.xlsx/.xls) without a password.") from exc
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("The file is empty.")

    def looks_like_header(r: list[str]) -> bool:
        low = [c.lower() for c in r]
        return any("date" in c for c in low) and any(any(h in c for h in HEADER_HINTS) for c in low)

    header_idx = next((i for i, r in enumerate(rows[:40]) if looks_like_header(r)), None)
    if header_idx is None:
        header_idx = next((i for i, r in enumerate(rows[:40]) if any("date" in c.lower() for c in r)), 0)
    header = [c.strip() or f"Column {i + 1}" for i, c in enumerate(rows[header_idx])]
    body = [r + [""] * (len(header) - len(r)) for r in rows[header_idx + 1:]]
    return header, [r[: len(header)] for r in body]


def guess_mapping(header: list[str]) -> dict[str, str | None]:
    low = [h.lower() for h in header]

    def find(*keys: str, exclude: tuple[str, ...] = ()) -> str | None:
        for k in keys:
            for h, l in zip(header, low):
                if k in l and not any(x in l for x in exclude):
                    return h
        return None

    debit = find("withdrawal", "debit", "dr amount", "dr.", exclude=("card",))
    return {
        "date": find("txn date", "transaction date", "tran date", "value date", "date"),
        "description": find("narration", "description", "particulars", "details", "remarks", "transaction remarks"),
        "debit": debit,
        "credit": find("deposit", "credit", "cr amount", "cr.", exclude=("card",)),
        "amount": None if debit else find("amount"),
        "reference": find("ref", "chq", "cheque", "utr"),
        "balance": find("closing balance", "balance", "bal"),
    }


def parse_date(value: str) -> date | None:
    value = value.strip()
    value = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?(\s*[AP]M)?$", "", value, flags=re.I)  # drop a trailing time
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(value: str) -> Decimal | None:
    """Signed amount: "(1,234.00)" and "1,234.00 Dr" are negative, "1,234.00 Cr" positive."""
    raw = (value or "").strip()
    if not raw:
        return None
    negative = raw.startswith("(") and raw.endswith(")") or bool(re.search(r"(?i)\bdr\.?$", raw)) or raw.startswith("-")
    v = re.sub(r"[^\d.]", "", raw.replace(",", ""))
    if not v or v == "." or v.count(".") > 1:
        return None
    try:
        amount = D(v)
    except (ValueError, InvalidOperation):
        return None
    return -amount if negative else amount


@dataclass
class Result:
    imported: int = 0
    duplicates: int = 0
    skipped: int = 0
    balance_set: bool = False


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
    balances: list[tuple[date, int, Decimal]] = []
    for row_no, r in enumerate(rows):
        d = parse_date(r[idx["date"]])
        desc = r[idx["description"]].strip()
        amount, direction = None, None
        if "amount" in idx:
            a = parse_amount(r[idx["amount"]])
            if a is not None and a != 0:
                amount, direction = abs(a), ("credit" if a > 0 else "debit")
        else:
            dr = parse_amount(r[idx["debit"]]) if "debit" in idx else None
            cr = parse_amount(r[idx["credit"]]) if "credit" in idx else None
            if dr:
                amount, direction = abs(dr), "debit"
            elif cr:
                amount, direction = abs(cr), "credit"
        if "balance" in idx and d:
            bal = parse_amount(r[idx["balance"]])
            if bal is not None:
                balances.append((d, row_no, bal))
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
            if ref and c.ref_no and (ref in c.ref_no or c.ref_no in ref):
                dup = c
                break
            if fuzz.partial_ratio(normalize(desc), normalize(f"{c.description} {c.merchant_name} {c.counterparty or ''}")) >= 60 or len(cands) == 1:
                dup = c
                break
        if dup is not None:
            if acct and dup.account_id is None:
                dup.account_id = acct.id
            res.duplicates += 1
            continue
        c = cat.categorize(desc, direction=direction, hint=desc)
        db.add(Transaction(user_id=user.id, account_id=acct.id if acct else None, txn_date=d, occurred_at=datetime.combine(d, time(12)),
                           amount=amount, direction=direction, description=desc[:255], merchant_id=c.merchant_id, merchant_name=c.merchant_name,
                           category_id=c.category_id, category_source=c.source, category_confidence=c.confidence, origin="csv", ref_no=ref or None,
                           needs_review=c.category_name == "Misc"))
        res.imported += 1
    db.flush()
    if acct is not None and balances:
        # the statement's closing balance: the latest date; on that date, the row printed last in date order
        ascending = balances[0][0] <= balances[-1][0]
        last_day = max(b[0] for b in balances)
        same_day = [b for b in balances if b[0] == last_day]
        closing = (max if ascending else min)(same_day, key=lambda b: b[1])[2]
        from app.services.accounts import set_balance

        set_balance(db, user.id, acct, closing, datetime.combine(last_day, time(23, 59, 59)), "statement")
        res.balance_set = True
    db.add(ImportBatch(user_id=user.id, kind="csv", filename=filename[:200], total=len(rows), imported=res.imported,
                       duplicates=res.duplicates, ignored=res.skipped))
    db.flush()
    return res
