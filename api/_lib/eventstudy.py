"""
eventstudy.py
=============
Does the signal actually predict anything, and is the screener finding real
names or arithmetic?

TWO KINDS OF HONESTY, BOTH MISSING FROM MOST RETAIL TOOLS
---------------------------------------------------------
1. EVENT STUDY. Every anomaly-detection product asserts that its signal means
   something. This measures it, using the standard methodology: estimate a
   market model on a clean pre-event window, compute abnormal returns after the
   event, cumulate them, and test whether the average is distinguishable from
   zero. If accumulation signals do not beat the market, this says so.

2. MULTIPLE TESTING. Scanning twenty tickers at a threshold produces hits by
   construction. A screener that reports "3 names flagged" without saying how
   many it would flag from noise is reporting its own false-positive rate as a
   finding. Benjamini-Hochberg controls the false discovery rate across the
   scan, and the expected-false-discovery count is reported next to the hits.

WHY THE ESTIMATION WINDOW HAS A GAP
-----------------------------------
The market model is fitted on days ending `gap` days BEFORE the event, not
right up to it. If an anomaly is the visible edge of a multi-day episode — which
`accumulation.py` exists to detect — then fitting through the event contaminates
the baseline with the very behaviour under test, and shrinks the abnormal return
toward zero. Brown & Warner's designs leave the gap for exactly this reason.

References
----------
Brown, S. J., & Warner, J. B. (1985). "Using daily stock returns: The case of
    event studies." Journal of Financial Economics 14(1), 3-31.
MacKinlay, A. C. (1997). "Event Studies in Economics and Finance." Journal of
    Economic Literature 35(1), 13-39.
Bernard, V. L., & Thomas, J. K. (1989). "Post-Earnings-Announcement Drift:
    Delayed Price Response or Risk Premium?" Journal of Accounting Research 27.
Benjamini, Y., & Hochberg, Y. (1995). "Controlling the False Discovery Rate."
    Journal of the Royal Statistical Society B 57(1), 289-300.
Harvey, C. R., Liu, Y., & Zhu, H. (2016). "...and the Cross-Section of Expected
    Returns." Review of Financial Studies 29(1), 5-68.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd
from scipy import stats

DEFAULT_HORIZONS = (5, 20, 60)
DEFAULT_ESTIMATION_WINDOW = 120
DEFAULT_GAP = 10
MIN_ESTIMATION_DAYS = 40

# Bernard & Thomas's drift runs for roughly a quarter after the announcement,
# so an anomaly inside this window has an obvious benign explanation.
PEAD_WINDOW_DAYS = 3


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


# --------------------------------------------------------------------------- #
# Event study
# --------------------------------------------------------------------------- #
def abnormal_returns(stock: pd.Series, market: pd.Series, event_position: int,
                     estimation_window: int = DEFAULT_ESTIMATION_WINDOW,
                     gap: int = DEFAULT_GAP,
                     horizons: Sequence[int] = DEFAULT_HORIZONS) -> Optional[dict]:
    """Market-model abnormal returns and CARs for one event.

    Returns None when there is not enough clean history before the event or no
    post-event window to measure — silence rather than a number computed from
    twelve observations.
    """
    estimation_end = event_position - gap
    estimation_start = estimation_end - estimation_window
    if estimation_start < 0 or estimation_end - estimation_start < MIN_ESTIMATION_DAYS:
        return None

    y = stock.iloc[estimation_start:estimation_end].to_numpy()
    x = market.iloc[estimation_start:estimation_end].to_numpy()
    usable = np.isfinite(y) & np.isfinite(x)
    if usable.sum() < MIN_ESTIMATION_DAYS:
        return None
    y, x = y[usable], x[usable]

    x_centred = x - x.mean()
    sxx = float(np.sum(x_centred ** 2))
    if sxx <= 0:
        return None
    beta = float(np.sum(x_centred * (y - y.mean())) / sxx)
    alpha = float(y.mean() - beta * x.mean())

    residuals = y - (alpha + beta * x)
    residual_sd = float(np.std(residuals, ddof=2)) if len(residuals) > 2 else np.nan
    if not np.isfinite(residual_sd) or residual_sd <= 0:
        return None

    out = {"alpha": alpha, "beta": beta, "residualSd": residual_sd, "cars": {}}
    for horizon in horizons:
        window_end = event_position + 1 + horizon
        if window_end > len(stock):
            out["cars"][horizon] = None
            continue
        window_stock = stock.iloc[event_position + 1:window_end].to_numpy()
        window_market = market.iloc[event_position + 1:window_end].to_numpy()
        valid = np.isfinite(window_stock) & np.isfinite(window_market)
        if valid.sum() < max(1, horizon // 2):
            out["cars"][horizon] = None
            continue
        abnormal = window_stock[valid] - (alpha + beta * window_market[valid])
        car = float(np.sum(abnormal))
        # Standardised CAR: the residual sd scales with the square root of the
        # number of days cumulated, so this is comparable across horizons.
        out["cars"][horizon] = {
            "car": car,
            "standardised": car / (residual_sd * np.sqrt(valid.sum())),
            "days": int(valid.sum()),
        }
    return out


def run_event_study(price_history: pd.DataFrame, market_history: pd.DataFrame,
                    events: pd.DataFrame,
                    horizons: Sequence[int] = DEFAULT_HORIZONS,
                    estimation_window: int = DEFAULT_ESTIMATION_WINDOW,
                    gap: int = DEFAULT_GAP) -> dict:
    """Aggregate CARs across every detected event, with cross-sectional tests.

    `events` is expected to carry a `Flow` column so results can be split by
    direction — the question that matters is not "do anomalies predict returns"
    but "does the ACCUMULATION label predict a different outcome from the
    DISTRIBUTION one".
    """
    if price_history is None or price_history.empty or events is None or events.empty:
        return {"events": 0, "horizons": {}, "byDirection": {}, "usable": False,
                "reason": "No events to study."}

    stock = price_history["Close"].astype("float64").pct_change(fill_method=None)
    market = market_history["Close"].astype("float64").pct_change(fill_method=None)
    market = market.reindex(stock.index)

    positions = {date: i for i, date in enumerate(stock.index)}
    collected: list[dict] = []

    for date, row in events.iterrows():
        position = positions.get(date)
        if position is None:
            continue
        result = abnormal_returns(stock, market, position, estimation_window, gap, horizons)
        if result is None:
            continue
        collected.append({
            "date": date,
            "flow": row.get("Flow"),
            "strength": row.get("Strength"),
            "cars": result["cars"],
        })

    if not collected:
        return {"events": 0, "horizons": {}, "byDirection": {}, "usable": False,
                "reason": ("Not enough clean history around the detected events to "
                           "estimate a market model.")}

    def summarise(subset: list[dict], horizon: int) -> Optional[dict]:
        values = [c["cars"].get(horizon) for c in subset]
        cars = [v["car"] for v in values if v is not None and np.isfinite(v["car"])]
        if len(cars) < 3:
            return None
        cars_array = np.array(cars)
        mean = float(cars_array.mean())
        sd = float(cars_array.std(ddof=1))
        t_stat = mean / (sd / np.sqrt(len(cars_array))) if sd > 0 else np.nan
        p_value = (float(2 * (1 - stats.t.cdf(abs(t_stat), len(cars_array) - 1)))
                   if np.isfinite(t_stat) else None)
        return {
            "meanCar": mean, "medianCar": float(np.median(cars_array)),
            "sd": sd, "n": len(cars_array),
            "tStat": _finite(t_stat), "pValue": p_value,
            "hitRate": float((cars_array > 0).mean()),
        }

    horizon_summary = {str(h): summarise(collected, h) for h in horizons}
    by_direction = {}
    for direction in ("Accumulation", "Distribution"):
        subset = [c for c in collected if c["flow"] == direction]
        if subset:
            by_direction[direction] = {str(h): summarise(subset, h) for h in horizons}

    return {
        "events": len(collected),
        "horizons": horizon_summary,
        "byDirection": by_direction,
        "usable": True,
        "config": {"estimationWindow": estimation_window, "gap": gap,
                   "horizons": list(horizons)},
        "caveat": (
            "Cumulative abnormal returns versus a market model fitted on the "
            "120 trading days ending 10 days before each event. In-sample, on "
            "one ticker, with overlapping windows — indicative, not a backtest."
        ),
    }


# --------------------------------------------------------------------------- #
# Post-earnings-announcement drift
# --------------------------------------------------------------------------- #
def tag_earnings_proximity(events: pd.DataFrame, earnings_dates: Sequence,
                           window: int = PEAD_WINDOW_DAYS) -> dict:
    """Mark anomalies that sit within `window` days of an earnings release.

    The app's own disclaimer says anomalous activity has benign causes. This
    names the most common one. An anomaly two days after a print is not evidence
    of institutional accumulation; it is the market repricing an announcement,
    and Bernard & Thomas showed that repricing continues for weeks.
    """
    if events is None or events.empty or not len(earnings_dates):
        return {"available": False, "tagged": 0, "total": 0 if events is None else len(events),
                "dates": []}

    announcements = pd.to_datetime(pd.Series(list(earnings_dates))).dt.tz_localize(None)
    announcements = announcements.dropna().sort_values()

    tagged = []
    for date in events.index:
        naive = pd.Timestamp(date).tz_localize(None) if pd.Timestamp(date).tz else pd.Timestamp(date)
        deltas = (announcements - naive).abs().dt.days
        if len(deltas) and int(deltas.min()) <= window:
            nearest = announcements.iloc[int(deltas.values.argmin())]
            tagged.append({
                "date": naive.strftime("%Y-%m-%d"),
                "earnings": nearest.strftime("%Y-%m-%d"),
                "daysApart": int(deltas.min()),
            })

    return {
        "available": True,
        "tagged": len(tagged),
        "total": len(events),
        "share": len(tagged) / len(events) if len(events) else 0.0,
        "window": window,
        "dates": tagged[:20],
    }


# --------------------------------------------------------------------------- #
# Multiple testing
# --------------------------------------------------------------------------- #
def binomial_pvalue(observed: int, trials: int, rate: float) -> float:
    """P(X >= observed) under Binomial(trials, rate) — a one-sided exact test."""
    if trials <= 0 or observed <= 0:
        return 1.0
    rate = float(min(max(rate, 1e-9), 1.0 - 1e-9))
    return float(stats.binom.sf(observed - 1, trials, rate))


def benjamini_hochberg(pvalues: Sequence[float], alpha: float = 0.10) -> dict:
    """Benjamini-Hochberg step-up procedure controlling the false discovery rate.

    Returns per-test `qValues` (adjusted p-values, monotonised) and a boolean
    `rejected` flag, plus the count of discoveries. FDR rather than
    family-wise error: rejecting a few false positives among many screening hits
    is an acceptable trade, whereas Bonferroni on a 20-name scan would reject
    almost nothing and make the screener useless.
    """
    values = np.asarray([1.0 if p is None or not np.isfinite(p) else float(p)
                         for p in pvalues], dtype=float)
    n = len(values)
    if n == 0:
        return {"qValues": [], "rejected": [], "discoveries": 0, "alpha": alpha}

    order = np.argsort(values)
    ranked = values[order]
    adjusted = ranked * n / np.arange(1, n + 1)
    # Monotonise from the largest p-value down, so q-values never decrease.
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)

    q = np.empty(n)
    q[order] = adjusted
    rejected = q <= alpha
    return {
        "qValues": [float(v) for v in q],
        "rejected": [bool(v) for v in rejected],
        "discoveries": int(rejected.sum()),
        "alpha": alpha,
    }


def screener_significance(rows: Sequence[dict], recent_trading_days: int,
                          alpha: float = 0.10) -> dict:
    """Attach a p-value and a BH q-value to every screener hit.

    The null is that a ticker's anomalies arrive at its OWN long-run rate,
    independently across days. Under that null, seeing `k` flags in a window of
    `recent_trading_days` has an exact binomial probability — so a name that
    flags constantly needs far more recent activity to be interesting than a
    normally quiet one. That per-ticker calibration is the point: a fixed count
    threshold silently favours noisy stocks.
    """
    usable = [r for r in rows
              if r.get("anomalyRate") is not None and r.get("recentAnomalies") is not None]
    if not usable:
        return {"available": False, "rows": list(rows),
                "reason": "Screener rows carry no base rate to test against."}

    pvalues = [binomial_pvalue(int(r["recentAnomalies"]), int(recent_trading_days),
                               float(r["anomalyRate"])) for r in usable]
    correction = benjamini_hochberg(pvalues, alpha)

    for row, p, q, rejected in zip(usable, pvalues, correction["qValues"],
                                   correction["rejected"], strict=True):
        row["pValue"] = float(p)
        row["qValue"] = float(q)
        row["significant"] = bool(rejected)

    expected_false = float(np.sum(pvalues))     # sum of null probabilities
    return {
        "available": True,
        "rows": list(rows),
        "tested": len(usable),
        "discoveries": correction["discoveries"],
        "expectedByChance": expected_false,
        "alpha": alpha,
        "reading": (
            f"{correction['discoveries']} of {len(usable)} names survive a "
            f"false-discovery-rate correction at {alpha:.0%}. About "
            f"{expected_false:.1f} hit{'' if abs(expected_false - 1) < 0.05 else 's'} "
            f"would be expected from each name's own base rate alone."
        ),
    }
