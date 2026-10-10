"""Load/save trained models under data/models with a version stamp, so stale models retrain."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import joblib
import sklearn

from app.core.config import get_settings

# Bump when training data or features change; models with an older version are retrained.
MODEL_VERSION = "2026.10.3"
_cache: dict[str, Any] = {}
_lock = threading.Lock()


def _paths(name: str) -> tuple[Path, Path]:
    d = get_settings().models_dir
    return d / f"{name}.joblib", d / f"{name}.json"


def version_tag() -> str:
    return f"{MODEL_VERSION}+sklearn{sklearn.__version__}"


def save(name: str, model: Any, metrics: dict[str, Any]) -> None:
    model_path, meta_path = _paths(name)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    meta_path.write_text(json.dumps({"version": version_tag(), "metrics": metrics}, indent=2, default=str))
    with _lock:
        _cache[name] = model


def is_current(name: str) -> bool:
    model_path, meta_path = _paths(name)
    if not (model_path.exists() and meta_path.exists()):
        return False
    try:
        return json.loads(meta_path.read_text()).get("version") == version_tag()
    except (OSError, ValueError):
        return False


def metrics(name: str) -> dict[str, Any]:
    _, meta_path = _paths(name)
    try:
        return json.loads(meta_path.read_text()).get("metrics", {})
    except (OSError, ValueError):
        return {}


_train_lock = threading.Lock()


def load(name: str) -> Any:
    with _lock:
        if name in _cache:
            return _cache[name]
    if not is_current(name):  # first use, deleted, or trained by an older version: train now
        with _train_lock:
            if not is_current(name):
                from app.ml.train import ensure_models

                ensure_models()
    model_path, _ = _paths(name)
    model = joblib.load(model_path)
    with _lock:
        _cache[name] = model
    return model


def clear_cache() -> None:
    with _lock:
        _cache.clear()
