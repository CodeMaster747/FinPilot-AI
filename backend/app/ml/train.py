"""Train (or reuse) every base model. Deterministic: same code + same seeds => same models."""

from __future__ import annotations

import logging
import time

from app.ml import categorizer, coach_intents, message_classifier, registry

log = logging.getLogger("finpilot.ml")

MODELS = {
    "categorizer": categorizer.train,
    "message_classifier": message_classifier.train,
    "coach_intents": coach_intents.train,
}


def ensure_models(force: bool = False, progress=None) -> dict[str, dict]:  # noqa: ANN001
    results = {}
    for i, (name, trainer) in enumerate(MODELS.items()):
        if not force and registry.is_current(name):
            results[name] = registry.metrics(name)
            continue
        t0 = time.time()
        if progress:
            progress(name)
        model, metrics = trainer()
        metrics["train_seconds"] = round(time.time() - t0, 1)
        registry.save(name, model, metrics)
        log.info("trained %s in %.1fs: %s", name, time.time() - t0, {k: v for k, v in metrics.items() if k != "per_kind_f1"})
        results[name] = metrics
    return results
