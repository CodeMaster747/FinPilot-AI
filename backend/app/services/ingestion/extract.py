"""Field extraction: per-bank templates first (precise), a generic extractor for unknown formats.

Every field is returned as {value, confidence, span} — the same contract the OCR pipeline uses — so
the review screen can highlight exactly where a value came from and flag low-confidence fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from bs4 import BeautifulSoup

from app.core.money import D
from app.services.ingestion.types import RawMessage
from app.services.jsonld import extract_jsonld, of_type

TEMPLATE_FILE = Path(__file__).with_name("templates.yaml")

BANKS = {
    "HDFCBK": "HDFC Bank", "HDFCBN": "HDFC Bank", "ICICIT": "ICICI Bank", "ICICIB": "ICICI Bank", "ICICIO": "ICICI Bank",
    "SBIINB": "State Bank of India", "SBIUPI": "State Bank of India", "SBIPSG": "State Bank of India", "ATMSBI": "State Bank of India",
    "CBSSBI": "State Bank of India", "SBIBNK": "State Bank of India", "SBMSMS": "State Bank of India", "SBIOTP": "State Bank of India",
    "SBICRD": "SBI Card", "SBICRT": "SBI Card", "AXISBK": "Axis Bank", "AXISMR": "Axis Bank", "KOTAKB": "Kotak Mahindra Bank",
    "KOTAKM": "Kotak Mahindra Bank", "IDFCFB": "IDFC FIRST Bank", "YESBNK": "Yes Bank", "PNBSMS": "Punjab National Bank",
    "PUNBNK": "Punjab National Bank", "CANBNK": "Canara Bank", "BOBTXN": "Bank of Baroda", "BOBSMS": "Bank of Baroda",
    "BOBCRD": "BOBCARD", "INDUSB": "IndusInd Bank", "PAYTMB": "Paytm Payments Bank", "AUBANK": "AU Small Finance Bank",
    "FEDBNK": "Federal Bank", "UNIONB": "Union Bank of India", "AMEXIN": "American Express", "SCBANK": "Standard Chartered",
    "INDBNK": "Indian Bank", "IOBCHN": "Indian Overseas Bank", "IOBSMS": "Indian Overseas Bank", "CENTBK": "Central Bank of India",
    "BOIIND": "Bank of India", "UCOBNK": "UCO Bank", "RBLBNK": "RBL Bank", "RBLCRD": "RBL Bank", "DBSBNK": "DBS Bank",
    "HSBCIN": "HSBC", "CITIBK": "Citibank", "IDBIBK": "IDBI Bank", "KVBANK": "Karur Vysya Bank", "CUBANK": "City Union Bank",
    "TMBANK": "Tamilnad Mercantile Bank", "SIBSMS": "South Indian Bank", "KBLBNK": "Karnataka Bank", "EQUTAS": "Equitas Small Finance Bank",
    "UJJIVN": "Ujjivan Small Finance Bank", "AIRBNK": "Airtel Payments Bank", "ONECRD": "OneCard", "JUPITR": "Jupiter",
    "FIMONY": "Fi Money", "BAJAJF": "Bajaj Finance", "IHMCLF": "FASTag",
}
DOMAIN_BANKS = {"hdfcbank": "HDFC Bank", "icicibank": "ICICI Bank", "sbi": "State Bank of India", "axisbank": "Axis Bank"}
BILLERS = {"TNPDCL": "TNPDCL", "AIRTEL": "Airtel", "ACTFBR": "ACT Fibernet", "JIOINF": "Jio", "BESCOM": "BESCOM",
           "TATAPW": "Tata Power", "VFIDEA": "Vi"}

MONEY = re.compile(r"(?i)(?:rs\.?|inr|₹)\s?[:.]?\s?([0-9][0-9,]*(?:\.\d{1,2})?)")
BARE_AMOUNT = re.compile(r"(?i)\b(?:debited|credited|spent|paid|sent|received|withdrawn)\s+(?:by|with|for|of)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)\b")
BAL_BEFORE = re.compile(r"(?i)(avl\.?\s*bal\.?(?:ance)?|available\s+bal(?:ance)?|a/c\s+bal(?:ance)?|bal(?:ance)?\s+(?:is|of)|balance)[\s:\-]*(?:is|was|of)?[\s:\-]*$")
LIMIT_BEFORE = re.compile(r"(?i)(avl\.?\s*lmt|avl\.?\s*limit|available\s+(?:credit\s+)?limit|credit\s+limit)[\s:\-]*(?:is)?[\s:\-]*$")
DUE_BEFORE = re.compile(r"(?i)(minimum|min\.?)\s*(?:amount|amt)?\s*due[\s:\-]*$")
DEBIT_WORDS = re.compile(r"(?i)\b(debited|debit(?!\s*card)|spent|sent|paid|withdrawn|purchase|deducted|charged|has been used|used for|for using|money transferred|transferred from|dr\b)")
CREDIT_WORDS = re.compile(r"(?i)\b(credited|received|deposited|refund(?:ed)?|added to|has a credit|a credit of|credit by|cr\b)")
MASK_RES = [
    re.compile(r"(?i)\b(?:a/?c|ac|acct|account|card)\b[^\d\n]{0,24}?[x*.]{1,10}\s?(\d{3,5})\b"),
    re.compile(r"(?i)\b(?:a/?c|ac|acct|account)\b[^\d\n]{0,14}?\d[x*]{2,10}(\d{3,4})\b"),  # "A/C 2XXXXX1188"
    re.compile(r"(?i)\bcard\s+(?:no\.?\s*)?(\d{4})\b"),
    re.compile(r"(?i)\bending\s*(?:with|in)?\s*[x*]*(\d{4,5})\b"),
]
REF_RE = re.compile(
    r"(?i)\b(?:upi\s*ref(?:erence)?(?:\s*no\.?)?|ref(?:erence)?(?:\s*(?:no\.?|number))?|refno|rrn|utr|txn\s*(?:id|no\.?)|"
    r"transaction\s*(?:id|reference\s*number))\s*(?:is)?\s*[:#.]?\s*([A-Z0-9]{6,22})"
)
SLASH_REF = re.compile(r"(?i)\b(?:UPI|NEFT|IMPS|RTGS)(?:/(?:P2[AMP]|CR|DR|MOB))?/([A-Z0-9]{6,24})/([^/\n]{2,48})")
DASH_REF = re.compile(r"(?i)\bUPI-(\d{6,22})-([^.\n]{2,48})")
REFUND_OF = re.compile(r"(?i)\brefund\s+of\s+(?:UPI|IMPS|NEFT)?[/ :-]*(\d{6,22})")
VPA_RE = re.compile(r"\b([a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,})\b(?!\.[a-z])")
PAYEE_RES = [
    re.compile(r"(?i)\b(?:Ach D|ACH DR|NACH|ECS|SI)\s?-\s*([A-Za-z][^-\n]{1,48}?)(?:\s*-|\.\s|\s+Ref\b|$)"),
    re.compile(r"(?i)\bNEFT\s*Cr-\w+-([^-\n]{2,60}?)-"),
    re.compile(r"(?i)\bNEFT\s*-\s*(?:[A-Z0-9]*\d[A-Z0-9]*-)?([A-Za-z][^-\n]{2,60}?)(?:-|\.\s|\s+on\b|\.$|$)"),
    re.compile(r"(?i);\s*([A-Za-z][A-Za-z0-9 .&'-]{1,48}?)\s+credited\b"),
    re.compile(r"(?i)\b(?:autopay|auto pay|e-?mandate|mandate)\s+(?:of|for|towards)\s+([A-Za-z][A-Za-z0-9 .&'-]{1,48}?)(?:\.\s|\.$|\s+UPI\b|\s+on\b|,|$)"),
    re.compile(r"(?i)\btransferred to\s+(?:MR\.?|MRS\.?|MS\.?|M/S\.?)?\s*([A-Za-z][A-Za-z .&'-]{1,48}?)(?:\.\s|\.$|\s+Avl|\s+on\b|$)"),
    re.compile(r"(?i)\btransfer from\s+([A-Za-z][A-Za-z .&'-]{1,48}?)\s+Ref"),
    re.compile(r"(?i)\btrf to\s+(.+?)\s+(?:refno|ref)\b"),
    re.compile(r"(?i)\bInfo[:\-]\s*(?:(?:UPI|NEFT|IMPS)/[^/\s]*/)?([^.\n]{2,48})"),
    re.compile(r"(?i)\btowards\s+(.+?)(?:\s+ref\b|\.\s|\.$|$)"),
    re.compile(r"(?m)^\s*To\s+([^\n]{2,48})$"),
    re.compile(r"(?i)(?:\bat|@)\s*([A-Za-z0-9][A-Za-z0-9 &'.*\-]{2,40}?)(?:\s+on\b|\.\s|\.$|,|\n|$)"),
    re.compile(r"(?i)\bto\s+(?:VPA\s+)?(?!your\b|a/c\b|ac\b)([A-Za-z][A-Za-z0-9 &'.\-]{2,40}?)(?:\s+on\b|\s+via\b|\s+ref\b|\s+from\b|,|\.\s|\.$|\n|$)"),
    re.compile(r"(?i)\bfrom\s+(?!your\b|a/c\b|ac\b)([A-Za-z][A-Za-z0-9 &'.\-]{2,40}?)(?:\s+on\b|\s+has\b|\.\s|\.$|\n|$)"),
]
# words that are never a payee ("subject to clearing", "towards refund of …", "to your a/c")
NOT_PAYEE = re.compile(r"(?i)^(your|the|a/c|ac|account|card|clearing|refund(?: of)?|self|transfer|upi|neft|imps|rtgs|"
                       r"cash deposit|branch|mob bk|net ?banking|atm|bank|vpa|.*\d{6,}.*)$")
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b")
DATE_RES = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})[- ]?([A-Za-z]{3})[a-z]*[- ,]?\s?'?(\d{2,4})\b"), "dMy"),
    (re.compile(r"\b([A-Za-z]{3})[a-z]*\.? (\d{1,2}),? (\d{4})\b"), "Mdy"),
]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
TOTAL_RE = re.compile(r"(?i)(order total|total paid|total amount|amount paid|grand total|total)\s*[:\-]?\s*(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.\d{1,2})?)")
ORDER_RE = re.compile(r"(?i)\border\s*(?:no\.?|id|number|#)\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{5,})")


@dataclass
class Extraction:
    parser: str
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    channel: str | None = None
    account_kind: str | None = None
    institution: str | None = None

    def set(self, name: str, value: Any, confidence: float, span: tuple[int, int] | None = None) -> None:
        if value is None or value == "":
            return
        self.fields[name] = {"value": value, "confidence": round(confidence, 2), "span": list(span) if span else None}

    def get(self, name: str, default: Any = None) -> Any:
        f = self.fields.get(name)
        return f["value"] if f else default

    def conf(self, name: str) -> float:
        f = self.fields.get(name)
        return f["confidence"] if f else 0.0

    def to_json(self) -> dict[str, Any]:
        return {"parser": self.parser, "channel": self.channel, "account_kind": self.account_kind,
                "institution": self.institution, "fields": self.fields}


@lru_cache
def templates() -> list[dict[str, Any]]:
    data = yaml.safe_load(TEMPLATE_FILE.read_text())
    for t in data:
        t["_re"] = re.compile(t["regex"])
    return data


HEADER = re.compile(r"^(?:[A-Z]{2}-)?([A-Z0-9]{6})(?:-([PSTG]))?$")


def header_of(sender: str) -> tuple[str | None, str | None]:
    """'VM-HDFCBK-S' -> ('HDFCBK', 'S'). Phones show the operator prefix and the route suffix differently, and some
    show the bare header; a sender with no letters is a phone number, not a header."""
    raw = (sender or "").strip().upper()
    m = HEADER.match(raw)
    if not m or not any(c.isalpha() for c in m.group(1)):
        return (None, None)
    return m.group(1), m.group(2)


def parse_date(text: str, formats: list[str] | None = None) -> date | None:
    text = text.strip()
    for fmt in formats or []:
        try:
            return datetime.strptime(text.title() if "%b" in fmt else text, fmt).date()
        except ValueError:
            continue
    return None


def find_date(text: str, received: datetime) -> tuple[date | None, tuple[int, int] | None]:
    lo, hi = received.date() - timedelta(days=75), received.date() + timedelta(days=1)
    for rx, kind in DATE_RES:
        for m in rx.finditer(text):
            try:
                if kind == "ymd":
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif kind == "dmy":
                    y = int(m.group(3))
                    d = date(y + 2000 if y < 100 else y, int(m.group(2)), int(m.group(1)))
                elif kind == "dMy":
                    mon = MONTHS.get(m.group(2)[:3].lower())
                    if not mon:
                        continue
                    y = int(m.group(3))
                    d = date(y + 2000 if y < 100 else y, mon, int(m.group(1)))
                else:
                    mon = MONTHS.get(m.group(1)[:3].lower())
                    if not mon:
                        continue
                    d = date(int(m.group(3)), mon, int(m.group(2)))
            except ValueError:
                continue
            if lo <= d <= hi:
                return d, m.span()
    return None, None


def find_future_date(text: str, received: datetime) -> date | None:
    """Due dates / effective dates lie ahead of the message."""
    for rx, kind in DATE_RES:
        for m in rx.finditer(text):
            try:
                if kind == "ymd":
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif kind == "dmy":
                    y = int(m.group(3))
                    d = date(y + 2000 if y < 100 else y, int(m.group(2)), int(m.group(1)))
                elif kind == "dMy":
                    mon = MONTHS.get(m.group(2)[:3].lower())
                    if not mon:
                        continue
                    y = int(m.group(3))
                    d = date(y + 2000 if y < 100 else y, mon, int(m.group(1)))
                else:
                    mon = MONTHS.get(m.group(1)[:3].lower())
                    if not mon:
                        continue
                    d = date(int(m.group(3)), mon, int(m.group(2)))
            except ValueError:
                continue
            if received.date() - timedelta(days=3) <= d <= received.date() + timedelta(days=120):
                return d
    return None


def _clean_payee(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" .:-,*")
    text = re.sub(r"(?i)\s+(on|via|ref|refno|upi|avl|bal|total|not you|if not)\b.*$", "", text)
    text = re.sub(r"(?i)^(dividend|payment|purchase)\s+from\s+", "", text)
    if re.search(r"(?i)\s+to\s+", text) and re.match(r"(?i)(upi|neft|imps|p2m|p2a|payment)\b", text):
        text = re.split(r"(?i)\s+to\s+", text)[-1]  # "UPI P2M payment to BIGBASKET" -> "BIGBASKET"
    return text.strip(" .:-,*")[:80]


def _good_payee(text: str | None) -> bool:
    return bool(text) and not NOT_PAYEE.match(text.strip())


# -- SMS / text extraction -------------------------------------------------------------------------
def extract_template(msg: RawMessage) -> Extraction | None:
    header, _ = header_of(msg.sender)
    if header is None:
        return None
    for t in templates():
        if t.get("header") and t["header"] != header:
            continue
        m = t["_re"].search(msg.body)
        if not m:
            continue
        ex = Extraction(parser=t["id"], channel=t.get("channel"), account_kind=t.get("account_kind"),
                        institution=BANKS.get(header) or BILLERS.get(header))
        g = m.groupdict()
        for name in ("amount", "balance", "limit", "total", "min"):
            if g.get(name):
                ex.set(name if name != "limit" else "available_limit", str(D(g[name])), 0.99, m.span(name))
        if g.get("mask"):
            ex.set("mask", g["mask"], 0.99, m.span("mask"))
        if g.get("ref"):
            ex.set("ref", g["ref"], 0.99, m.span("ref"))
        if g.get("payee"):
            ex.set("payee", _clean_payee(g["payee"]), 0.97, m.span("payee"))
        elif t.get("payee"):
            ex.set("payee", t["payee"], 0.95)
        if g.get("account"):
            ex.set("account_no", g["account"].strip(), 0.95, m.span("account"))
        if g.get("date"):
            d = parse_date(g["date"], t.get("date_formats"))
            if d:
                ex.set("date", d.isoformat(), 0.99, m.span("date"))
        if g.get("due"):
            d = parse_date(g["due"], t.get("date_formats"))
            if d:
                ex.set("due_date", d.isoformat(), 0.99, m.span("due"))
        if g.get("time"):
            ex.set("time", g["time"], 0.99, m.span("time"))
        if t.get("direction"):
            ex.set("direction", t["direction"], 0.99)
        vpa = VPA_RE.search(msg.body)
        if vpa:
            ex.set("vpa", vpa.group(1).lower(), 0.95, vpa.span(1))
        if t["kind"] in ("bill_due", "statement") and ex.get("total") and not ex.get("amount"):
            ex.set("amount", ex.get("total"), 0.99)
        return ex
    return None


def extract_generic(text: str, received: datetime, sender: str = "") -> Extraction:
    ex = Extraction(parser="generic")
    header, _ = header_of(sender)
    ex.institution = BANKS.get(header or "") or BILLERS.get(header or "")
    amount_set = False
    for m in MONEY.finditer(text):
        before = text[max(0, m.start() - 28): m.start()]
        value = str(D(m.group(1)))
        if LIMIT_BEFORE.search(before):
            ex.set("available_limit", value, 0.85, m.span(1))
        elif BAL_BEFORE.search(before):
            ex.set("balance", value, 0.85, m.span(1))
        elif DUE_BEFORE.search(before):
            ex.set("min", value, 0.85, m.span(1))
        elif not amount_set:
            ex.set("amount", value, 0.9, m.span(1))
            amount_set = True
    if not amount_set:
        m = BARE_AMOUNT.search(text)
        if m:
            ex.set("amount", str(D(m.group(1))), 0.75, m.span(1))
    deb, cre = DEBIT_WORDS.search(text), CREDIT_WORDS.search(text)
    if deb and (not cre or deb.start() < cre.start()):
        ex.set("direction", "debit", 0.9, deb.span())
    elif cre:
        ex.set("direction", "credit", 0.9, cre.span())
    elif re.search(r"(?i)\b(transaction|txn|purchase)\b.{0,60}\bcard\b.{0,60}\bat\s+\S", text):
        ex.set("direction", "debit", 0.8)  # "Transaction of Rs X on your … Card … at MERCHANT": a card spend
    for rx in MASK_RES:
        m = rx.search(text)
        if m:
            ex.set("mask", m.group(1), 0.85, m.span(1))
            break
    refund_of = REFUND_OF.search(text)
    slash = SLASH_REF.search(text) or DASH_REF.search(text)
    if refund_of:  # "towards refund of UPI/6275…": the reference of the payment being refunded
        ex.set("ref", refund_of.group(1), 0.9, refund_of.span(1))
        ex.set("refund_of_ref", refund_of.group(1), 0.9, refund_of.span(1))
    elif slash:
        ex.set("ref", slash.group(1), 0.85, slash.span(1))
        payee = _clean_payee(slash.group(2))
        if _good_payee(payee):
            ex.set("payee", payee, 0.8, slash.span(2))
    else:
        m = REF_RE.search(text)
        if m and any(c.isdigit() for c in m.group(1)):
            ex.set("ref", m.group(1), 0.85, m.span(1))
    vpa = VPA_RE.search(text)
    if vpa:
        ex.set("vpa", vpa.group(1).lower(), 0.9, vpa.span(1))
    if not ex.get("payee") and not refund_of:
        axis_card = re.search(r"\n\d{2}-\d{2}-\d{2,4},? \d{2}:\d{2}:\d{2}(?: IST)?\n([^\n]+)\n", text)
        if axis_card and not re.match(r"(?i)(upi|neft|imps|rtgs)/", axis_card.group(1)) and _good_payee(_clean_payee(axis_card.group(1))):
            ex.set("payee", _clean_payee(axis_card.group(1)), 0.75, axis_card.span(1))
        else:
            for rx in PAYEE_RES:
                m = rx.search(text)
                if m:
                    payee = _clean_payee(m.group(1))
                    if _good_payee(payee):
                        ex.set("payee", payee, 0.7, m.span(1))
                        break
    if not ex.get("payee") and vpa:
        ex.set("payee", vpa.group(1).split("@")[0], 0.6, vpa.span(1))
    d, span = find_date(text, received)
    if d:
        ex.set("date", d.isoformat(), 0.85, span)
    else:
        ex.set("date", received.date().isoformat(), 0.5)
    tm = TIME_RE.search(text)
    if tm:
        ex.set("time", tm.group(0), 0.7, tm.span())
    low = text.lower()
    if "upi" in low or ex.get("vpa"):
        ex.channel = "upi"
    elif "atm" in low or "withdrawn" in low:
        ex.channel = "atm"
    elif "card" in low:
        ex.channel = "card"
    elif "neft" in low:
        ex.channel = "neft"
    elif "imps" in low:
        ex.channel = "imps"
    elif "nach" in low or "ach d" in low or "ecs" in low:
        ex.channel = "nach"
    ex.account_kind = "credit_card" if ("credit card" in low or ex.get("available_limit")) else "savings"
    due = re.search(r"(?i)\bdue(?:\s+date)?\b", text)
    if due:
        dd = find_future_date(text[due.start():], received)
        if dd:
            ex.set("due_date", dd.isoformat(), 0.8)
    tot = re.search(r"(?i)total\s*(?:amount|amt)?\s*due\s*[:\-]?\s*(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", text)
    if tot:
        ex.set("total", str(D(tot.group(1))), 0.85, tot.span(1))
    return ex


def extract_sms(msg: RawMessage, kind: str) -> Extraction:
    ex = extract_template(msg)
    if ex is not None:
        return ex
    ex = extract_generic(msg.body, msg.received_at, msg.sender)
    header, _ = header_of(msg.sender)
    if kind == "bill_due" and not ex.get("payee"):
        ex.set("payee", BILLERS.get(header or "", (header or "Biller").title()), 0.7)
    if kind == "statement":
        if ex.get("total"):
            ex.set("amount", ex.get("total"), ex.conf("total"))
        ex.set("payee", f"{ex.institution or 'Card'} Credit Card", 0.7)
    return ex


# -- email extraction ------------------------------------------------------------------------------
def sender_name(sender: str) -> tuple[str, str]:
    """'Swiggy <noreply@swiggy.in>' -> ('Swiggy', 'swiggy.in')."""
    m = re.match(r'\s*"?([^"<]*)"?\s*<([^>]+)>', sender or "")
    if m:
        name, addr = m.group(1).strip(), m.group(2).strip()
    else:
        name, addr = "", (sender or "").strip()
    domain = addr.rsplit("@", 1)[-1].lower()
    if not name:
        name = domain.split(".")[0].title()
    return name, domain


def _items_from_html(markup: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(markup, "lxml")
    items = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if len(cells) < 2:
                continue
            money = MONEY.search(cells[-1]) or re.fullmatch(r"([0-9][0-9,]*\.\d{2})", cells[-1])
            if not money:
                continue
            name = cells[0]
            if not name or re.match(r"(?i)^(total|amount|minimum|payment due|invoice)", name):
                continue
            qty = 1.0
            if len(cells) >= 3:
                try:
                    qty = float(cells[1])
                except ValueError:
                    qty = 1.0
            items.append({"description": name, "quantity": qty, "amount": str(D(money.group(1)))})
    return items


def extract_email(msg: RawMessage, kind: str) -> Extraction:
    name, domain = sender_name(msg.sender)
    text = f"{msg.subject or ''}\n{msg.body}"
    received = msg.received_at
    if kind in ("transaction", "refund", "failed_or_reversed", "balance"):
        ex = extract_generic(msg.body, received, "")
        ex.parser = "generic_email"
        stem = domain.split(".")[0]
        ex.institution = DOMAIN_BANKS.get(stem) or ex.institution
        icici = re.search(r"(?i)transaction of INR ([\d,]+\.\d{2}) on ([A-Za-z]{3} \d{1,2}, \d{4}) at (\d{2}:\d{2}:\d{2})\. Info: ([^.]+)\.", msg.body)
        if icici:
            ex.parser = "icici_alert_email"
            ex.set("amount", str(D(icici.group(1))), 0.98, icici.span(1))
            ex.set("date", datetime.strptime(icici.group(2), "%b %d, %Y").date().isoformat(), 0.98, icici.span(2))
            ex.set("time", icici.group(3), 0.98, icici.span(3))
            ex.set("payee", _clean_payee(icici.group(4)), 0.95, icici.span(4))
            ex.set("direction", "debit", 0.98)
            ex.channel, ex.account_kind = "card", "credit_card"
        if kind == "refund":
            ex.set("direction", "credit", 0.95)
            ex.set("merchant", name, 0.9)
            m = ORDER_RE.search(text)
            if m:
                ex.set("order_id", m.group(1), 0.9)
        return ex

    ex = Extraction(parser=f"email_{kind}")
    ex.set("merchant", name, 0.95)
    if kind == "order_receipt":
        orders = of_type(extract_jsonld(msg.html or ""), "Order") if msg.html else []
        if orders:
            ex.parser = "schema_org_order"
            o = orders[0]
            if o.get("price"):
                ex.set("amount", str(D(o["price"])), 0.99)
            if o.get("orderNumber"):
                ex.set("order_id", str(o["orderNumber"]), 0.99)
            merchant = (o.get("merchant") or {}).get("name") if isinstance(o.get("merchant"), dict) else None
            if merchant:
                ex.set("merchant", merchant, 0.99)
            offers = o.get("acceptedOffer") or []
            offers = offers if isinstance(offers, list) else [offers]
            items = []
            for off in offers:
                product = off.get("itemOffered") or {}
                qty = (off.get("eligibleQuantity") or {}).get("value", 1)
                price = D(off.get("price", 0))
                items.append({"description": product.get("name", "Item"), "quantity": float(qty),
                              "amount": str((price * D(qty)).quantize(D("0.01")))})
            if items:
                ex.set("items", items, 0.99)
        if not ex.get("amount"):
            m = TOTAL_RE.search(msg.body)
            if m:
                ex.set("amount", str(D(m.group(2))), 0.92, m.span(2))
            else:
                m = MONEY.search(msg.body)
                if m:
                    ex.set("amount", str(D(m.group(1))), 0.6, m.span(1))
        if not ex.get("items") and msg.html:
            items = _items_from_html(msg.html)
            if items:
                ex.set("items", items, 0.9)
        if not ex.get("order_id"):
            m = ORDER_RE.search(text)
            if m:
                ex.set("order_id", m.group(1), 0.85)
        scheme = re.search(r"in\s+([A-Z][\w&' -]+? Fund)\b", msg.body)
        if scheme:
            ex.set("scheme", scheme.group(1), 0.9)
        policy = re.search(r"(?i)policy(?: no\.?)?\s+([A-Z0-9/]{6,})", msg.body)
        if policy:
            ex.set("policy", policy.group(1), 0.85)
        ex.set("date", received.date().isoformat(), 0.8)
    elif kind in ("bill_due", "statement"):
        m = re.search(r"(?i)(total amount due|amount due|invoice amount|bill (?:amount|of))\s*[:\-]?\s*(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", msg.body)
        if m:
            ex.set("amount", str(D(m.group(2))), 0.92, m.span(2))
        else:
            m = MONEY.search(msg.body)
            if m:
                ex.set("amount", str(D(m.group(1))), 0.7, m.span(1))
        due = re.search(r"(?i)(?:payment )?due date[\s:\-]*(.{6,14})", msg.body)
        dd = find_future_date(due.group(1), received) if due else find_future_date(msg.body, received)
        if dd:
            ex.set("due_date", dd.isoformat(), 0.9)
        mn = re.search(r"(?i)minimum amount due\s*[:\-]?\s*(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", msg.body)
        if mn:
            ex.set("min", str(D(mn.group(1))), 0.9)
        if kind == "statement":
            bank = DOMAIN_BANKS.get(domain.split(".")[0], name)
            ex.set("payee", f"{bank} Credit Card", 0.9)
            mask = re.search(r"XX(\d{4})", text)
            if mask:
                ex.set("mask", mask.group(1), 0.9)
        else:
            ex.set("payee", name, 0.9)
    elif kind == "subscription_notice":
        ex.set("service", name, 0.95)
        prices = list(re.finditer(r"(?:₹|rs\.?\s?|inr\s?)([0-9][0-9,]*(?:\.\d{1,2})?)\s*/\s*month", msg.body, re.I))
        if prices:
            ex.set("amount", str(D(prices[-1].group(1))), 0.9, prices[-1].span(1))
            if len(prices) > 1:
                ex.set("old_amount", str(D(prices[0].group(1))), 0.9, prices[0].span(1))
        eff = re.search(r"(?i)(?:starting|from|ends on|effective)\s+(.{6,20})", msg.body)
        dd = find_future_date(eff.group(1), received) if eff else None
        if dd:
            ex.set("effective_date", dd.isoformat(), 0.85)
        low = text.lower()
        ex.set("notice", "trial" if "trial" in low else "price_change" if ("price" in low and "chang" in low) else "renewal", 0.9)
    elif kind == "usage":
        ex.set("service", name, 0.95)
        d, span = find_date(msg.body, received + timedelta(days=2))
        ex.set("date", (d or received.date()).isoformat(), 0.8, span)
    elif kind == "promo":
        pass
    return ex


def extract(msg: RawMessage, kind: str) -> Extraction:
    return extract_sms(msg, kind) if msg.channel == "sms" else extract_email(msg, kind)
