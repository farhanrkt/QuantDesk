"""Microstructure estimators, validated against simulated data with KNOWN truth.

The point of these tests is that the truth is planted. A bid-ask spread is
simulated into an intraday price path, the daily OHLC bars are built from that
path, and the estimator is asked to recover a number it was never told. That is
a real test of the formula; comparing the implementation to a second
implementation of the same formula would not be.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import microstructure as M


def simulate(n_days=500, spread=0.01, daily_vol=0.02, overnight_vol=0.008,
             ticks_per_day=200, volume=1e6, seed=11):
    """Daily OHLCV bars built from an intraday path with a planted spread.

    The efficient price is a random walk. Every observed trade is that price
    pushed half a spread up or down at random — the Roll (1984) bid-ask bounce.
    Daily bars are then the first/max/min/last of the observed trades, exactly
    as a real bar is built, so the spread contaminates the high and the low the
    same way it does in the market.
    """
    rng = np.random.default_rng(seed)
    step_vol = daily_vol / np.sqrt(ticks_per_day)

    efficient = np.empty((n_days, ticks_per_day))
    level = np.log(100.0)
    for day in range(n_days):
        level += rng.normal(0.0, overnight_vol)          # gap between sessions
        steps = rng.normal(0.0, step_vol, ticks_per_day)
        efficient[day] = level + np.cumsum(steps)
        level = efficient[day, -1]

    prices = np.exp(efficient)
    side = rng.choice([-1.0, 1.0], size=prices.shape)
    observed = prices * (1.0 + side * spread / 2.0)

    index = pd.bdate_range("2020-01-01", periods=n_days)
    return pd.DataFrame(
        {
            "Open": observed[:, 0],
            "High": observed.max(axis=1),
            "Low": observed.min(axis=1),
            "Close": observed[:, -1],
            "Volume": np.full(n_days, volume),
        },
        index=index,
    )


# --------------------------------------------------------------------------- #
# Spread estimators
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("estimator", [M.corwin_schultz_spread, M.abdi_ranaldo_spread])
def test_spread_estimates_rise_with_the_planted_spread(estimator):
    """Monotonicity is the property that must hold; it is what makes the
    estimate usable as a relative liquidity ranking."""
    estimates = [
        float(estimator(simulate(spread=s, seed=3)).dropna().median())
        for s in (0.000, 0.005, 0.020, 0.050)
    ]
    assert estimates == sorted(estimates), f"not monotonic: {estimates}"
    assert estimates[-1] > estimates[0] * 3


@pytest.mark.parametrize("estimator", [M.corwin_schultz_spread, M.abdi_ranaldo_spread])
@pytest.mark.parametrize("true_spread", [0.01, 0.03])
def test_spread_estimates_recover_the_right_order_of_magnitude(estimator, true_spread):
    """Both estimators are biased in finite samples — the papers say so — but a
    usable estimate has to land within a factor of a few of the truth."""
    estimated = float(estimator(simulate(spread=true_spread, seed=5)).dropna().median())
    assert true_spread / 4 < estimated < true_spread * 4, (
        f"recovered {estimated:.5f} for a planted {true_spread:.5f}"
    )


def test_spreads_are_never_negative():
    """A negative spread is not a quantity; both estimators clip at zero."""
    for estimator in (M.corwin_schultz_spread, M.abdi_ranaldo_spread):
        values = estimator(simulate(spread=0.0, seed=9)).dropna()
        assert (values >= 0).all()


def test_spread_summary_reports_both_estimators():
    summary = M.spread_summary(simulate(spread=0.02, seed=4))
    assert summary["corwinSchultz"] > 0
    assert summary["abdiRanaldo"] > 0
    assert summary["primary"] == summary["abdiRanaldo"]
    assert summary["observations"] > 0
    assert 0.0 <= summary["disagreement"] < 1.0


def test_abdi_ranaldo_is_less_biased_than_corwin_schultz_on_a_zero_spread_series():
    """The documented reason AR is the headline estimator.

    On a series with no spread at all, the ideal estimate is zero. CS clips
    negative pair estimates before averaging and so cannot reach it; AR averages
    the squared quantity first, letting negative draws cancel.
    """
    frame = simulate(spread=0.0, seed=5)
    cs = float(M.corwin_schultz_spread(frame).dropna().median())
    ar = float(M.abdi_ranaldo_spread(frame).dropna().median())
    assert ar < cs, f"AR {ar:.5f} was not below CS {cs:.5f} on a zero-spread series"
    assert ar < 0.001


# --------------------------------------------------------------------------- #
# Yang-Zhang volatility
# --------------------------------------------------------------------------- #
def test_yang_zhang_recovers_known_volatility():
    """Total simulated variance is session + overnight; YZ estimates the sum."""
    daily_vol, overnight_vol = 0.02, 0.008
    expected_annual = np.sqrt(daily_vol**2 + overnight_vol**2) * np.sqrt(M.TRADING_DAYS)

    frame = simulate(n_days=750, spread=0.0, daily_vol=daily_vol,
                     overnight_vol=overnight_vol, seed=21)
    estimated = float(M.yang_zhang_volatility(frame, window=60).dropna().median())
    assert estimated == pytest.approx(expected_annual, rel=0.25), (
        f"YZ estimated {estimated:.4f} against a planted {expected_annual:.4f}"
    )


def test_yang_zhang_is_more_efficient_than_close_to_close():
    """The reason to use it at all: same data, far less estimation noise.

    Twenty independent samples from an identical process; the estimator whose
    estimates scatter less is the more efficient one.
    """
    window = 21
    yz_estimates, cc_estimates = [], []
    for seed in range(20):
        frame = simulate(n_days=window + 5, spread=0.0, daily_vol=0.02,
                         overnight_vol=0.008, seed=100 + seed)
        yz_estimates.append(float(M.yang_zhang_volatility(frame, window=window).dropna().iloc[-1]))
        close_to_close = np.log(frame["Close"]).diff().dropna()
        cc_estimates.append(float(close_to_close.std(ddof=1) * np.sqrt(M.TRADING_DAYS)))

    assert np.std(yz_estimates) < np.std(cc_estimates), (
        f"YZ scatter {np.std(yz_estimates):.4f} was not below "
        f"close-to-close {np.std(cc_estimates):.4f}"
    )


def test_yang_zhang_is_never_negative_and_scales_with_vol():
    # spread=0: the bid-ask bounce inflates the high-low range, and on a very
    # quiet series that inflation dominates the real volatility. Isolating the
    # scaling property means removing it.
    quiet = M.yang_zhang_volatility(simulate(daily_vol=0.005, spread=0.0, seed=7)).dropna()
    wild = M.yang_zhang_volatility(simulate(daily_vol=0.040, spread=0.0, seed=7)).dropna()
    assert (quiet >= 0).all() and (wild >= 0).all()
    assert wild.median() > quiet.median() * 3


# --------------------------------------------------------------------------- #
# Amihud illiquidity
# --------------------------------------------------------------------------- #
def test_amihud_rises_as_volume_falls():
    """ILLIQ is price impact per dollar traded: same path, less volume, higher."""
    liquid = M.amihud_illiquidity(simulate(volume=1e7, seed=2)).dropna().median()
    thin = M.amihud_illiquidity(simulate(volume=1e5, seed=2)).dropna().median()
    assert thin > liquid
    assert thin / liquid == pytest.approx(100.0, rel=0.05)   # exactly the volume ratio


def test_amihud_handles_zero_volume_days():
    frame = simulate(n_days=120, seed=6)
    frame.loc[frame.index[10:20], "Volume"] = 0.0
    values = M.amihud_illiquidity(frame).dropna()
    assert len(values) > 0
    assert np.isfinite(values).all()


# --------------------------------------------------------------------------- #
# The caller-facing profile
# --------------------------------------------------------------------------- #
def test_liquidity_profile_flags_moves_inside_the_spread():
    """A 30% round-trip spread makes almost any daily move untradeable noise."""
    wide = M.liquidity_profile(simulate(spread=0.30, daily_vol=0.005, seed=8))
    assert wide["spread"] > 0
    assert wide["insideSpreadNoise"] is True

    tight = M.liquidity_profile(simulate(spread=0.002, daily_vol=0.03, seed=8))
    assert tight["moveVsSpread"] > wide["moveVsSpread"]


def test_a_large_move_on_a_tight_name_is_not_flagged_as_spread_noise():
    """Deterministic counterpart: the last day's move is planted, not drawn.

    `insideSpreadNoise` reads the MOST RECENT return, so leaving that day to
    chance makes the assertion a coin flip rather than a test of the rule.
    """
    frame = simulate(spread=0.001, daily_vol=0.01, seed=8).copy()
    last = frame.index[-1]
    previous_close = float(frame["Close"].iloc[-2])
    jump = previous_close * 1.25                       # an unmistakable +25% day
    frame.loc[last, ["Open", "Low", "Close"]] = jump
    frame.loc[last, "High"] = jump * 1.001

    profile = M.liquidity_profile(frame)
    assert profile["moveVsSpread"] > 2.0
    assert profile["insideSpreadNoise"] is False


def test_liquidity_profile_is_json_safe():
    from _lib.jsonsafe import clean
    import json

    profile = M.liquidity_profile(simulate(n_days=80, seed=1))
    json.dumps(clean(profile), allow_nan=False)      # raises on NaN/Infinity


def test_liquidity_profile_survives_a_short_frame():
    profile = M.liquidity_profile(simulate(n_days=8, seed=1))
    assert set(profile) >= {"amihud", "spread", "yangZhangVol", "moveVsSpread"}
