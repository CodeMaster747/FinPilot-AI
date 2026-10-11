"""SMS/email kind classifier (transaction, otp, promo, bill_due, ...).

Trained on messages rendered from two independent persona runs; evaluated on a third run plus bank
styles that never appear in training (Axis, Kotak) to measure generalisation honestly.
"""

from __future__ import annotations

from datetime import date

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

from app.ml.text import message_text
from app.services.ingestion.types import RawMessage


def corpus(end: date, seed: int) -> list[RawMessage]:
    from app.seed.emails import render_emails
    from app.seed.persona import build_persona
    from app.seed.sms import render_sms

    persona = build_persona(end, seed=seed)
    return render_sms(persona) + render_emails(persona)


def features(m: RawMessage) -> str:
    return message_text(m.channel, m.sender, m.subject, m.body)


def make_pipeline() -> Pipeline:
    feats = FeatureUnion([
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=40000)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True, max_features=60000)),
    ])
    return Pipeline([("features", feats), ("clf", LogisticRegression(C=6.0, max_iter=3000, class_weight="balanced"))])


def _dedupe(msgs: list[RawMessage]) -> tuple[list[str], list[str]]:
    seen, X, y = set(), [], []
    for m in msgs:
        text = features(m)
        if text in seen:
            continue
        seen.add(text)
        X.append(text)
        y.append(m.truth["kind"])
    return X, y


def train() -> tuple[Pipeline, dict]:
    from app.seed.sms import heldout_sms

    from app.ml.phrasebank import generate as phrasebank

    train_msgs = corpus(date(2026, 3, 31), seed=101) + corpus(date(2025, 12, 31), seed=202) + phrasebank()
    X, y = _dedupe(train_msgs)
    model = make_pipeline().fit(X, y)

    test_msgs = corpus(date(2026, 8, 31), seed=303)
    Xt, yt = _dedupe(test_msgs)
    pred = model.predict(Xt)
    held = heldout_sms(160)
    Xh, yh = [features(m) for m in held], [m.truth["kind"] for m in held]
    pred_h = model.predict(Xh)
    report = classification_report(yt, pred, output_dict=True, zero_division=0)
    metrics = {
        "train_examples": len(X),
        "test_examples": len(Xt),
        "accuracy": round(float(accuracy_score(yt, pred)), 4),
        "macro_f1": round(float(f1_score(yt, pred, average="macro")), 4),
        "per_kind_f1": {k: round(v["f1-score"], 3) for k, v in report.items() if isinstance(v, dict) and k not in ("macro avg", "weighted avg")},
        "heldout_bank_styles_accuracy": round(float(accuracy_score(yh, pred_h)), 4),
    }
    return model, metrics


def predict(model: Pipeline, msgs: list[RawMessage]) -> list[tuple[str, float]]:
    if not msgs:
        return []
    proba = model.predict_proba([features(m) for m in msgs])
    classes = model.classes_
    best = np.argmax(proba, axis=1)
    return [(str(classes[i]), float(proba[row, i])) for row, i in enumerate(best)]
