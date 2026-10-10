"""Measured results for the report: classification and field extraction on three message sets."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from app.services.ingestion.classify import classify
from app.services.ingestion.extract import extract
from app.services.ingestion.prefilter import prefilter
from app.services.ingestion.types import RawMessage

MONEY_KINDS = ("transaction", "refund")


def score(msgs: list[RawMessage], label: str, verbose: bool = False) -> dict:
    kept = [m for m in msgs if prefilter(m).keep]
    dropped = Counter(m.truth["kind"] for m in msgs if not prefilter(m).keep)
    preds = classify(kept)
    correct_kind = 0
    amount_ok = amount_n = direction_ok = direction_n = 0
    per_template: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    errors = []
    for m, (kind, p) in zip(kept, preds):
        truth = m.truth
        if kind == truth["kind"]:
            correct_kind += 1
        elif verbose:
            errors.append(f"KIND {truth['template']}: got {kind} ({p:.2f}) want {truth['kind']} :: {m.body[:90]!r}")
        exp = truth.get("expect") or {}
        if truth["kind"] in MONEY_KINDS + ("bill_due", "statement", "order_receipt") and exp.get("amount"):
            ex = extract(m, truth["kind"])
            got = ex.get("amount")
            ok = got is not None and Decimal(got) == Decimal(exp["amount"])
            amount_n += 1
            amount_ok += ok
            per_template[truth["template"]][0] += ok
            per_template[truth["template"]][1] += 1
            if not ok and verbose:
                errors.append(f"AMOUNT {truth['template']}: got {got} want {exp['amount']} :: {m.body[:90]!r}")
            if exp.get("direction"):
                direction_n += 1
                dok = ex.get("direction") == exp["direction"]
                direction_ok += dok
                if not dok and verbose:
                    errors.append(f"DIRECTION {truth['template']}: got {ex.get('direction')} want {exp['direction']} :: {m.body[:90]!r}")
    result = {
        "set": label,
        "messages": len(msgs),
        "dropped_by_prefilter": dict(dropped),
        "classified": len(kept),
        "kind_accuracy": round(correct_kind / max(1, len(kept)), 4),
        "amount_exact": round(amount_ok / max(1, amount_n), 4),
        "amount_cases": amount_n,
        "direction_exact": round(direction_ok / max(1, direction_n), 4),
        "direction_cases": direction_n,
        "weak_templates": {k: f"{v[0]}/{v[1]}" for k, v in per_template.items() if v[0] < v[1]},
    }
    if verbose:
        result["errors"] = errors[:60]
    return result


def run(verbose: bool = False) -> dict:
    from app.ml.challenge_set import messages as challenge
    from app.seed.emails import render_emails
    from app.seed.persona import build_persona
    from app.seed.sms import heldout_sms, render_sms

    persona = build_persona(date(2026, 8, 31), seed=303)
    known = render_sms(persona) + render_emails(persona)
    return {
        "known_formats": score(known, "known formats (fresh persona run)", verbose),
        "heldout_styles": score(heldout_sms(200, seed=5), "held-out bank styles (Axis, Kotak)", verbose),
        "challenge": score(challenge(), "challenge set (hand-written, other banks/merchants)", verbose),
    }
