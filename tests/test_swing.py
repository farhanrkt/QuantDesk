"""Short- and mid-horizon structure, against planted ground truth.

Every number here is either hand-computed from the textbook formula (pivots,
VWAP, risk/reward) or planted into a synthetic price path whose answer is known
by construction (a peak at bar 20, a 40% gap that never fills, a divergence
between two specific swing highs). Nothing is checked against a second copy of
the implementation.

The behavioural tests matter as much as the arithmetic ones. `detect_setup`
returning None on a random walk is a REQUIREMENT, not an accident: a screen
that always finds something is a horoscope, and the test that would catch that
regression is `test_a_random_walk_usually_has_no_setup`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import swing as S


def bars(rows, start="2024-01-02"):
    """Build an OHLCV frame from (open, high, low, close, volume) tuples."""
    index = pd.bdate_range(start, periods=len(rows))
    return pd.DataFrame(rows, index=index,
                        columns=["Open", "High", "Low", "Close", "Volume"]).astype("float64")


def flat_walk(n=300, seed=11, drift=0.0, sigma=0.012, start_price=100.0):
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, sigma, n)
    close = start_price * np.exp(np.cumsum(returns))
    index = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame({
        "Open": close * (1 + rng.normal(0, 0.002, n)),
        "High": close * (1 + np.abs(rng.normal(0, 0.008, n))),
        "Low": close * (1 - np.abs(rng.normal(0, 0.008, n))),
        "Close": close,
        "Volume": rng.lognormal(15.0, 0.25, n),
    }, index=index)


# ============================================================================ #
# Swing points and levels
# ============================================================================ #
def test_swing_points_find_a_planted_peak_and_trough():
    # A flat series with one spike up at bar 20 and one spike down at bar 40.
    n = 60
    high = np.full(n, 100.0)
    low = np.full(n, 99.0)
    high[20] = 120.0
    low[40] = 80.0
    frame = bars(list(zip(np.full(n, 99.5), high, low, np.full(n, 99.5), np.full(n, 1e6), strict=True)))

    peaks, troughs = S.swing_points(frame["High"], frame["Low"], order=3)
    assert bool(peaks.iloc[20]) is True
    assert bool(troughs.iloc[40]) is True


def test_the_last_bars_can_never_be_a_confirmed_swing():
    """A turning point needs bars on BOTH sides. Today's high never qualifies."""
    frame = flat_walk(80)
    peaks, troughs = S.swing_points(frame["High"], frame["Low"], order=5)
    assert not peaks.iloc[-5:].any()
    assert not troughs.iloc[-5:].any()


def test_level_clusters_merge_within_tolerance_and_count_touches():
    prices = pd.Series([100.0, 100.4, 100.8, 130.0, 130.2])
    clusters = S.level_clusters(prices, tolerance=1.0)
    assert len(clusters) == 2
    assert clusters[0]["touches"] == 3
    assert clusters[0]["price"] == pytest.approx((100.0 + 100.4 + 100.8) / 3)
    assert clusters[1]["touches"] == 2


def test_level_clusters_split_when_the_gap_exceeds_tolerance():
    prices = pd.Series([100.0, 102.0])
    assert len(S.level_clusters(prices, tolerance=1.0)) == 2
    assert len(S.level_clusters(prices, tolerance=3.0)) == 1


def test_support_and_resistance_land_on_the_correct_side_of_price():
    frame = flat_walk(200, seed=5)
    result = S.support_resistance(frame, order=5)
    assert result["usable"]
    price = result["price"]
    assert all(level["price"] > price for level in result["resistances"])
    assert all(level["price"] < price for level in result["supports"])
    # Nearest first, so the reader sees the level the price reaches next.
    resistances = [level["price"] for level in result["resistances"]]
    supports = [level["price"] for level in result["supports"]]
    assert resistances == sorted(resistances)
    assert supports == sorted(supports, reverse=True)


def test_level_distances_agree_with_the_prices_they_describe():
    frame = flat_walk(200, seed=9)
    result = S.support_resistance(frame, order=5)
    price = result["price"]
    for level in result["resistances"] + result["supports"]:
        assert level["distancePct"] == pytest.approx(level["price"] / price - 1.0)


# ============================================================================ #
# Pivot points — hand-computed from the published formulas
# ============================================================================ #
def test_classic_pivots_match_the_textbook_arithmetic():
    # H=110, L=90, C=105  ->  P = 305/3 = 101.666...
    result = S.pivot_points(110.0, 90.0, 105.0, "classic")
    pivot = 305.0 / 3.0
    assert result["pivot"] == pytest.approx(pivot)
    assert result["r1"] == pytest.approx(2 * pivot - 90.0)       # 113.333
    assert result["s1"] == pytest.approx(2 * pivot - 110.0)      # 93.333
    assert result["r2"] == pytest.approx(pivot + 20.0)           # 121.667
    assert result["s2"] == pytest.approx(pivot - 20.0)           # 81.667
    assert result["r3"] == pytest.approx(110.0 + 2 * (pivot - 90.0))
    assert result["s3"] == pytest.approx(90.0 - 2 * (110.0 - pivot))


def test_fibonacci_pivots_use_the_retracement_fractions():
    result = S.pivot_points(110.0, 90.0, 105.0, "fibonacci")
    pivot = 305.0 / 3.0
    assert result["r1"] == pytest.approx(pivot + 0.382 * 20.0)
    assert result["r2"] == pytest.approx(pivot + 0.618 * 20.0)
    assert result["r3"] == pytest.approx(pivot + 20.0)
    assert result["s1"] == pytest.approx(pivot - 0.382 * 20.0)


def test_pivots_are_ordered_and_straddle_the_pivot():
    result = S.pivot_points(110.0, 90.0, 105.0, "classic")
    assert result["s3"] < result["s2"] < result["s1"] < result["pivot"]
    assert result["pivot"] < result["r1"] < result["r2"] < result["r3"]


def test_pivots_decline_on_impossible_input():
    assert S.pivot_points(90.0, 110.0, 100.0)["usable"] is False
    assert S.pivot_points(np.nan, 90.0, 100.0)["usable"] is False


def test_period_pivots_use_the_last_COMPLETE_period():
    """The current week is still being written; pivots from it move every day.

    Two full weeks with deliberately different ranges, then a partial third.
    The result must describe week two, not week three.
    """
    rows = []
    # Week 1 (Mon 1 Jan 2024 - Fri 5 Jan): high 105, low 95, close 100
    for high, low, close in [(105, 95, 100)] * 5:
        rows.append((close, high, low, close, 1e6))
    # Week 2 (8-12 Jan): high 210, low 190, close 200
    for high, low, close in [(210, 190, 200)] * 5:
        rows.append((close, high, low, close, 1e6))
    # Week 3, partial (15-16 Jan): wild range that must NOT be used
    rows.append((300, 500, 250, 300, 1e6))
    rows.append((300, 500, 250, 300, 1e6))
    frame = bars(rows, start="2024-01-01")

    result = S.period_pivots(frame, "W", "classic")
    assert result["usable"]
    assert result["periodHigh"] == pytest.approx(210.0)
    assert result["periodLow"] == pytest.approx(190.0)
    assert result["pivot"] == pytest.approx((210 + 190 + 200) / 3)
    assert result["period"] == "week"


# ============================================================================ #
# VWAP
# ============================================================================ #
def test_anchored_vwap_is_the_volume_weighted_mean_of_typical_prices():
    rows = [
        (10, 12, 8, 10, 100.0),      # typical (12+8+10)/3 = 10
        (20, 24, 16, 20, 300.0),     # typical (24+16+20)/3 = 20
    ]
    frame = bars(rows)
    expected = (10 * 100 + 20 * 300) / 400.0        # = 17.5
    assert S.anchored_vwap(frame, frame.index[0]) == pytest.approx(expected)


def test_anchored_vwap_respects_its_anchor():
    rows = [(10, 12, 8, 10, 100.0), (20, 24, 16, 20, 300.0)]
    frame = bars(rows)
    # Anchored at the second bar, only that bar counts.
    assert S.anchored_vwap(frame, frame.index[1]) == pytest.approx(20.0)


def test_vwap_profile_anchors_at_the_yearly_extremes():
    frame = flat_walk(300, seed=3)
    profile = S.vwap_profile(frame)
    assert profile["usable"]
    labels = {a["label"] for a in profile["anchors"]}
    assert {"52-week low", "52-week high"} <= labels
    for anchor in profile["anchors"]:
        assert anchor["above"] == (profile["price"] > anchor["vwap"])


# ============================================================================ #
# Candlestick patterns
# ============================================================================ #
def test_bullish_engulfing_is_recognised_when_planted():
    rows = [(100, 101, 99, 100, 1e6)] * 20
    rows.append((100, 100.5, 96, 96.5, 1e6))         # down bar
    rows.append((96, 101.5, 95.5, 101.0, 1e6))       # up bar covering it
    frame = bars(rows)
    names = [p["name"] for p in S.candlestick_patterns(frame, atr_value=2.0)]
    assert "Bullish engulfing" in names


def test_inside_bar_is_recognised_and_carries_no_direction():
    rows = [(100, 101, 99, 100, 1e6)] * 20
    rows.append((100, 110, 90, 100, 1e6))            # wide bar
    rows.append((100, 105, 95, 100, 1e6))            # entirely inside it
    frame = bars(rows)
    found = {p["name"]: p for p in S.candlestick_patterns(frame, atr_value=5.0)}
    assert "Inside bar" in found
    assert found["Inside bar"]["direction"] == "none"


def test_hammer_needs_a_long_lower_shadow_and_a_small_body():
    rows = [(100, 101, 99, 100, 1e6)] * 20
    rows.append((100, 100.4, 94.0, 100.2, 1e6))      # long lower wick, tiny body
    frame = bars(rows)
    names = [p["name"] for p in S.candlestick_patterns(frame, atr_value=2.0)]
    assert "Hammer" in names


def test_doji_is_recognised_and_a_normal_bar_is_not():
    doji = bars([(100, 101, 99, 100, 1e6)] * 20 + [(100, 105, 95, 100.05, 1e6)])
    trend = bars([(100, 101, 99, 100, 1e6)] * 20 + [(100, 106, 99.5, 105.5, 1e6)])
    assert "Doji" in [p["name"] for p in S.candlestick_patterns(doji, 3.0)]
    assert "Doji" not in [p["name"] for p in S.candlestick_patterns(trend, 3.0)]


def test_every_candlestick_pattern_is_labelled_weak_evidence():
    """Non-negotiable: these were shown to have no value on DJIA components."""
    frame = bars([(100, 101, 99, 100, 1e6)] * 20 + [(100, 100.4, 94.0, 100.2, 1e6)])
    found = S.candlestick_patterns(frame, 2.0)
    assert found
    assert all(pattern["evidence"] == "weak" for pattern in found)


def test_the_undetectable_patterns_are_named_rather_than_faked():
    names = {name for name, _why in S.UNDETECTABLE_PATTERNS}
    assert "Head and shoulders" in names
    assert "Flags and pennants" in names
    for _name, why in S.UNDETECTABLE_PATTERNS:
        assert len(why) > 30       # an actual reason, not a shrug


# ============================================================================ #
# Gaps, squeeze, volume, divergence
# ============================================================================ #
def test_an_unfilled_gap_is_reported_as_unfilled():
    # Flat at 100, then jumps to 120 and never trades back down to 100.
    rows = [(100, 100.5, 99.5, 100, 1e6)] * 20
    rows += [(120, 121, 119, 120, 1e6)] * 20
    frame = bars(rows)
    result = S.gap_analysis(frame, atr_value=1.0)
    assert result["unfilledCount"] == 1
    gap = result["unfilled"][0]
    assert gap["direction"] == "up"
    assert gap["filled"] is False
    assert gap["from"] == pytest.approx(100.0)


def test_a_gap_that_is_traded_back_through_counts_as_filled():
    rows = [(100, 100.5, 99.5, 100, 1e6)] * 20
    rows += [(120, 121, 119, 120, 1e6)] * 3
    rows += [(98, 101, 95, 98, 1e6)] * 10         # comes all the way back
    frame = bars(rows)
    result = S.gap_analysis(frame, atr_value=1.0)
    assert all(gap["filled"] for gap in result["gaps"] if gap["direction"] == "up")


def test_small_gaps_are_ignored():
    """Below half an average range, a gap is just where the open happened to be."""
    rows = [(100, 101, 99, 100, 1e6), (100.2, 101, 99, 100, 1e6)] * 15
    frame = bars(rows)
    assert S.gap_analysis(frame, atr_value=4.0)["count"] == 0


def test_a_quiet_stretch_scores_as_a_squeeze_and_a_wild_one_does_not():
    calm = flat_walk(300, seed=2, sigma=0.02)
    # Replace the last 60 bars with a near-flat stretch.
    quiet = calm.copy()
    level = float(quiet["Close"].iloc[-61])
    for column, value in (("Open", level), ("High", level * 1.001),
                          ("Low", level * 0.999), ("Close", level)):
        quiet.iloc[-60:, quiet.columns.get_loc(column)] = value

    squeezed = S.squeeze_state(quiet)
    ordinary = S.squeeze_state(calm)
    assert squeezed["inSqueeze"] is True
    assert squeezed["percentile"] < ordinary["percentile"]


def test_volume_confirmation_compares_against_the_trailing_month():
    rows = [(100, 101, 99, 100, 1_000_000.0)] * 30
    rows.append((100, 101, 99, 100, 3_000_000.0))
    result = S.volume_confirmation(bars(rows))
    assert result["ratio"] == pytest.approx(3.0)
    assert result["confirms"] is True
    assert result["anaemic"] is False


def test_thin_volume_is_flagged_as_anaemic():
    rows = [(100, 101, 99, 100, 1_000_000.0)] * 30
    rows.append((100, 101, 99, 100, 300_000.0))
    assert S.volume_confirmation(bars(rows))["anaemic"] is True


def test_bearish_divergence_is_found_when_planted():
    """Price makes a higher high; RSI does not.

    Built by making the first rally steep (high RSI) and the second one a slow
    grind to a slightly higher price (lower RSI at the peak).
    """
    closes = (
        [100.0] * 12
        + list(np.linspace(100, 140, 10))       # sharp rally -> high RSI peak
        + list(np.linspace(140, 110, 12))       # pull back
        + list(np.linspace(110, 145, 45))       # slow grind to a HIGHER high
        + list(np.linspace(145, 132, 12))       # pull back again, still declining
    )
    rows = [(c, c * 1.004, c * 0.996, c, 1e6) for c in closes]
    result = S.momentum_divergence(bars(rows), order=5)
    assert result["usable"]
    assert result["bearish"] is not None
    assert result["bearish"]["priceTo"] > result["bearish"]["priceFrom"]
    assert result["bearish"]["rsiTo"] < result["bearish"]["rsiFrom"]


def test_divergence_reports_its_own_fragility():
    result = S.momentum_divergence(flat_walk(200), order=5)
    assert "definition" in result["caveat"] or "defined" in result["caveat"]


# ============================================================================ #
# Setups — including the requirement to find nothing
# ============================================================================ #
def test_a_clean_breakout_is_detected():
    # 120 flat bars at 100, then a decisive close above the whole range.
    rows = [(100, 101, 99, 100, 1_000_000.0)] * 120
    rows.append((101, 108, 100.5, 107, 3_000_000.0))
    frame = bars(rows)
    config = S.HORIZONS["short"]
    levels = S.support_resistance(frame, order=config["swing_order"])
    setup = S.detect_setup(frame, config, levels,
                           S.squeeze_state(frame), S.volume_confirmation(frame))
    assert setup["name"] == "20-day breakout"
    assert setup["direction"] == "long"
    assert setup["evidence"] == "moderate"
    assert "Volume on the day was heavier" in setup["reason"]


def test_a_breakout_on_thin_volume_says_so():
    rows = [(100, 101, 99, 100, 1_000_000.0)] * 120
    rows.append((101, 108, 100.5, 107, 200_000.0))
    frame = bars(rows)
    config = S.HORIZONS["short"]
    setup = S.detect_setup(frame, config,
                           S.support_resistance(frame, order=config["swing_order"]),
                           S.squeeze_state(frame), S.volume_confirmation(frame))
    assert "not unusually heavy" in setup["reason"]


def test_a_breakdown_is_described_but_not_planned():
    rows = [(100, 101, 99, 100, 1_000_000.0)] * 120
    rows.append((99, 99.5, 92, 93, 2_000_000.0))
    frame = bars(rows)
    config = S.HORIZONS["short"]
    levels = S.support_resistance(frame, order=config["swing_order"])
    setup = S.detect_setup(frame, config, levels,
                           S.squeeze_state(frame), S.volume_confirmation(frame))
    assert setup["direction"] == "short"
    assert S.build_plan(setup, levels, config)["usable"] is False


def test_a_random_walk_usually_has_no_setup():
    """The requirement that keeps this from being a horoscope.

    Across twenty independent random walks, the pre-registered setups should
    fire on a minority. A build where every seed produces a trade has stopped
    detecting configurations and started describing noise.
    """
    found = 0
    for seed in range(20):
        frame = flat_walk(250, seed=seed)
        config = S.HORIZONS["short"]
        levels = S.support_resistance(frame, order=config["swing_order"])
        setup = S.detect_setup(frame, config, levels,
                               S.squeeze_state(frame), S.volume_confirmation(frame))
        if setup["name"] is not None:
            found += 1
    assert found < 15, f"{found}/20 random walks produced a setup — too eager"


def test_no_setup_explains_itself_rather_than_going_silent():
    frame = flat_walk(250, seed=4)
    config = S.HORIZONS["short"]
    setup = S.detect_setup(frame, config,
                           S.support_resistance(frame, order=config["swing_order"]),
                           {"usable": False}, S.volume_confirmation(frame))
    if setup["name"] is None:
        assert "ordinary state of most stocks" in setup["reason"]


# ============================================================================ #
# The risk plan
# ============================================================================ #
def _plan_fixture(stop_level=94.0, price=100.0, atr=2.0):
    """A plan built from levels chosen so the arithmetic is checkable by hand."""
    setup = {"direction": "long", "invalidation": stop_level,
             "anchor": price, "consolidation": {"usable": True, "height": 10.0}}
    levels = {
        "price": price, "atr": atr,
        "supports": [{"price": stop_level, "touches": 3, "distancePct": -0.06}],
        "resistances": [{"price": 112.0, "touches": 2, "distancePct": 0.12}],
    }
    return S.build_plan(setup, levels, S.HORIZONS["short"])


def test_the_stop_sits_below_structure_by_a_quarter_of_a_range():
    plan = _plan_fixture()
    assert plan["usable"]
    assert plan["stopBasis"] == "structure"
    assert plan["stop"] == pytest.approx(94.0 - 0.25 * 2.0)      # 93.5


def test_risk_reward_is_the_ratio_of_the_two_distances():
    plan = _plan_fixture()
    risk = 100.0 - 93.5          # 6.5
    reward = 112.0 - 100.0       # 12.0
    assert plan["riskReward"] == pytest.approx(reward / risk)
    assert plan["targets"][0]["rMultiple"] == pytest.approx(reward / risk)


def test_a_stop_tighter_than_one_average_range_is_widened_and_flagged():
    """A stop inside daily noise is not a risk control, and the plan says so."""
    plan = _plan_fixture(stop_level=99.5, atr=2.0)
    assert plan["stopWidened"] is True
    assert plan["stopDistanceAtr"] >= S.MIN_STOP_ATR
    assert plan["stop"] == pytest.approx(100.0 - S.MIN_STOP_ATR * 2.0)


def test_position_size_risks_exactly_the_budget():
    """The arithmetic people most often get wrong in the direction that hurts."""
    plan = _plan_fixture()
    stop_distance = plan["stopDistancePct"]              # 6.5%
    share = plan["positionShare"]
    # Losing `stop_distance` of a position worth `share` of the account costs
    # exactly the risk budget.
    assert share * stop_distance == pytest.approx(plan["riskBudget"], rel=1e-9)


def test_position_size_is_capped_at_the_whole_account():
    plan = _plan_fixture(stop_level=99.9, atr=0.2)       # a very tight stop
    assert plan["positionShare"] <= 1.0
    assert plan["positionUncapped"] >= plan["positionShare"]


def test_the_target_prefers_a_real_level_to_a_projection():
    plan = _plan_fixture()
    assert plan["targets"][0]["basis"] == "structure"
    assert plan["targets"][0]["price"] == pytest.approx(112.0)


def test_with_no_resistance_overhead_the_target_falls_back_and_says_so():
    setup = {"direction": "long", "invalidation": 94.0, "anchor": 100.0,
             "consolidation": {"usable": True, "height": 10.0}}
    levels = {"price": 100.0, "atr": 2.0,
              "supports": [{"price": 94.0, "touches": 2, "distancePct": -0.06}],
              "resistances": []}
    plan = S.build_plan(setup, levels, S.HORIZONS["short"])
    assert plan["targets"][0]["basis"] == "measured move"
    assert plan["targets"][0]["price"] == pytest.approx(110.0)


def test_the_mid_horizon_places_a_wider_stop_than_the_short_one():
    """The two horizons must actually differ, not share one parameter set."""
    setup = {"direction": "long", "invalidation": None, "anchor": 100.0,
             "consolidation": {"usable": False}}
    levels = {"price": 100.0, "atr": 2.0, "supports": [], "resistances": []}
    short = S.build_plan(setup, levels, S.HORIZONS["short"])
    mid = S.build_plan(setup, levels, S.HORIZONS["mid"])
    assert mid["stop"] < short["stop"]
    assert short["stopBasis"] == mid["stopBasis"] == "volatility"


# ============================================================================ #
# Assembly
# ============================================================================ #
def test_a_horizon_is_withheld_rather_than_computed_from_too_little_data():
    frame = flat_walk(40)
    result = S.analyse_horizon(frame, "mid")
    assert result["usable"] is False
    assert "at least 160" in result["reason"]


def test_both_horizons_come_back_from_one_frame():
    frame = flat_walk(300, seed=6)
    result = S.analyse(frame)
    assert set(result) == {"short", "mid"}
    assert result["short"]["usable"] and result["mid"]["usable"]
    assert result["short"]["label"] == "Short term"
    assert result["mid"]["window"] == "weeks to months"


def test_the_horizons_use_different_breakout_windows():
    frame = flat_walk(300, seed=8)
    result = S.analyse(frame)
    # Whatever setup fires, the two must be reading different lookbacks.
    assert S.HORIZONS["short"]["breakout_window"] != S.HORIZONS["mid"]["breakout_window"]
    assert result["short"]["levels"]["confirmationLag"] < result["mid"]["levels"]["confirmationLag"]
