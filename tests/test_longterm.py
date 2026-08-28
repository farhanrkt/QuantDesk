"""Long-horizon analytics, checked against planted paths.

Where a property can be constructed exactly — a known drawdown, a known CAGR, a
known worst 3-year window — the test builds that path and asserts the number
comes back. Ratios are checked for the properties that justify using them
(Sortino above Sharpe when the downside is quiet, Calmar falling as drawdown
deepens) rather than against a second copy of the formula.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import longterm as L


def price_path(values, start="2015-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)),
                     dtype="float64")


@pytest.fixture(scope="module")
def history():
    """Twelve years of daily prices with a real bear market in the middle."""
    rng = np.random.default_rng(19)
    n = 12 * L.TRADING_DAYS
    returns = rng.normal(0.0005, 0.011, n)
    returns[1200:1500] -= 0.0035           # a sustained decline
    close = 100 * np.exp(np.cumsum(returns))
    index = pd.bdate_range("2013-01-02", periods=n)
    return pd.Series(close, index=index)


# ============================================================================ #
# Drawdown
# ============================================================================ #
def test_drawdown_recovers_a_planted_decline():
    # 100 -> 60 (a 40% fall) -> back to 100.
    path = price_path([100.0] * 10 + list(np.linspace(100, 60, 30))
                      + list(np.linspace(60, 100, 40)) + [100.0] * 10)
    profile = L.drawdown_profile(path)

    assert profile["maxDrawdown"] == pytest.approx(-0.40, abs=1e-9)
    assert profile["currentDrawdown"] == pytest.approx(0.0, abs=1e-9)
    assert profile["maxDrawdownRecovered"] is not None
    assert profile["maxDrawdownTrough"] > profile["maxDrawdownPeak"]


def test_drawdown_reports_an_unrecovered_decline():
    path = price_path([100.0] * 10 + list(np.linspace(100, 55, 40)))
    profile = L.drawdown_profile(path)
    assert profile["maxDrawdown"] == pytest.approx(-0.45, abs=1e-9)
    assert profile["maxDrawdownRecovered"] is None
    assert profile["currentUnderWaterDays"] > 30


def test_time_under_water_is_the_longest_stretch():
    # Two dips: a short deep one, then a long shallow one.
    path = price_path(
        [100.0] * 5
        + [70.0] * 3 + [100.0] * 5              # deep, 3 days under
        + [95.0] * 40 + [101.0] * 5             # shallow, 40 days under
    )
    profile = L.drawdown_profile(path)
    assert profile["timeUnderWaterDays"] >= 40
    assert profile["maxDrawdown"] == pytest.approx(-0.30, abs=1e-9)


def test_ulcer_index_punishes_long_shallow_declines():
    """The reason to report it: a grind is worse to hold than a quick fall."""
    quick = price_path([100.0] * 20 + [65.0] * 2 + [100.0] * 78)
    grind = price_path([100.0] * 20 + [88.0] * 78 + [100.0] * 2)
    assert L.drawdown_profile(grind)["ulcerIndex"] > L.drawdown_profile(quick)["ulcerIndex"]


def test_drawdown_declines_on_a_tiny_series():
    assert L.drawdown_profile(price_path([100.0, 101.0]))["usable"] is False


# ============================================================================ #
# Return and risk
# ============================================================================ #
def test_cagr_matches_a_planted_growth_rate():
    """Growth is planted per CALENDAR year, which is what CAGR measures.

    Compounding per business day and expecting 252 of them to make a year is the
    trap here: 252 trading days span roughly 348 calendar days, so that path
    grows ~3.7% a year faster than intended and the function is blamed for it.
    """
    rate = 0.12
    index = pd.bdate_range("2015-01-01", periods=10 * L.TRADING_DAYS)
    elapsed = (index - index[0]).days.to_numpy() / 365.25
    path = pd.Series(100 * (1 + rate) ** elapsed, index=index)
    assert L.cagr(path) == pytest.approx(rate, rel=1e-6)


def test_risk_metrics_on_a_flat_riser():
    index = pd.bdate_range("2015-01-01", periods=5 * L.TRADING_DAYS)
    elapsed = (index - index[0]).days.to_numpy() / 365.25
    path = pd.Series(100 * 1.10 ** elapsed, index=index)
    metrics = L.risk_metrics(path)

    assert metrics["cagr"] == pytest.approx(0.10, rel=1e-6)
    assert metrics["positiveDays"] == pytest.approx(1.0)
    # Not exactly zero: growth is per calendar day, so a Monday return spans
    # three of them and the daily series is not perfectly constant. 0.3% a year
    # is the weekend, not volatility.
    assert metrics["volatility"] < 0.01


def test_sortino_exceeds_sharpe_when_the_downside_is_quiet():
    """The property that makes Sortino worth reporting separately.

    A series with big upside jumps and small declines is penalised by Sharpe for
    the very thing an investor wants.
    """
    rng = np.random.default_rng(4)
    n = 3 * L.TRADING_DAYS
    returns = np.where(rng.random(n) < 0.5,
                       rng.normal(0.004, 0.010, n),      # large up moves
                       rng.normal(-0.001, 0.002, n))     # small down moves
    path = price_path(100 * np.exp(np.cumsum(returns)))
    metrics = L.risk_metrics(path)
    assert metrics["sortino"] > metrics["sharpe"]


def test_calmar_falls_as_the_drawdown_deepens():
    rng = np.random.default_rng(2)
    n = 4 * L.TRADING_DAYS
    # A mild wobble, so BOTH paths have a drawdown to divide by. Calmar is
    # undefined on a path that never falls, and reports None rather than a
    # fabricated infinity.
    base = 100 * np.exp(np.cumsum(rng.normal(0.0006, 0.004, n)))

    shocked = base.copy()
    shocked[n // 2:] *= 0.55                  # a 45% hole mid-way

    calm = L.risk_metrics(price_path(base))["calmar"]
    hurt = L.risk_metrics(price_path(shocked))["calmar"]
    assert calm is not None and hurt is not None
    assert hurt < calm


def test_calmar_is_none_when_a_path_never_falls():
    index = pd.bdate_range("2015-01-01", periods=3 * L.TRADING_DAYS)
    elapsed = (index - index[0]).days.to_numpy() / 365.25
    metrics = L.risk_metrics(pd.Series(100 * 1.10 ** elapsed, index=index))
    assert metrics["calmar"] is None, "no drawdown means the ratio is undefined"


def test_var_and_cvar_describe_the_left_tail(history):
    metrics = L.risk_metrics(history)
    assert metrics["var95"] < 0
    assert metrics["cvar95"] <= metrics["var95"], "CVaR is the mean BEYOND VaR"
    assert metrics["worstDay"] <= metrics["cvar95"]


def test_risk_metrics_declines_on_short_history():
    assert L.risk_metrics(price_path(np.linspace(100, 110, 10)))["usable"] is False


# ============================================================================ #
# Rolling returns
# ============================================================================ #
def test_rolling_returns_bracket_the_planted_rate():
    n = 12 * L.TRADING_DAYS
    daily = (1.10) ** (1 / L.TRADING_DAYS) - 1
    path = price_path(100 * (1 + daily) ** np.arange(n))

    rows = L.rolling_returns(path, years=(1, 3, 5))
    assert [r["years"] for r in rows] == [1, 3, 5]
    for row in rows:
        assert row["median"] == pytest.approx(0.10, rel=0.02)
        assert row["worst"] == pytest.approx(0.10, rel=0.02)
        assert row["positiveShare"] == pytest.approx(1.0)


def test_rolling_returns_expose_a_bad_window(history):
    """The number a headline CAGR hides: the worst entry point in the record."""
    rows = L.rolling_returns(history, years=(1, 3))
    assert rows
    one_year = next(r for r in rows if r["years"] == 1)
    assert one_year["worst"] < one_year["median"] < one_year["best"]
    assert 0.0 <= one_year["positiveShare"] <= 1.0
    assert one_year["p25"] <= one_year["median"] <= one_year["p75"]


def test_a_horizon_the_history_cannot_support_is_marked_not_dropped():
    """It used to vanish, and on the app's own default range the five-year row
    usually did. A reader then could not tell whether the stock had never had a
    bad five-year stretch or whether nobody had looked — which is the
    absence-reads-as-evidence failure, in the oldest table in the app."""
    short = price_path(np.linspace(100, 130, 400))
    rows = {r["years"]: r for r in L.rolling_returns(short, years=(1, 3, 5))}

    assert set(rows) == {1, 3, 5}, "every requested horizon must be accounted for"
    assert rows[1]["usable"] is True
    for horizon in (3, 5):
        assert rows[horizon]["usable"] is False
        assert rows[horizon]["windows"] == 0
        # The reason has to be actionable, not a shrug.
        assert "Widen the chart range" in rows[horizon]["reason"]
        assert "400" in rows[horizon]["reason"], "say how much history there actually is"
        # And it must carry no numbers that would read as a result.
        assert "worst" not in rows[horizon] and "median" not in rows[horizon]


def test_the_default_horizons_are_the_ones_a_holder_would_state():
    assert L.HOLDING_HORIZONS == (1, 2, 3, 5, 10)
    rows = L.rolling_returns(price_path(np.linspace(100, 130, 400)))
    assert [r["years"] for r in rows] == list(L.HOLDING_HORIZONS)


# ============================================================================ #
# Seasonality and calendar
# ============================================================================ #
def test_calendar_returns_are_year_by_year(history):
    rows = L.calendar_returns(history)
    assert rows
    assert all("year" in r for r in rows)
    assert rows == sorted(rows, key=lambda r: r["year"])


def test_monthly_seasonality_covers_twelve_months(history):
    result = L.monthly_seasonality(history)
    assert result["usable"] is True
    assert len(result["months"]) == 12
    assert [m["month"] for m in result["months"]] == L.MONTHS
    assert "caveat" in result and "data-mined" in result["caveat"]


def test_seasonality_declines_without_a_year_of_data():
    assert L.monthly_seasonality(price_path(np.linspace(100, 110, 50)))["usable"] is False


# ============================================================================ #
# Momentum and position
# ============================================================================ #
def test_momentum_12_1_skips_the_last_month():
    """Not a quirk — short-term reversal contaminates the recent weeks."""
    n = 400
    values = np.linspace(100, 200, n)
    values[-21:] = np.linspace(200, 150, 21)      # a sharp recent reversal
    path = price_path(values)

    momentum = L.time_series_momentum(path)
    assert momentum["12m"] is not None and momentum["momentum12_1"] is not None
    # The plain 12-month figure is dragged down by the reversal; 12-1 is not.
    assert momentum["momentum12_1"] > momentum["12m"]


def test_trend_following_signal_flips_with_the_year():
    rising = price_path(np.linspace(100, 200, 400))
    falling = price_path(np.linspace(200, 100, 400))
    assert L.time_series_momentum(rising)["trendFollowingSignal"] == "long"
    assert L.time_series_momentum(falling)["trendFollowingSignal"] == "flat"


def test_price_position_against_the_52_week_range():
    n = 300
    close = price_path(np.linspace(50, 150, n))
    high = close * 1.01
    low = close * 0.99
    position = L.price_position(close, high, low)

    assert position["usable"] is True
    assert position["rangePosition"] == pytest.approx(1.0, abs=0.02)   # at the top
    assert position["fromHigh52w"] == pytest.approx(-0.0099, abs=0.005)
    assert position["fromAllTimeHigh"] == pytest.approx(0.0, abs=1e-9)


def test_price_position_after_a_fall_from_the_high():
    values = list(np.linspace(50, 150, 250)) + list(np.linspace(150, 100, 50))
    close = price_path(values)
    position = L.price_position(close, close * 1.001, close * 0.999)
    assert position["fromAllTimeHigh"] == pytest.approx(-1 / 3, abs=0.01)
    assert position["rangePosition"] < 0.6


# ============================================================================ #
# Faber timing
# ============================================================================ #
def test_faber_is_invested_in_an_uptrend():
    path = price_path(np.linspace(100, 300, 3 * L.TRADING_DAYS))
    result = L.faber_timing(path)
    assert result["usable"] is True
    assert result["signal"] == "invested"
    assert result["distance"] > 0
    assert result["monthsInStance"] > 6


def test_faber_turns_defensive_in_a_downtrend():
    path = price_path(np.linspace(300, 100, 3 * L.TRADING_DAYS))
    result = L.faber_timing(path)
    assert result["signal"] == "defensive"
    assert result["distance"] < 0


def test_faber_declines_on_short_history():
    assert L.faber_timing(price_path(np.linspace(100, 120, 100)))["usable"] is False


# ============================================================================ #
# Relative strength
# ============================================================================ #
def test_relative_strength_detects_outperformance():
    n = 3 * L.TRADING_DAYS
    index = pd.bdate_range("2020-01-01", periods=n)
    benchmark = pd.Series(100 * 1.0002 ** np.arange(n), index=index)
    stock = pd.Series(100 * 1.0006 ** np.arange(n), index=index)

    result = L.relative_strength(stock, benchmark, "^GSPC")
    assert result["usable"] is True
    assert result["outperforming"] is True
    assert result["periods"]["12m"]["excess"] > 0
    assert result["benchmark"] == "^GSPC"


def test_relative_strength_detects_underperformance():
    n = 3 * L.TRADING_DAYS
    index = pd.bdate_range("2020-01-01", periods=n)
    benchmark = pd.Series(100 * 1.0008 ** np.arange(n), index=index)
    stock = pd.Series(100 * 1.0001 ** np.arange(n), index=index)

    result = L.relative_strength(stock, benchmark, "^GSPC")
    assert result["outperforming"] is False
    assert result["periods"]["12m"]["excess"] < 0


def test_relative_strength_needs_overlap():
    a = pd.Series([1.0, 2.0], index=pd.bdate_range("2024-01-01", periods=2))
    b = pd.Series([1.0, 2.0], index=pd.bdate_range("2020-01-01", periods=2))
    assert L.relative_strength(a, b, "^GSPC")["usable"] is False


def test_longterm_output_is_json_safe(history):
    import json
    from _lib.jsonsafe import clean

    payload = {
        "drawdown": L.drawdown_profile(history),
        "risk": L.risk_metrics(history),
        "rolling": L.rolling_returns(history),
        "seasonality": L.monthly_seasonality(history),
        "momentum": L.time_series_momentum(history),
        "position": L.price_position(history, history * 1.01, history * 0.99),
        "faber": L.faber_timing(history),
        "calendar": L.calendar_returns(history),
    }
    json.dumps(clean(payload), allow_nan=False)
