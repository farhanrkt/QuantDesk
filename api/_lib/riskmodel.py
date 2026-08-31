"""
riskmodel.py
============
Estimating the parameters the valuation engine currently guesses.

TWO ARBITRARY CONSTANTS, REPLACED
---------------------------------
1. `clip_beta` pinned beta into [0.4, 2.5]. That clip is doing the right JOB —
   raw betas are noisy and extreme values are usually estimation error rather
   than real risk — but it does it with a hard edge applied identically to a
   mega-cap with a precise estimate and an IDX small cap whose beta is barely
   distinguishable from noise. Blume (1971) and Vasicek (1973) solve exactly
   this, and Vasicek solves it properly: shrink toward the cross-sectional mean
   IN PROPORTION TO how imprecise each individual estimate is.

   Bloomberg's famous "adjusted beta" (2/3 x raw + 1/3 x 1.0) is Blume's rule.

2. `sd_growth = 0.02` in the Monte Carlo. This number drives the entire width of
   the valuation fan chart and it came from nowhere. `shrunk_growth_volatility`
   estimates it from the company's OWN cash-flow history, then shrinks it hard
   toward a cross-sectional prior — because four annual filings give three
   growth observations, which is far too few to trust on their own. The result
   is not precise. It is, unlike a flat 2%, anchored to something.

WHERE BETA COMES FROM
---------------------
Not `yfinance.info["beta"]`, which is an opaque number computed against an
undisclosed index over an undisclosed window. This regresses the stock on its
own market's index (^GSPC for US, ^JKSE for IDX) over a stated window and
reports the standard error and R² alongside, so the user can see how much the
estimate is worth.

References
----------
Blume, M. E. (1971). "On the Assessment of Risk." Journal of Finance 26(1).
Vasicek, O. A. (1973). "A Note on Using Cross-Sectional Information in Bayesian
    Estimation of Security Betas." Journal of Finance 28(5), 1233-1239.
Sharpe, W. F. (1964). "Capital Asset Prices." Journal of Finance 19(3).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from . import market_data

MARKET_INDEX = {"US": "^GSPC", "ID": "^JKSE"}

# Cross-sectional prior for beta. Mean 1.0 is the market by definition; the
# dispersion is the width of the cross-section of true betas, NOT of estimated
# ones (estimates are wider because they carry noise). 0.5 is a conventional
# working value for developed equities and is deliberately not tuned to fit.
PRIOR_BETA_MEAN = 1.0
PRIOR_BETA_SD = 0.5

# Prior for the Monte Carlo growth sigma. Note carefully what this is the
# dispersion OF: not one year's growth rate, but the SUSTAINED rate applied
# across the whole projection horizon (see `shrunk_growth_volatility`). Those
# are different quantities and the second is much smaller. 5% is a wide but not
# absurd prior on how wrong a five-year average growth assumption can be.
PRIOR_GROWTH_SD = 0.05
PRIOR_GROWTH_WEIGHT = 8.0    # in units of "pseudo-observations"

# The projection horizon the drawn growth rate is applied over. Kept in step
# with valuation.PROJECTION_YEARS; imported there rather than here to avoid a
# circular import.
GROWTH_HORIZON = 5

_INDEX_CACHE: dict[tuple[str, str, str], pd.Series] = {}


@dataclass
class BetaEstimate:
    """A beta with its own error bars attached, because they matter here."""

    raw: float
    adjusted: float
    stderr: float
    r_squared: float
    observations: int
    method: str
    index_symbol: str
    prior_weight: float          # 0 = all data, 1 = all prior
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "raw": _finite(self.raw),
            "adjusted": _finite(self.adjusted),
            "stderr": _finite(self.stderr),
            "rSquared": _finite(self.r_squared),
            "observations": int(self.observations),
            "method": self.method,
            "indexSymbol": self.index_symbol,
            "priorWeight": _finite(self.prior_weight),
            "notes": list(self.notes),
        }


def effective_independent(matrix) -> Optional[float]:
    """How many genuinely independent things a correlation matrix describes.

        effective N = (sum of eigenvalues)^2 / sum(eigenvalues^2)

    The participation ratio. It equals the column count when everything is
    independent and collapses toward 1 as the columns become redundant, so it
    answers a question a count cannot: seven ranking signals that correlate at
    0.98 are one signal wearing seven labels, and nine holdings that all track
    the same index are close to one position.

    ONE IMPLEMENTATION, TWO CALLERS, and that is why it lives here rather than
    inside either. `ranking.signal_correlation` uses it to say how many opinions
    a composite is really averaging; `portfolio.py` uses the identical
    arithmetic to say how many independent bets a set of holdings really is. A
    second copy would eventually disagree with the first about what redundancy
    means, in an app whose whole argument is that agreement between correlated
    measures is worth less than it looks.
    """
    try:
        values = np.asarray(matrix, dtype="float64")
    except (TypeError, ValueError):
        return None
    # A NON-FINITE ENTRY MUST BE REFUSED HERE, NOT FILTERED LATER. `eigvalsh`
    # reads only one triangle, so a matrix with NaN on the diagonal returns
    # perfectly finite eigenvalues computed from the half it happened to look
    # at — a plausible number from an unusable matrix, which is the failure
    # shape this codebase keeps finding. Caught by a test that fed it exactly
    # that.
    if values.ndim != 2 or values.shape[0] != values.shape[1] or values.size == 0:
        return None
    if not np.all(np.isfinite(values)):
        return None
    try:
        eigenvalues = np.linalg.eigvalsh(values)
    except np.linalg.LinAlgError:
        return None
    eigenvalues = np.clip(eigenvalues[np.isfinite(eigenvalues)], 0.0, None)
    denominator = float(np.sum(eigenvalues ** 2))
    if denominator <= 0:
        return None
    return float(np.sum(eigenvalues) ** 2 / denominator)


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


# --------------------------------------------------------------------------- #
# Shrinkage rules
# --------------------------------------------------------------------------- #
def blume_adjust(beta: float) -> float:
    """Blume (1971): betas regress toward 1 over time, so shrink toward it.

    The coefficients are Blume's own empirical estimates. This is the rule
    Bloomberg ships as "adjusted beta". It applies the SAME shrinkage to every
    stock regardless of estimate quality, which is its weakness relative to
    Vasicek and the reason it is offered here only as a fallback.
    """
    value = _finite(beta)
    if value is None:
        return PRIOR_BETA_MEAN
    return 0.343 + 0.677 * value


def vasicek_adjust(beta: float, stderr: float,
                   prior_mean: float = PRIOR_BETA_MEAN,
                   prior_sd: float = PRIOR_BETA_SD) -> tuple[float, float]:
    """Vasicek (1973): precision-weighted shrinkage toward the cross-section.

    Returns `(adjusted_beta, prior_weight)`.

    The weight on the prior is the estimate's own variance divided by the total,
    so a precisely measured beta barely moves and a noisy one collapses toward
    the market. This is the whole reason to prefer it here: an IDX small cap
    with thin trading produces a beta whose standard error can exceed 0.5, and
    treating that number as equal in standing to AAPL's is the error the old
    fixed clip made.
    """
    value = _finite(beta)
    error = _finite(stderr)
    if value is None:
        return prior_mean, 1.0
    if error is None or error <= 0:
        return value, 0.0

    prior_var = prior_sd ** 2
    estimate_var = error ** 2
    prior_weight = estimate_var / (estimate_var + prior_var)
    adjusted = (1.0 - prior_weight) * value + prior_weight * prior_mean
    return adjusted, prior_weight


# --------------------------------------------------------------------------- #
# Beta estimation
# --------------------------------------------------------------------------- #
def _index_returns(market_code: str, period: str = "2y") -> Optional[pd.Series]:
    """Daily log-ish simple returns for the market index, cached for the day."""
    symbol = MARKET_INDEX.get((market_code or "US").upper(), MARKET_INDEX["US"])
    key = (symbol, period, dt.date.today().isoformat())
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    history = market_data.index_history(symbol, period)
    if history is None or "Close" not in history:
        return None

    close = history["Close"].dropna()
    returns = close.pct_change(fill_method=None).dropna()
    returns.index = pd.to_datetime(returns.index).normalize()

    _INDEX_CACHE.clear()          # only ever hold the current day
    _INDEX_CACHE[key] = returns
    return returns


def ols_beta(stock: np.ndarray, market: np.ndarray) -> tuple[float, float, float]:
    """Plain OLS slope with its standard error and R².

    Written out rather than pulled from statsmodels: three lines of algebra do
    not justify a dependency in a serverless bundle, and the standard error is
    the part that actually matters downstream.
    """
    n = len(stock)
    if n < 3:
        return np.nan, np.nan, np.nan

    market_centred = market - market.mean()
    stock_centred = stock - stock.mean()
    sxx = float(np.sum(market_centred ** 2))
    if sxx <= 0:
        return np.nan, np.nan, np.nan

    beta = float(np.sum(market_centred * stock_centred) / sxx)
    residuals = stock_centred - beta * market_centred
    dof = n - 2
    residual_var = float(np.sum(residuals ** 2) / dof) if dof > 0 else np.nan
    stderr = float(np.sqrt(residual_var / sxx)) if np.isfinite(residual_var) else np.nan

    total_var = float(np.sum(stock_centred ** 2))
    r_squared = float(1.0 - np.sum(residuals ** 2) / total_var) if total_var > 0 else np.nan
    return beta, stderr, r_squared


_HISTORY_CACHE: dict[tuple[str, str, str], pd.DataFrame] = {}


def estimate_beta_for_symbol(symbol: str, market_code: str = "US", period: str = "2y",
                             fallback_beta: Optional[float] = None) -> BetaEstimate:
    """`estimate_beta`, fetching the stock's own history and caching it for the day.

    The valuation engine has no OHLCV frame of its own — it reads statements, not
    prices — so beta estimation needs one fetch. Caching by (symbol, period, day)
    keeps a screener run or a series of assumption refinements on the same ticker
    from paying for it repeatedly.
    """
    key = (symbol.upper(), period, dt.date.today().isoformat())
    history = _HISTORY_CACHE.get(key)
    if history is None:
        # OPT-OUT 2 OF 4, and the same reason as the other three: this is the
        # reader's own ticker. A stale beta is a real cost, but it is carried by
        # a stated window and a reported R-squared, whereas refusing here would
        # send a suspended name down the Blume fallback with a note blaming the
        # INDEX for a gap in the stock's own history.
        history = market_data.ohlcv(symbol, period=period, allow_stale=True)
        if history is None:
            return estimate_beta(pd.DataFrame(), market_code, period, fallback_beta)
        if len(_HISTORY_CACHE) > 256:
            _HISTORY_CACHE.clear()
        _HISTORY_CACHE[key] = history
    return estimate_beta(history, market_code, period, fallback_beta)


def estimate_beta(price_history: pd.DataFrame, market_code: str = "US",
                  period: str = "2y", fallback_beta: Optional[float] = None) -> BetaEstimate:
    """Regress the stock on its own market index, then shrink Vasicek-style.

    `price_history` is the OHLCV frame an engine has already fetched, so this
    costs one extra network call for the index — cached for the day and shared
    across every ticker in a screener run.
    """
    index_symbol = MARKET_INDEX.get((market_code or "US").upper(), MARKET_INDEX["US"])
    notes: list = []

    market_returns = _index_returns(market_code, period)
    if market_returns is None or price_history is None or price_history.empty:
        adjusted = blume_adjust(fallback_beta)
        notes.append("Index history unavailable; fell back to Yahoo's beta with Blume shrinkage.")
        return BetaEstimate(
            raw=_finite(fallback_beta) or np.nan, adjusted=adjusted, stderr=np.nan,
            r_squared=np.nan, observations=0, method="blume-fallback",
            index_symbol=index_symbol, prior_weight=np.nan, notes=notes,
        )

    close = price_history["Close"].astype("float64").dropna()
    if getattr(close.index, "tz", None) is not None:
        close.index = close.index.tz_localize(None)
    stock_returns = close.pct_change(fill_method=None).dropna()
    stock_returns.index = pd.to_datetime(stock_returns.index).normalize()

    paired = pd.concat([stock_returns, market_returns], axis=1, join="inner").dropna()
    paired.columns = ["stock", "market"]

    if len(paired) < 30:
        adjusted = blume_adjust(fallback_beta)
        notes.append(
            f"Only {len(paired)} overlapping trading days with {index_symbol}; "
            "too few to regress, so Yahoo's beta was used with Blume shrinkage."
        )
        return BetaEstimate(
            raw=_finite(fallback_beta) or np.nan, adjusted=adjusted, stderr=np.nan,
            r_squared=np.nan, observations=len(paired), method="blume-fallback",
            index_symbol=index_symbol, prior_weight=np.nan, notes=notes,
        )

    raw, stderr, r_squared = ols_beta(paired["stock"].to_numpy(),
                                      paired["market"].to_numpy())
    adjusted, prior_weight = vasicek_adjust(raw, stderr)

    if np.isfinite(prior_weight) and prior_weight > 0.5:
        notes.append(
            f"Beta is imprecisely measured (se {stderr:.2f}), so it is shrunk "
            f"{prior_weight:.0%} of the way toward the market's 1.0."
        )
    if np.isfinite(r_squared) and r_squared < 0.05:
        notes.append(
            f"Only {r_squared:.1%} of this stock's daily moves are explained by "
            f"{index_symbol}; a single-factor cost of equity is weak here."
        )

    return BetaEstimate(
        raw=raw, adjusted=adjusted, stderr=stderr, r_squared=r_squared,
        observations=len(paired), method="vasicek", index_symbol=index_symbol,
        prior_weight=prior_weight, notes=notes,
    )


# --------------------------------------------------------------------------- #
# Monte Carlo dispersion
# --------------------------------------------------------------------------- #
def shrunk_growth_volatility(values, prior_sd: float = PRIOR_GROWTH_SD,
                             prior_weight: float = PRIOR_GROWTH_WEIGHT,
                             horizon: int = GROWTH_HORIZON) -> dict:
    """Dispersion of the SUSTAINED growth rate, from a short history, shrunk.

    WHAT IS BEING ESTIMATED, because getting this wrong inflates the fan chart
    by an order of magnitude. The Monte Carlo draws ONE growth rate and applies
    it to all `horizon` years. So the quantity that needs a standard deviation
    is the average growth over the horizon — NOT the year-to-year scatter of
    past growth, which is much larger. Feeding raw annual dispersion in produces
    a P5-P95 price range spanning more than a factor of ten, which is not
    honesty about uncertainty, it is a units error.

    Given annual growth rates modelled as iid draws with standard deviation s,
    the predictive standard deviation of the horizon average has two parts:

        parameter uncertainty about the mean   s^2 / n
        realisation scatter around that mean   s^2 / horizon

        predictive_sd = s * sqrt(1/n + 1/horizon)

    That is then blended with the prior in variance units:

        sd = sqrt( (n*predictive_var + w*prior_var) / (n + w) )

    so a company needs a long, stable record before its own history outweighs
    the prior — four filings give three growth observations, which do not.

    Sign changes are dropped rather than propagated: free cash flow crossing
    zero produces growth rates of thousands of percent, which would swamp any
    dispersion estimate. The count of dropped observations is reported.
    """
    series = pd.Series(list(values), dtype="float64").dropna()
    usable, skipped = [], 0

    for previous, current in zip(series.iloc[:-1], series.iloc[1:], strict=True):
        if not np.isfinite(previous) or not np.isfinite(current) or previous == 0:
            skipped += 1
            continue
        if previous <= 0 or current <= 0:
            # A sign change makes percentage growth meaningless.
            skipped += 1
            continue
        usable.append(current / previous - 1.0)

    n = len(usable)
    sample_sd = float(np.std(usable, ddof=1)) if n >= 2 else np.nan

    if n >= 2 and np.isfinite(sample_sd):
        predictive_sd = sample_sd * np.sqrt(1.0 / n + 1.0 / max(1, horizon))
        blended_var = ((n * predictive_sd ** 2 + prior_weight * prior_sd ** 2)
                       / (n + prior_weight))
        weight_on_prior = prior_weight / (n + prior_weight)
    else:
        predictive_sd = np.nan
        blended_var = prior_sd ** 2
        weight_on_prior = 1.0

    return {
        "sd": float(np.sqrt(blended_var)),
        # The per-year scatter, reported because it is what a reader expects to
        # see and would otherwise wonder about — but NOT what `sd` is.
        "sampleSd": _finite(sample_sd),
        "predictiveSd": _finite(predictive_sd),
        "horizon": int(horizon),
        "observations": n,
        "skipped": skipped,
        "priorSd": prior_sd,
        "priorWeight": float(weight_on_prior),
        "source": "history+prior" if n >= 2 else "prior only",
    }
