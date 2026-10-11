"""Parser quality on three sets: known formats, generated held-out bank styles, hand-written challenge set."""

from datetime import date
from decimal import Decimal

from app.ml import evaluate
from app.seed.persona import build_persona
from app.seed.sms import render_sms
from app.services.ingestion.classify import classify
from app.services.ingestion.extract import extract_template


def test_every_known_bank_template_extracts_exactly(demo):
    msgs = render_sms(build_persona(date(2026, 6, 30), seed=41))
    checked = 0
    for m in msgs:
        exp = m.truth["expect"]
        if m.truth["kind"] not in ("transaction", "refund") or not exp.get("amount"):
            continue
        ex = extract_template(m)
        assert ex is not None, f"no template matched {m.truth['template']}: {m.body!r}"
        assert Decimal(ex.get("amount")) == Decimal(exp["amount"]), m.body
        assert ex.get("direction") == exp["direction"], m.body
        assert ex.get("mask") == exp["mask"], m.body
        checked += 1
    assert checked > 1000


def test_quality_thresholds(demo):
    res = evaluate.run()
    assert res["known_formats"]["amount_exact"] >= 0.98
    assert res["heldout_styles"]["amount_exact"] >= 0.90
    assert res["heldout_styles"]["direction_exact"] >= 0.90
    ch = res["challenge"]
    assert ch["kind_accuracy"] >= 0.90
    assert ch["amount_exact"] >= 0.90
    assert ch["direction_exact"] >= 0.90


def test_otp_is_never_a_transaction(demo):
    from app.ml.challenge_set import messages as challenge

    msgs = [m for m in render_sms(build_persona(date(2026, 6, 30), seed=41)) + challenge() if m.truth["kind"] == "otp"]
    assert msgs
    for m, (kind, _) in zip(msgs, classify(msgs)):
        assert kind == "otp", m.body
