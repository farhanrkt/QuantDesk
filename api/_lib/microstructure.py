"""
microstructure.py
=================
Liquidity and volatility estimators computed from daily OHLCV alone.

WHY THIS MODULE EXISTS
----------------------
The anomaly engine's core claim is that an unusual volume/price day is an
institutional footprint. The most common way that claim is WRONG is liquidity:
on a thin stock, "heavy volume moved the price a lot" is a statement about the
order book being shallow, not about anyone accumulating. Two of the tags the
engine emits — "Price Gap" and "Volume Spike" — are exactly the ones a wide
spread manufactures for free.

So this module supplies the confounders, from the data already fetched:

  Amihud ILLIQ        how much price moves per dollar traded
  Corwin-Schultz      effective bid-ask spread from daily highs and lows
  Abdi-Ranaldo        ditto, using close as well; lower bias in most regimes
  Yang-Zhang          drift-independent, gap-aware volatility

WHAT IS DELIBERATELY ABSENT
---------------------------
Order-flow toxicity (VPIN, Easley-Lopez de Prado-O'Hara 2012) and PIN
(Easley et al. 1996) both need trade-level data with a buy/sell classification.
Daily OHLCV cannot support either, and a "daily VPIN" is not a weaker version of
VPIN — it is a different number wearing its name. If tick data ever arrives,
that is the moment to add it, not before.

References
----------
Amihud, Y. (2002). "Illiquidity and stock returns: cross-section and
    time-series effects." Journal of Financial Markets 5(1), 31-56.
Corwin, S. A., & Schultz, P. (2012). "A Simple Way to Estimate Bid-Ask Spreads
    from Daily High and Low Prices." Journal of Finance 67(2), 719-759.
Abdi, F., & Ranaldo, A. (2017). "A Simple Estimation of Bid-Ask Spreads from
    Daily Close, High, and Low Prices." Review of Financial Studies 30(12).
Yang, D., & Zhang, Q. (2000). "Drift-Independent Volatility Estimation Based on
    High, Low, Open, and Close Prices." Journal of Business 73(3), 477-491.
Rogers, L. C. G., & Satchell, S. E. (1991). "Estimating Variance From High, Low
    and Closing Prices." Annals of Applied Probability 1(4), 504-512.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# Corwin-Schultz works in units of this constant throughout; naming it once
# keeps the algebra below readable and matches the paper's notation.
_CS_K = 3.0 - 2.0 * np.sqrt(2.0)          # ~0.1716


def _positive(series: pd.Series) -> pd.Series:
    """Guard against zeros and negatives before a log."""
    return series.where(series > 0)


# --------------------------------------------------------------------------- #
# Amihud illiquidity
# --------------------------------------------------------------------------- #
def amihud_illiquidity(frame: pd.DataFrame, window: int = 21,
                       scale: float = 1e6) -> pd.Series:
    """Rolling Amihud ILLIQ: mean(|return| / dollar volume) over `window` days.

    Higher means less liquid — more price impact per dollar traded. The raw
    number is tiny, so it is reported scaled by `scale` (1e6 by convention,
    giving "percent price move per million traded"-ish units). The level is not
    comparable across currencies; the CROSS-SECTIONAL RANK within one market is
    the usable signal, which is how Amihud (2002) uses it.
    """
    close = _positive(frame["Close"].astype("float64"))
    returns = close.pct_change().abs()
    dollar_volume = (close * frame["Volume"].astype("float64")).replace(0.0, np.nan)
    daily = (returns / dollar_volume) * scale
    return daily.rolling(window, min_periods=max(2, window // 2)).mean()


# --------------------------------------------------------------------------- #
# Bid-ask spread estimators
# --------------------------------------------------------------------------- #
def corwin_schultz_spread(frame: pd.DataFrame, window: int = 21) -> pd.Series:
    """Rolling two-day high-low effective spread, as a fraction of price.

    The estimator exploits a difference in how two quantities scale: the daily
    high-low range reflects both volatility and the spread, but volatility
    scales with the square root of elapsed time while the spread does not. Two
    single days versus one two-day window therefore separate them.

    AGGREGATION FOLLOWS THE PAPER. Each two-day pair yields its own spread,
    negative values are set to zero (section II: the estimator is unbiased in
    expectation, but individual pairs go negative from sampling noise and a
    negative spread is not a quantity), and the estimate reported for a period
    is the MEAN of those daily values. A single pair is far too noisy to use.
    """
    high = _positive(frame["High"].astype("float64"))
    low = _positive(frame["Low"].astype("float64"))

    log_hl = np.log(high / low)
    beta = log_hl.pow(2) + log_hl.pow(2).shift(-1)          # days t and t+1

    high_2day = pd.concat([high, high.shift(-1)], axis=1).max(axis=1)
    low_2day = pd.concat([low, low.shift(-1)], axis=1).min(axis=1)
    gamma = np.log(high_2day / low_2day) ** 2

    alpha = ((np.sqrt(2.0 * beta) - np.sqrt(beta)) / _CS_K
             - np.sqrt(gamma / _CS_K))
    pairwise = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    return pairwise.clip(lower=0.0).rolling(
        window, min_periods=max(2, window // 2)).mean()


def abdi_ranaldo_spread(frame: pd.DataFrame, window: int = 21) -> pd.Series:
    """Rolling Close-High-Low spread estimator, as a fraction of price.

    Uses the mid-range (h+l)/2 as a proxy for the efficient price, so the
    covariance between the close and the surrounding mid-ranges isolates the
    bid-ask bounce. Abdi & Ranaldo report lower bias than Corwin-Schultz across
    most simulated and empirical regimes, which is why both are exposed here
    rather than one being picked on the caller's behalf.

    AGGREGATION ORDER IS LOAD-BEARING. The paper's estimator averages the
    SQUARED quantity over the window and takes one square root at the end.
    Clipping and rooting each day first — the obvious way to write it — throws
    away every negative draw instead of letting it cancel a positive one, which
    biases the spread upward by roughly a factor of two on a liquid name.
    """
    close = np.log(_positive(frame["Close"].astype("float64")))
    high = np.log(_positive(frame["High"].astype("float64")))
    low = np.log(_positive(frame["Low"].astype("float64")))

    mid = (high + low) / 2.0
    squared = 4.0 * (close - mid) * (close - mid.shift(-1))
    mean_squared = squared.rolling(window, min_periods=max(2, window // 2)).mean()
    return np.sqrt(mean_squared.clip(lower=0.0))


# BOTH ESTIMATORS HAVE A NOISE FLOOR, AND IT SCALES WITH VOLATILITY.
#
# Measured against a correct generative model — an efficient price diffusing
# inside each day, every observed price a transaction carrying a bid-ask bounce,
# open/high/low/close taken from those transactions — with the TRUE spread set
# to zero, the estimators still report:
#
#     Abdi-Ranaldo    ~0.148 x the daily standard deviation
#     Corwin-Schultz  ~0.361 x
#
# Those ratios held to three decimals across daily sigmas of 0.008 to 0.040 — a
# five-fold range — and did not shrink when intraday sampling was refined from
# 40 ticks a day to 1500, so this is a property of inferring a spread from daily
# bars rather than an artefact of the simulation. It is volatility leaking into
# the spread estimate. The ratios are measured against THIS MODULE'S OWN
# aggregation (median of the rolling series), not against the raw daily values,
# because that is the number callers actually receive.
#
# WHY IT MATTERS MORE THAN IT LOOKS. On a stock with 1.5% daily volatility the
# floor is about 0.29%, which is an order of magnitude above the true spread of
# a mega-cap. Left unstated, the app reports a 0.29% round-trip cost on a name
# that actually trades at a basis point or two, warns that ordinary moves are
# "inside spread noise", and does it most confidently on exactly the names where
# it is most wrong.
AR_FLOOR_RATIO = 0.148
CS_FLOOR_RATIO = 0.361

# How close to the floor an estimate has to be before it is reported as
# unresolvable rather than as a measurement.
#
# CHOSEN FROM THE ESTIMATOR'S DISPERSION, not from its mean. At a true spread of
# zero the estimate is bimodal — the rolling median clips to exactly zero about
# half the time and otherwise lands near 3x the floor — so a tolerance fitted to
# the average (1.5) let a third of genuinely zero-spread names through as a
# quoted cost. Measured over 40 seeds at 1.5% daily volatility, the share
# correctly refused is:
#
#     true spread     tol 2.0    tol 3.0    tol 4.0
#     0.0%              68%        88%       100%
#     0.2%              65%        85%       100%
#     1.0%              12%        52%        92%
#     2.0%               0%         0%        30%
#
# 3.0 refuses to quote a figure below roughly half a percent, at the cost of
# also refusing about half of true 1% spreads. That asymmetry is deliberate:
# quoting a fabricated 0.3% cost on a mega-cap makes the app claim trading costs
# matter when they do not, while declining to measure a real 1% spread only
# withholds a number — and the reading still states the estimate as an upper
# bound, which stays true either way.
FLOOR_TOLERANCE = 3.0


# The floor is measured in units of daily volatility, so it needs a volatility
# estimate that the SPREAD ITSELF does not inflate — otherwise the two chase
# each other and a genuinely wide spread produces a floor wide enough to hide
# behind. Measured against a 1.5%-a-day series as the true spread went from 0
# to 30%, the candidates read:
#
#     true spread      0%      0.5%      2%       5%      30%
#     Yang-Zhang    0.0141   0.0170   0.0303   0.0587   0.3036
#     1-day close   0.0145   0.0150   0.0205   0.0388   0.2216
#     5-day close   0.0143   0.0144   0.0157   0.0214   0.0993
#
# Yang-Zhang is the worst possible choice here precisely because it reads the
# high-low range, which is where the bounce lives: at a 5% spread it reported
# four times the true volatility, inflating the floor until a genuinely wide
# spread was marked unresolvable — the exact opposite of the intent, and caught
# by two existing tests. A bid-ask bounce adds a FIXED amount to the variance of
# a return over any holding period, so measuring over five days and scaling back
# divides its contribution by five.
SIGMA_HORIZON = 5


def _daily_sigma(frame: pd.DataFrame, window: int = 252) -> Optional[float]:
    """Daily volatility, measured so a wide spread does not inflate it."""
    close = frame["Close"].astype("float64").tail(window)
    log_returns = np.log(close.where(close > 0)).diff(SIGMA_HORIZON).dropna()
    if len(log_returns) < 20:
        return None
    sigma = float(log_returns.std(ddof=1) / np.sqrt(SIGMA_HORIZON))
    return sigma if np.isfinite(sigma) and sigma > 0 else None


def spread_resolution_floor(frame: pd.DataFrame, window: int = 63,
                            ratio: float = AR_FLOOR_RATIO) -> Optional[float]:
    """The smallest spread this data can tell apart from zero, for this name.

    Scales with the stock's own volatility, because that is what the floor is
    made of. Returns None when there is not enough data to estimate volatility.
    """
    sigma = _daily_sigma(frame)
    return ratio * sigma if sigma else None


def spread_summary(frame: pd.DataFrame, window: int = 63) -> dict:
    """Both spread estimates over the recent window, against their noise floor.

    `window` defaults to a quarter of trading days: long enough for the noise in
    individual two-day estimates to average out, short enough to describe the
    stock's CURRENT trading conditions rather than last year's.

    WHICH ONE IS THE HEADLINE, and why. Abdi-Ranaldo, because its floor is
    roughly half of Corwin-Schultz's. Neither is unbiased at the tight end: on a
    planted-spread simulation Abdi-Ranaldo reads -3% at a 2% spread, -13% at
    0.5%, +54% at 0.2% and +474% at 0.05%, and Corwin-Schultz is worse at every
    point. An earlier version of this docstring claimed the headline estimator
    recovered the truth to within about 1% and attributed the floor to CS alone;
    that was true only for wide spreads. CS is kept as a cross-check: when the
    two disagree sharply, neither should be trusted.

    `resolutionFloor` and `atFloor` exist so a caller can say "at or below X"
    instead of quoting a number the data cannot support.
    """
    corwin = corwin_schultz_spread(frame).tail(window).dropna()
    abdi = abdi_ranaldo_spread(frame).tail(window).dropna()

    cs = float(corwin.median()) if len(corwin) else None
    ar = float(abdi.median()) if len(abdi) else None

    disagreement = None
    if cs is not None and ar is not None and max(cs, ar) > 0:
        disagreement = abs(cs - ar) / max(cs, ar)

    primary = ar if ar is not None else cs
    floor = spread_resolution_floor(frame, window=window)
    at_floor = bool(primary is not None and floor is not None
                    and primary <= floor * FLOOR_TOLERANCE)

    return {
        "primary": primary,
        "primarySource": "Abdi-Ranaldo (2017)" if ar is not None else "Corwin-Schultz (2012)",
        "corwinSchultz": cs,
        "abdiRanaldo": ar,
        "disagreement": disagreement,
        "observations": int(min(len(corwin), len(abdi))),
        "resolutionFloor": floor,
        "atFloor": at_floor,
    }


# --------------------------------------------------------------------------- #
# Yang-Zhang volatility
# --------------------------------------------------------------------------- #
def yang_zhang_volatility(frame: pd.DataFrame, window: int = 21,
                          annualize: bool = True) -> pd.Series:
    """Rolling Yang-Zhang volatility.

    Close-to-close volatility throws away the high and the low, which is most of
    each day's information — Yang-Zhang is roughly an order of magnitude more
    efficient at typical window lengths, meaning far less estimation noise for
    the same amount of history.

    It is the sum of three components: overnight (close-to-open) variance,
    open-to-close variance, and the Rogers-Satchell drift-independent estimator,
    combined with the weight `k` that minimises total variance. Unlike
    Garman-Klass or Parkinson it handles BOTH opening gaps and a non-zero drift,
    which is why it is the right choice for equities that gap on news.
    """
    open_ = _positive(frame["Open"].astype("float64"))
    high = _positive(frame["High"].astype("float64"))
    low = _positive(frame["Low"].astype("float64"))
    close = _positive(frame["Close"].astype("float64"))

    log_oc_prev = np.log(open_ / close.shift(1))     # overnight jump
    log_co = np.log(close / open_)                   # the session itself
    log_ho = np.log(high / open_)
    log_lo = np.log(low / open_)

    min_periods = max(3, window // 2)
    var_overnight = log_oc_prev.rolling(window, min_periods=min_periods).var(ddof=1)
    var_session = log_co.rolling(window, min_periods=min_periods).var(ddof=1)
    rogers_satchell = (log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co))
    var_rs = rogers_satchell.rolling(window, min_periods=min_periods).mean()

    # Yang-Zhang's variance-minimising weight. It depends only on the window.
    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    variance = var_overnight + k * var_session + (1.0 - k) * var_rs

    volatility = np.sqrt(variance.clip(lower=0.0))
    return volatility * np.sqrt(TRADING_DAYS) if annualize else volatility


# --------------------------------------------------------------------------- #
# The caller-facing summary
# --------------------------------------------------------------------------- #
def liquidity_profile(frame: pd.DataFrame, window: int = 21) -> dict:
    """Everything the anomaly panel needs to caveat its own signal.

    `moveVsSpread` is the number that matters most: a day whose absolute return
    is only a small multiple of the estimated round-trip spread is inside the
    noise the market maker charges, however dramatic the RVOL looks.
    """
    illiq = amihud_illiquidity(frame, window=window).dropna()
    spreads = spread_summary(frame)
    volatility = yang_zhang_volatility(frame, window=window).dropna()

    spread_estimate = spreads["primary"]
    if spread_estimate is not None and not np.isfinite(spread_estimate):
        spread_estimate = None

    # The POINT ESTIMATE is Abdi-Ranaldo (lower bias). The WARNING below is
    # computed against the larger of the two estimators instead, deliberately.
    # This flag exists to say "that move may be spread noise", and the two error
    # directions are not symmetric: an unnecessary caveat costs the user a
    # second of attention, while a missing one lets them act on a signal that
    # cannot survive a round trip. Where AR reads exactly zero on a tight name,
    # taking the max also keeps the ratio defined instead of undefined.
    candidates = [s for s in (spreads["corwinSchultz"], spreads["abdiRanaldo"])
                  if s is not None and np.isfinite(s) and s > 0]
    warning_spread = max(candidates) if candidates else None

    # WHETHER THE WARNING SPREAD IS A MEASUREMENT AT ALL. Taking the larger of
    # the two estimators means taking Corwin-Schultz on almost every liquid
    # name, and its noise floor is 0.40 x daily volatility — about 0.55% on a
    # stock that moves 1.5% a day, when the true spread of a mega-cap is a basis
    # point or two. Comparing a day's move against a "spread" that is really
    # volatility in disguise made the app announce "this move is inside the
    # spread" on ordinary days, most confidently on exactly the names where it
    # was most wrong. When the estimate sits at its own floor, the honest
    # statement is that the cost could not be measured — not that it is large.
    sigma = _daily_sigma(frame)
    warning_floor = CS_FLOOR_RATIO * sigma if sigma else None
    spread_resolved = bool(
        warning_spread is not None and warning_floor is not None
        and warning_spread > warning_floor * FLOOR_TOLERANCE
    )

    close = frame["Close"].astype("float64")
    dollar_volume = (close * frame["Volume"].astype("float64")).tail(window)
    latest_move = abs(float(close.pct_change().iloc[-1])) if len(close) > 1 else None

    move_vs_spread = None
    if warning_spread and latest_move is not None:
        move_vs_spread = latest_move / warning_spread

    return {
        "amihud": float(illiq.iloc[-1]) if len(illiq) else None,
        "spread": spread_estimate,
        "warningSpread": warning_spread,
        "spreadDetail": spreads,
        "yangZhangVol": float(volatility.iloc[-1]) if len(volatility) else None,
        "medianDollarVolume": float(dollar_volume.median()) if len(dollar_volume) else None,
        "latestMove": latest_move,
        "moveVsSpread": move_vs_spread,
        # A single round trip costs the spread, so a move worth less than about
        # two spreads is not tradeable even if the model finds it interesting.
        "spreadResolved": spread_resolved,
        "warningFloor": warning_floor,
        # Only claim a move is inside the spread when the spread is a
        # measurement rather than the estimator's own noise floor.
        "insideSpreadNoise": bool(move_vs_spread is not None
                                  and move_vs_spread < 2.0 and spread_resolved),
        "window": window,
    }
