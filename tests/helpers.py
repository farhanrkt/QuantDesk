"""Shared offline fixtures.

`path` and `steady` build OHLCV frames from a planted return series; `_Stub`
reproduces both column shapes `yf.download` actually returns. All three are used
by more than one suite — the ranking tests and the data-boundary tests — so they
live here rather than being copied, which is how two copies drift into
disagreeing about what a realistic frame looks like.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def path(returns, start_price=100.0, start="2023-01-02"):
    """An OHLCV frame from a return series, with a mild fixed intraday range."""
    close = start_price * np.exp(np.cumsum(np.asarray(returns, dtype="float64")))
    index = pd.bdate_range(start, periods=len(close))
    return pd.DataFrame({
        "Open": close,
        "High": close * 1.01,
        "Low": close * 0.99,
        "Close": close,
        "Volume": np.full(len(close), 1_000_000.0),
    }, index=index)


def steady(n=400, drift=0.0004, sigma=0.010, seed=3):
    rng = np.random.default_rng(seed)
    return rng.normal(drift, sigma, n)



class _Stub:
    """Stands in for `yf.download`, reproducing both real column shapes."""

    def __init__(self, frames: dict[str, pd.DataFrame], multiindex: bool = True):
        self.frames = frames
        self.multiindex = multiindex
        self.calls: list[list[str]] = []

    def __call__(self, chunk, **_kwargs):
        symbols = list(chunk) if isinstance(chunk, (list, tuple)) else [chunk]
        self.calls.append(symbols)
        available = [s for s in symbols if s in self.frames]
        if not available:
            return pd.DataFrame()
        if self.multiindex:
            return pd.concat({s: self.frames[s] for s in available}, axis=1)
        return self.frames[available[0]]

