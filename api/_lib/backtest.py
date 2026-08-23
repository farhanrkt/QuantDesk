"""
backtest.py
===========
Does the composite ranking predict anything?

WHY THIS EXISTS
---------------
The ranking tier scores a universe on seven signals and orders it. It reports
how much those signals overlap — about 3.4 columns' worth of independent
information out of seven — but it has never reported whether the resulting order
has any relationship to what happens next. Every other claim in this app is
either measured or explicitly graded; this one was asserted by omission.

The flow lens already has its answer: `eventstudy.py` measures whether an
anomaly flag predicts abnormal returns, and on JPM it returned no significant
effect at any horizon. Reporting that is the point. This is the same question
asked of the breadth tier.

WHAT IS MEASURED
----------------
At each rebalance date the universe is ranked using ONLY data available on that
date, and the forward return of every name over the next `horizon` trading days
is recorded. Two summaries come out of that, and they answer different things:

  INFORMATION COEFFICIENT — the rank correlation, within each period, between a
  name's composite score and its subsequent return. This is the direct question:
  does a higher rank correspond to a better outcome? It is averaged across
  periods and given a t-statistic. An IC of 0.03 sustained is considered useful
  by professional standards; an IC indistinguishable from zero means the order
  carries no information about the future.

  QUINTILE SPREAD — the mean forward return of the top fifth minus the bottom
  fifth. More intuitive, noisier, and the thing people actually picture.

FOUR REASONS THE RESULT WILL FLATTER ITSELF, ALL UNAVOIDABLE HERE
------------------------------------------------------------------
1. SURVIVORSHIP. The universes in `universes.py` are today's constituents. A
   company that was in the index five years ago and collapsed is absent, and one
   promoted last year is present for the whole history. Every name tested is a
   name that survived and was still large enough to be a member today. This
   biases returns upward and there is no fix without a point-in-time membership
   dataset, which this app does not have.

2. NO COSTS. No spread, no commission, no market impact, no tax. The app's own
   microstructure module exists precisely because those are not negligible.

3. SMALL SAMPLE. A handful of years divided into non-overlapping periods leaves
   tens of observations, not hundreds. A t-statistic on thirty periods is a weak
   instrument.

4. ONE HISTORY. This is one path through one market regime, not a distribution
   of possible histories.

The periods are NON-OVERLAPPING by default — the rebalance interval defaults to
the horizon — because overlapping windows share days, which inflates a
t-statistic without adding information. That is the one bias here that can be
removed for free, so it is.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, Sequence

import numpy as np
import pandas as pd
from scipy import stats

from . import market_data, ranking, riskmodel

# Enough history before the first rebalance for the hungriest signal to exist.
# `ranking.MIN_BARS` is 280 bars; a calendar year is roughly 252, so this buys
# the warm-up plus a margin for holidays.
WARMUP_DAYS = 460


def _forward_return(close: pd.Series, start: pd.Timestamp,
                    horizon: int) -> Optional[float]:
    """Return from the close on `start` to `horizon` trading days later."""
    position = close.index.searchsorted(start)
    if position >= len(close):
        return None
    end = position + horizon
    if end >= len(close):
        return None
    first, last = float(close.iloc[position]), float(close.iloc[end])
    if not np.isfinite(first) or not np.isfinite(last) or first <= 0:
        return None
    return last / first - 1.0


def rebalance_dates(index: pd.DatetimeIndex, horizon: int,
                    every: Optional[int] = None) -> list[pd.Timestamp]:
    """Dates to rank on, spaced so the forward windows do not overlap.

    `every` defaults to `horizon`, which makes each period independent of the
    last. Overlapping windows share trading days: the observations are then
    correlated, and a t-statistic computed as though they were not overstates
    its own significance. That is the easiest bias to remove and the one most
    often left in.
    """
    step = every or horizon
    start = index.searchsorted(index[0] + pd.Timedelta(days=WARMUP_DAYS))
    stop = len(index) - horizon - 1
    return [index[i] for i in range(start, stop, step)] if stop > start else []


def run(symbols: Sequence[str], market_code: str = "US", horizon: int = 63,
        years: int = 6, every: Optional[int] = None) -> dict:
    """Rank the universe at each rebalance and score the order that came out."""
    end = dt.date.today()
    start = end - dt.timedelta(days=int(365.25 * years) + WARMUP_DAYS)

    frames = market_data.ohlcv_batch(list(symbols), start, end)
    benchmark_symbol = riskmodel.MARKET_INDEX.get((market_code or "US").upper(), "^GSPC")
    index_frames = market_data.ohlcv_batch([benchmark_symbol], start, end)
    benchmark = (index_frames[benchmark_symbol]["Close"].astype("float64")
                 if benchmark_symbol in index_frames else None)

    usable = {s: f for s, f in frames.items() if len(f) >= ranking.MIN_BARS}
    if len(usable) < 10:
        return {"usable": False,
                "reason": (f"Only {len(usable)} symbols had enough history. A "
                           f"cross-sectional test needs a cross-section.")}

    calendar = sorted({d for f in usable.values() for d in f.index})
    calendar = pd.DatetimeIndex(calendar)
    dates = rebalance_dates(calendar, horizon, every)
    if len(dates) < 5:
        return {"usable": False,
                "reason": f"Only {len(dates)} independent periods fit in {years} years "
                          f"at a {horizon}-day horizon."}

    periods = []
    for asof in dates:
        # POINT IN TIME. Every frame is truncated at the rebalance date before
        # any signal is computed, so nothing downstream can see the future —
        # `price_signals` reads from the END of whatever it is given.
        sliced = {s: f.loc[:asof] for s, f in usable.items()}
        sliced = {s: f for s, f in sliced.items() if len(f) >= ranking.MIN_BARS}
        if len(sliced) < 10:
            continue
        bench = benchmark.loc[:asof] if benchmark is not None else None

        ranked = ranking.rank_universe(sliced, benchmark=bench)
        rows = [r for r in ranked["rows"] if r.get("composite") is not None]
        if len(rows) < 10:
            continue

        scored = []
        for row in rows:
            forward = _forward_return(usable[row["ticker"]]["Close"].astype("float64"),
                                      asof, horizon)
            if forward is not None:
                scored.append((row["composite"], forward))
        if len(scored) < 10:
            continue

        composites = np.array([c for c, _ in scored], dtype="float64")
        forwards = np.array([f for _, f in scored], dtype="float64")

        # Information coefficient: does a higher rank go with a better outcome?
        ic = stats.spearmanr(composites, forwards).statistic
        order = np.argsort(composites)
        fifth = max(1, len(order) // 5)
        bottom = float(np.mean(forwards[order[:fifth]]))
        top = float(np.mean(forwards[order[-fifth:]]))

        periods.append({
            "date": asof.strftime("%Y-%m-%d"),
            "names": len(scored),
            "ic": float(ic) if np.isfinite(ic) else None,
            "top": top, "bottom": bottom, "spread": top - bottom,
            "universeMean": float(np.mean(forwards)),
        })

    if len(periods) < 5:
        return {"usable": False,
                "reason": f"Only {len(periods)} periods produced a usable cross-section."}

    ics = np.array([p["ic"] for p in periods if p["ic"] is not None], dtype="float64")
    spreads = np.array([p["spread"] for p in periods], dtype="float64")

    def summarise(values: np.ndarray) -> dict:
        """Mean, and whether it is distinguishable from zero.

        The t-statistic is the plain one-sample form. It is honest ONLY because
        the periods do not overlap; with overlapping windows the same arithmetic
        would overstate significance, which is why `rebalance_dates` spaces them.
        """
        n = len(values)
        mean = float(np.mean(values))
        sd = float(np.std(values, ddof=1)) if n > 1 else float("nan")
        t = mean / (sd / np.sqrt(n)) if n > 1 and sd > 0 else float("nan")
        p = float(2 * (1 - stats.t.cdf(abs(t), df=n - 1))) if np.isfinite(t) else float("nan")
        # WHAT THE TEST COULD HAVE SEEN. A null result is only informative
        # alongside its own power: "no effect found" and "no effect large enough
        # to find" are different statements, and with tens of noisy periods the
        # second is usually the true one. This is the smallest mean the test
        # would detect four times in five at the 5% level — anything under it
        # could be real and still invisible here.
        detectable = 2.8 * sd / np.sqrt(n) if n > 1 and np.isfinite(sd) else float("nan")
        return {"mean": mean, "stdev": sd if np.isfinite(sd) else None,
                "tStat": float(t) if np.isfinite(t) else None,
                "pValue": p if np.isfinite(p) else None, "periods": n,
                "positiveShare": float(np.mean(values > 0)),
                "minimumDetectable": float(detectable) if np.isfinite(detectable) else None}

    ic_summary, spread_summary = summarise(ics), summarise(spreads)
    significant = (spread_summary["pValue"] is not None and spread_summary["pValue"] < 0.05
                   and spread_summary["mean"] > 0)

    return {
        "usable": True,
        "symbols": len(usable),
        "horizonDays": horizon,
        "rebalanceDays": every or horizon,
        "overlapping": bool(every and every < horizon),
        "from": periods[0]["date"], "to": periods[-1]["date"],
        "benchmark": benchmark_symbol if benchmark is not None else None,
        "informationCoefficient": ic_summary,
        "quintileSpread": spread_summary,
        "periods": periods,
        "verdict": _verdict(ic_summary, spread_summary, significant),
        "caveats": [
            "Survivorship: the universe is today's constituents, so every name "
            "tested is one that survived and is still a member. This biases the "
            "result upward and cannot be corrected without point-in-time "
            "membership data.",
            "No trading costs, spread, market impact or tax are deducted.",
            f"{ic_summary['periods']} non-overlapping periods is a small sample; "
            f"a t-statistic on it is a weak instrument.",
            "One history, one market regime. Not a distribution of outcomes.",
        ],
    }


def _verdict(ic: dict, spread: dict, significant: bool) -> str:
    """The sentence this whole module exists to be able to write honestly."""
    if significant:
        return (f"Over this sample the top fifth beat the bottom fifth by "
                f"{spread['mean']:.2%} per period on average "
                f"(t = {spread['tStat']:.2f}, p = {spread['pValue']:.3f}), with a mean "
                f"information coefficient of {ic['mean']:.3f}. Read it against the "
                f"caveats below before treating it as an edge — survivorship alone "
                f"could account for a result of this size.")
    floor = ""
    if ic.get("minimumDetectable"):
        floor = (f" This test could only have detected a mean information coefficient of "
                 f"about {ic['minimumDetectable']:.3f} or larger, so a real but modest "
                 f"edge would be invisible in a sample this size — 'not found' is not "
                 f"'not there'.")
    return (f"No significant relationship between rank and subsequent return in this "
            f"sample. The top fifth beat the bottom by {spread['mean']:.2%} per period "
            f"on average, which is not distinguishable from zero "
            f"(t = {spread['tStat']:.2f}, p = {spread['pValue']:.3f}); the mean "
            f"information coefficient is {ic['mean']:.3f}. On this evidence the "
            f"composite orders the universe without demonstrably predicting it.{floor}")
