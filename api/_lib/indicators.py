"""
indicators.py
=============
The indicator library, written out rather than imported.

WHY HAND-ROLLED
---------------
`technical.py` already explains the bundle-size reason: pandas-ta is ~40 MB for
a handful of functions and its import-time numpy probing is fragile on
serverless Python. The consequence is that these formulas are now this
project's responsibility, so every one of them is checked in
tests/test_indicators.py against a reference written independently from the
original definition — not against a second copy of the same code.

WHICH OF THESE ACTUALLY HELP A LONG-TERM INVESTOR
-------------------------------------------------
Most classical technical analysis was designed for traders holding for days.
Someone holding for years needs a different subset, and pretending otherwise
would be the easy way to build something impressive and useless. So this module
tags each indicator with its natural horizon, and `longterm.py` carries the
metrics that actually decide a multi-year holding:

  LONG HORIZON     200-day and 10-month averages, Ichimoku, ADX, Aroon,
                   Donchian (52-week breakout), Coppock, linear-regression
                   channel, Hurst
  MEDIUM           MACD, CCI, ROC, Keltner, Chaikin Money Flow
  SHORT            Stochastic, Williams %R, RSI, ATR

The short-horizon ones are included because they are what people expect to
find, and because an oversold reading is genuinely useful as ENTRY TIMING once
a long-horizon case already exists. They are not a thesis on their own, and the
UI groups them so that is visible.

References
----------
Wilder, J. W. (1978). New Concepts in Technical Trading Systems. (RSI, ATR,
    ADX/DMI, Parabolic SAR.)
Appel, G. (1979). The Moving Average Convergence Divergence Method. (MACD.)
Bollinger, J. (2001). Bollinger on Bollinger Bands.
Lane, G. (1984). "Lane's Stochastics." Technical Analysis of Stocks & Commodities.
Lambert, D. (1980). "Commodity Channel Index." Commodities Magazine.
Chande, T. (1995). "The Aroon Indicator." Stocks & Commodities 13(9).
Hosoda, G. (1969). Ichimoku Kinko Hyo.
Donchian, R. (1960). "High Finance in Copper." Financial Analysts Journal.
Keltner, C. (1960). How to Make Money in Commodities.
Coppock, E. S. C. (1962). "Practical Relative Strength Charting."
    Barron's — designed explicitly as a LONG-TERM buy signal for investors.
Hurst, H. E. (1951). "Long-term storage capacity of reservoirs."
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ============================================================================ #
# Moving averages
# ============================================================================ #
def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length, min_periods=length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    """Standard EMA with span=length, seeded on the first observation."""
    return series.ewm(span=length, min_periods=length, adjust=False).mean()


def wilder_smooth(series: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothing: an EMA with alpha = 1/length rather than 2/(n+1).

    Wilder's own indicators (RSI, ATR, ADX) all use this, and substituting a
    conventional EMA silently changes every one of their published thresholds.
    """
    return series.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()


# ============================================================================ #
# Volatility and range
# ============================================================================ #
def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """max(H-L, |H-C_prev|, |L-C_prev|) — the gap-aware daily range."""
    previous_close = close.shift(1)
    return pd.concat([
        high - low,
        (high - previous_close).abs(),
        (low - previous_close).abs(),
    ], axis=1).max(axis=1)


def atr(high, low, close, length: int = 14) -> pd.Series:
    """Average True Range (Wilder). The unit a long-term investor should size
    positions and stops in — a 2% move means something different on a utility
    than on a biotech."""
    return wilder_smooth(true_range(high, low, close), length)


def keltner_channels(high, low, close, length: int = 20, multiplier: float = 2.0):
    """EMA centre with ATR-scaled bands. Unlike Bollinger, the width tracks the
    TRUE range, so overnight gaps widen it rather than being ignored."""
    middle = ema(close, length)
    width = multiplier * atr(high, low, close, length)
    return middle - width, middle, middle + width


def donchian_channels(high, low, length: int = 252):
    """Highest high and lowest low over `length` bars.

    The default is one trading YEAR on purpose: the upper band is then the
    52-week high, and a close at it is the classic long-horizon breakout that
    Donchian's followers traded and that George & Hwang (2004) later documented
    as an anomaly in its own right.
    """
    upper = high.rolling(length, min_periods=max(2, length // 4)).max()
    lower = low.rolling(length, min_periods=max(2, length // 4)).min()
    return lower, (upper + lower) / 2.0, upper


def bollinger_bands(close: pd.Series, length: int = 20, std: float = 2.0, ddof: int = 1):
    middle = close.rolling(window=length, min_periods=length).mean()
    deviation = close.rolling(window=length, min_periods=length).std(ddof=ddof)
    return middle - std * deviation, middle, middle + std * deviation


def bollinger_percent_b(close, lower, upper) -> pd.Series:
    """Where price sits inside the bands: 0 at the lower, 1 at the upper."""
    span = (upper - lower).replace(0.0, np.nan)
    return (close - lower) / span


def bollinger_bandwidth(lower, middle, upper) -> pd.Series:
    """Band width relative to the centre — the 'squeeze' measure."""
    return (upper - lower) / middle.replace(0.0, np.nan)


# ============================================================================ #
# Momentum oscillators
# ============================================================================ #
def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = wilder_smooth(gain, length)
    avg_loss = wilder_smooth(loss, length)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.where(avg_loss != 0.0, 100.0).where(avg_gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    signal_line = ema(line, signal)
    return line, signal_line, line - signal_line


def stochastic(high, low, close, k_length: int = 14, k_smooth: int = 3,
               d_smooth: int = 3):
    """Lane's %K/%D — where the close sits in its recent high-low range."""
    lowest = low.rolling(k_length, min_periods=k_length).min()
    highest = high.rolling(k_length, min_periods=k_length).max()
    span = (highest - lowest).replace(0.0, np.nan)
    raw_k = 100.0 * (close - lowest) / span
    k = raw_k.rolling(k_smooth, min_periods=k_smooth).mean()
    d = k.rolling(d_smooth, min_periods=d_smooth).mean()
    return k, d


def williams_r(high, low, close, length: int = 14) -> pd.Series:
    """Stochastic %K inverted onto a -100..0 scale."""
    highest = high.rolling(length, min_periods=length).max()
    lowest = low.rolling(length, min_periods=length).min()
    span = (highest - lowest).replace(0.0, np.nan)
    return -100.0 * (highest - close) / span


def cci(high, low, close, length: int = 20) -> pd.Series:
    """Commodity Channel Index. Uses MEAN absolute deviation, not standard
    deviation — a detail that is wrong in a surprising number of libraries."""
    typical = (high + low + close) / 3.0
    average = typical.rolling(length, min_periods=length).mean()
    mean_deviation = typical.rolling(length, min_periods=length).apply(
        lambda window: np.abs(window - window.mean()).mean(), raw=True
    )
    return (typical - average) / (0.015 * mean_deviation.replace(0.0, np.nan))


def roc(close: pd.Series, length: int = 12) -> pd.Series:
    """Rate of change, in percent."""
    return close.pct_change(length) * 100.0


def coppock_curve(close: pd.Series, long_roc: int = 14, short_roc: int = 11,
                  wma_length: int = 10) -> pd.Series:
    """Coppock (1962) — built for long-term investors, not traders.

    Coppock was asked by an Episcopal church endowment when to buy, and reasoned
    that a market recovers from a bear phase over roughly the same period people
    grieve a bereavement. Hence 11- and 14-MONTH rates of change, weighted-
    averaged. A turn upward from below zero is the signal. It fires a handful of
    times a decade, which is exactly what makes it useful to someone holding for
    years and useless to anyone trading the week.

    Applied to MONTHLY data as intended; feeding it daily bars produces a
    different (and much noisier) indicator.
    """
    momentum = roc(close, long_roc) + roc(close, short_roc)
    weights = np.arange(1, wma_length + 1, dtype=float)
    return momentum.rolling(wma_length, min_periods=wma_length).apply(
        lambda window: float(np.dot(window, weights) / weights.sum()), raw=True
    )


# ============================================================================ #
# Trend strength and direction
# ============================================================================ #
def adx(high, low, close, length: int = 14):
    """Wilder's ADX with +DI and -DI.

    ADX measures how STRONG a trend is, not which way it points — that is what
    the two directional indicators are for. Reading it as bullish because it is
    rising is the standard misuse; a violent downtrend also has a high ADX.

    Conventional bands: below 20 is trendless chop, above 25 is a real trend.
    """
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
                        index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
                         index=high.index)

    atr_value = wilder_smooth(true_range(high, low, close), length).replace(0.0, np.nan)
    plus_di = 100.0 * wilder_smooth(plus_dm, length) / atr_value
    minus_di = 100.0 * wilder_smooth(minus_dm, length) / atr_value

    denominator = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denominator
    return wilder_smooth(dx, length), plus_di, minus_di


def aroon(high, low, length: int = 25):
    """Days since the window's high and low, as 0-100.

    Answers "how long since this last made a new high?", which is a more
    natural question for a long-horizon holder than most oscillators.
    """
    def since_max(window):
        return 100.0 * (len(window) - 1 - int(np.argmax(window))) / (len(window) - 1)

    def since_min(window):
        return 100.0 * (len(window) - 1 - int(np.argmin(window))) / (len(window) - 1)

    periods = length + 1
    up = high.rolling(periods, min_periods=periods).apply(
        lambda w: 100.0 - since_max(w), raw=True)
    down = low.rolling(periods, min_periods=periods).apply(
        lambda w: 100.0 - since_min(w), raw=True)
    return up, down, up - down


def ichimoku(high, low, close, conversion: int = 9, base: int = 26,
             span_b: int = 52, displacement: int = 26):
    """Ichimoku Kinko Hyo — 'one glance equilibrium chart'.

    Included because the cloud is genuinely a long-horizon construct: Span B
    uses a 52-period midpoint and both spans are projected 26 periods FORWARD,
    so the chart carries a forward-looking support/resistance band rather than
    only a backward-looking average.

    The spans are shifted forward, which means the last `displacement` rows of
    the returned spans describe the future and have no price beside them yet.
    That is the intended behaviour, not a bug — but it is why they must never be
    joined to returns for any statistical test.
    """
    def midpoint(length):
        return (high.rolling(length, min_periods=length).max()
                + low.rolling(length, min_periods=length).min()) / 2.0

    conversion_line = midpoint(conversion)         # Tenkan-sen
    base_line = midpoint(base)                     # Kijun-sen
    leading_a = ((conversion_line + base_line) / 2.0).shift(displacement)   # Senkou A
    leading_b = midpoint(span_b).shift(displacement)                        # Senkou B
    lagging = close.shift(-displacement)                                    # Chikou
    return conversion_line, base_line, leading_a, leading_b, lagging


def linear_regression_channel(close: pd.Series, length: int = 252, deviations: float = 2.0):
    """Least-squares trend line through the last `length` closes, plus bands.

    Returns `(slope_per_year, r_squared, lower, mid, upper)` where the bands are
    the fitted line plus and minus `deviations` residual standard deviations.

    The slope is annualised and the R² reported because a trend line without a
    goodness of fit is decoration: the same line drawn through a random walk
    looks equally confident.
    """
    values = close.dropna().tail(length)
    if len(values) < 10:
        return None, None, None, None, None

    x = np.arange(len(values), dtype=float)
    y = np.log(values.to_numpy())          # log space: a straight line is constant %
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    residuals = y - fitted
    residual_sd = float(np.std(residuals, ddof=2)) if len(residuals) > 2 else 0.0

    total = float(np.sum((y - y.mean()) ** 2))
    r_squared = float(1.0 - np.sum(residuals ** 2) / total) if total > 0 else np.nan

    mid = pd.Series(np.exp(fitted), index=values.index)
    upper = pd.Series(np.exp(fitted + deviations * residual_sd), index=values.index)
    lower = pd.Series(np.exp(fitted - deviations * residual_sd), index=values.index)
    return float(np.expm1(slope * 252)), r_squared, lower, mid, upper


# Sampling error of the estimator below, measured rather than assumed.
#
# Exact fractional Brownian motion was generated by Cholesky factorisation of
# the fGn covariance at known H, the estimator run over 60 seeds at each of
# n = 400, 800, 1250, 2000 and 3000, and the standard deviation of the estimate
# recorded. `sd * sqrt(n)` came out at 2.09, 2.18, 1.84, 1.78 and 1.74 — flat
# enough to treat the error as c/sqrt(n) with c below.
#
# WHY THIS CONSTANT EARNS ITS PLACE. The estimator is well calibrated (it
# recovers true H to within about 0.02-0.07 across 0.3-0.8) but it is NOISY, and
# the fixed 0.45-0.55 "random walk" band this module used to be read against is
# barely one standard error wide at a realistic sample size. On five years of
# daily bars — the app's default range — a GENUINE random walk was being
# labelled trending or mean-reverting 35% of the time, and on two years, 83%,
# with a systematic downward bias that made short samples read "mean-reverting"
# on nothing at all. For the one number whose whole job is to say when the rest
# of the technical lens is describing noise, that is the wrong error to make.
HURST_STDERR_CONSTANT = 1.92


def hurst_estimate(close: pd.Series, max_lag: int = 100) -> dict:
    """Hurst with its sampling error and a sample-size-aware verdict.

    The band that counts as "indistinguishable from a random walk" is
    0.5 +/- 2 standard errors, so it WIDENS when there is less history rather
    than pretending a short sample supports the same confidence as a long one.
    Measured against exact fBm, that takes the false-verdict rate on a true
    random walk from 35% to 7% at five years and from 83% to 17% at one and a
    half, while still calling a genuinely persistent series (H = 0.7) trending
    82% of the time.
    """
    value = hurst_exponent(close, max_lag)
    usable = close.dropna()
    observations = int((usable > 0).sum())

    if value is None or not np.isfinite(value) or observations < 2:
        return {"hurst": None, "stderr": None, "observations": observations,
                "randomWalkLow": None, "randomWalkHigh": None,
                "verdict": "unavailable"}

    stderr = HURST_STDERR_CONSTANT / np.sqrt(observations)
    low, high = 0.5 - 2.0 * stderr, 0.5 + 2.0 * stderr
    verdict = ("persistent" if value >= high
               else "meanReverting" if value <= low
               else "indistinguishable")
    return {
        "hurst": float(value),
        "stderr": float(stderr),
        "observations": observations,
        "randomWalkLow": float(low),
        "randomWalkHigh": float(high),
        "verdict": verdict,
    }


def hurst_exponent(close: pd.Series, max_lag: int = 100) -> float:
    """Rescaled-range style estimate of long memory, via the variance of lagged
    differences.

    H = 0.5   a random walk; past direction says nothing about the future
    H > 0.5   trending / persistent — momentum has some basis here
    H < 0.5   mean-reverting; a fall is more likely to be given back

    Worth having precisely because it is the honest check on every trend
    indicator above: if H sits at 0.5, the trend tools are describing noise.

    THE POINT ESTIMATE ALONE IS NOT ENOUGH TO ACT ON — see `hurst_estimate`,
    which pairs it with its sampling error. Reading this figure against a fixed
    0.45-0.55 band mislabels a genuine random walk a third of the time on five
    years of data.
    """
    # Prices are positive by definition, but a caller can hand this anything —
    # and log(0) returns -inf with a warning rather than failing, which would
    # then propagate a silently meaningless exponent.
    positive = close.dropna()
    positive = positive[positive > 0]
    if len(positive) < 100:
        return float("nan")
    values = np.log(positive.to_numpy())
    n = len(values)

    lags = range(2, min(max_lag, n // 2))
    tau = []
    usable_lags = []
    for lag in lags:
        differences = values[lag:] - values[:-lag]
        deviation = float(np.std(differences))
        if deviation > 0:
            tau.append(deviation)
            usable_lags.append(lag)
    if len(tau) < 10:
        return float("nan")

    slope = np.polyfit(np.log(usable_lags), np.log(tau), 1)[0]
    return float(slope)


# ============================================================================ #
# Volume
# ============================================================================ #
def on_balance_volume(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).fillna(0.0).cumsum()


def accumulation_distribution(high, low, close, volume) -> pd.Series:
    """Chaikin's A/D line: volume weighted by where the close sat in the range."""
    span = (high - low).replace(0.0, np.nan)
    multiplier = ((close - low) - (high - close)) / span
    return (multiplier.fillna(0.0) * volume).cumsum()


def chaikin_money_flow(high, low, close, volume, length: int = 21) -> pd.Series:
    """A/D flow as a fraction of volume over the window: -1 to +1."""
    span = (high - low).replace(0.0, np.nan)
    multiplier = ((close - low) - (high - close)) / span
    flow = (multiplier.fillna(0.0) * volume).rolling(length, min_periods=length).sum()
    total = volume.rolling(length, min_periods=length).sum().replace(0.0, np.nan)
    return flow / total


def money_flow_index(high, low, close, volume, length: int = 14) -> pd.Series:
    typical = (high + low + close) / 3.0
    raw_flow = typical * volume
    delta = typical.diff()
    positive = raw_flow.where(delta > 0, 0.0).rolling(length, min_periods=length).sum()
    negative = raw_flow.where(delta < 0, 0.0).rolling(length, min_periods=length).sum()
    ratio = positive / negative.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + ratio)).fillna(50.0)


def volume_trend(volume: pd.Series, short: int = 21, long: int = 252) -> pd.Series:
    """Recent volume against its own long-run average. Rising participation in a
    trend is the classic confirmation; a trend on fading volume is not."""
    return (volume.rolling(short, min_periods=short // 2).mean()
            / volume.rolling(long, min_periods=long // 4).mean().replace(0.0, np.nan))
