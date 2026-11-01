"""How many bets a buy list actually is.

WHAT THESE TESTS PROTECT, IN ORDER OF HOW BADLY IT WOULD HURT TO LOSE IT

1. THE HEADLINE IS WEEKLY. Non-synchronous trading attenuates daily
   correlations between thin names, so a daily figure flatters exactly the
   concentration this module exists to find. The daily number is reported
   beside it so the size of the attenuation stays visible.

2. IT RECOVERS PLANTED STRUCTURE. Names built from a shared factor must read as
   fewer bets than independent ones. If that fails, nothing else here matters.

3. IT SCORES NOTHING. Concentration is a property of a list, not of a company.
   A `score` key would be the first step to a portfolio property leaking into a
   per-name number where no reader could find it.

4. A THRESHOLD THAT NEVER BINDS IS BROKEN. The cluster link was first set above
   the entire observed correlation distribution, so every name formed its own
   group and the output said nothing. The sensitivity report is what makes that
   visible rather than reassuring.

5. TOO LITTLE DATA DECLINES. A correlation matrix from thirty weeks describes
   the thirty weeks.

The wording is free to change. Those five are not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import basket as B


def frame_from(returns: np.ndarray, start: str = "2023-01-02") -> pd.DataFrame:
    close = 100.0 * np.exp(np.cumsum(returns))
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99,
         "Close": close, "Volume": np.full(len(close), 1e6)},
        index=pd.bdate_range(start, periods=len(close)))


def planted(names: int = 8, n: int = 400, loading: float = 0.0,
            seed: int = 11) -> dict:
    """`names` series sharing a common factor at strength `loading`.

    At 0 they are independent; at 1 they are the same series. The bet count must
    fall as the loading rises, and that is the property worth testing — not any
    particular number, which depends on the sample.
    """
    rng = np.random.default_rng(seed)
    factor = rng.normal(0.0, 0.012, n)
    frames = {}
    for i in range(names):
        own = rng.normal(0.0, 0.012, n)
        series = loading * factor + np.sqrt(max(0.0, 1.0 - loading ** 2)) * own
        frames[f"N{i}.JK"] = frame_from(series)
    return frames


# ============================================================================ #
# 1. The headline is weekly
# ============================================================================ #
def test_the_headline_frequency_is_weekly_and_daily_rides_beside_it():
    frames = planted(loading=0.5)
    result = B.analyse(frames, list(frames))
    assert result["available"] is True
    assert result["frequency"] == "weekly"
    assert result["effectiveBetsDaily"] is not None
    assert result["observations"] < result["dailyObservations"], (
        "weekly observations should be far fewer than daily ones")


def test_weekly_returns_are_the_sum_of_their_days():
    """Log returns add. Averaging them or resampling prices and re-differencing
    would give a different and wrong number."""
    frames = planted(names=3, n=200)
    daily = B.returns_matrix(frames, list(frames))
    weekly = B.weekly(daily)
    first_week = daily.loc[daily.index <= weekly.index[0]]
    assert weekly.iloc[0].iloc[0] == pytest.approx(
        first_week.iloc[:, 0].sum(), abs=1e-9)


# ============================================================================ #
# 2. It recovers planted structure
# ============================================================================ #
def test_a_shared_factor_reduces_the_bet_count():
    independent = B.analyse(*_args(planted(loading=0.0)))
    correlated = B.analyse(*_args(planted(loading=0.85)))
    assert independent["effectiveBets"] > correlated["effectiveBets"]
    assert correlated["effectiveBets"] < 3.0, (
        "eight names on one factor should collapse to very few bets")


def test_independent_names_span_close_to_their_own_count():
    result = B.analyse(*_args(planted(names=8, loading=0.0)))
    assert result["effectiveBets"] > 6.0


def test_the_diversification_ratio_falls_as_names_converge():
    independent = B.analyse(*_args(planted(loading=0.0)))
    correlated = B.analyse(*_args(planted(loading=0.9)))
    assert independent["diversificationRatio"] > correlated["diversificationRatio"]
    assert correlated["diversificationRatio"] == pytest.approx(1.0, abs=0.25)


def test_correlation_makes_the_portfolio_more_volatile_than_independence_implies():
    result = B.analyse(*_args(planted(loading=0.8)))
    assert result["portfolioVolatility"] > result["independentVolatility"]


def test_the_most_redundant_name_is_named():
    result = B.analyse(*_args(planted(loading=0.7)))
    assert result["mostRedundant"] in result["names"]
    assert set(result["averageToRest"]) == set(result["names"])


def _args(frames: dict):
    return frames, list(frames)


# ============================================================================ #
# 3. It scores nothing
# ============================================================================ #
def test_nothing_here_emits_a_score():
    """Concentration is a property of a list. A `score` key would be the first
    step to it leaking into a per-name number."""
    result = B.analyse(*_args(planted(loading=0.5)))
    assert "score" not in result
    assert "action" not in result


def test_weights_change_the_diversification_ratio_but_not_the_bet_count():
    """Effective bets is a property of the SET; the ratio is what the weights
    capture of it. Conflating them would hide a concentrated set behind
    well-chosen weights."""
    frames = planted(loading=0.4)
    names = list(frames)
    even = B.analyse(frames, names)
    lopsided = B.analyse(frames, names,
                         weights={names[0]: 0.9,
                                  **{n: 0.01 for n in names[1:]}})
    assert even["effectiveBets"] == pytest.approx(lopsided["effectiveBets"])
    assert even["diversificationRatio"] != pytest.approx(
        lopsided["diversificationRatio"])


# ============================================================================ #
# 4. A threshold that never binds is broken
# ============================================================================ #
def test_the_cluster_sensitivity_is_reported_either_side_of_the_link():
    result = B.analyse(*_args(planted(loading=0.6)))
    assert set(result["clusterSensitivity"]) == {
        f"{v:.2f}" for v in B.CLUSTER_SENSITIVITY}
    assert result["clusterLink"] == B.CLUSTER_LINK


def test_a_strong_common_factor_groups_the_names_together():
    result = B.analyse(*_args(planted(loading=0.9)))
    biggest = max((len(g) for g in result["clusters"]), default=0)
    assert biggest > 1, "names on one factor should link at the stated threshold"


def test_independent_names_form_no_group():
    result = B.analyse(*_args(planted(loading=0.0)))
    assert all(len(g) == 1 for g in result["clusters"])


def test_clustering_chains_and_that_is_the_intended_error():
    """A links B links C groups all three even where A and C are uncorrelated.
    A chain of correlated names is what a common factor looks like."""
    correlation = pd.DataFrame(
        [[1.0, 0.8, 0.0], [0.8, 1.0, 0.8], [0.0, 0.8, 1.0]],
        index=["A", "B", "C"], columns=["A", "B", "C"])
    assert B.clusters(correlation, link=0.5) == [["A", "B", "C"]]


# ============================================================================ #
# 5. Too little data declines
# ============================================================================ #
def test_one_name_is_not_a_set():
    result = B.analyse(*_args(planted(names=1)))
    assert result["available"] is False
    assert "at least two" in result["reason"]


def test_too_few_weeks_declines_rather_than_quoting_a_noisy_matrix():
    result = B.analyse(*_args(planted(n=150)))
    assert result["available"] is False
    assert str(B.MIN_WEEKS) in result["reason"]


def test_a_thin_but_usable_sample_says_so_in_the_reading():
    result = B.analyse(*_args(planted(n=280)))
    if result["available"] and result["thin"]:
        assert "noisy" in result["reading"]


def test_a_missing_name_is_dropped_rather_than_sinking_the_matrix():
    frames = planted(names=6)
    result = B.analyse(frames, [*frames, "ABSENT.JK"])
    assert result["available"] is True
    assert "ABSENT.JK" not in result["names"]
    assert result["count"] == 6
