"""Every indicator checked against a reference written independently.

The point of this file is that the reference implementations below are written
from each indicator's DEFINITION — plain loops, no pandas cleverness — rather
than being a second copy of the module's code. If both were written the same
way, agreeing would prove nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import indicators as I


@pytest.fixture(scope="module")
def bars():
    """Deterministic OHLCV with enough history for a 252-day window."""
    rng = np.random.default_rng(7)
    n = 900
    returns = rng.normal(0.0004, 0.013, n)
    close = 100 * np.exp(np.cumsum(returns))
    spread = close * rng.uniform(0.004, 0.02, n)
    open_ = close * (1 + rng.normal(0, 0.003, n))
    return pd.DataFrame(
        {
            "Open": open_,
            "High": np.maximum(close, open_) + spread / 2,
            "Low": np.minimum(close, open_) - spread / 2,
            "Close": close,
            "Volume": rng.lognormal(15, 0.3, n),
        },
        index=pd.bdate_range("2021-01-04", periods=n),
    )


# ============================================================================ #
# Moving averages
# ============================================================================ #
def test_sma_matches_an_explicit_window_mean(bars):
    result = I.sma(bars["Close"], 50)
    values = bars["Close"].to_numpy()
    for i in (60, 300, 899):
        assert result.iloc[i] == pytest.approx(values[i - 49:i + 1].mean(), rel=1e-12)
    assert result.iloc[:49].isna().all()


def test_ema_matches_the_recurrence(bars):
    length = 20
    alpha = 2.0 / (length + 1)
    values = bars["Close"].to_numpy()
    result = I.ema(bars["Close"], length).to_numpy()

    running = values[0]
    for i in range(1, len(values)):
        running = alpha * values[i] + (1 - alpha) * running
        if i >= length + 50:
            assert result[i] == pytest.approx(running, rel=1e-9)


def test_wilder_smoothing_differs_from_a_plain_ema(bars):
    """Substituting one for the other silently moves every Wilder threshold."""
    wilder = I.wilder_smooth(bars["Close"], 14).dropna()
    plain = I.ema(bars["Close"], 14).dropna()
    assert not np.allclose(wilder.tail(200), plain.tail(200))

    # Wilder's alpha is 1/n, a plain EMA's is 2/(n+1).
    values = bars["Close"].to_numpy()
    running = values[0]
    for i in range(1, 400):
        running = values[i] / 14 + running * 13 / 14
    assert I.wilder_smooth(bars["Close"], 14).iloc[399] == pytest.approx(running, rel=1e-9)


# ============================================================================ #
# Volatility
# ============================================================================ #
def test_true_range_is_the_max_of_three_measures(bars):
    high, low, close = bars["High"], bars["Low"], bars["Close"]
    result = I.true_range(high, low, close)
    for i in (5, 200, 700):
        expected = max(
            high.iloc[i] - low.iloc[i],
            abs(high.iloc[i] - close.iloc[i - 1]),
            abs(low.iloc[i] - close.iloc[i - 1]),
        )
        assert result.iloc[i] == pytest.approx(expected, rel=1e-12)


def test_atr_is_positive_and_tracks_range(bars):
    result = I.atr(bars["High"], bars["Low"], bars["Close"]).dropna()
    assert (result > 0).all()
    typical_range = (bars["High"] - bars["Low"]).tail(400).mean()
    assert 0.3 * typical_range < result.tail(400).mean() < 3 * typical_range


def test_keltner_uses_true_range_so_gaps_widen_it(bars):
    frame = bars.copy()
    lower_a, _, upper_a = I.keltner_channels(frame["High"], frame["Low"], frame["Close"])
    width_before = float((upper_a - lower_a).iloc[-1])

    # Plant an overnight gap that leaves the intraday range untouched.
    gapped = frame.copy()
    for column in ("Open", "High", "Low", "Close"):
        gapped.iloc[-30:, gapped.columns.get_loc(column)] *= 1.25
    lower_b, _, upper_b = I.keltner_channels(gapped["High"], gapped["Low"], gapped["Close"])
    assert float((upper_b - lower_b).iloc[-1]) > width_before


def test_donchian_upper_is_the_52_week_high(bars):
    lower, _, upper = I.donchian_channels(bars["High"], bars["Low"], 252)
    assert upper.iloc[-1] == pytest.approx(bars["High"].tail(252).max())
    assert lower.iloc[-1] == pytest.approx(bars["Low"].tail(252).min())


def test_bollinger_percent_b_and_bandwidth(bars):
    lower, middle, upper = I.bollinger_bands(bars["Close"])
    percent_b = I.bollinger_percent_b(bars["Close"], lower, upper).dropna()
    bandwidth = I.bollinger_bandwidth(lower, middle, upper).dropna()

    # %B is 0 at the lower band and 1 at the upper, by construction.
    i = bars.index[-1]
    assert percent_b.loc[i] == pytest.approx(
        (bars["Close"].loc[i] - lower.loc[i]) / (upper.loc[i] - lower.loc[i]))
    assert (bandwidth > 0).all()


# ============================================================================ #
# Momentum
# ============================================================================ #
def reference_rsi(values, length=14):
    """Wilder's recurrence, written as a loop."""
    out = np.full(len(values), np.nan)
    deltas = np.diff(values)
    gains = np.clip(deltas, 0, None)
    losses = -np.clip(deltas, None, 0)
    avg_gain, avg_loss = gains[0], losses[0]
    for i in range(1, len(deltas)):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length
        out[i + 1] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def test_rsi_matches_wilders_recurrence(bars):
    got = I.rsi(bars["Close"]).to_numpy()
    expected = reference_rsi(bars["Close"].to_numpy())
    np.testing.assert_allclose(got[200:], expected[200:], rtol=1e-6, atol=1e-6)


def test_rsi_is_bounded(bars):
    values = I.rsi(bars["Close"]).dropna()
    assert values.between(0, 100).all()


def test_macd_histogram_is_line_minus_signal(bars):
    line, signal, histogram = I.macd(bars["Close"])
    np.testing.assert_allclose(
        (line - signal).dropna().to_numpy(), histogram.dropna().to_numpy(), rtol=1e-12)


def test_stochastic_is_bounded_and_positioned(bars):
    k, d = I.stochastic(bars["High"], bars["Low"], bars["Close"])
    assert k.dropna().between(0, 100).all()
    assert d.dropna().between(0, 100).all()


def test_williams_r_is_the_inverted_stochastic(bars):
    """%R and raw %K describe the same position on opposite scales."""
    r = I.williams_r(bars["High"], bars["Low"], bars["Close"], 14)
    highest = bars["High"].rolling(14, min_periods=14).max()
    lowest = bars["Low"].rolling(14, min_periods=14).min()
    raw_k = 100 * (bars["Close"] - lowest) / (highest - lowest)
    np.testing.assert_allclose(
        (r + 100).dropna().to_numpy(), raw_k.dropna().to_numpy(), rtol=1e-9)


def test_cci_uses_mean_absolute_deviation_not_stdev(bars):
    """The detail most libraries get wrong."""
    length = 20
    result = I.cci(bars["High"], bars["Low"], bars["Close"], length)
    typical = (bars["High"] + bars["Low"] + bars["Close"]) / 3.0

    i = 500
    window = typical.iloc[i - length + 1:i + 1].to_numpy()
    expected = (typical.iloc[i] - window.mean()) / (
        0.015 * np.abs(window - window.mean()).mean())
    assert result.iloc[i] == pytest.approx(expected, rel=1e-9)

    # And it is NOT the standard-deviation version.
    wrong = (typical.iloc[i] - window.mean()) / (0.015 * window.std(ddof=0))
    assert abs(result.iloc[i] - wrong) > 1e-6


def test_roc_is_percent_change(bars):
    result = I.roc(bars["Close"], 12)
    close = bars["Close"]
    assert result.iloc[-1] == pytest.approx(
        (close.iloc[-1] / close.iloc[-13] - 1) * 100, rel=1e-12)


def test_coppock_is_a_weighted_average_of_two_rocs(bars):
    monthly = bars["Close"].resample("ME").last()
    result = I.coppock_curve(monthly).dropna()
    assert len(result) > 0

    momentum = I.roc(monthly, 14) + I.roc(monthly, 11)
    weights = np.arange(1, 11, dtype=float)
    window = momentum.dropna().tail(10).to_numpy()
    assert result.iloc[-1] == pytest.approx(float(np.dot(window, weights) / weights.sum()),
                                            rel=1e-9)


def test_coppock_fires_rarely(bars):
    """Its whole value to a long-term investor is that it is not chatty."""
    monthly = bars["Close"].resample("ME").last()
    curve = I.coppock_curve(monthly).dropna()
    crossings = int(((curve.shift(1) < 0) & (curve >= 0)).sum())
    assert crossings <= 4, f"{crossings} signals in ~{len(monthly)} months is too many"


# ============================================================================ #
# Trend strength
# ============================================================================ #
def test_adx_is_bounded_and_directional_indicators_agree(bars):
    adx_value, plus_di, minus_di = I.adx(bars["High"], bars["Low"], bars["Close"])
    assert adx_value.dropna().between(0, 100).all()
    assert plus_di.dropna().between(0, 100).all()
    assert minus_di.dropna().between(0, 100).all()


def test_adx_is_high_in_a_trend_and_low_in_chop():
    """ADX measures strength, not direction — a pure downtrend scores high too."""
    n = 400
    index = pd.bdate_range("2022-01-03", periods=n)

    def frame_from(close):
        return pd.DataFrame({"High": close * 1.005, "Low": close * 0.995,
                             "Close": close}, index=index)

    trend = frame_from(pd.Series(np.linspace(100, 300, n), index=index))
    falling = frame_from(pd.Series(np.linspace(300, 100, n), index=index))
    rng = np.random.default_rng(3)
    chop = frame_from(pd.Series(100 + np.cumsum(rng.normal(0, 0.5, n)) * 0.1, index=index))

    trend_adx = I.adx(trend["High"], trend["Low"], trend["Close"])[0].dropna().tail(50).mean()
    fall_adx = I.adx(falling["High"], falling["Low"], falling["Close"])[0].dropna().tail(50).mean()
    chop_adx = I.adx(chop["High"], chop["Low"], chop["Close"])[0].dropna().tail(50).mean()

    assert trend_adx > 40 and fall_adx > 40
    assert chop_adx < trend_adx


def test_aroon_hits_100_on_a_fresh_high():
    n = 120
    index = pd.bdate_range("2023-01-02", periods=n)
    rising = pd.Series(np.linspace(50, 150, n), index=index)
    up, down, oscillator = I.aroon(rising, rising, 25)
    assert up.iloc[-1] == pytest.approx(100.0)
    assert down.iloc[-1] == pytest.approx(0.0)
    assert oscillator.iloc[-1] == pytest.approx(100.0)


def test_ichimoku_spans_are_projected_forward(bars):
    _, _, _, span_b, lagging = I.ichimoku(
        bars["High"], bars["Low"], bars["Close"])

    # Span B is the 52-period midpoint shifted forward 26 bars.
    midpoint = (bars["High"].rolling(52, min_periods=52).max()
                + bars["Low"].rolling(52, min_periods=52).min()) / 2
    assert span_b.iloc[-1] == pytest.approx(midpoint.iloc[-27], rel=1e-12)
    # And the lagging line is the close shifted backward.
    assert lagging.iloc[-27] == pytest.approx(bars["Close"].iloc[-1], rel=1e-12)


def test_linear_regression_channel_recovers_a_planted_slope():
    n = 300
    index = pd.bdate_range("2023-01-02", periods=n)
    daily = 0.0008                                    # ~22% a year, compounded
    close = pd.Series(100 * np.exp(np.arange(n) * daily), index=index)

    slope, r_squared, lower, mid, upper = I.linear_regression_channel(close, n)
    assert slope == pytest.approx(np.expm1(daily * 252), rel=1e-6)
    assert r_squared > 0.999
    assert (upper >= mid).all() and (mid >= lower).all()


def test_linear_regression_reports_low_r2_on_noise():
    rng = np.random.default_rng(5)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300))),
                      index=pd.bdate_range("2023-01-02", periods=300))
    _, r_squared, *_ = I.linear_regression_channel(close, 300)
    assert r_squared < 0.95


def test_linear_regression_declines_on_a_short_series():
    close = pd.Series([1.0, 2.0, 3.0])
    assert I.linear_regression_channel(close)[0] is None


def test_hurst_separates_trending_from_mean_reverting():
    n = 4000
    rng = np.random.default_rng(11)

    random_walk = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))))
    trending = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.001, 0.004, n))))
    # An Ornstein-Uhlenbeck style pull back to the mean.
    values, level = [], 0.0
    for _ in range(n):
        level += -0.25 * level + rng.normal(0, 0.01)
        values.append(level)
    reverting = pd.Series(100 * np.exp(values))

    h_walk = I.hurst_exponent(random_walk)
    h_trend = I.hurst_exponent(trending)
    h_revert = I.hurst_exponent(reverting)

    assert 0.4 < h_walk < 0.6, f"random walk should sit near 0.5, got {h_walk:.2f}"
    assert h_trend > h_walk
    assert h_revert < h_walk


def test_hurst_returns_nan_on_short_input():
    assert np.isnan(I.hurst_exponent(pd.Series(np.arange(50, dtype=float))))


# ============================================================================ #
# Volume
# ============================================================================ #
def test_obv_accumulates_signed_volume(bars):
    result = I.on_balance_volume(bars["Close"], bars["Volume"])
    close, volume = bars["Close"], bars["Volume"]
    expected = 0.0
    for i in range(1, 60):
        expected += np.sign(close.iloc[i] - close.iloc[i - 1]) * volume.iloc[i]
    assert result.iloc[59] == pytest.approx(expected, rel=1e-9)


def test_chaikin_money_flow_is_bounded(bars):
    result = I.chaikin_money_flow(bars["High"], bars["Low"], bars["Close"],
                                  bars["Volume"]).dropna()
    assert result.between(-1, 1).all()


def test_chaikin_money_flow_is_positive_when_closes_are_strong():
    n = 120
    index = pd.bdate_range("2023-01-02", periods=n)
    high = pd.Series(np.full(n, 101.0), index=index)
    low = pd.Series(np.full(n, 99.0), index=index)
    close = pd.Series(np.full(n, 100.9), index=index)      # closing at the high
    volume = pd.Series(np.full(n, 1e6), index=index)
    assert I.chaikin_money_flow(high, low, close, volume).dropna().iloc[-1] > 0.8


def test_money_flow_index_is_bounded(bars):
    result = I.money_flow_index(bars["High"], bars["Low"], bars["Close"], bars["Volume"])
    assert result.dropna().between(0, 100).all()


def test_volume_trend_compares_recent_to_long_run(bars):
    result = I.volume_trend(bars["Volume"]).dropna()
    assert (result > 0).all()
    assert 0.2 < result.median() < 5.0


def test_accumulation_distribution_runs_up_when_closing_strong():
    n = 100
    index = pd.bdate_range("2023-01-02", periods=n)
    high = pd.Series(np.full(n, 101.0), index=index)
    low = pd.Series(np.full(n, 99.0), index=index)
    close = pd.Series(np.full(n, 100.95), index=index)
    volume = pd.Series(np.full(n, 1e6), index=index)
    line = I.accumulation_distribution(high, low, close, volume)
    assert line.iloc[-1] > line.iloc[0]
    assert line.is_monotonic_increasing


# ============================================================================ #
# Hurst: calibration against exact fractional Brownian motion
#
# The estimator's POINT VALUE was already exercised elsewhere. What was never
# checked is its SAMPLING ERROR, and that turned out to be the problem: on five
# years of daily bars the standard error is about 0.05, so the fixed 0.45-0.55
# band the reading used to be judged against was barely one standard error wide
# and labelled a genuine random walk "trending" or "mean-reverting" 35% of the
# time. These tests pin the calibration that replaced it.
# ============================================================================ #
def _fbm(hurst: float, n: int, seed: int) -> np.ndarray:
    """Exact fractional Brownian motion, by Cholesky of the fGn covariance.

    Exact rather than approximate on purpose: the whole point is to compare the
    estimator against a series whose true Hurst exponent is known by
    construction, not against another estimate of it.
    """
    from scipy.linalg import cholesky

    lags = np.arange(n)
    gamma = 0.5 * (np.abs(lags + 1) ** (2 * hurst)
                   - 2 * np.abs(lags) ** (2 * hurst)
                   + np.abs(lags - 1) ** (2 * hurst))
    covariance = np.empty((n, n))
    for row in range(n):
        covariance[row, :] = gamma[np.abs(lags - row)]
    covariance += np.eye(n) * 1e-10
    noise = np.random.default_rng(seed).standard_normal(n)
    return np.cumsum(cholesky(covariance, lower=True) @ noise)


def _fbm_prices(hurst: float, n: int, seed: int) -> pd.Series:
    return pd.Series(100.0 * np.exp(_fbm(hurst, n, seed) * 0.01))


@pytest.mark.parametrize("true_hurst", [0.3, 0.5, 0.7])
def test_hurst_recovers_a_known_exponent(true_hurst):
    """It must land near the H it was generated with, not merely be stable."""
    estimates = np.array([I.hurst_exponent(_fbm_prices(true_hurst, 1200, seed))
                          for seed in range(10)])
    assert estimates.mean() == pytest.approx(true_hurst, abs=0.08)


def test_the_random_walk_band_widens_when_there_is_less_history():
    """Less evidence must buy less confidence, not the same confidence."""
    long_reading = I.hurst_estimate(_fbm_prices(0.5, 2500, 1))
    short_reading = I.hurst_estimate(_fbm_prices(0.5, 400, 1))
    long_width = long_reading["randomWalkHigh"] - long_reading["randomWalkLow"]
    short_width = short_reading["randomWalkHigh"] - short_reading["randomWalkLow"]
    assert short_width > long_width * 1.5


def test_a_genuine_random_walk_is_rarely_called_trending():
    """The failure this calibration exists to prevent.

    Against the old fixed 0.45-0.55 band this rate was 35% at five years of
    daily bars. Anything above roughly one in ten makes the reading worse than
    useless, because it is the number the rest of the lens is supposed to be
    discounted against.
    """
    verdicts = [I.hurst_estimate(_fbm_prices(0.5, 1250, seed))["verdict"]
                for seed in range(40)]
    wrong = sum(1 for verdict in verdicts if verdict != "indistinguishable")
    assert wrong / len(verdicts) <= 0.15, (
        f"{wrong}/40 random walks were given a directional verdict"
    )


def test_real_persistence_is_still_detected():
    """Widening the band must not make the measure blind."""
    verdicts = [I.hurst_estimate(_fbm_prices(0.75, 1250, seed))["verdict"]
                for seed in range(20)]
    found = sum(1 for verdict in verdicts if verdict == "persistent")
    assert found / len(verdicts) >= 0.7


def test_hurst_estimate_declines_on_a_series_it_cannot_read():
    flat = I.hurst_estimate(pd.Series(np.full(500, 100.0)))
    assert flat["verdict"] == "unavailable"
    assert flat["hurst"] is None
    short = I.hurst_estimate(pd.Series(np.linspace(100, 110, 50)))
    assert short["verdict"] == "unavailable"
