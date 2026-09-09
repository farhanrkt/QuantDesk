"""Chart formations, and the three refusals that make them shippable.

WHAT THESE TESTS PROTECT, IN ORDER OF HOW BADLY IT WOULD HURT TO LOSE IT

1. NO LOOK-AHEAD. A kernel regression is two-sided, so smoothing a whole series
   and finding a pattern in the middle of it builds the shape partly out of the
   returns it is about to claim to predict. Detection runs in a rolling window
   with a confirmation lag, and nothing at day t may depend on a price after
   day t. This is the one that would invalidate everything.

2. NOTHING SCORES UNTIL IT HAS BEEN MEASURED. A detected formation contributes
   zero unless its forward return survived a false-discovery correction across
   every pattern and horizon tested. `swing.py` declines these shapes partly
   because Lo, Mamaysky and Wang found no demonstrated net edge, and shipping a
   vote without measuring one would be the claim `PRODUCT.md` constraint 2
   forbids.

3. THE MEASURED SIGN WINS OVER THE TEXTBOOK ONE. On both markets measured, a
   formation and its mirror image predicted the same thing. The bias every
   chart book attaches to the shape is carried for display and never scored.

4. THE UNDEFINABLE PATTERNS STAY REFUSED. Flags, pennants, wedges and cups have
   no numeric definition two practitioners agree on. They are named in the
   output, not silently absent.

5. THE DEFINITIONS ARE REPRODUCIBLE. Every shape is inequalities on five
   consecutive extrema of a smoothed series — no thresholds anybody picked by
   eye — which is the whole answer to "two honest implementations disagree".

The wording is free to change. Those five are not.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from _lib import patterns as P


# --------------------------------------------------------------------------- #
# Planted ground truth
# --------------------------------------------------------------------------- #
def from_path(points: list[float], per_leg: int = 8, noise: float = 0.0,
              seed: int = 3) -> pd.DataFrame:
    """OHLCV bars tracing a piecewise-linear path through `points`.

    The path IS the pattern: passing a head-and-shoulders' five turning points
    produces a series whose smoothed extrema are those points, so a test can
    state the shape it expects rather than hunting for one in random data.
    """
    rng = np.random.default_rng(seed)
    closes: list[float] = []
    for start, finish in pairwise(points):
        closes.extend(np.linspace(start, finish, per_leg, endpoint=False))
    closes.append(points[-1])
    values = np.asarray(closes, dtype="float64")
    if noise:
        values = values * (1.0 + rng.normal(0.0, noise, len(values)))

    index = pd.bdate_range("2024-01-01", periods=len(values))
    span = values * 0.01
    return pd.DataFrame(
        {"Open": values, "High": values + span, "Low": values - span,
         "Close": values, "Volume": np.full(len(values), 1_000_000.0)},
        index=index)


def padded(points: list[float], per_leg: int = 8, lead: int = 90,
           tail: int = 8) -> pd.DataFrame:
    """A planted path with flat history before it and a few bars after.

    `lead` clears `MIN_BARS`; `tail` gives the confirmation lag somewhere to
    live so a completed pattern is actually detectable.
    """
    level = points[0]
    body = from_path(points, per_leg=per_leg)
    pre = pd.DataFrame(
        {"Open": level, "High": level * 1.01, "Low": level * 0.99,
         "Close": level, "Volume": 1_000_000.0},
        index=pd.bdate_range("2023-01-02", periods=lead))
    post = pd.DataFrame(
        {"Open": points[-1], "High": points[-1] * 1.01, "Low": points[-1] * 0.99,
         "Close": points[-1], "Volume": 1_000_000.0},
        index=pd.bdate_range(body.index[-1] + pd.offsets.BDay(1), periods=tail))
    joined = pd.concat([pre, body, post])
    joined.index = pd.bdate_range("2023-01-02", periods=len(joined))
    return joined


def calibration(*significant: str, market: str = "ID", effect: float = -0.032) -> dict:
    """A pattern study in which exactly the named patterns survived."""
    return {
        "measuredOn": "2026-09-09", "alpha": P.CATALOGUE and 0.10,
        "markets": {market: {
            "names": 249, "population": "the Indonesian listed market",
            "measuredOn": "2026-09-09", "years": 6, "detections": 8929,
            "tests": 30, "survived": len(significant),
            "patterns": {
                name: {
                    "label": spec["label"], "textbookBias": spec["bias"],
                    "firingRate": 0.2, "namesFired": 50, "observations": 1475,
                    "significant": name in significant,
                    "forward": ({"horizonDays": 63, "meanExcess": effect,
                                 "qValue": 0.048, "months": 69}
                                if name in significant else None),
                    "verdict": "measured",
                }
                for name, spec in P.CATALOGUE.items()
            },
        }},
    }


# ============================================================================ #
# 1. No look-ahead
# ============================================================================ #
def test_a_detection_never_depends_on_a_price_after_it():
    """THE TEST THAT MATTERS MOST. Truncating the series immediately after a
    detection must not change that detection — if it does, the pattern was built
    out of prices that had not happened yet, and every forward return measured
    on it is circular."""
    frame = padded([100, 118, 104, 133, 103, 119, 100], per_leg=5, tail=14)
    full = P.detect(frame)
    assert full["available"] and full["detections"], "the fixture must detect something"

    for detection in full["detections"]:
        cut = frame.iloc[:detection["detectedIndex"] + 1]
        if len(cut) < P.MIN_BARS:
            continue
        again = P.detect(cut)
        assert again["available"]
        assert any(d["pattern"] == detection["pattern"]
                   and d["completedAt"] == detection["completedAt"]
                   for d in again["detections"]), (
            f"{detection['pattern']} completed {detection['completedAt']} vanished when "
            f"the series was cut at its own detection date — it was using later prices")


def test_the_confirmation_lag_separates_completion_from_detection():
    frame = padded([100, 118, 104, 133, 103, 119, 100], per_leg=5, tail=14)
    found = P.detect(frame)
    for detection in found["detections"]:
        gap = detection["detectedIndex"] - detection["completedIndex"]
        assert gap >= P.CONFIRM_LAG, (
            "a pattern was reported before its last extremum could be resolved "
            "from both sides")


def test_one_formation_is_reported_once_not_once_per_day_it_stays_visible():
    """A shape sits inside the rolling window for weeks after it forms. Counting
    each of those days would inflate every firing rate by an order of magnitude
    and make an event study's observations overlapping copies of one event."""
    frame = padded([100, 118, 104, 133, 103, 119, 100], per_leg=5, tail=30)
    found = P.detect(frame)
    completions = [(d["pattern"], d["completedIndex"]) for d in found["detections"]]
    assert len(completions) == len(set(completions))
    for name in {p for p, _ in completions}:
        indices = sorted(i for p, i in completions if p == name)
        for earlier, later in pairwise(indices):
            assert later - earlier >= P.WINDOW


# ============================================================================ #
# 2. Nothing scores until it has been measured
# ============================================================================ #
def test_without_a_calibration_nothing_scores():
    frame = padded([100, 118, 104, 133, 103, 119, 100], per_leg=5, tail=14)
    result = P.read(frame, market_code="ID", calibration={})
    assert result["available"] is True
    assert result["calibrated"] is False
    assert result["usable"] is False
    assert result["score"] is None
    assert "calibrate_patterns" in result["reading"]


def test_a_measured_null_scores_nothing_and_says_which_pattern_it_was():
    frame = padded([100, 118, 104, 133, 103, 119, 100], per_leg=5, tail=14)
    result = P.read(frame, market_code="ID", calibration=calibration())
    assert result["calibrated"] is True
    assert result["usable"] is False
    assert result["score"] is None
    assert result["survivors"] == []
    assert "survives correcting" in result["reading"]


def test_only_a_surviving_pattern_moves_the_score():
    frame = padded([100, 118, 104, 133, 103, 119, 100], per_leg=5, tail=14)
    found = {d["pattern"] for d in P.detect(frame)["detections"]}
    assert found, "the fixture must detect something"
    chosen = sorted(found)[0]

    scored = P.read(frame, market_code="ID", calibration=calibration(chosen))
    assert scored["usable"] is True
    assert scored["score"] is not None and scored["score"] < 50.0


def test_one_market_never_borrows_another_markets_study():
    assert P.calibration_for("US", calibration("doubleTop", market="ID")) is None
    assert P.calibration_for("ID", calibration("doubleTop", market="ID")) is not None


# ============================================================================ #
# 3. The measured sign wins over the textbook one
# ============================================================================ #
def test_a_bullish_shape_with_a_negative_measurement_lowers_the_score():
    """`inverseHeadAndShoulders` is textbook-bullish. Measured, it predicted
    underperformance. Scoring the textbook direction would be scoring a claim
    the data declined to support."""
    frame = padded([100, 82, 96, 67, 97, 81, 100], per_leg=5, tail=14)
    found = {d["pattern"] for d in P.detect(frame)["detections"]}
    if "inverseHeadAndShoulders" not in found:
        pytest.skip("fixture did not produce an inverse head and shoulders")

    assert P.CATALOGUE["inverseHeadAndShoulders"]["bias"] == "up"
    result = P.read(frame, market_code="ID",
                    calibration=calibration("inverseHeadAndShoulders", effect=-0.03))
    assert result["score"] < 50.0, "a bullish shape scored up despite a negative measurement"


def test_several_formations_do_not_add_up():
    """They are the same choppy stretch of tape seen through different
    five-point templates. Summing them would count one fact up to ten times."""
    frame = padded([100, 118, 104, 133, 103, 119, 100], per_leg=5, tail=14)
    every = tuple(P.CATALOGUE)
    result = P.read(frame, market_code="ID", calibration=calibration(*every))
    assert result["usable"] is True
    assert result["score"] >= 50.0 - P.MAX_PATTERN_SWING


def test_the_component_cannot_swing_the_score_further_than_its_cap():
    frame = padded([100, 118, 104, 133, 103, 119, 100], per_leg=5, tail=14)
    huge = P.read(frame, market_code="ID",
                  calibration=calibration(*tuple(P.CATALOGUE), effect=-0.90))
    assert huge["score"] == pytest.approx(50.0 - P.MAX_PATTERN_SWING, abs=0.01)


# ============================================================================ #
# 4. The undefinable patterns stay refused
# ============================================================================ #
def test_flags_wedges_and_cups_are_named_and_declined():
    frame = padded([100, 118, 104, 133, 103, 119, 100], per_leg=5)
    refused = {entry["name"] for entry in P.detect(frame)["refused"]}
    assert any("Flag" in name for name in refused)
    assert any("Wedge" in name for name in refused)
    assert any("Cup" in name for name in refused)
    for entry in P.detect(frame)["refused"]:
        assert entry["reason"], "a refusal without a reason is just an omission"


def test_no_refused_pattern_is_secretly_in_the_catalogue():
    labels = {spec["label"].lower() for spec in P.CATALOGUE.values()}
    for name, _ in P.REFUSED:
        assert name.lower() not in labels


# ============================================================================ #
# 5. Reproducible definitions
# ============================================================================ #
def test_detection_is_deterministic():
    frame = padded([100, 118, 104, 133, 103, 119, 100], per_leg=5, tail=14)
    first = P.detect(frame)["detections"]
    second = P.detect(frame)["detections"]
    assert [(d["pattern"], d["completedAt"]) for d in first] == \
           [(d["pattern"], d["completedAt"]) for d in second]


def test_a_head_and_shoulders_needs_its_shoulders_level():
    """The 1.5% tolerance is LMW's and it is what stops any three peaks from
    qualifying. A middle peak flanked by wildly different shoulders is not one."""
    assert P._classify([100.0, 90.0, 130.0, 91.0, 100.4], [1, -1, 1, -1, 1],
                       [0, 5, 10, 15, 20]) == "headAndShoulders"
    assert P._classify([100.0, 90.0, 130.0, 91.0, 60.0], [1, -1, 1, -1, 1],
                       [0, 5, 10, 15, 20]) != "headAndShoulders"


def test_a_double_top_needs_its_month_of_separation():
    """Two peaks a fortnight apart are one peak with a dent in it."""
    far = P._classify([100.0, 80.0, 90.0, 82.0, 100.5], [1, -1, 1, -1, 1],
                      [0, 8, 16, 24, 40])
    near = P._classify([100.0, 80.0, 90.0, 82.0, 100.5], [1, -1, 1, -1, 1],
                       [0, 3, 6, 9, 12])
    assert far == "doubleTop"
    assert near != "doubleTop"


def test_extrema_ignore_plateaus():
    """A flat stretch admitted as turning points would supply several 'extrema'
    at one level, which is how a rectangle gets found in a series that never
    turned."""
    positions, _ = P.extrema(np.array([1.0, 2.0, 2.0, 2.0, 1.0]))
    assert len(positions) == 0


def test_alternating_extrema_are_required():
    assert P._classify([100.0, 110.0, 120.0, 130.0, 140.0], [1, 1, 1, 1, 1],
                       [0, 5, 10, 15, 20]) is None


# ============================================================================ #
# Degradation
# ============================================================================ #
def test_too_little_history_declines_rather_than_returning_nothing_found():
    result = P.detect(from_path([100, 110, 100], per_leg=5))
    assert result["available"] is False
    assert str(P.MIN_BARS) in result["reason"]


def test_a_flat_series_declines():
    flat = padded([100, 100, 100, 100, 100], per_leg=10)
    result = P.detect(flat)
    assert result["available"] is False or result["detections"] == []


def test_the_bandwidth_adapts_and_stays_on_the_grid():
    frame = padded([100, 118, 104, 133, 103, 119, 100], per_leg=5)
    chosen = P.choose_bandwidth(frame["Close"].to_numpy(dtype="float64"))
    assert chosen in set(float(v) for v in P.BANDWIDTH_GRID)
