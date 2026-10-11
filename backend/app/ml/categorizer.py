"""Merchant-text -> category classifier: the ML fallback behind user rules and the alias map.

TF-IDF over words + character 3-5 grams (so 'SWIGGY*ORDER123' still looks like 'swiggy'),
calibrated logistic regression. Trained on alias variants and generic merchant-name vocabulary.
"""

from __future__ import annotations

import random

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

from app.ml.text import normalize
from app.seed.reference import CATEGORY_VOCAB, MERCHANTS

PREFIXES = ["", "", "upi ", "pos ", "upi/p2m/", "ach d- ", "neft ", "imps ", "ecom ", "vps ", "nfs "]
SUFFIXES = ["", "", " pvt ltd", " india", " ltd", " chennai", " bangalore", " mumbai", " online", " payments", " store"]
NAME_PARTS = ["sri", "new", "royal", "star", "city", "golden", "anand", "lakshmi", "balaji", "metro", "green", "classic",
              "galaxy", "venkateswara", "shree", "sunrise", "ganesh", "kumaran", "murugan", "national"]


def _noise(rng: random.Random, text: str) -> str:
    variants = [
        text,
        text.upper(),
        text.replace(" ", ""),
        f"{text}*{rng.randint(1000, 99999)}",
        f"{text} {rng.randint(100, 9999)}",
        f"{text.split()[0]}@{rng.choice(['ybl', 'okicici', 'okaxis', 'hdfcbank', 'icici', 'paytm', 'axl'])}",
    ]
    return f"{rng.choice(PREFIXES)}{rng.choice(variants)}{rng.choice(SUFFIXES)}"


def build_dataset(seed: int = 3, per_alias: int = 6, per_vocab: int = 18) -> tuple[list[str], list[str]]:
    rng = random.Random(seed)
    X, y = [], []
    for m in MERCHANTS:
        for alias in (*m.aliases, m.name.lower()):
            for _ in range(per_alias):
                X.append(normalize(_noise(rng, alias)))
                y.append(m.category)
    for category, words in CATEGORY_VOCAB.items():
        for _ in range(per_vocab):
            for word in words:
                name = f"{rng.choice(NAME_PARTS)} {word}" if rng.random() < 0.8 else word
                X.append(normalize(_noise(rng, name)))
                y.append(category)
    return X, y


def make_pipeline() -> Pipeline:
    features = FeatureUnion([
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)),
    ])
    return Pipeline([("features", features), ("clf", LogisticRegression(C=8.0, max_iter=3000))])


def train() -> tuple[Pipeline, dict]:
    X, y = build_dataset(seed=3)
    model = make_pipeline().fit(X, y)
    # held-out evaluation on freshly generated variants (different seed => unseen noise/names)
    Xt, yt = build_dataset(seed=97, per_alias=2, per_vocab=4)
    pred = model.predict(Xt)
    metrics = {
        "train_examples": len(X),
        "test_examples": len(Xt),
        "accuracy": round(float(accuracy_score(yt, pred)), 4),
        "macro_f1": round(float(f1_score(yt, pred, average="macro")), 4),
        "classes": len(set(y)),
    }
    return model, metrics


def predict(model: Pipeline, texts: list[str]) -> list[tuple[str, float]]:
    if not texts:
        return []
    proba = model.predict_proba([normalize(t) for t in texts])
    classes = model.classes_
    best = np.argmax(proba, axis=1)
    return [(str(classes[i]), float(proba[row, i])) for row, i in enumerate(best)]
