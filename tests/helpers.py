"""Shared offline fixtures.

`path` and `steady` build OHLCV frames from a planted return series; `_Stub`
reproduces both column shapes `yf.download` actually returns; `mixed_calendars`
plants names that do not share trading days. All of them are used by more than
one suite — the ranking tests and the data-boundary tests, the portfolio and
exposure tests — so they live here rather than being copied, which is how two
copies drift into disagreeing about what a realistic frame looks like.
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


def mixed_calendars(days: int = 900, seed: int = 29) -> dict[str, pd.DataFrame]:
    """OHLCV for names on three calendars, sampled from one price process.

    US names trade weekdays less 12 holidays of their own; IDX names trade
    weekdays less 40 of theirs and one week shut throughout; COIN trades every
    day; CL=F trades every weekday, as the futures that ride along in a
    portfolio batch do. Prices walk over EVERY calendar day and are sampled on
    each name's sessions, so a name reopening after a holiday has moved with
    everything that happened while it was shut.

    Handed to `_Stub`, the batch comes back on the union of these dates with
    NaN where a name did not trade, which is the shape yfinance returns. The
    frames end today, so nothing reads as stale whenever the suite runs.
    """
    rng = np.random.default_rng(seed)
    every = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days, freq="D")
    weekdays = every[every.dayofweek < 5]
    # Monday to Friday of one week, so it is one whole week to `to_weekly`.
    monday = every[-140] + pd.Timedelta(days=(7 - every[-140].dayofweek) % 7)
    shut_week = weekdays[(weekdays >= monday) & (weekdays < monday + pd.Timedelta(days=5))]
    open_days = weekdays.difference(shut_week)
    picks = rng.permutation(len(open_days))
    us_days = weekdays.difference(open_days[picks[:12]])
    idx_days = weekdays.difference(open_days[picks[12:52]]).difference(shut_week)

    market = rng.normal(0.0002, 0.01, len(every))
    spec = {  # symbol: (sessions, beta, idiosyncratic sd)
        "AAA": (us_days, 1.0, 0.004), "CCC": (us_days, 1.0, 0.004),
        "EEE": (us_days, 0.6, 0.010),
        "BBB.JK": (idx_days, 1.0, 0.004), "DDD.JK": (idx_days, 1.0, 0.004),
        "FFF.JK": (idx_days, 0.6, 0.010),
        "COIN": (every, 1.0, 0.010), "CL=F": (weekdays, 0.3, 0.020),
    }
    out = {}
    for symbol, (sessions, beta, idio) in spec.items():
        walk = pd.Series(100.0 * np.exp(np.cumsum(beta * market + rng.normal(0.0, idio, len(every)))),
                         index=every)
        close = walk.reindex(sessions)
        out[symbol] = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                                    "Close": close, "Volume": 1_000_000.0}, index=sessions)
    return out



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

