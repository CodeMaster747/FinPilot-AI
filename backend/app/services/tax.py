"""India income tax estimates for salaried individuals — FY 2025-26 (Income-tax Act 1961) and
Tax Year 2026-27 (Income-tax Act 2025; Budget 2026 kept the slabs, the ₹75,000 standard deduction and the
₹12 lakh rebate unchanged). Deductions are detected from the user's own transactions, with evidence.

Estimates for planning only — not tax advice. Rates and limits live in YEARS below and are unit tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import D, fmt_inr
from app.models import Category, Transaction, User
from app.services.recurring import detect_recurring

NEW_SLABS = [(400000, 0), (800000, 5), (1200000, 10), (1600000, 15), (2000000, 20), (2400000, 25), (None, 30)]
OLD_SLABS = [(250000, 0), (500000, 5), (1000000, 20), (None, 30)]
COMMON = {
    "new": {"slabs": NEW_SLABS, "std_deduction": 75000, "rebate_limit": 1200000, "rebate_max": 60000, "surcharge_cap": 25},
    "old": {"slabs": OLD_SLABS, "std_deduction": 50000, "rebate_limit": 500000, "rebate_max": 12500, "surcharge_cap": 37},
    "cess": 4,
    "limits": {"80C": 150000, "80D": 25000, "80CCD1B": 50000, "80TTA": 10000, "24b": 200000, "pt": 2500},
}
YEARS: dict[str, dict[str, Any]] = {
    "2025-26": {**COMMON, "label": "FY 2025-26", "act": "Income-tax Act, 1961", "start": date(2025, 4, 1), "end": date(2026, 3, 31),
                "sections": {"80C": "80C", "80D": "80D", "80E": "80E", "24b": "24(b)", "hra": "10(13A) HRA", "80TTA": "80TTA"}},
    "2026-27": {**COMMON, "label": "Tax Year 2026-27", "act": "Income-tax Act, 2025", "start": date(2026, 4, 1), "end": date(2027, 3, 31),
                "sections": {"80C": "s.123 (was 80C)", "80D": "80D*", "80E": "80E*", "24b": "24(b)*", "hra": "HRA*", "80TTA": "80TTA*"}},
}
SURCHARGE = [(5000000, 10), (10000000, 15), (20000000, 25), (50000000, 37)]
ADVANCE_TAX = [("15 Jun", 15), ("15 Sep", 45), ("15 Dec", 75), ("15 Mar", 100)]
DISCLAIMER = ("Estimates for planning, not tax advice. Based on the slabs announced for each year and on deductions detected "
              "from your transactions; verify with Form 16 / a tax professional before filing.")


def slab_tax(taxable: Decimal, slabs: list[tuple[int | None, int]]) -> Decimal:
    tax, lower = Decimal(0), Decimal(0)
    for upper, rate in slabs:
        top = taxable if upper is None else min(taxable, Decimal(upper))
        if top > lower:
            tax += (top - lower) * Decimal(rate) / 100
        if upper is None or taxable <= upper:
            break
        lower = Decimal(upper)
    return tax.quantize(Decimal("1"), ROUND_HALF_UP)


def compute(taxable: Decimal, regime: str, cfg: dict[str, Any]) -> dict[str, Any]:
    r = cfg[regime]
    taxable = max(Decimal(0), taxable.quantize(Decimal("1"), ROUND_HALF_UP))
    base = slab_tax(taxable, r["slabs"])
    rebate = Decimal(0)
    if taxable <= r["rebate_limit"]:
        rebate = min(base, Decimal(r["rebate_max"]))
    elif regime == "new" and base > taxable - r["rebate_limit"]:
        rebate = base - (taxable - r["rebate_limit"])  # marginal relief just above the rebate limit
    after_rebate = base - rebate
    rate = 0
    for threshold, pct in SURCHARGE:
        if taxable > threshold:
            rate = min(pct, r["surcharge_cap"])
    surcharge = (after_rebate * Decimal(rate) / 100).quantize(Decimal("1"), ROUND_HALF_UP)
    cess = ((after_rebate + surcharge) * Decimal(cfg["cess"]) / 100).quantize(Decimal("1"), ROUND_HALF_UP)
    total = after_rebate + surcharge + cess
    return {"taxable": taxable, "slab_tax": base, "rebate": rebate, "surcharge": surcharge, "cess": cess, "total": total,
            "effective_rate": float((total / taxable * 100).quantize(Decimal("0.01"))) if taxable else 0.0}


@dataclass
class Evidence:
    label: str
    amount: Decimal
    items: list[dict[str, Any]]
    projected: Decimal = Decimal(0)


def _sum(items: list[Transaction]) -> Decimal:
    return sum((t.amount for t in items), Decimal(0))


def _items(items: list[Transaction]) -> list[dict[str, Any]]:
    return [{"id": t.id, "date": t.txn_date.isoformat(), "merchant": t.merchant_name, "amount": float(t.amount)} for t in items[:24]]


def tax_summary(db: Session, user: User, year: str, today: date | None = None) -> dict[str, Any]:
    if year not in YEARS:
        raise ValueError("unknown year")
    today = today or date.today()
    cfg = YEARS[year]
    start, end = cfg["start"], cfg["end"]
    in_progress = start <= today < end
    cut = min(today, end)
    profile = dict(user.tax_profile or {})
    rows = db.execute(select(Transaction, Category).join(Category, Category.id == Transaction.category_id).where(
        Transaction.user_id == user.id, Transaction.status == "posted", Transaction.is_transfer.is_(False),
        Transaction.txn_date >= start, Transaction.txn_date <= cut)).all()
    txns = [(t, c) for t, c in rows]

    def pick(pred) -> list[Transaction]:  # noqa: ANN001
        return [t for t, c in txns if pred(t, c)]

    elss = pick(lambda t, c: c.name == "Investments" and "elss" in t.merchant_name.lower())
    lic = pick(lambda t, c: c.name == "Insurance" and ("lic" in t.merchant_name.lower() or "life" in t.merchant_name.lower()))
    health = pick(lambda t, c: c.name == "Insurance" and "health" in t.merchant_name.lower())
    rent = pick(lambda t, c: c.name == "Rent" and t.direction == "debit")
    tuition = pick(lambda t, c: c.name == "Education" and any(k in t.merchant_name.lower() for k in ("school", "tuition", "college")))
    interest = pick(lambda t, c: c.name == "Interest" and t.direction == "credit")
    edu_loan = pick(lambda t, c: c.name == "Loan EMI" and "education" in t.merchant_name.lower())
    salary = pick(lambda t, c: c.name == "Salary" and t.direction == "credit")

    # project the rest of an in-progress year from the recurring schedule
    proj: dict[str, Decimal] = {"elss": Decimal(0), "lic": Decimal(0), "health": Decimal(0), "rent": Decimal(0)}
    months_left = 0
    if in_progress:
        months_left = (end.year - today.year) * 12 + end.month - today.month
        for rec in detect_recurring(db, user.id, today):
            if not rec.active:
                continue
            n = len(rec.occurrences(today + timedelta(days=1), end))
            key = ("elss" if "elss" in rec.merchant.lower() else "lic" if "lic" in rec.merchant.lower()
                   else "health" if "health" in rec.merchant.lower() else "rent" if rec.category == "Rent" else None)
            if key:
                proj[key] += rec.amount * n
    elapsed = max(1, (cut.year - start.year) * 12 + cut.month - start.month + 1)
    interest_total = (_sum(interest) * (Decimal(12) / Decimal(elapsed) if in_progress else 1)).quantize(Decimal("1"), ROUND_HALF_UP)

    # salary: profile gross for FY 2025-26, scaled by the change in detected monthly salary for later years
    gross = D(profile.get("gross_salary") or 0)
    if year != "2025-26" and gross and salary:
        prev = [t.amount for t, c in db.execute(select(Transaction, Category).join(Category).where(
            Transaction.user_id == user.id, Category.name == "Salary", Transaction.txn_date >= YEARS["2025-26"]["start"],
            Transaction.txn_date <= YEARS["2025-26"]["end"])).all()]
        if prev:
            gross = (gross * (salary[-1].amount / (sum(prev, Decimal(0)) / len(prev)))).quantize(Decimal("1"))
    if not gross and salary:
        monthly = salary[-1].amount
        gross = (monthly * 12 / Decimal("0.74")).quantize(Decimal("1"))  # rough gross-up from net take-home
        profile.setdefault("estimated", True)
    basic = D(profile.get("basic_salary") or gross * Decimal("0.4"))
    hra_received = D(profile.get("hra_received") or 0)
    epf = D(profile.get("employee_pf") or 0)

    rent_paid = _sum(rent) + proj["rent"]
    metro_pct = Decimal("0.5") if profile.get("metro", True) else Decimal("0.4")
    hra_exempt = max(Decimal(0), min(hra_received, rent_paid - basic * Decimal("0.1"), basic * metro_pct)) if rent_paid else Decimal(0)
    limits = cfg["limits"]
    c80_parts = {"Employee PF (from salary)": epf, "ELSS mutual fund SIPs": _sum(elss) + proj["elss"],
                 "Life insurance premium": _sum(lic) + proj["lic"], "Tuition fees": _sum(tuition)}
    c80 = sum(c80_parts.values(), Decimal(0))
    c80_allowed = min(c80, Decimal(limits["80C"]))
    d80 = min(_sum(health) + proj["health"], Decimal(limits["80D"]))
    e80 = D(profile.get("education_loan_interest") or 0)
    b24 = min(D(profile.get("home_loan_interest") or 0), Decimal(limits["24b"]))
    tta = min(interest_total, Decimal(limits["80TTA"]))
    pt = min(D(profile.get("professional_tax") or 0), Decimal(limits["pt"]))

    old_deductions = {"Standard deduction": Decimal(cfg["old"]["std_deduction"]), f"HRA exemption ({cfg['sections']['hra']})": hra_exempt,
                      "Professional tax": pt, cfg["sections"]["80C"]: c80_allowed, cfg["sections"]["80D"]: d80,
                      cfg["sections"]["80E"]: e80, cfg["sections"]["24b"]: b24, cfg["sections"]["80TTA"]: tta}
    old_taxable = gross + interest_total - sum(old_deductions.values(), Decimal(0))
    new_deductions = {"Standard deduction": Decimal(cfg["new"]["std_deduction"])}
    new_taxable = gross + interest_total - sum(new_deductions.values(), Decimal(0))
    old = compute(old_taxable, "old", cfg)
    new = compute(new_taxable, "new", cfg)
    better = "new" if new["total"] <= old["total"] else "old"
    saving = abs(new["total"] - old["total"])
    chosen = new if better == "new" else old

    headroom = []
    if c80 < limits["80C"]:
        gap = Decimal(limits["80C"]) - c80
        tip = f"{fmt_inr(gap)} of your {cfg['sections']['80C']} limit is unused"
        if in_progress and months_left:
            tip += f" — an ELSS SIP of {fmt_inr(gap / months_left)}/month for the remaining {months_left} months would use it"
        headroom.append({"section": cfg["sections"]["80C"], "used": float(c80), "limit": limits["80C"], "tip": tip + " (only helps under the old regime)."})
    if d80 < limits["80D"]:
        headroom.append({"section": cfg["sections"]["80D"], "used": float(d80), "limit": limits["80D"],
                         "tip": f"{fmt_inr(Decimal(limits['80D']) - d80)} of health-insurance headroom left (old regime)."})
    tds = D(profile.get("tds_deducted") or 0) or chosen["total"]  # assume the employer withholds the full liability
    balance_due = max(Decimal(0), chosen["total"] - tds)
    evidence = [
        Evidence("ELSS SIPs", _sum(elss), _items(elss), proj["elss"]), Evidence("Life insurance", _sum(lic), _items(lic), proj["lic"]),
        Evidence("Health insurance", _sum(health), _items(health), proj["health"]), Evidence("Rent paid (for HRA)", _sum(rent), _items(rent), proj["rent"]),
        Evidence("Education-loan EMIs (interest from certificate)", _sum(edu_loan), _items(edu_loan)),
        Evidence("Savings interest", _sum(interest), _items(interest)),
    ]
    money = lambda v: float(v)  # noqa: E731
    return {
        "year": year, "label": cfg["label"], "act": cfg["act"], "in_progress": in_progress, "as_of": cut.isoformat(),
        "months_left": months_left, "disclaimer": DISCLAIMER,
        "income": {"gross_salary": money(gross), "other_income": money(interest_total), "estimated_salary": bool(profile.get("estimated"))},
        "regimes": {
            "old": {**{k: money(v) if isinstance(v, Decimal) else v for k, v in old.items()},
                    "deductions": [{"name": k, "amount": money(v)} for k, v in old_deductions.items() if v]},
            "new": {**{k: money(v) if isinstance(v, Decimal) else v for k, v in new.items()},
                    "deductions": [{"name": k, "amount": money(v)} for k, v in new_deductions.items()]},
        },
        "recommendation": {"regime": better, "saving": money(saving),
                           "text": f"The {'new' if better == 'new' else 'old'} regime costs {fmt_inr(saving)} less for you this year."},
        "section_80c": {"parts": [{"name": k, "amount": money(v)} for k, v in c80_parts.items() if v], "total": money(c80),
                        "limit": limits["80C"], "allowed": money(c80_allowed)},
        "hra": {"received": money(hra_received), "rent_paid": money(rent_paid), "exempt": money(hra_exempt),
                "rule": "least of HRA received, rent paid minus 10% of basic, and 50% (metro) / 40% of basic"},
        "headroom": headroom,
        "advance_tax": {"tds_assumed": money(tds), "balance_due": money(balance_due), "needed": balance_due > 10000,
                        "schedule": [{"due": d, "cumulative_pct": p, "amount": money((balance_due * p / 100).quantize(Decimal("1")))}
                                     for d, p in ADVANCE_TAX]},
        "evidence": [{"label": e.label, "amount": money(e.amount), "projected": money(e.projected), "items": e.items} for e in evidence],
        "profile": profile,
    }
