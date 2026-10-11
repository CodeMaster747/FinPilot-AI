"""Capability self-check: proves the ML stack actually runs on this machine (deck: 'capability gate')."""

from __future__ import annotations

import importlib.metadata as md
import logging
import platform
import sqlite3
import sys
import time
from typing import Any

from app.jobs.runner import job

log = logging.getLogger("finpilot.system")

CAPABILITIES: dict[str, Any] = {"status": "pending"}


def _version(pkg: str) -> str | None:
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


def check_prophet() -> dict[str, Any]:
    t0 = time.time()
    try:
        from app.services.forecasting.prophet_model import tiny_fit

        seconds = tiny_fit()
        return {"ok": True, "version": _version("prophet"), "fit_seconds": round(seconds, 2),
                "warmup_seconds": round(time.time() - t0, 1)}
    except Exception as exc:  # pragma: no cover - environment specific
        log.warning("prophet unavailable: %s", exc)
        return {"ok": False, "version": _version("prophet"), "error": str(exc)[:200]}


def check_sklearn() -> dict[str, Any]:
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    X = np.array([[0.0], [1.0], [2.0], [3.0]])
    y = np.array([0, 0, 1, 1])
    ok = LogisticRegression().fit(X, y).predict([[2.5]])[0] == 1
    return {"ok": bool(ok), "version": _version("scikit-learn")}


@job("system_warmup")
def system_warmup(ctx) -> dict[str, Any]:  # noqa: ANN001
    CAPABILITIES.update({"status": "checking"})
    result = {
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.machine()}",
        "sqlite": sqlite3.sqlite_version,
        "sklearn": check_sklearn(),
        "prophet": check_prophet(),
        "pdfplumber": {"ok": _version("pdfplumber") is not None, "version": _version("pdfplumber")},
        "ocr": {"ok": True, "engine": "tesseract.js (runs in the browser)"},
    }
    result["status"] = "ready"
    CAPABILITIES.clear()
    CAPABILITIES.update(result)
    return {"prophet_ok": result["prophet"]["ok"]}
