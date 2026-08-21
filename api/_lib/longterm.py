"""
longterm.py
===========
The analytics that actually decide a multi-year holding.

WHY THIS IS SEPARATE FROM indicators.py
---------------------------------------
Almost all classical technical analysis answers "should I buy this week?".
Someone holding for five years has different questions, and none of the
oscillators answer them:

  How much pain would I have had to sit through?   -> drawdown, time under water
  Would I actually have held on?                   -> Ulcer index, worst year
  Did it beat just owning the index?               -> relative strength, alpha
  What did I earn per unit of risk?                -> Sharpe, Sortino, Calmar
  If I'd bought at a random time, then what?       -> rolling-return distribution
  How bad is the left tail?                        -> VaR, CVaR, skew

Those are what this module computes. The single most useful of them is the
rolling-return distribution: it replaces "this returned 14% a year" — which
describes one lucky start date — with "across every 3-year window in this
history, the worst was -22% and the median was +31%".

MAXIMUM DRAWDOWN IS THE HONEST NUMBER
-------------------------------------
Backtests are won and lost on whether the investor could hold. A strategy
returning 15% a year through a 60% drawdown is, for almost everybody, a
strategy they sold at the bottom of. So drawdown here reports not just depth
but DURATION — time under water is what actually breaks conviction, and a
shallow four-year drawdown is harder to sit through than a sharp 30% one that
recovers in a quarter.

References
----------
Sharpe, W. F. (1966). "Mutual Fund Performance." Journal of Business 39(1).
Sortino, F., & Price, L. (1994). "Performance Measurement in a Downside Risk
    Framework." Journal of Investing 3(3).
Martin, P., & McCann, B. (1989). The Investor's Guide to Fidelity Funds.
    (Ulcer Index — depth AND duration of drawdown.)
Young, T. (1991). "Calmar Ratio: A Smoother Tool." Futures Magazine.
Moskowitz, T., Ooi, Y. H., & Pedersen, L. H. (2012). "Time series momentum."
    Journal of Financial Economics 104(2), 228-250.
Jegadeesh, N., & Titman, J. (1993). "Returns to Buying Winners and Selling
    Losers." Journal of Finance 48(1).
George, T., & Hwang, C. (2004). "The 52-Week High and Momentum Investing."
    Journal of Finance 59(5).
Faber, M. (2007). "A Quantitative Approach to Tactical Asset Allocation."
    Journal of Wealth Management 9(4). (The 10-month moving average rule.)
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

TRADING_DAYS = 252
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


# ============================================================================ #
# Drawdown
# ============================================================================ #
def drawdown_series(close: pd.Series) -> pd.Series:
    """Percentage below the running peak, at every point in the history."""
    peak = close.cummax()
    return close / peak - 1.0


def drawdown_profile(close: pd.Series) -> dict:
    """Depth, duration and recovery of the worst episodes.

    `timeUnderWaterDays` is the longest stretch spent below a previous peak.
    It is reported alongside depth because they break conviction differently:
    a 30% fall that recovers in four months is survivable, while a 15% one that
    grinds on for three years is where most people give up.
    """
    prices = close.dropna()
    if len(prices) < 3:
        return {"maxDrawdown": None, "currentDrawdown": None, "usable": False}

    peak = prices.cummax()
    drawdown = prices / peak - 1.0

    trough_date = drawdown.idxmin()
    max_drawdown = float(drawdown.min())
    peak_date = prices.loc[:trough_date].idxmax()

    # Recovery: the first date after the trough that regains the old peak.
    peak_value = float(prices.loc[peak_date])
    after = prices.loc[trough_date:]
    recovered = after[after >= peak_value]
    recovery_date = recovered.index[0] if len(recovered) else None

    # Longest continuous stretch below a previous high, anywhere in the record.
    under_water = drawdown < -1e-9
    longest, running = 0, 0
    for flag in under_water.to_numpy():
        running = running + 1 if flag else 0
        longest = max(longest, running)

    current = float(drawdown.iloc[-1])
    current_run = 0
    for flag in reversed(under_water.to_numpy()):
        if not flag:
            break
        current_run += 1

    # Ulcer index: RMS of the drawdown path, so a long shallow decline scores
    # worse than a brief deep one — which is the way it actually feels.
    ulcer = float(np.sqrt(np.mean((drawdown.to_numpy() * 100.0) ** 2)))

    return {
        "usable": True,
        "maxDrawdown": max_drawdown,
        "maxDrawdownPeak": peak_date.strftime("%Y-%m-%d"),
        "maxDrawdownTrough": trough_date.strftime("%Y-%m-%d"),
        "maxDrawdownRecovered": recovery_date.strftime("%Y-%m-%d") if recovery_date is not None else None,
        "maxDrawdownRecoveryDays": (int((recovery_date - trough_date).days)
                                    if recovery_date is not None else None),
        "currentDrawdown": current,
        "currentUnderWaterDays": int(current_run),
        "timeUnderWaterDays": int(longest),
        "ulcerIndex": ulcer,
        "series": [
            {"date": date.strftime("%Y-%m-%d"), "drawdown": float(value)}
            for date, value in drawdown.items()
        ],
    }


# ============================================================================ #
# Return and risk
# ============================================================================ #
def cagr(close: pd.Series) -> Optional[float]:
    prices = close.dropna()
    if len(prices) < 2:
        return None
    years = (prices.index[-1] - prices.index[0]).days / 365.25
    if years <= 0 or prices.iloc[0] <= 0:
        return None
    return float((prices.iloc[-1] / prices.iloc[0]) ** (1.0 / years) - 1.0)


def risk_metrics(close: pd.Series, risk_free: float = 0.0) -> dict:
    """Risk-adjusted performance, with the downside measures that matter more.

    Sharpe punishes upside volatility as heavily as downside, which is wrong for
    an investor — nobody minds their holding rising quickly. Sortino divides by
    downside deviation only. Calmar divides return by the worst drawdown, which
    for a long-horizon holder is the most decision-relevant ratio of the three.
    """
    prices = close.dropna()
    returns = prices.pct_change().dropna()
    if len(returns) < 20:
        return {"usable": False}

    annual_return = cagr(prices)
    volatility = float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS))

    downside = returns[returns < 0]
    downside_deviation = (float(downside.std(ddof=1) * np.sqrt(TRADING_DAYS))
                          if len(downside) > 1 else np.nan)

    excess = (annual_return - risk_free) if annual_return is not None else np.nan
    sharpe = excess / volatility if volatility > 0 and np.isfinite(excess) else np.nan
    sortino = (excess / downside_deviation
               if np.isfinite(downside_deviation) and downside_deviation > 0
               and np.isfinite(excess) else np.nan)

    profile = drawdown_profile(prices)
    max_drawdown = profile.get("maxDrawdown")
    calmar = (annual_return / abs(max_drawdown)
              if annual_return is not None and max_drawdown not in (None, 0) else np.nan)

    # Historical VaR / CVaR on daily returns — the left tail, not a normal
    # approximation of it, because equity returns are not normal.
    var_95 = float(np.percentile(returns, 5))
    tail = returns[returns <= var_95]
    cvar_95 = float(tail.mean()) if len(tail) else np.nan

    positive_days = float((returns > 0).mean())
    best_day = float(returns.max())
    worst_day = float(returns.min())

    return {
        "usable": True,
        "cagr": _finite(annual_return),
        "volatility": _finite(volatility),
        "downsideDeviation": _finite(downside_deviation),
        "sharpe": _finite(sharpe),
        "sortino": _finite(sortino),
        "calmar": _finite(calmar),
        "var95": _finite(var_95),
        "cvar95": _finite(cvar_95),
        "skew": _finite(returns.skew()),
        "kurtosis": _finite(returns.kurtosis()),
        "positiveDays": _finite(positive_days),
        "bestDay": _finite(best_day),
        "worstDay": _finite(worst_day),
        "riskFree": risk_free,
        "observations": len(returns),
    }


def rolling_returns(close: pd.Series, years: Sequence[int] = (1, 3, 5)) -> list[dict]:
    """Every N-year holding period in the history, summarised.

    THE MOST USEFUL SINGLE TABLE for a long-term investor, because it answers
    the question a headline CAGR quietly dodges: not "what did this return?" but
    "what would I have earned buying at a RANDOM moment and holding N years?".
    The worst case in that distribution is the number that decides position
    size, and it is invisible in any single-path backtest.
    """
    prices = close.dropna()
    out = []
    for horizon in years:
        window = int(horizon * TRADING_DAYS)
        if len(prices) < window + 20:
            continue
        ratio = prices / prices.shift(window)
        annualised = (ratio ** (1.0 / horizon) - 1.0).dropna()
        if annualised.empty:
            continue
        out.append({
            "years": horizon,
            "windows": len(annualised),
            "best": float(annualised.max()),
            "worst": float(annualised.min()),
            "median": float(annualised.median()),
            "mean": float(annualised.mean()),
            "positiveShare": float((annualised > 0).mean()),
            "p25": float(annualised.quantile(0.25)),
            "p75": float(annualised.quantile(0.75)),
        })
    return out


def calendar_returns(close: pd.Series, limit: int = 12) -> list[dict]:
    """Year-by-year total return — the plainest possible history."""
    prices = close.dropna()
    if prices.empty:
        return []
    yearly = prices.resample("YE").last()
    first = prices.iloc[0]
    out = []
    previous = first
    for date, value in yearly.items():
        out.append({"year": int(date.year),
                    "return": float(value / previous - 1.0) if previous else None})
        previous = value
    return out[-limit:]


def monthly_seasonality(close: pd.Series) -> dict:
    """Average return by calendar month.

    DESCRIPTIVE ONLY, and labelled as such wherever it is shown. Calendar
    effects are the single most over-mined corner of finance: with twelve
    months, one will always look best, and Harvey, Liu & Zhu (2016) is a long
    argument about why that number is not a finding. This is here so a reader
    can see the shape of the history, not so anyone trades January.
    """
    prices = close.dropna()
    if len(prices) < TRADING_DAYS:
        return {"usable": False, "months": []}

    monthly = prices.resample("ME").last().pct_change().dropna()
    if monthly.empty:
        return {"usable": False, "months": []}

    grouped = monthly.groupby(monthly.index.month)
    months = []
    for number in range(1, 13):
        if number not in grouped.groups:
            months.append({"month": MONTHS[number - 1], "mean": None, "count": 0,
                           "positiveShare": None})
            continue
        values = grouped.get_group(number)
        months.append({
            "month": MONTHS[number - 1],
            "mean": float(values.mean()),
            "median": float(values.median()),
            "count": len(values),
            "positiveShare": float((values > 0).mean()),
        })
    return {
        "usable": True,
        "months": months,
        "yearsCovered": float(len(monthly) / 12.0),
        "caveat": ("Descriptive history, not a signal. With twelve months one will "
                   "always look best by chance; calendar effects are the most "
                   "data-mined corner of finance."),
    }


# ============================================================================ #
# Momentum and position
# ============================================================================ #
def time_series_momentum(close: pd.Series) -> dict:
    """Trailing returns over the horizons the momentum literature uses.

    `momentum12_1` skips the most recent month. That is not a quirk: short-term
    reversal contaminates the last few weeks, so Jegadeesh & Titman (1993) and
    everyone since measure 12 months ending one month ago. Reporting plain
    12-month return as "momentum" quietly mixes two opposing effects.
    """
    prices = close.dropna()
    result: dict = {}
    for label, days in (("1m", 21), ("3m", 63), ("6m", 126),
                        ("12m", 252), ("36m", 756)):
        result[label] = (float(prices.iloc[-1] / prices.iloc[-1 - days] - 1.0)
                         if len(prices) > days else None)

    if len(prices) > 252:
        result["momentum12_1"] = float(prices.iloc[-22] / prices.iloc[-253] - 1.0)
    else:
        result["momentum12_1"] = None

    twelve = result.get("12m")
    result["trendFollowingSignal"] = (
        None if twelve is None else ("long" if twelve > 0 else "flat")
    )
    return result


def price_position(close: pd.Series, high: pd.Series, low: pd.Series) -> dict:
    """Where the price sits against its 52-week range and its all-time high.

    The distance from the 52-week high is a documented momentum variable in its
    own right (George & Hwang 2004), and the drawdown from the all-time high is
    the number a long-term holder feels most directly.
    """
    prices = close.dropna()
    if prices.empty:
        return {"usable": False}

    latest = float(prices.iloc[-1])
    window = min(len(prices), TRADING_DAYS)
    year_high = float(high.dropna().tail(window).max())
    year_low = float(low.dropna().tail(window).min())
    span = year_high - year_low

    all_time_high = float(prices.cummax().iloc[-1])
    all_time_low = float(prices.min())

    return {
        "usable": True,
        "price": latest,
        "high52w": year_high,
        "low52w": year_low,
        "rangePosition": float((latest - year_low) / span) if span > 0 else None,
        "fromHigh52w": float(latest / year_high - 1.0) if year_high else None,
        "fromLow52w": float(latest / year_low - 1.0) if year_low else None,
        "allTimeHigh": all_time_high,
        "fromAllTimeHigh": float(latest / all_time_high - 1.0) if all_time_high else None,
        "allTimeLow": all_time_low,
        "windowDays": int(window),
    }


def faber_timing(close: pd.Series) -> dict:
    """Faber's (2007) 10-month moving average rule, on monthly closes.

    The simplest published long-horizon timing rule there is: hold while the
    monthly close is above its 10-month average, stand aside below. It trades a
    couple of times a year at most and its documented value is not higher
    returns but SHALLOWER DRAWDOWNS — which is the variable that decides whether
    a long-term holder stays invested at all.
    """
    prices = close.dropna()
    if len(prices) < TRADING_DAYS:
        return {"usable": False}

    monthly = prices.resample("ME").last().dropna()
    if len(monthly) < 11:
        return {"usable": False}

    average = monthly.rolling(10, min_periods=10).mean()
    above = monthly > average
    valid = above[average.notna()]
    if valid.empty:
        return {"usable": False}

    # How long the current stance has held.
    stance = bool(valid.iloc[-1])
    months_in_stance = 0
    for flag in reversed(valid.to_numpy()):
        if bool(flag) != stance:
            break
        months_in_stance += 1

    return {
        "usable": True,
        "signal": "invested" if stance else "defensive",
        "monthlyClose": float(monthly.iloc[-1]),
        "movingAverage": float(average.iloc[-1]),
        "distance": float(monthly.iloc[-1] / average.iloc[-1] - 1.0),
        "monthsInStance": int(months_in_stance),
        "monthsObserved": len(valid),
        "sharOfTimeInvested": float(valid.mean()),
    }


# ============================================================================ #
# Relative strength
# ============================================================================ #
def relative_strength(close: pd.Series, benchmark: pd.Series,
                      benchmark_symbol: str = "") -> dict:
    """Performance against the index, which is the real alternative.

    A long-term investor's counterfactual is never cash — it is the index fund
    they could have bought instead. A stock up 40% over three years while the
    market rose 60% has cost its holder money in the only sense that matters.

    `ratioTrend` is the slope of the price-relative line: positive means the
    stock has been gaining on the index recently, whatever either did outright.
    """
    prices = close.dropna()
    index = benchmark.dropna()
    if prices.empty or index.empty:
        return {"usable": False, "benchmark": benchmark_symbol}

    joined = pd.concat([prices, index], axis=1, join="inner").dropna()
    joined.columns = ["stock", "benchmark"]
    if len(joined) < 60:
        return {"usable": False, "benchmark": benchmark_symbol}

    ratio = joined["stock"] / joined["benchmark"]
    normalised = ratio / ratio.iloc[0]

    periods = {}
    for label, days in (("3m", 63), ("6m", 126), ("12m", 252), ("36m", 756)):
        if len(joined) > days:
            stock_return = float(joined["stock"].iloc[-1] / joined["stock"].iloc[-1 - days] - 1)
            index_return = float(joined["benchmark"].iloc[-1] / joined["benchmark"].iloc[-1 - days] - 1)
            periods[label] = {"stock": stock_return, "benchmark": index_return,
                              "excess": stock_return - index_return}
        else:
            periods[label] = None

    recent = normalised.tail(min(len(normalised), TRADING_DAYS))
    x = np.arange(len(recent), dtype=float)
    slope = float(np.polyfit(x, recent.to_numpy(), 1)[0]) if len(recent) > 10 else np.nan

    stock_returns = joined["stock"].pct_change().dropna()
    index_returns = joined["benchmark"].pct_change().dropna()
    correlation = float(stock_returns.corr(index_returns))

    return {
        "usable": True,
        "benchmark": benchmark_symbol,
        "periods": periods,
        "ratioTrend": _finite(slope),
        "outperforming": bool(np.isfinite(slope) and slope > 0),
        "correlation": _finite(correlation),
        "series": [
            {"date": date.strftime("%Y-%m-%d"), "ratio": float(value)}
            for date, value in normalised.resample("W").last().dropna().items()
        ],
    }
