"""Prophet wrapper. Imported lazily: the first import builds matplotlib's font cache (slow once)."""

from __future__ import annotations

import logging
import os
import time
import warnings

from app.core.config import get_settings


def _silence() -> None:
    # cmdstanpy/prophet configure their own handlers at import time, so levels are set afterwards
    for name in ("cmdstanpy", "prophet", "prophet.plot", "prophet.forecaster", "prophet.models", "matplotlib"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.ERROR)
        for handler in logger.handlers:
            handler.setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", module="prophet")


def load_prophet():  # noqa: ANN201
    os.environ.setdefault("MPLCONFIGDIR", str(get_settings().data_dir / "mpl"))
    logging.getLogger("prophet.plot").setLevel(logging.CRITICAL)  # "Importing plotly failed" — plotting isn't used
    from prophet import Prophet

    _silence()
    return Prophet


def tiny_fit() -> float:
    """Fit a small model end to end; returns seconds taken (capability check)."""
    import numpy as np
    import pandas as pd

    Prophet = load_prophet()
    t0 = time.time()
    ds = pd.date_range("2025-01-01", periods=120, freq="D")
    y = 100 + 10 * np.sin(np.arange(120) / 7 * 2 * np.pi)
    model = Prophet(weekly_seasonality=True, yearly_seasonality=False, daily_seasonality=False, uncertainty_samples=0)
    model.fit(pd.DataFrame({"ds": ds, "y": y}))
    model.predict(model.make_future_dataframe(periods=7))
    return time.time() - t0
