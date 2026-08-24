"""Event study, PEAD tagging and multiple-testing correction.

Abnormal returns are planted after synthetic events, so the study is asked to
recover a drift it was not told about — and, just as importantly, to report
NOTHING when there is nothing there. A method that finds signal in noise is
worse than no method.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import eventstudy as E


def market_and_stock(n=600, beta=1.1, seed=4, drift=0.0, event_positions=(),
                     drift_days=20):
    """A market-model stock, optionally with abnormal drift planted post-event."""
    rng = np.random.default_rng(seed)
    market_returns = rng.normal(0.0003, 0.010, n)
    stock_returns = beta * market_returns + rng.normal(0.0, 0.008, n)

    for position in event_positions:
        end = min(n, position + 1 + drift_days)
        stock_returns[position + 1:end] += drift / drift_days

    index = pd.bdate_range("2022-01-03", periods=n)
    stock = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(stock_returns))}, index=index)
    market = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(market_returns))}, index=index)
    return stock, market, index


def events_frame(index, positions, flow="Accumulation"):
    return pd.DataFrame(
        {"Flow": [flow] * len(positions), "Strength": [70] * len(positions)},
        index=[index[p] for p in positions],
    )


# --------------------------------------------------------------------------- #
# Event study
# --------------------------------------------------------------------------- #
def test_recovers_planted_positive_drift():
    # 24 events, not 12: with a 20-day CAR window and per-day residual sd of
    # 0.008, a dozen observations leaves the cross-sectional test underpowered
    # even when the drift is unambiguously there.
    positions = list(range(200, 560, 15))
    stock, market, index = market_and_stock(drift=0.05, event_positions=positions, seed=1)
    result = E.run_event_study(stock, market, events_frame(index, positions))

    assert result["usable"] is True
    summary = result["horizons"]["20"]
    assert summary["meanCar"] > 0.02
    assert summary["tStat"] > 2.0
    assert summary["pValue"] < 0.05


def test_recovers_planted_negative_drift():
    positions = list(range(200, 560, 15))
    stock, market, index = market_and_stock(drift=-0.05, event_positions=positions, seed=2)
    result = E.run_event_study(stock, market,
                               events_frame(index, positions, flow="Distribution"))
    assert result["horizons"]["20"]["meanCar"] < -0.02
    assert result["horizons"]["20"]["tStat"] < -2.0


def test_finds_nothing_when_there_is_nothing():
    """The property that makes a positive result worth anything."""
    positions = list(range(200, 560, 30))
    stock, market, index = market_and_stock(drift=0.0, event_positions=positions, seed=3)
    result = E.run_event_study(stock, market, events_frame(index, positions))
    summary = result["horizons"]["20"]
    assert abs(summary["tStat"]) < 2.5
    assert summary["pValue"] > 0.01


def test_splits_results_by_flow_direction():
    positions = list(range(200, 560, 25))
    stock, market, index = market_and_stock(drift=0.04, event_positions=positions, seed=5)
    events = events_frame(index, positions)
    events.iloc[: len(positions) // 2, events.columns.get_loc("Flow")] = "Distribution"

    result = E.run_event_study(stock, market, events)
    assert set(result["byDirection"]) == {"Accumulation", "Distribution"}


def test_estimation_window_excludes_the_event_itself():
    """The gap is load-bearing; without it the baseline eats the signal."""
    stock, market, _ = market_and_stock(seed=6)
    returns = stock["Close"].pct_change()
    market_returns = market["Close"].pct_change()

    result = E.abnormal_returns(returns, market_returns, event_position=300,
                                estimation_window=120, gap=10)
    assert result is not None
    assert np.isfinite(result["beta"])
    assert result["residualSd"] > 0


def test_declines_without_enough_pre_event_history():
    stock, market, _ = market_and_stock(n=200, seed=7)
    returns = stock["Close"].pct_change()
    market_returns = market["Close"].pct_change()
    assert E.abnormal_returns(returns, market_returns, event_position=20) is None


def test_reports_unusable_rather_than_guessing():
    stock, market, index = market_and_stock(n=150, seed=8)
    events = events_frame(index, [30, 40])
    result = E.run_event_study(stock, market, events)
    assert result["usable"] is False
    assert "reason" in result


def test_event_study_is_json_safe():
    import json
    from _lib.jsonsafe import clean

    positions = list(range(200, 560, 30))
    stock, market, index = market_and_stock(drift=0.03, event_positions=positions, seed=9)
    result = E.run_event_study(stock, market, events_frame(index, positions))
    json.dumps(clean(result), allow_nan=False)


# --------------------------------------------------------------------------- #
# PEAD tagging
# --------------------------------------------------------------------------- #
def test_tags_anomalies_near_earnings():
    index = pd.bdate_range("2024-01-01", periods=200)
    events = pd.DataFrame({"Flow": ["Accumulation"] * 4},
                          index=[index[10], index[50], index[100], index[150]])
    earnings = [index[9], index[149]]        # two of the four sit beside a print

    result = E.tag_earnings_proximity(events, earnings)
    assert result["available"] is True
    assert result["tagged"] == 2
    assert result["share"] == pytest.approx(0.5)
    assert all(d["daysApart"] <= E.PEAD_WINDOW_DAYS for d in result["dates"])


def test_untagged_when_earnings_are_far_away():
    index = pd.bdate_range("2024-01-01", periods=200)
    events = pd.DataFrame({"Flow": ["Accumulation"]}, index=[index[100]])
    result = E.tag_earnings_proximity(events, [index[10]])
    assert result["tagged"] == 0


def test_pead_handles_absent_earnings_data():
    index = pd.bdate_range("2024-01-01", periods=50)
    events = pd.DataFrame({"Flow": ["Accumulation"]}, index=[index[10]])
    result = E.tag_earnings_proximity(events, [])
    assert result["available"] is False


# --------------------------------------------------------------------------- #
# Multiple testing
# --------------------------------------------------------------------------- #
def test_binomial_pvalue_endpoints():
    assert E.binomial_pvalue(0, 20, 0.05) == 1.0
    assert E.binomial_pvalue(20, 20, 0.05) < 1e-15
    assert 0.0 < E.binomial_pvalue(3, 20, 0.05) < 1.0


def test_binomial_pvalue_falls_as_observations_rise():
    values = [E.binomial_pvalue(k, 20, 0.05) for k in (1, 2, 3, 5, 8)]
    assert values == sorted(values, reverse=True)


def test_benjamini_hochberg_rejects_the_obvious_and_spares_noise():
    pvalues = [0.001, 0.002, 0.004, 0.6, 0.7, 0.8, 0.9, 0.95]
    result = E.benjamini_hochberg(pvalues, alpha=0.10)
    assert result["discoveries"] == 3
    assert result["rejected"][:3] == [True, True, True]
    assert not any(result["rejected"][3:])


def test_benjamini_hochberg_q_values_are_monotone():
    rng = np.random.default_rng(0)
    pvalues = sorted(rng.uniform(0, 1, 40))
    q = E.benjamini_hochberg(pvalues)["qValues"]
    assert q == sorted(q)
    assert all(0.0 <= v <= 1.0 for v in q)


def test_benjamini_hochberg_finds_almost_nothing_in_pure_noise():
    """Uniform p-values are what a screener over random tickers produces."""
    rng = np.random.default_rng(11)
    discoveries = [E.benjamini_hochberg(rng.uniform(0, 1, 20), alpha=0.10)["discoveries"]
                   for _ in range(40)]
    assert np.mean(discoveries) < 1.0


def test_benjamini_hochberg_is_less_conservative_than_bonferroni():
    pvalues = [0.001, 0.008, 0.02, 0.03, 0.04, 0.5, 0.6, 0.7, 0.8, 0.9]
    bh = E.benjamini_hochberg(pvalues, alpha=0.10)["discoveries"]
    bonferroni = sum(1 for p in pvalues if p <= 0.10 / len(pvalues))
    assert bh >= bonferroni


def test_screener_significance_calibrates_per_ticker():
    """A chronically noisy name needs more recent hits to count as a finding."""
    rows = [
        {"ticker": "QUIET", "recentAnomalies": 4, "anomalyRate": 0.01},
        {"ticker": "NOISY", "recentAnomalies": 4, "anomalyRate": 0.25},
    ]
    result = E.screener_significance(rows, recent_trading_days=20)
    assert result["available"] is True

    quiet = next(r for r in result["rows"] if r["ticker"] == "QUIET")
    noisy = next(r for r in result["rows"] if r["ticker"] == "NOISY")
    assert quiet["pValue"] < noisy["pValue"]
    assert quiet["significant"] is True
    assert noisy["significant"] is False


def test_screener_significance_reports_expected_false_discoveries():
    rows = [{"ticker": f"T{i}", "recentAnomalies": 1, "anomalyRate": 0.10}
            for i in range(20)]
    result = E.screener_significance(rows, recent_trading_days=20)
    assert result["expectedByChance"] > 5
    assert result["discoveries"] == 0
    assert "expected" in result["reading"]


def test_screener_significance_degrades_without_base_rates():
    rows = [{"ticker": "A", "recentAnomalies": 3}]
    result = E.screener_significance(rows, recent_trading_days=20)
    assert result["available"] is False
    assert result["rows"] == rows
