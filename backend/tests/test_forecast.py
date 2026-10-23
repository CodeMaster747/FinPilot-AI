from datetime import date

from sqlalchemy import select

from app.db.session import session_scope
from app.models import User
from app.services import system
from app.services.forecasting.engine import forecast, lowest_point, what_if


def _uid():
    with session_scope() as db:
        return db.scalar(select(User.id).where(User.is_demo.is_(True)))


def test_forecast_and_backtest(demo):
    with session_scope() as db:
        fc = forecast(db, _uid())
    assert len(fc["projection"]) == 90
    assert all(p["p10"] <= p["p50"] <= p["p90"] for p in fc["projection"])
    m = fc["metrics"]
    assert set(m) >= {"baseline", "baseline_schedule"}
    # knowing the schedule (salary, rent, EMIs, SIPs) — as it was known at each origin, never the future payments
    # themselves — must clearly beat the plain seasonal-naive baseline
    assert m["baseline_schedule"]["mae"] < 0.75 * m["baseline"]["mae"]
    if "prophet_schedule" in m:
        assert m["prophet_schedule"]["mae"] < m["baseline"]["mae"]
        assert m["prophet_schedule"]["end_error"] < m["baseline"]["end_error"]


def test_short_history_gets_an_honest_note(new_user):
    c = new_user
    c.post("/api/v1/transactions", json={"date": "2026-10-01", "amount": 250, "direction": "debit", "merchant": "Saravana Stores"})
    fc = c.get("/api/v1/forecast").json()
    assert fc.get("model") == "baseline" and "you have" in (fc.get("note") or "")


def test_what_if_shifts_every_quantile():
    proj = [{"date": f"2026-11-{d:02d}", "p10": 1000.0 + d, "p50": 2000.0 + d, "p90": 3000.0 + d} for d in range(1, 31)]
    w = what_if(proj, 500, date(2026, 11, 10))
    assert w["projection"][5]["p50"] == proj[5]["p50"]
    assert w["projection"][12]["p10"] == proj[12]["p10"] - 500
    expected = min(min(p["p10"] for p in proj[:9]), min(p["p10"] - 500 for p in proj[9:]))
    assert w["lowest_after"] == expected and w["lowest_before"] == lowest_point(proj)[0]


def test_baseline_fallback_when_prophet_unavailable(demo, monkeypatch):
    monkeypatch.setitem(system.CAPABILITIES, "prophet", {"ok": False})
    with session_scope() as db:
        fc = forecast(db, _uid(), run_backtest=False)
    assert fc["model"] == "baseline" and fc["note"]
