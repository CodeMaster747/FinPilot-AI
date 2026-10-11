from decimal import Decimal

import pytest

from app.core.money import D, fmt_inr, from_paise, to_paise


def test_decimal_parsing_handles_indian_grouping():
    assert D("1,23,456.50") == Decimal("123456.50")
    assert D("₹ 450") == Decimal("450.00")
    assert D(0.1) + D(0.2) == Decimal("0.30")  # no float drift


def test_paise_round_trip():
    for v in ("0.01", "99.99", "123456.78"):
        assert from_paise(to_paise(v)) == Decimal(v)


@pytest.mark.parametrize("value,expected", [(1234567.5, "₹12,34,568"), (999, "₹999"), (100000, "₹1,00,000"), (-2500, "-₹2,500")])
def test_indian_formatting(value, expected):
    assert fmt_inr(value) == expected


def test_rejects_non_numbers():
    with pytest.raises(ValueError):
        D("abc")
