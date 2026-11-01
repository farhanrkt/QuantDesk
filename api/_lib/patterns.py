"""
patterns.py
===========
Multi-bar chart patterns, defined the only way they can be defined reproducibly.

WHY THIS FILE EXISTS WHEN `swing.py` DECLINES THESE BY NAME
------------------------------------------------------------
`swing.UNDETECTABLE_PATTERNS` refuses head-and-shoulders, flags, wedges, cups
and double tops, and gives three reasons. They are good reasons and this module
does not wave them away — it answers each on its own terms, and where an answer
is not available the pattern stays refused.

  1. "TWO HONEST IMPLEMENTATIONS DISAGREE." True of a fixed-threshold matcher.
     Not true of Lo, Mamaysky & Wang (2000), whose whole contribution was to
     make these shapes arithmetic: smooth the price with a kernel regression at
     a cross-validated bandwidth, take the extrema of the smoothed series, and
     define each pattern as inequalities on five consecutive extrema. Nothing in
     that is a judgement call. Two implementations of it agree, and this is one.

  2. "A FIXED-THRESHOLD MATCHER FOR 'FLAG' FIRES ON NOISE SEVERAL TIMES A
     MONTH." Also true, and it is a MEASURABLE claim rather than a reason to
     stop. `scripts/calibrate_patterns.py` counts how often each pattern fires
     across a whole market and publishes the rate. A pattern that fires on a
     third of names in a quarter is describing the market — the same argument
     `pretrade.py` makes about every flag it demotes to a base condition.

  3. "SOME INCREMENTAL DISTRIBUTIONAL INFORMATION, NOT A DEMONSTRATED NET
     EDGE." Exactly right, and it is why nothing here votes until it has been
     measured. The same script runs an event study on every detection — forward
     returns against the market and against the cross-section of the same month,
     with a Benjamini-Hochberg correction across all patterns and horizons — and
     `verdict.py` reads the result. A pattern whose forward returns do not
     survive correction contributes NOTHING to the score.

WHAT THE MEASUREMENT ACTUALLY FOUND, WHICH IS NOT WHAT THE TEXTBOOKS SAY
------------------------------------------------------------------------
Across sixty Indonesian names over five years — 1,778 detections, thirty tests,
ten surviving a false-discovery correction — the result is coherent and it is
not the one the pattern literature describes:

  * EVERY SURVIVING PATTERN IS NEGATIVE. Head-and-shoulders reads -9.4% abnormal
    over a quarter. Inverse head-and-shoulders, which is its textbook mirror and
    supposedly bullish, reads -6.4%. Double top -7.6%, double bottom -6.1%,
    broadening top and broadening bottom both around -9%.

  * THE TEXTBOOK DIRECTION CARRIES NO INFORMATION. A pattern and its mirror
    image predict the same thing, which is the cleanest possible demonstration
    that the shape's supposed meaning is not what is being measured.

  * THE EFFECT SCALES WITH HORIZON — about -1% at ten sessions, -3% at
    twenty-one, -8% at sixty-three — and the median moves with the mean, so it
    is not a few outliers dragging an average.

The mechanism is not mysterious and it is worth naming, because it decides how
this is used. A five-extremum pattern needs five turning points inside
thirty-five sessions: it can only be found in a stock that is CHOPPING rather
than trending. Choppy names underperform trending ones — that is cross-sectional
momentum, seen from behind. The formation is not a forecast, it is a marker of
going nowhere.

So this module scores the PRESENCE of a formation, using the measured effect and
its measured sign, and ignores the bias every textbook attaches to it. That bias
is still carried in the payload as `textbookBias`, labelled as what it is, so a
reader can see the claim the measurement declined to support.

The corollary is a redundancy warning rather than a boast: if this is momentum
in disguise, it overlaps the trend and price-rank components that live in the
same family. `verdict.py` files it inside price-and-volume for exactly that
reason, and the scanner reports the realised correlation.

FLAGS, PENNANTS, WEDGES AND CUPS ARE STILL REFUSED
---------------------------------------------------
LMW never defined them, and this module does not invent definitions. A flag
needs a "flagpole", which is a move sharp enough to count — and no threshold
survives contact with two stocks of different volatility. `swing.py` keeps
naming them, and `REFUSED` below repeats the list so a reader of this file does
not conclude that everything is now detectable.

THE LOOK-AHEAD PROBLEM, WHICH IS THE ONE THAT WOULD INVALIDATE EVERYTHING
--------------------------------------------------------------------------
A kernel regression is two-sided: the smoothed value at day t is a weighted
average of the days around it, INCLUDING THE DAYS AFTER IT. Smooth a whole
series at once, find a head-and-shoulders in the middle of it, and then measure
what happened next, and the "pattern" you found was partly built out of the
returns you are about to claim it predicted. The result is a beautiful, entirely
circular edge.

So detection is done in a ROLLING WINDOW, as LMW specify. At each day t the
regression is fitted on the trailing `WINDOW` bars only, extrema are taken
inside that window, and the pattern must have COMPLETED at least `CONFIRM_LAG`
bars before t — so its last extremum is one the two-sided smoother could already
see from both sides using data available at t. Nothing at day t uses a price
from day t+1.

The one thing computed on the whole series is the BANDWIDTH, which LMW also do.
It is a nuisance parameter describing how noisy this stock is, not a signal, and
recomputing it per window makes it jump around for reasons that have nothing to
do with the pattern. That is a stated compromise rather than an oversight.

References
----------
Lo, A. W., Mamaysky, H., & Wang, J. (2000). "Foundations of Technical Analysis:
    Computational Algorithms, Statistical Inference, and Empirical
    Implementation." Journal of Finance 55(4), 1705-1765. Every definition below
    is theirs; §I and Table I carry the inequalities.
Nadaraya, E. A. (1964). "On Estimating Regression." Theory of Probability and
    its Applications 9(1).
Watson, G. S. (1964). "Smooth Regression Analysis." Sankhya A 26(4).
Marshall, B., Young, M., & Rose, L. (2006). "Candlestick technical trading
    strategies: Can they create value for investors?" Journal of Banking &
    Finance 30(8). (Why `swing.py` grades its own candlesticks weak.)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# The algorithm's constants, each as LMW set it
# --------------------------------------------------------------------------- #
# The rolling window, in trading days. LMW use 35 plus a 3-day confirmation lag,
# giving 38. Long enough to hold five extrema, short enough that the pattern is
# a recent event rather than a feature of last year.
WINDOW = 35

# Bars that must pass after the pattern's last extremum before it counts as
# detected. This is what makes the last extremum visible to a two-sided smoother
# from data available at detection time — see the look-ahead note above.
CONFIRM_LAG = 3

# Bandwidth search grid, IN TRADING DAYS. The units matter and getting them
# wrong is invisible: an earlier version measured the bandwidth in positions
# scaled to [0, 1], calibrated it on 780 bars of history, then applied it to a
# 35-bar rolling window — where the same number meant a twentieth of the
# smoothing it had meant during calibration. The windows were effectively not
# smoothed at all. A bandwidth in bars means the same thing everywhere.
BANDWIDTH_GRID = np.array([4.0, 3.0, 2.5, 2.0, 1.5, 1.0])

# HOW THE BANDWIDTH IS CHOSEN, AND WHY NOT BY CROSS-VALIDATION.
#
# LMW pick it by cross-validation and then multiply by 0.3. That was tried here
# first, twice, and it does not survive contact with this data:
#
#   * Leave-one-out CV is degenerate on a price series. Prices are near a random
#     walk, so the best predictor of today excluding today is yesterday, and CV
#     drives the bandwidth to the smallest value on any grid. All six test names
#     returned the grid minimum.
#   * h-block CV, which exists precisely to fix that, did no better here: with
#     the neighbourhood excluded the objective is nearly flat across the whole
#     grid, and the minimum still landed on the floor for every name.
#
# A criterion that returns its own floor on every input is not selecting
# anything. So the bandwidth is chosen by the requirement the ALGORITHM
# actually has, which is a stated and reproducible rule rather than a fitted
# one: a five-extremum pattern cannot be found in a window holding fewer than
# five extrema, so take the LARGEST bandwidth at which the median window still
# holds enough. Maximum smoothing subject to the geometry existing.
#
# Measured across six Indonesian names, the median extrema per 35-bar window
# runs 7 at h=1.0, 5 at h=1.5, 3 at h=2.0 and 2 at h=3.0 — and detections fall
# from 7 a year to essentially none over the same range. The rule lands near
# h=1.5 for most names, which is where the method has what it needs.
MIN_EXTREMA = 5

# How close two tops (or two bottoms) must be to count as "the same level".
# LMW's own tolerances: 1.5% for head-and-shoulders shoulders and double
# tops, 0.75% for the tighter rectangle definition.
LEVEL_TOLERANCE = 0.015
RECTANGLE_TOLERANCE = 0.0075

# Minimum separation between the two peaks of a double top, in trading days.
# LMW require a month; a shorter gap is one peak with a dent in it.
DOUBLE_SEPARATION = 22

# History needed before any of this is meaningful.
MIN_BARS = WINDOW * 3

# Patterns this module still refuses, and why. Kept here as well as in
# `swing.UNDETECTABLE_PATTERNS` so that a reader who arrives at the file that
# DOES detect patterns is told which ones it does not.
REFUSED = [
    ("Flags and pennants", "needs a 'flagpole' — a move sharp enough to count — and no "
                           "threshold for that survives two stocks of different volatility. "
                           "Lo, Mamaysky and Wang never defined one either."),
    ("Wedges", "two converging trend lines fit almost any twenty bars once you are "
               "allowed to choose which highs and lows to use."),
    ("Cup and handle", "a shape defined by how it looks, with no numeric definition "
                       "different practitioners agree on."),
]

# The eight LMW patterns and what each is conventionally read as. `bias` is the
# textbook direction and is NEVER used as a score on its own — it is what the
# calibration is testing, not something the module asserts.
CATALOGUE: dict[str, dict] = {
    "headAndShoulders": {
        "label": "Head and shoulders", "bias": "down",
        "note": "Three peaks, the middle one highest, with the outer two at a similar level.",
    },
    "inverseHeadAndShoulders": {
        "label": "Inverse head and shoulders", "bias": "up",
        "note": "Three troughs, the middle one lowest, with the outer two at a similar level.",
    },
    "broadeningTop": {
        "label": "Broadening top", "bias": "down",
        "note": "Successively higher peaks and lower troughs — the range widening from a top.",
    },
    "broadeningBottom": {
        "label": "Broadening bottom", "bias": "up",
        "note": "Successively lower troughs and higher peaks — the range widening from a bottom.",
    },
    "triangleTop": {
        "label": "Triangle top", "bias": "down",
        "note": "Lower peaks against higher troughs, converging from a top.",
    },
    "triangleBottom": {
        "label": "Triangle bottom", "bias": "up",
        "note": "Higher troughs against lower peaks, converging from a bottom.",
    },
    "rectangleTop": {
        "label": "Rectangle top", "bias": "down",
        "note": "Peaks at one level and troughs at another, both held tightly — a range.",
    },
    "rectangleBottom": {
        "label": "Rectangle bottom", "bias": "up",
        "note": "The same range, entered from below.",
    },
    "doubleTop": {
        "label": "Double top", "bias": "down",
        "note": "Two peaks at a similar level at least a month apart, with a trough between.",
    },
    "doubleBottom": {
        "label": "Double bottom", "bias": "up",
        "note": "Two troughs at a similar level at least a month apart.",
    },
}

_CALIBRATION_PATH = Path(__file__).with_name("patterns_calibration.json")
_CALIBRATION_CACHE: Optional[dict] = None
_LOAD_FROM_DISK = object()


# --------------------------------------------------------------------------- #
# Kernel regression
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=64)
def _operator(n: int, bandwidth: float) -> np.ndarray:
    """The row-normalised Nadaraya-Watson smoothing matrix for `n` bars.

    CACHED, AND THAT IS WHAT MAKES A WHOLE-MARKET SWEEP AFFORDABLE. Every
    rolling window has the same length and the same evenly spaced positions, so
    the kernel matrix is identical for all of them — the only thing that changes
    is the prices it multiplies. Rebuilding it per window turned each name into
    750 matrix constructions instead of one matrix and 750 matrix-vector
    products.

    Positions are BAR INDICES and the bandwidth is in bars, so the same number
    means the same amount of smoothing on any window length.
    """
    positions = np.arange(n, dtype="float64")
    weights = np.exp(-0.5 * ((positions[:, None] - positions[None, :]) / bandwidth) ** 2)
    totals = weights.sum(axis=1, keepdims=True)
    return weights / np.where(totals > 1e-12, totals, 1.0)


def smooth(prices: np.ndarray, bandwidth: float) -> np.ndarray:
    """Nadaraya-Watson fit of `prices` against bar position."""
    return _operator(len(prices), float(bandwidth)) @ prices


def choose_bandwidth(prices: np.ndarray, window: int = WINDOW) -> float:
    """The most smoothing this name's windows will bear and still hold a pattern.

    Walks the grid from the smoothest end down and returns the first bandwidth
    whose MEDIAN window still contains `MIN_EXTREMA` turning points. See the
    comment on `MIN_EXTREMA` for why this replaced cross-validation rather than
    supplementing it.

    Falls back to the least smoothing on the grid when nothing qualifies, which
    happens on a series so quiet that even the raw closes barely turn — and the
    detections that follow will be few, which is the right outcome.
    """
    if len(prices) < window + 1:
        return float(BANDWIDTH_GRID[-1])

    starts = range(0, len(prices) - window + 1)
    for bandwidth in BANDWIDTH_GRID:
        operator = _operator(window, float(bandwidth))
        counts = [len(extrema(operator @ prices[start:start + window])[0])
                  for start in starts]
        if counts and float(np.median(counts)) >= MIN_EXTREMA:
            return float(bandwidth)
    return float(BANDWIDTH_GRID[-1])


# A turn smaller than this share of the price level is not a turn, it is
# arithmetic. THE REASON IS A REAL BUG, not defensive habit: the smoothing
# operator's rows sum to one only to within floating-point error, so smoothing a
# PERFECTLY FLAT stretch returns values that differ in their last bits — and a
# strict `>` then reports a turning point every second bar. On a synthetic flat
# series that produced enough spurious extrema for `choose_bandwidth` to believe
# the maximum smoothing on the grid still left five turns per window. Real
# instances of this are suspended listings and prices pinned at the exchange's
# tick floor, which IDX has plenty of. A part in a million is far below any real
# price move and far above the noise.
TURN_TOLERANCE = 1e-6


def extrema(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Indices and signs of the smoothed series' turning points.

    Sign is +1 for a maximum and -1 for a minimum. The turn must clear
    `TURN_TOLERANCE` on BOTH sides: a plateau is not a turning point, and
    admitting one would let a flat stretch supply several "extrema" at the same
    level — which is how a rectangle gets detected in a series that never turned
    at all.
    """
    if len(values) < 3:
        return np.array([], dtype=int), np.array([], dtype=int)
    scale = np.maximum(np.abs(values[1:-1]), 1e-12) * TURN_TOLERANCE
    left = values[1:-1] - values[:-2]
    right = values[1:-1] - values[2:]
    is_max = (left > scale) & (right > scale)
    is_min = (left < -scale) & (right < -scale)
    positions = np.nonzero(is_max | is_min)[0] + 1
    signs = np.where(is_max[positions - 1], 1, -1)
    return positions, signs


# --------------------------------------------------------------------------- #
# The pattern definitions — LMW Table I, as inequalities
# --------------------------------------------------------------------------- #
def _within(values: list[float], tolerance: float) -> bool:
    """Whether every value sits within `tolerance` of their common average."""
    average = float(np.mean(values))
    if average == 0:
        return False
    return all(abs(v - average) <= tolerance * abs(average) for v in values)


def _classify(points: list[float], signs: list[int], positions: list[int]) -> Optional[str]:
    """Which LMW pattern, if any, five consecutive extrema form.

    `signs[0] == 1` means the sequence starts on a maximum, which is what
    separates the "top" family from the "bottom" family. Everything else is the
    inequalities from their Table I, unchanged.
    """
    if len(points) != 5:
        return None
    # Extrema must alternate; anything else means the caller mis-assembled them.
    if any(signs[i] == signs[i + 1] for i in range(4)):
        return None

    e1, e2, e3, e4, e5 = points
    starts_high = signs[0] == 1

    if starts_high:
        # E1, E3, E5 are maxima; E2, E4 are minima.
        if (e3 > e1 and e3 > e5
                and _within([e1, e5], LEVEL_TOLERANCE)
                and _within([e2, e4], LEVEL_TOLERANCE)):
            return "headAndShoulders"
        if e1 < e3 < e5 and e2 > e4:
            return "broadeningTop"
        if e1 > e3 > e5 and e2 < e4:
            return "triangleTop"
        if (_within([e1, e3, e5], RECTANGLE_TOLERANCE)
                and _within([e2, e4], RECTANGLE_TOLERANCE)
                and min(e1, e3, e5) > max(e2, e4)):
            return "rectangleTop"
        # A double top is the only two-extremum pattern here, and it is checked
        # on the OUTER pair with a minimum separation — LMW require a month, so
        # that two peaks a fortnight apart are one peak with a dent in it.
        if (_within([e1, e5], LEVEL_TOLERANCE)
                and positions[4] - positions[0] >= DOUBLE_SEPARATION
                and e1 > e2 and e5 > e4
                and max(e1, e5) >= e3):
            return "doubleTop"
        return None

    # E1, E3, E5 are minima; E2, E4 are maxima.
    if (e3 < e1 and e3 < e5
            and _within([e1, e5], LEVEL_TOLERANCE)
            and _within([e2, e4], LEVEL_TOLERANCE)):
        return "inverseHeadAndShoulders"
    if e1 > e3 > e5 and e2 < e4:
        return "broadeningBottom"
    if e1 < e3 < e5 and e2 > e4:
        return "triangleBottom"
    if (_within([e1, e3, e5], RECTANGLE_TOLERANCE)
            and _within([e2, e4], RECTANGLE_TOLERANCE)
            and max(e1, e3, e5) < min(e2, e4)):
        return "rectangleBottom"
    if (_within([e1, e5], LEVEL_TOLERANCE)
            and positions[4] - positions[0] >= DOUBLE_SEPARATION
            and e1 < e2 and e5 < e4
            and min(e1, e5) <= e3):
        return "doubleBottom"
    return None


# --------------------------------------------------------------------------- #
# Rolling detection
# --------------------------------------------------------------------------- #
def detect(frame: Optional[pd.DataFrame], window: int = WINDOW,
           confirm_lag: int = CONFIRM_LAG,
           lookback: Optional[int] = None) -> dict:
    """Every pattern that completed in the trailing history, with its date.

    ONE DETECTION PER PATTERN PER COMPLETION, not one per day it stays visible.
    A head-and-shoulders sits inside the rolling window for a fortnight after it
    forms, and counting each of those days as a separate detection would inflate
    every firing rate by an order of magnitude and make the event study's
    observations overlapping copies of one event.

    `lookback` bounds how far back detections are reported. The scanner passes
    a quarter, because a pattern that completed nine months ago is history
    rather than a reason to act; the calibration script passes None to sweep
    everything.
    """
    if frame is None or len(frame) < MIN_BARS:
        have = 0 if frame is None else len(frame)
        return {"available": False,
                "reason": (f"needs {MIN_BARS} sessions for a rolling {window}-bar "
                           f"window; this has {have}")}

    close = frame["Close"].astype("float64")
    prices = close.to_numpy(dtype="float64")
    if not np.isfinite(prices).all() or len(np.unique(prices)) < 5:
        return {"available": False,
                "reason": "the close series is flat or carries gaps this cannot smooth"}

    # ONE BANDWIDTH FOR THE WHOLE NAME. It describes how noisy this stock is,
    # not what is happening this month — see the look-ahead note in the module
    # docstring for why that compromise is stated rather than hidden.
    bandwidth = choose_bandwidth(prices, window)
    operator = _operator(window, bandwidth)

    detections: list[dict] = []
    # `last_seen` holds the completion index of the most recent detection of
    # each pattern, so the same formation is not re-reported on every day it
    # remains inside the window.
    last_seen: dict[str, int] = {}

    for end in range(window, len(prices) + 1):
        segment = prices[end - window:end]
        positions, signs = extrema(operator @ segment)
        if len(positions) < 5:
            continue

        # The pattern must be COMPLETE: its final extremum at least
        # `confirm_lag` bars before the window's right edge, so that extremum
        # was resolvable from data available at `end`.
        take = slice(-5, None)
        chosen = positions[take]
        if window - 1 - chosen[-1] < confirm_lag:
            continue

        name = _classify([float(segment[p]) for p in chosen],
                         [int(s) for s in signs[take]],
                         [int(p) for p in chosen])
        if name is None:
            continue

        completed_at = end - window + int(chosen[-1])
        if last_seen.get(name) is not None and completed_at - last_seen[name] < window:
            continue
        last_seen[name] = completed_at

        detections.append({
            "pattern": name,
            "label": CATALOGUE[name]["label"],
            "bias": CATALOGUE[name]["bias"],
            "note": CATALOGUE[name]["note"],
            # The bar the shape finished on, and the bar a reader could first
            # have known about it. They are not the same day and conflating them
            # is how a backtest acquires three free days of hindsight.
            "completedAt": close.index[completed_at].strftime("%Y-%m-%d"),
            "detectedAt": close.index[end - 1].strftime("%Y-%m-%d"),
            "completedIndex": completed_at,
            "detectedIndex": end - 1,
            "priceAtDetection": float(prices[end - 1]),
        })

    if lookback is not None:
        cutoff = len(prices) - lookback
        detections = [d for d in detections if d["detectedIndex"] >= cutoff]

    return {
        "available": True,
        "bandwidth": bandwidth,
        "window": window,
        "confirmLag": confirm_lag,
        "sessions": len(prices),
        "detections": detections,
        "refused": [{"name": name, "reason": reason} for name, reason in REFUSED],
    }


# --------------------------------------------------------------------------- #
# Drawing what was detected
#
# A detection is a claim about a shape, and a shape is the one kind of claim a
# reader can check instantly and cannot check at all from a sentence. "An
# inverse head-and-shoulders completed on 14 August" is unfalsifiable prose
# until the five points are on the chart.
#
# THE HARD PART IS NOT DRAWING IT, IT IS DRAWING THE RIGHT CURVE. Smoothing the
# whole series and plotting that is one line of code and it is a lie: the
# kernel is two-sided, so a whole-series fit at the pattern's location is built
# partly from prices that came AFTER the detection — the exact look-ahead the
# module docstring says detection avoids. The drawn curve would be smoother and
# better-formed than anything the detector could have seen, and it would be
# most misleading precisely where a reader looks hardest, at the right-hand
# edge. So the curve is refitted on the same trailing window, at the same
# bandwidth, ending on the same bar.
# --------------------------------------------------------------------------- #
def geometry(prices: np.ndarray, detection: dict, bandwidth: float,
             window: int = WINDOW) -> Optional[dict]:
    """The smoothed curve at detection time, and the five points read off it.

    Returns None where the window falls outside the series — which happens when
    a caller trims the frame after detecting. That is a missing drawing, never a
    drawing of a different window.
    """
    end = int(detection.get("detectedIndex", -1)) + 1
    start = end - window
    if start < 0 or end > len(prices) or end <= 0:
        return None

    segment = np.asarray(prices[start:end], dtype="float64")
    smoothed = _operator(window, float(bandwidth)) @ segment
    positions, signs = extrema(smoothed)
    if len(positions) < 5:
        return None

    chosen, chosen_signs = positions[-5:], signs[-5:]
    return {
        "startIndex": start,
        "endIndex": end - 1,
        "path": [{"index": start + i, "price": float(value)}
                 for i, value in enumerate(smoothed)],
        # BOTH PRICES, because they are two different things and the difference
        # is the whole method. `price` is the close the inequalities in
        # `_classify` were actually evaluated on; `smoothed` is where the fitted
        # curve turned. Plotting the marker on the smoothed value would show a
        # tidier pattern than the one that was tested.
        "points": [{"index": start + int(position),
                    "price": float(segment[position]),
                    "smoothed": float(smoothed[position]),
                    "kind": "peak" if int(sign) == 1 else "trough"}
                   for position, sign in zip(chosen, chosen_signs, strict=True)],
    }


def guides(points: list[dict], pattern: Optional[str] = None) -> list[dict]:
    """The construction lines the pattern's own definition implies.

    Every line here is determined BY THE FIVE POINTS, with no free parameters —
    a neckline is the line through the two inner extrema because that is what
    the inequalities compared, not because it looked right. Nothing is
    projected forward: a "measured move" target would be a price forecast, and
    the measurement in this module's docstring found the textbook direction
    carries no information, so drawing one would put a claim on the chart that
    the data declined to support.
    """
    if len(points) != 5:
        return []

    outer = [points[0], points[2], points[4]]
    inner = [points[1], points[3]]
    tops, bottoms = ((outer, inner) if points[0]["kind"] == "peak"
                     else (inner, outer))

    def through(pair: list[dict], role: str, label: str) -> dict:
        return {"role": role, "label": label,
                "from": {"index": pair[0]["index"], "price": pair[0]["price"]},
                "to": {"index": pair[-1]["index"], "price": pair[-1]["price"]}}

    def level(group: list[dict], role: str, label: str) -> dict:
        price = float(np.mean([point["price"] for point in group]))
        return {"role": role, "label": label,
                "from": {"index": points[0]["index"], "price": price},
                "to": {"index": points[4]["index"], "price": price}}

    if pattern in ("headAndShoulders", "inverseHeadAndShoulders"):
        return [through(inner, "neckline", "Neckline — through the two inner turns")]

    if pattern in ("doubleTop", "doubleBottom"):
        # The intervening turn, which is the level a textbook would call the
        # neckline. Horizontal: the two inner extrema are not both part of the
        # two-peak definition, so a sloping line through them would draw a
        # relationship the classifier never tested.
        prices = [point["price"] for point in inner]
        price = min(prices) if pattern == "doubleTop" else max(prices)
        return [{"role": "neckline", "label": "Neckline — the turn between the two",
                 "from": {"index": points[0]["index"], "price": price},
                 "to": {"index": points[4]["index"], "price": price}}]

    if pattern in ("rectangleTop", "rectangleBottom"):
        return [level(tops, "upper", "Ceiling — the peaks' common level"),
                level(bottoms, "lower", "Floor — the troughs' common level")]

    if pattern in ("triangleTop", "triangleBottom",
                   "broadeningTop", "broadeningBottom"):
        return [through(tops, "upper", "Through the peaks"),
                through(bottoms, "lower", "Through the troughs")]

    return []


# --------------------------------------------------------------------------- #
# The calibrated reading
# --------------------------------------------------------------------------- #
def load_calibration() -> dict:
    global _CALIBRATION_CACHE
    if _CALIBRATION_CACHE is None:
        try:
            _CALIBRATION_CACHE = json.loads(_CALIBRATION_PATH.read_text())
        except (OSError, ValueError):
            _CALIBRATION_CACHE = {}
    return _CALIBRATION_CACHE


def calibration_for(market_code: Optional[str],
                    calibration=_LOAD_FROM_DISK) -> Optional[dict]:
    """One market's measured pattern statistics, or None.

    Never another market's. The firing rates and the forward returns are
    properties of the population they were measured on, and IDX and the US
    behave differently enough elsewhere in this codebase that borrowing would be
    worse than having nothing.
    """
    if calibration is _LOAD_FROM_DISK:
        calibration = load_calibration()
    markets = (calibration or {}).get("markets") or {}
    return markets.get((market_code or "").strip().upper())


def read(frame: Optional[pd.DataFrame], market_code: Optional[str] = None,
         calibration=_LOAD_FROM_DISK, lookback: int = 63) -> dict:
    """Recent patterns, each carrying what its own measurement said about it.

    THE SCORE IS ZERO UNLESS A PATTERN SURVIVED CORRECTION. `verdict.py` reads
    `score` only when `usable` is true, and `usable` is true only when at least
    one detected pattern has a measured forward return that cleared a
    Benjamini-Hochberg correction across every pattern and horizon tested. Until
    `scripts/calibrate_patterns.py` has run, or where it found nothing, this
    module renders its detections and contributes nothing.

    That is not caution for its own sake. `swing.py` declines these patterns
    partly because Lo, Mamaysky and Wang found "some incremental distributional
    information, not a demonstrated net edge", and shipping a vote on the
    strength of a shape nobody has measured would be exactly the claim
    `PRODUCT.md` constraint 2 forbids.
    """
    found = detect(frame, lookback=lookback)
    if not found["available"]:
        return found

    row = calibration_for(market_code, calibration)
    detections = found["detections"]

    measured: list[dict] = []
    for detection in detections:
        stats = ((row or {}).get("patterns") or {}).get(detection["pattern"]) or {}
        detection = {**detection,
                     "firingRate": stats.get("firingRate"),
                     "namesFired": stats.get("namesFired"),
                     "observations": stats.get("observations"),
                     "forward": stats.get("forward"),
                     "significant": bool(stats.get("significant")),
                     "verdict": stats.get("verdict")}
        measured.append(detection)

    survivors = [d for d in measured if d["significant"]]
    usable = bool(row) and bool(survivors)

    score = 50.0
    if usable:
        # ONLY SURVIVING PATTERNS MOVE ANYTHING, and each moves the score by the
        # size and SIGN of its own measured effect — never by the direction a
        # textbook attaches to the shape. Measured, a head-and-shoulders and its
        # mirror image predict the same thing, so using the textbook bias would
        # be scoring a claim the data declined to support.
        #
        # THE STRONGEST SURVIVOR DECIDES, and the rest do not add to it. Several
        # formations inside one quarter are not several independent findings:
        # they are the same choppy stretch of tape seen through different
        # five-point templates, and summing them would count one fact up to ten
        # times.
        effects = [(d.get("forward") or {}).get("meanExcess") for d in survivors]
        effects = [e for e in effects if e is not None]
        if effects:
            strongest = max(effects, key=abs)
            score += float(np.clip(strongest * 100.0 * PATTERN_POINTS_PER_PCT,
                                   -MAX_PATTERN_SWING, MAX_PATTERN_SWING))
        score = float(np.clip(score, 0.0, 100.0))

    return {
        **found,
        "detections": measured,
        "market": (market_code or "").upper() or None,
        "calibrated": bool(row),
        "measuredOn": (row or {}).get("measuredOn"),
        "usable": usable,
        "score": score if usable else None,
        "survivors": [d["pattern"] for d in survivors],
        "lookback": lookback,
        "reading": _reading(measured, survivors, row, lookback),
    }


# How many points of score one percentage point of measured abnormal return is
# worth, and the ceiling on the whole component. Both are deliberately small.
# The measured effects are around -8% over a quarter, which at 1.5 points per
# point of return reaches the 12-point cap — so a detected formation moves this
# component from 50 to 38 and no further, whatever else is found. That is a
# nudge inside one weak-graded component of eight, which is the right size for
# a result this sample cannot pin down more precisely: the p-values are
# optimistic because 63-day windows overlap, and the effect is probably momentum
# wearing a different name.
PATTERN_POINTS_PER_PCT = 1.5
MAX_PATTERN_SWING = 12.0


def _reading(detections: list[dict], survivors: list[dict],
             row: Optional[dict], lookback: int) -> str:
    if not row:
        return ("No pattern measurement exists for this market, so any shapes found are "
                "reported and score nothing. Run scripts/calibrate_patterns.py.")

    if not detections:
        return (f"No head-and-shoulders, broadening, triangle, rectangle or double "
                f"formation completed in the last {lookback} sessions. Most stocks show "
                f"none most of the time, which is what makes the ones that do worth "
                f"looking at.")

    # COUNT THE DISTINCT SHAPES, not the detections. "3 formations — Double
    # bottom, Double top" invited the reader to look for a third name that was
    # never there; the same shape appearing twice in a quarter is one kind of
    # finding reported once.
    labels = sorted({d["label"] for d in detections})
    text = f"{len(labels)} formation{'' if len(labels) == 1 else 's'} — {', '.join(labels)}. "

    if not survivors:
        rates = [d for d in detections if d.get("firingRate") is not None]
        if rates:
            worst = max(rates, key=lambda d: d["firingRate"])
            text += (f"None of them scores: on the measured population none showed a "
                     f"forward return that survives correcting for every pattern and "
                     f"horizon tested. {worst['label']} alone fires on "
                     f"{worst['firingRate'] * 100:.0f}% of names, which describes the "
                     f"market rather than this company.")
        else:
            text += ("None of them has a measured forward return, so none of them "
                     "scores.")
        return text

    parts = []
    for detection in survivors:
        forward = detection.get("forward") or {}
        excess = forward.get("meanExcess")
        if excess is None:
            continue
        parts.append(f"{detection['label']} {excess * 100:+.1f}% over "
                     f"{forward.get('horizonDays', '?')} sessions across "
                     f"{detection.get('observations', '?')} occurrences")
    text += ("Measured against other names in the same month: " + "; ".join(parts)
             + ". Those survived a correction across every pattern and horizon tested, "
               "which most did not. ")

    # THE SENTENCE THE READER MOST NEEDS, because it contradicts every chart
    # book they have ever seen and the panel must not let that pass silently.
    negative = [e for e in
                [(d.get("forward") or {}).get("meanExcess") for d in survivors]
                if e is not None and e < 0]
    if negative:
        text += ("Note the sign: on this market the formations that survived predicted "
                 "UNDERperformance whichever way the textbook reads them — a "
                 "head-and-shoulders and its bullish mirror image measured the same. "
                 "What a five-point pattern needs is five turning points in thirty-five "
                 "sessions, which only a stock going nowhere provides.")
    return text
