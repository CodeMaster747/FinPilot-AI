from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import session_scope
from app.models import User
from app.services.tax import YEARS, compute, slab_tax, tax_summary

CFG = YEARS["2025-26"]


@pytest.mark.parametrize("taxable,regime,expected", [
    (1200000, "new", 0),          # full 87A rebate up to ₹12 lakh
    (1210000, "new", 10400),      # marginal relief: tax capped at income above ₹12 lakh, + 4% cess
    (2000000, "new", 208000),     # 0+20k+40k+60k+80k = 2,00,000 + 4% cess
    (700000, "new", 0),
    (1000000, "old", 117000),     # 12,500 + 1,00,000 + 4% cess
    (500000, "old", 0),           # old-regime rebate
    (6000000, "new", round((slab_tax(Decimal(6000000), CFG["new"]["slabs"]) * Decimal("1.10")) * Decimal("1.04"))),  # 10% surcharge
])
def test_slabs_rebate_and_relief(taxable, regime, expected):
    assert compute(Decimal(taxable), regime, CFG)["total"] == Decimal(expected)


def test_both_years_share_budget_2026_numbers():
    for key in ("new", "old", "cess", "limits"):
        assert YEARS["2025-26"][key] == YEARS["2026-27"][key]
    assert YEARS["2026-27"]["act"] == "Income-tax Act, 2025"


def test_persona_summary(demo):
    with session_scope() as db:
        user = db.scalar(select(User).where(User.is_demo.is_(True)))
        s = tax_summary(db, user, "2025-26")
    assert s["recommendation"]["regime"] == "new"
    assert s["section_80c"]["allowed"] == 150000  # capped
    assert 0 < s["hra"]["exempt"] <= s["hra"]["received"]
    assert "not tax advice" in s["disclaimer"]
