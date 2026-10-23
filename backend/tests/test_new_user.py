"""A brand-new real user: every screen's API answers sensibly with no data at all, and again after the first SMS sync."""

from conftest import sign_up_phone
from realistic import phone_upload
from test_phone import _sync

PAGE_ENDPOINTS = [
    "/auth/me", "/system/status", "/review", "/dashboard", "/categories", "/transactions", "/anomalies", "/accounts", "/sources",
    "/sources/history", "/sources/sms/sync-state", "/sources/email/mailbox", "/sources/email/providers", "/forecast",
    "/forecast/whatif?amount=1500", "/subscriptions", "/wishlist", "/insights", "/coach/suggestions", "/coach/history", "/budgets",
    "/goals", "/tax?year=2025-26", "/tax?year=2026-27", "/tax/export.csv", "/tax/export.pdf", "/rules", "/system/quality",
    "/system/pairing", "/settings/export", "/upcoming", "/receipts",
]
QUESTIONS = ["How much did I spend last month?", "Can I afford a ₹20,000 phone?", "Which subscriptions should I cancel?",
             "What will my balance be at the end of the month?", "Which tax regime is better for me?",
             "What can I buy from my wishlist?", "What data can you see?", "Show my Swiggy payments"]


def _all_pages_answer(c):
    for path in PAGE_ENDPOINTS:
        r = c.get("/api/v1" + path)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
    for q in QUESTIONS:
        r = c.post("/api/v1/coach/ask", json={"question": q})
        assert r.status_code == 200 and r.json()["text"], q


def test_a_new_user_with_no_data(phone):
    sign_up_phone(phone, "Nisha Varma")
    _all_pages_answer(phone)
    d = phone.get("/api/v1/dashboard").json()
    assert d["has_data"] is False and d["kpis"]["balance"] is None and d["kpis"]["balance_known"] is False
    titles = [i["title"] for i in phone.get("/api/v1/insights").json()]
    assert not any("run low" in t.lower() for t in titles)  # no false alarm about a balance we don't know
    fc = phone.get("/api/v1/forecast").json()
    assert fc.get("model") == "baseline" and "you have" in fc.get("note", "")
    assert fc["backtest"] == [] and fc["history_days"] < fc["backtest_min_days"]  # the page explains why accuracy is missing
    tax = phone.get("/api/v1/tax?year=2026-27").json()
    assert tax["advance_tax"]["tds_known"] is False and tax["advance_tax"]["balance_due"] is None
    assert phone.get("/api/v1/subscriptions").status_code == 200


def test_after_the_first_sms_sync_every_screen_has_real_numbers(phone):
    sign_up_phone(phone, "Arun Prakash")
    phone.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 3})
    _sync(phone, phone_upload())
    phone.patch("/api/v1/auth/me", json={"preferences": {"take_home_monthly": 85000, "payday": 1, "rent_monthly": 18000,
                                                         "rent_payee": "Ramesh Kumar", "rent_day": 5}})
    _all_pages_answer(phone)
    d = phone.get("/api/v1/dashboard").json()
    assert d["has_data"] is True and d["kpis"]["balance_known"] is True and d["kpis"]["balance"] is not None
    assert d["kpis"]["safe_to_spend"] is not None and d["categories"]
    rent = phone.get("/api/v1/transactions", params={"q": "Ramesh"}).json()["items"]
    assert rent and rent[0]["category"]["name"] == "Rent"  # the landlord from onboarding
    fc = phone.get("/api/v1/forecast").json()
    names = {r["merchant"] for r in fc["recurring"]}
    assert "Salary (you told us)" in names  # seeded from onboarding until three salary credits have been seen
    tax = phone.get("/api/v1/tax?year=2026-27").json()
    assert tax["hra"]["rent_paid"] > 0
    phone.put("/api/v1/tax/profile", json={"city": "Bengaluru", "gross_salary": 1500000, "basic_salary": 600000,
                                           "hra_received": 240000, "tds_deducted": 90000})
    t26 = phone.get("/api/v1/tax?year=2026-27").json()
    t25 = phone.get("/api/v1/tax?year=2025-26").json()
    assert t26["hra"]["metro"] is True and t25["hra"]["metro"] is False  # Bengaluru is a 50% HRA city from Tax Year 2026-27
    assert t26["advance_tax"]["tds_known"] is True
    pdf = phone.get("/api/v1/tax/export.pdf?year=2026-27")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and "attachment" in pdf.headers["content-disposition"]
    assert pdf.headers["access-control-expose-headers"].lower() == "content-disposition"


def test_safe_to_spend_is_not_zero_just_because_income_is_not_measured_yet(phone):
    # The emulator's first sync: one salary credit and two balance alerts, under a month of history, no take-home entered.
    # There is no basis for a wants budget yet, so it must not cap safe-to-spend at ₹0.
    import time

    now = int(time.time() * 1000)
    day = 86_400_000
    sign_up_phone(phone, "Kavya Iyer")
    phone.post("/api/v1/sources/sms/grant", json={"purposes": ["transactions"], "backfill_months": 12})
    _sync(phone, [
        {"address": "VK-HDFCBK-S", "date_ms": now - 25 * day, "body": "Update! INR 85,000.00 deposited in HDFC Bank A/c XX4521 on "
         + time.strftime("%d-%b-%y", time.localtime((now - 25 * day) / 1000)).upper()
         + " for NEFT Cr-HSBC0560002-ACME SOFTWARE PVT LTD-SALARY-160509419144.Avl bal INR 1,02,450.00."},
        {"address": "JD-SBIINB-S", "date_ms": now - 10 * day, "body": "Your a/c no. XXXXXXX9034 is debited for Rs.6,200.00 on "
         + time.strftime("%d-%m-%y", time.localtime((now - 10 * day) / 1000)) + " by NACH towards SBI EDU LOAN A/C 3345. Avl Bal Rs.45,351.00 -SBI"},
    ])
    k = phone.get("/api/v1/dashboard").json()["kpis"]
    assert k["safe_basis"] == "balance" and k["wants_left"] is None
    assert k["safe_to_spend"] == k["safe_to_spend_total"] and k["safe_to_spend"] > 0
    snap = phone.get("/api/v1/wishlist").json()["snapshot"]
    assert snap["wants_known"] is False and snap["spendable"] == snap["safe_to_spend"] > 0
    # once take-home pay is entered, the monthly wants budget applies again
    phone.patch("/api/v1/auth/me", json={"preferences": {"take_home_monthly": 85000}})
    k = phone.get("/api/v1/dashboard").json()["kpis"]
    assert k["wants_left"] is not None and k["safe_to_spend"] == min(k["safe_to_spend_total"], k["wants_left"])


def test_with_no_balance_and_no_income_safe_to_spend_is_unknown_not_zero(phone):
    sign_up_phone(phone, "Dev Menon")
    k = phone.get("/api/v1/dashboard").json()["kpis"]
    assert k["safe_basis"] in (None, "none") and k["safe_to_spend"] is None
