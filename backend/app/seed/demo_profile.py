"""The demo persona's own settings: budgets, goals, wishlist, tax profile and a categorisation rule."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

BUDGETS = {
    "Groceries": Decimal("10000"), "Dining Out": Decimal("4000"), "Food Delivery": Decimal("5000"),
    "Shopping": Decimal("6000"), "Transport": Decimal("4500"), "Entertainment": Decimal("2000"),
    "Fashion": Decimal("3000"), "Subscriptions": Decimal("3500"),
}


def goals(today: date) -> list[dict]:
    year = today.year
    return [
        {"name": "New laptop", "target": Decimal("70000"), "saved": Decimal("18000"),
         "target_date": date(year + 1, 3, 31) if today.month > 3 else date(year, 9, 30), "keywords": "laptop notebook ultrabook"},
        {"name": "Goa trip", "target": Decimal("35000"), "saved": Decimal("12000"),
         "target_date": date(year, 12, 20) if today.month < 12 else date(year + 1, 6, 1), "keywords": "travel trip luggage"},
        {"name": "Emergency fund top-up", "target": Decimal("150000"), "saved": Decimal("60000"),
         "target_date": date(year + 1, 12, 31), "keywords": ""},
    ]


WISHLIST = [
    {"text": "Noise-cancelling headphones", "max_price": Decimal("12000")},
    {"text": "Running shoes", "max_price": Decimal("6000")},
    {"text": "Air fryer", "max_price": None},
    {"text": "Mirrorless camera", "max_price": Decimal("80000")},
]

RULES = [("ramesh kumar", "Rent")]  # the landlord's UPI name -> Rent

# Ground truth for evaluating Smart Picks: what this persona actually wants, from the wishlist, goals,
# regular purchases and the merchants they use. Never read by the recommender itself.
TRUE_INTERESTS = ["headphones", "running shoes", "air fryer", "camera", "laptop", "luggage", "travel", "backpack", "packing",
                  "whey", "coffee", "tea", "fitness", "yoga", "foam", "gym", "dumbbell", "pull-up", "kettle", "music", "earbuds", "speaker"]

TAX_PROFILE = {
    "employer": "Zentrix Technologies Pvt Ltd",
    "city": "Chennai",
    "metro": True,
    # annual salary structure (FY 2025-26); the app scales it for other years by the detected salary credits
    "gross_salary": 1980000,
    "basic_salary": 792000,
    "hra_received": 396000,
    "employee_pf": 95040,
    "professional_tax": 2500,
    "education_loan_interest": 38000,
    "home_loan_interest": 0,
    "tds_deducted": None,  # estimated by the app if left empty
}

PREFERENCES = {
    "picks_enabled": True,
    "buffer_floor": 15000,
    "emergency_months": 3,
    "picks_weekly_cap": 12,
    "excluded_interest_categories": ["Healthcare"],
    "retention_days": 90,
}
