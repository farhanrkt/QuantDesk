"""
accumulation.py
===============
Sustained accumulation and distribution, via sequential change detection.

THE GAP THIS FILLS
------------------
The Isolation Forest finds POINT anomalies — days that look unlike other days.
But an institution building a position does the opposite of standing out: it
splits the order across weeks precisely so no single print is remarkable. A
detector that scores each day independently is structurally blind to the patient
buyer the product is named after. It can only ever catch the impatient one.

Change detection asks a different question. Not "was today unusual?" but "has
the ORDER FLOW REGIME shifted, and when?". Page's CUSUM accumulates small
deviations from a baseline, so a long run of mildly positive money flow — each
day individually unremarkable — trips the alarm that no single day would.

WHAT IT RUNS ON
---------------
`OBV_Change_Z`: the day's on-balance-volume change standardised by its own
rolling volatility, which `whale.py` already engineers as a model feature. Using
it here costs nothing and keeps both detectors reading the same quantity.

CUSUM, briefly
--------------
Two one-sided statistics walk alongside the series:

    S+_t = max(0, S+_{t-1} + (x_t - k))        upward drift
    S-_t = max(0, S-_{t-1} - (x_t + k))        downward drift

`k` is a slack that absorbs ordinary noise, so a stationary series leaves both
statistics pinned near zero. Once either exceeds `h`, a regime is declared. The
episode's start is backdated to where the statistic last left zero, which is
the estimated changepoint rather than the day the alarm happened to fire.

References
----------
Page, E. S. (1954). "Continuous Inspection Schemes." Biometrika 41(1/2).
Granville, J. E. (1963). New Key to Stock Market Profits. (On-balance volume.)
Basseville, M., & Nikiforov, I. V. (1993). Detection of Abrupt Changes:
    Theory and Application. Prentice-Hall.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# Slack, in standard deviations. Half a sigma is the textbook default: it makes
# CUSUM most sensitive to a sustained shift of about one sigma, which is the
# size of drift a patient accumulator actually leaves behind.
DEFAULT_SLACK = 0.5

# Decision threshold, in the same units. Five gives an average run length to
# false alarm in the hundreds of days for a stationary series — appropriate when
# a year of history holds ~250 observations and false episodes are expensive.
DEFAULT_THRESHOLD = 5.0

# An episode shorter than this is a spike, which the Isolation Forest already
# reports. This module only claims the ones it is uniquely able to see.
MIN_EPISODE_DAYS = 5

# Per-observation cap, in standard deviations — the robust CUSUM variant.
#
# THIS IS WHAT KEEPS THE TWO DETECTORS FROM DUPLICATING EACH OTHER. Without it,
# one 40-sigma print pushes the statistic far past the threshold on its own, and
# because CUSUM only decays by `slack` per day it then reports a fictitious
# eleven-week "accumulation regime" that is really the tail of a single day.
# Clipping says: an extreme single day is the point detector's finding, not
# this one's. Sustained drift still accumulates normally, because a real regime
# is made of ordinary days.
DEFAULT_WINSOR = 4.0


def cusum_episodes(series: pd.Series, slack: float = DEFAULT_SLACK,
                   threshold: float = DEFAULT_THRESHOLD,
                   min_days: int = MIN_EPISODE_DAYS,
                   winsor: float = DEFAULT_WINSOR) -> list[dict]:
    """Two-sided robust CUSUM over a standardised series; returns episodes.

    Each episode carries the estimated changepoint (`start`), the day the
    statistic crossed the threshold (`detected`), and where it decayed back to
    zero (`end`) — so the reader can see both when the regime began and when
    there was enough evidence to say so.
    """
    values = pd.Series(series).astype("float64").replace([np.inf, -np.inf], np.nan).dropna()
    if len(values) < min_days:
        return []

    index = values.index
    x = np.clip(values.to_numpy(), -abs(winsor), abs(winsor))

    pos = neg = 0.0
    pos_anchor = neg_anchor = 0          # where the statistic last left zero
    active: Optional[dict] = None
    episodes: list[dict] = []

    def close(episode: dict, end_position: int) -> None:
        episode["end"] = index[end_position]
        episode["days"] = end_position - episode["_start_position"] + 1
        if episode["days"] >= min_days:
            episodes.append(episode)

    for i, value in enumerate(x):
        previous_pos, previous_neg = pos, neg
        pos = max(0.0, pos + value - slack)
        neg = max(0.0, neg - value - slack)

        if previous_pos == 0.0 and pos > 0.0:
            pos_anchor = i
        if previous_neg == 0.0 and neg > 0.0:
            neg_anchor = i

        # An active episode ends when its own statistic decays back to zero.
        if active is not None:
            statistic = pos if active["direction"] == "Accumulation" else neg
            if statistic == 0.0:
                close(active, i - 1)
                active = None

        if active is None:
            if pos > threshold:
                active = {
                    "direction": "Accumulation", "_start_position": pos_anchor,
                    "start": index[pos_anchor], "detected": index[i], "peak": pos,
                }
                neg = 0.0
            elif neg > threshold:
                active = {
                    "direction": "Distribution", "_start_position": neg_anchor,
                    "start": index[neg_anchor], "detected": index[i], "peak": neg,
                }
                pos = 0.0
        else:
            statistic = pos if active["direction"] == "Accumulation" else neg
            active["peak"] = max(active["peak"], statistic)

    if active is not None:
        active["ongoing"] = True
        close(active, len(x) - 1)

    for episode in episodes:
        episode.pop("_start_position", None)
        episode.setdefault("ongoing", False)
    return episodes


def detect(frame: pd.DataFrame, slack: float = DEFAULT_SLACK,
           threshold: float = DEFAULT_THRESHOLD,
           min_days: int = MIN_EPISODE_DAYS,
           winsor: float = DEFAULT_WINSOR) -> dict:
    """Accumulation episodes for an engineered whale-tracker frame.

    Expects the columns `whale.WhaleTracker._engineer_features` produces:
    `OBV_Change_Z`, `Close`, and `Volume_vs_Avg`.
    """
    if frame is None or frame.empty or "OBV_Change_Z" not in frame.columns:
        return {"episodes": [], "current": None, "config": {
            "slack": slack, "threshold": threshold, "minDays": min_days,
            "winsor": winsor}}

    raw = cusum_episodes(frame["OBV_Change_Z"], slack, threshold, min_days, winsor)

    episodes = []
    for episode in raw:
        window = frame.loc[episode["start"]:episode["end"]]
        if window.empty:
            continue
        open_price = float(window["Close"].iloc[0])
        close_price = float(window["Close"].iloc[-1])
        episodes.append({
            "direction": episode["direction"],
            "start": episode["start"].strftime("%Y-%m-%d"),
            "detected": episode["detected"].strftime("%Y-%m-%d"),
            "end": episode["end"].strftime("%Y-%m-%d"),
            "days": int(episode["days"]),
            "peakStatistic": float(episode["peak"]),
            "priceChangePct": ((close_price / open_price - 1.0) * 100.0
                               if open_price else None),
            "avgRvol": (float(window["Volume_vs_Avg"].mean())
                        if "Volume_vs_Avg" in window else None),
            "ongoing": bool(episode.get("ongoing", False)),
        })

    episodes.sort(key=lambda e: e["start"], reverse=True)
    current = next((e for e in episodes if e["ongoing"]), None)

    return {
        "episodes": episodes,
        "current": current,
        "config": {"slack": slack, "threshold": threshold, "minDays": min_days,
                   "winsor": winsor},
    }
