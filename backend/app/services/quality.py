"""Model evaluation shown in Settings → Model evaluation (and quoted in the README). The models are trained on
synthetic messages; they are measured on held-out synthetic data and on hand-written messages in real bank formats.
Computed once after training (cached as JSON) because evaluating the parsers re-renders a persona."""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from app.core.config import get_settings
from app.ml import registry

log = logging.getLogger("finpilot.quality")


def _path():  # noqa: ANN202
    return get_settings().models_dir / "quality.json"


def compute(user_id: int | None = None) -> dict[str, Any]:
    from app.ml import evaluate
    from app.ml.evaluate_pipeline import evaluate_capture

    parsing = evaluate.run()
    report: dict[str, Any] = {
        "generated_for": date.today().isoformat(),
        "model_version": registry.version_tag(),
        "categorizer": registry.metrics("categorizer"),
        "message_classifier": registry.metrics("message_classifier"),
        "coach_intents": registry.metrics("coach_intents"),
        "parsing": {k: {kk: vv for kk, vv in v.items() if kk != "errors"} for k, v in parsing.items()},
    }
    if user_id is not None:
        try:
            report["capture"] = evaluate_capture(user_id, date.today())
        except Exception as exc:  # pragma: no cover
            log.warning("capture evaluation failed: %s", exc)
    _path().write_text(json.dumps(report, indent=2, default=str))
    return report


def load() -> dict[str, Any] | None:
    try:
        return json.loads(_path().read_text())
    except (OSError, ValueError):
        return None
