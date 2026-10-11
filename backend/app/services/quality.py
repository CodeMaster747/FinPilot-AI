"""Model-quality report shown in Settings → System & model quality (and quoted in the README).
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


def picks_precision(db, user, k: int = 10) -> dict[str, Any] | None:  # noqa: ANN001
    """Precision@k of the demo persona's Smart Picks against its known interests, next to a popularity baseline
    (the k most-reviewed products). Only defined for the demo persona, whose true interests are known."""
    from sqlalchemy import select

    from app.models import Product, ProductRecommendation
    from app.seed.demo_profile import TRUE_INTERESTS

    if not user.is_demo:
        return None

    def relevant(p: Product) -> bool:
        text = (p.title + " " + " ".join(p.tags or [])).lower()
        return any(word in text for word in TRUE_INTERESTS)

    recs = db.scalars(select(Product).join(ProductRecommendation, ProductRecommendation.product_id == Product.id)
                      .where(ProductRecommendation.user_id == user.id).order_by(ProductRecommendation.score.desc()).limit(k)).all()
    popular = db.scalars(select(Product).where(Product.stale.is_(False)).order_by(Product.rating_count.desc()).limit(k)).all()
    if not recs:
        return None
    return {"k": k, "picks": round(sum(map(relevant, recs)) / len(recs), 2),
            "popularity_baseline": round(sum(map(relevant, popular)) / max(1, len(popular)), 2), "evaluated": len(recs)}
