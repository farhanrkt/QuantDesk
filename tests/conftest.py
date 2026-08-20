"""Shared fixtures.

EVERY TEST IN THIS SUITE RUNS OFFLINE. Nothing here touches yfinance, Google
News or any other network service — the engines are exercised against
deterministic synthetic OHLCV. That is deliberate: a suite that needs the
network is a suite that gets skipped, and the failures worth catching here
(a silently wrong number) do not require real market data to reproduce.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# api/ is not a package; index.py does the same sys.path dance at import time.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))


@pytest.fixture(scope="session")
def ohlcv() -> pd.DataFrame:
    """Two years of deterministic daily bars with a few planted extreme days.

    A geometric random walk with a fixed seed, plus five deliberate volume and
    price shocks so that anomaly detection has something unambiguous to find.
    """
    rng = np.random.default_rng(20260820)
    n = 500
    index = pd.bdate_range("2024-01-01", periods=n)

    returns = rng.normal(0.0004, 0.012, n)
    volume = rng.lognormal(mean=15.0, sigma=0.25, size=n)

    # Planted shocks: large move AND heavy volume on the same day.
    for position in (90, 180, 270, 360, 450):
        returns[position] = 0.09 if position % 2 == 0 else -0.09
        volume[position] *= 8.0

    close = 100.0 * np.exp(np.cumsum(returns))
    spread = close * 0.012
    return pd.DataFrame(
        {
            "Open": close * (1 + rng.normal(0, 0.002, n)),
            "High": close + spread,
            "Low": close - spread,
            "Close": close,
            "Volume": volume,
        },
        index=index,
    )
