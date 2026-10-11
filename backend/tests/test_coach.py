from datetime import date
from decimal import Decimal

import pytest

from app.services.coach import parse_amount, parse_category, parse_period


@pytest.mark.parametrize("text,amount", [("can i afford a 45k laptop", 45000), ("₹1,20,000 tv", 120000), ("1.2 lakh bike", 120000),
                                         ("spend rs 5000 today", 5000), ("last 3 months", None), ("in 2025", None)])
def test_amounts(text, amount):
    got = parse_amount(text)
    assert (got is None and amount is None) or got == Decimal(amount)


def test_periods_and_categories():
    today = date(2026, 10, 10)
    assert parse_period("how much last month", today)[:2] == (date(2026, 9, 1), date(2026, 9, 30))
    assert parse_period("spent in august", today)[0] == date(2026, 8, 1)
    assert parse_period("may i buy shoes", today)[2] == "this month"  # not the month of May
    assert parse_category("how much on eating out") == "Dining Out"
    assert parse_category("cabs this week") == "Transport"


QUESTIONS = {
    "How much did I spend on food delivery last month?": "spend_by_category",
    "Can I afford a ₹60,000 laptop?": "affordability_check",
    "Which subscriptions should I cancel?": "subscription_query",
    "What will my balance be at the end of the month?": "forecast_query",
    "Which tax regime is better for me?": "tax_query",
    "What data can you see?": "privacy_query",
}


def test_coach_answers_from_real_data(demo_client):
    for q, intent in QUESTIONS.items():
        a = demo_client.post("/api/v1/coach/ask", json={"question": q}).json()
        assert a["intent"] == intent, (q, a)
        assert a["text"] and "₹" in a["text"] or intent == "privacy_query"
    a = demo_client.post("/api/v1/coach/ask", json={"question": "what's the weather in Paris?"}).json()
    assert a["intent"] == "fallback"
