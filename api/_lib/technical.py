"""
technical.py
============
Engine 2 — QuantDash technical analysis, extracted from the Streamlit app.

EXTRACTION NOTE (read this before you touch anything)
-----------------------------------------------------
Every threshold, window, weighting and branch below is transcribed verbatim
from the original `app.py`. What was removed is presentation only:
`st.*` calls, Plotly figure construction and CSS.

ONE DELIBERATE DEVIATION, declared up front:
`pandas_ta` is NOT a dependency here. The original imported it inside a
try/except and fell back to hand-rolled indicators when it was missing; this
build always takes the fallback path. Reasons: pandas-ta is ~40 MB of bundle
for four functions, and its import-time numpy probing is fragile on serverless
Python. The fallback formulas are the standard definitions and agree with
pandas-ta to floating-point noise for SMA, RSI (Wilder) and MACD.

The single genuine numerical difference is Bollinger standard deviation:
pandas-ta's `bbands` defaults to ddof=0 (population), the fallback uses
ddof=1 (sample). BB_DDOF below preserves the original fallback's ddof=1.
Set it to 0 if you want to match a pandas-ta-installed run of the old app.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.signal import argrelextrema

from . import explain as ex
from . import indicators as ind
from . import swing
from . import longterm as lt
from . import riskmodel
from .valuation import MARKETS

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "IDR": "Rp", "AUD": "A$"}

# A long-term investor cannot be served by a five-year maximum. Drawdown depth,
# rolling multi-year returns and Coppock all need a decade or more before they
# say anything — a "worst 3-year window" computed from five years of history is
# one and a half observations wearing a statistic's clothes.
RANGE_PRESETS = {
    "3mo": 91,
    "6mo": 182,
    "1y": 365,
    "2y": 730,
    "5y": 1826,
    "10y": 3652,
    "max": 36525,        # ~100 years; yfinance returns whatever exists
}

# Below this many bars the long-horizon section is withheld rather than
# computed from too little data.
MIN_LONGTERM_BARS = 252

# Windows that need a full year of history to mean anything.
DONCHIAN_WINDOW = 252
REGRESSION_WINDOW = 252

BB_DDOF = 1  # see EXTRACTION NOTE


class TechnicalError(Exception):
    """Raised when a ticker yields no usable price history."""


# --------------------------------------------------------------------------- #
# Indicators (verbatim fallback implementations)
# --------------------------------------------------------------------------- #
def _sma(close: pd.Series, length: int) -> pd.Series:
    return close.rolling(window=length, min_periods=length).mean()


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.where(avg_loss != 0.0, 100.0).where(avg_gain.notna())


def _bbands(close: pd.Series, length: int = 20, std: float = 2.0) -> tuple:
    middle = close.rolling(window=length, min_periods=length).mean()
    deviation = close.rolling(window=length, min_periods=length).std(ddof=BB_DDOF)
    return middle - std * deviation, middle, middle + std * deviation


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    ema_fast = close.ewm(span=fast, min_periods=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, min_periods=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    signal_line = line.ewm(span=signal, min_periods=signal, adjust=False).mean()
    return line, signal_line, line - signal_line


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def _flatten_columns(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if not isinstance(frame.columns, pd.MultiIndex):
        return frame
    target = ticker.upper()
    for level in range(frame.columns.nlevels):
        values = {str(value).upper() for value in frame.columns.get_level_values(level)}
        if target in values:
            return frame.droplevel(level, axis=1)
    frame = frame.copy()
    frame.columns = frame.columns.get_level_values(0)
    return frame


def fetch_data(ticker: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    symbol = ticker.strip().upper()
    if not symbol:
        return pd.DataFrame()
    try:
        raw = yf.download(
            symbol,
            start=start,
            end=end + dt.timedelta(days=1),
            interval="1d",
            auto_adjust=True,
            actions=False,
            progress=False,
            threads=False,
        )
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()

    frame = _flatten_columns(raw, symbol)
    available = [column for column in OHLCV_COLUMNS if column in frame.columns]
    if not {"Open", "High", "Low", "Close"}.issubset(set(available)):
        return pd.DataFrame()

    frame = frame.loc[:, available].copy()
    frame.index = pd.to_datetime(frame.index)
    if getattr(frame.index, "tz", None) is not None:
        frame.index = frame.index.tz_localize(None)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()

    for column in available:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "Volume" not in frame.columns:
        frame["Volume"] = 0.0

    frame[["Open", "High", "Low", "Close"]] = frame[["Open", "High", "Low", "Close"]].ffill()
    frame["Volume"] = frame["Volume"].fillna(0.0)
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    frame = frame[frame["Close"] > 0]
    frame.index.name = "Date"
    return frame


def fetch_currency(ticker: str) -> str:
    try:
        fast_info = yf.Ticker(ticker).fast_info
        currency = fast_info["currency"] if "currency" in fast_info else None
        if isinstance(currency, str) and currency:
            return currency.upper()
    except Exception:
        return "USD"
    return "USD"


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Every indicator, on one frame.

    The originals (SMA 50/200, RSI, MACD, Bollinger) keep their exact previous
    definitions so nothing that was correct before has moved. Everything added
    comes from `_lib/indicators.py`, where each formula is checked against an
    independently written reference.
    """
    frame = df.copy()
    close = frame["Close"].astype("float64")

    # This used to run on Close alone, and callers exist that still hand it a
    # close-only frame — a moving-average crossover needs nothing else. Rather
    # than raising KeyError on the first range-based indicator, treat a missing
    # high or low as equal to the close: the range-based indicators then report
    # a zero range, which is the honest answer for a series that has no
    # intraday information rather than a fabricated one.
    high = (frame["High"] if "High" in frame else close).astype("float64")
    low = (frame["Low"] if "Low" in frame else close).astype("float64")
    volume = ((frame["Volume"] if "Volume" in frame else pd.Series(0.0, index=frame.index))
              .astype("float64"))

    # --- trend: the long-horizon averages first ---------------------------
    frame["SMA_20"] = _sma(close, 20)
    frame["SMA_50"] = _sma(close, 50)
    frame["SMA_100"] = _sma(close, 100)
    frame["SMA_200"] = _sma(close, 200)
    frame["EMA_21"] = ind.ema(close, 21)
    frame["EMA_50"] = ind.ema(close, 50)

    # --- bands ------------------------------------------------------------
    lower, middle, upper = _bbands(close, 20, 2.0)
    frame["BB_LOWER"], frame["BB_MID"], frame["BB_UPPER"] = lower, middle, upper
    frame["BB_PERCENT_B"] = ind.bollinger_percent_b(close, lower, upper)
    frame["BB_BANDWIDTH"] = ind.bollinger_bandwidth(lower, middle, upper)

    k_lower, k_mid, k_upper = ind.keltner_channels(high, low, close)
    frame["KC_LOWER"], frame["KC_MID"], frame["KC_UPPER"] = k_lower, k_mid, k_upper

    d_lower, d_mid, d_upper = ind.donchian_channels(high, low, DONCHIAN_WINDOW)
    frame["DC_LOWER"], frame["DC_MID"], frame["DC_UPPER"] = d_lower, d_mid, d_upper

    # --- momentum ---------------------------------------------------------
    frame["RSI"] = _rsi(close, 14)
    macd_line, macd_signal, macd_hist = _macd(close, 12, 26, 9)
    frame["MACD"], frame["MACD_SIGNAL"], frame["MACD_HIST"] = macd_line, macd_signal, macd_hist
    stoch_k, stoch_d = ind.stochastic(high, low, close)
    frame["STOCH_K"], frame["STOCH_D"] = stoch_k, stoch_d
    frame["WILLIAMS_R"] = ind.williams_r(high, low, close)
    frame["CCI"] = ind.cci(high, low, close)
    frame["ROC_63"] = ind.roc(close, 63)
    frame["ROC_252"] = ind.roc(close, 252)

    # --- trend strength ---------------------------------------------------
    adx_value, plus_di, minus_di = ind.adx(high, low, close)
    frame["ADX"], frame["PLUS_DI"], frame["MINUS_DI"] = adx_value, plus_di, minus_di
    aroon_up, aroon_down, aroon_osc = ind.aroon(high, low)
    frame["AROON_UP"], frame["AROON_DOWN"], frame["AROON_OSC"] = aroon_up, aroon_down, aroon_osc

    conversion, base, span_a, span_b, lagging = ind.ichimoku(high, low, close)
    frame["ICHI_CONVERSION"], frame["ICHI_BASE"] = conversion, base
    frame["ICHI_SPAN_A"], frame["ICHI_SPAN_B"] = span_a, span_b
    frame["ICHI_LAGGING"] = lagging

    # --- volatility -------------------------------------------------------
    frame["ATR"] = ind.atr(high, low, close)
    frame["ATR_PCT"] = frame["ATR"] / close.replace(0.0, np.nan)

    # --- volume -----------------------------------------------------------
    frame["OBV"] = ind.on_balance_volume(close, volume)
    frame["AD_LINE"] = ind.accumulation_distribution(high, low, close, volume)
    frame["CMF"] = ind.chaikin_money_flow(high, low, close, volume)
    frame["MFI"] = ind.money_flow_index(high, low, close, volume)
    frame["VOLUME_TREND"] = ind.volume_trend(volume)

    # --- drawdown, carried on the frame so the chart can show it ----------
    frame["DRAWDOWN"] = lt.drawdown_series(close)
    return frame


def calculate_support_resistance(
    df: pd.DataFrame,
    window: int = 10,
    max_levels: int = 6,
) -> list:
    if df.empty or len(df) < (2 * window + 1):
        return []

    highs = df["High"].to_numpy(dtype="float64")
    lows = df["Low"].to_numpy(dtype="float64")
    peak_positions = argrelextrema(highs, np.greater_equal, order=window)[0]
    trough_positions = argrelextrema(lows, np.less_equal, order=window)[0]
    candidates = np.concatenate([highs[peak_positions], lows[trough_positions]])
    candidates = candidates[np.isfinite(candidates)]
    if candidates.size == 0:
        return []

    last_price = float(df["Close"].iloc[-1])
    tolerance = float(np.nanmean(highs - lows))
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        tolerance = abs(last_price) * 0.005

    clusters: list = []
    for value in np.sort(candidates):
        if clusters and (value - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(float(value))
        else:
            clusters.append([float(value)])

    ranked = sorted(
        clusters,
        key=lambda group: (len(group), -abs(float(np.mean(group)) - last_price)),
        reverse=True,
    )
    levels = [round(float(np.mean(group)), 6) for group in ranked[:max_levels]]
    return sorted(levels)


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    frame["Signal"] = ""
    if "SMA_50" not in frame.columns or "SMA_200" not in frame.columns:
        return frame

    fast = frame["SMA_50"]
    slow = frame["SMA_200"]
    valid = fast.notna() & slow.notna()
    # `fill_value=` rather than `.fillna()`: shifting a bool Series introduces
    # NaN, which upcasts to object, and pandas now warns that the silent
    # downcast on fillna will be removed. Same result, no deprecation.
    valid_previous = valid.shift(1, fill_value=False).astype(bool)
    above = (fast > slow) & valid
    above_previous = above.shift(1, fill_value=False).astype(bool)

    golden_cross = above & (~above_previous) & valid & valid_previous
    death_cross = (~above) & above_previous & valid & valid_previous
    frame.loc[golden_cross, "Signal"] = "Buy"
    frame.loc[death_cross, "Signal"] = "Sell"
    return frame


# --------------------------------------------------------------------------- #
# Narrative readout
# --------------------------------------------------------------------------- #
def _last_valid(series: pd.Series) -> Optional[float]:
    cleaned = series.dropna()
    return float(cleaned.iloc[-1]) if len(cleaned) else None


def _percentile_of_last(series: pd.Series, window: int) -> Optional[float]:
    """Where the latest reading sits within its own recent history, as 0-1.

    An absolute band width is uninterpretable — 4% is tight on one stock and
    wide on another — so the squeeze test has to be relative to the name's own
    range. Returns the fraction of the last `window` readings that sit BELOW
    today's, which makes 0.05 mean "narrower than 95% of the past year".
    """
    cleaned = series.dropna().tail(window)
    if len(cleaned) < 20:
        return None
    latest = float(cleaned.iloc[-1])
    return float((cleaned < latest).mean())


def _format_currency(value: float, currency: str) -> str:
    symbol = CURRENCY_SYMBOLS.get(currency, "")
    decimals = 2 if abs(value) >= 1.0 else 6
    formatted = f"{value:,.{decimals}f}"
    return f"{symbol}{formatted}" if symbol else f"{formatted} {currency}"


def _typical_daily_move(df: pd.DataFrame, window: int = 20) -> Optional[float]:
    if df.empty:
        return None
    span = df.tail(window)
    moves = ((span["High"] - span["Low"]) / span["Close"].replace(0.0, np.nan)) * 100.0
    value = float(moves.mean()) if len(moves.dropna()) else np.nan
    return value if np.isfinite(value) else None


def summarise_market(df: pd.DataFrame, levels: list, currency: str, ticker: str) -> dict:
    """Identical branching to the Streamlit version. The only change: the
    headline is emitted as plain text with `**bold**` markers instead of raw
    <b> tags, so the client renders it rather than trusting injected HTML."""
    price = float(df["Close"].iloc[-1])
    sma_fast = _last_valid(df["SMA_50"])
    sma_slow = _last_valid(df["SMA_200"])
    rsi = _last_valid(df["RSI"])
    macd_line = _last_valid(df["MACD"])
    macd_signal = _last_valid(df["MACD_SIGNAL"])

    if sma_fast is not None and sma_slow is not None:
        if price > sma_fast > sma_slow:
            trend, trend_tone = "Uptrend", "bull"
        elif price < sma_fast < sma_slow:
            trend, trend_tone = "Downtrend", "bear"
        else:
            trend, trend_tone = "Sideways", "neutral"
        gap = (price / sma_slow - 1.0) * 100.0
        side = "above" if gap >= 0 else "below"
        trend_sentence = (
            f"**{ticker}** is in a **{trend.lower()}**, trading "
            f"{abs(gap):.1f}% {side} its 200-day average."
        )
    elif sma_fast is not None:
        drift = (price / sma_fast - 1.0) if sma_fast else 0.0
        if abs(drift) < 0.001:
            trend, trend_tone = "Flat", "neutral"
        else:
            trend = "Rising" if drift > 0 else "Falling"
            trend_tone = "bull" if drift > 0 else "bear"
        trend_sentence = (
            f"**{ticker}** is **{trend.lower()}** against its 50-day average. "
            "Load more history for the full trend picture."
        )
    else:
        trend, trend_tone = "Too early to call", "neutral"
        trend_sentence = (
            f"**{ticker}** has too little history here to read a trend. "
            "Widen the date range."
        )

    if rsi is None:
        momentum, momentum_tone = "No reading", "neutral"
        momentum_sentence = "Momentum needs about two more weeks of data."
    elif rsi >= 70:
        momentum, momentum_tone = f"Overbought ({rsi:.0f})", "warn"
        momentum_sentence = "It has run hot recently, so a pause would not be a surprise."
    elif rsi <= 30:
        momentum, momentum_tone = f"Oversold ({rsi:.0f})", "warn"
        momentum_sentence = "It has been sold hard recently and is stretched to the downside."
    elif rsi >= 50:
        momentum, momentum_tone = f"Firm ({rsi:.0f})", "bull"
        momentum_sentence = "Buyers have had the upper hand over the past two weeks."
    else:
        momentum, momentum_tone = f"Soft ({rsi:.0f})", "bear"
        momentum_sentence = "Sellers have had the upper hand over the past two weeks."

    if macd_line is None or macd_signal is None:
        macd_label, macd_tone = "No reading", "neutral"
    elif macd_line == macd_signal:
        macd_label, macd_tone = "Level", "neutral"
    elif macd_line > macd_signal:
        macd_label, macd_tone = "Turning up", "bull"
    else:
        macd_label, macd_tone = "Turning down", "bear"

    above_levels = [level for level in levels if level > price]
    below_levels = [level for level in levels if level < price]
    resistance = min(above_levels) if above_levels else None
    support = max(below_levels) if below_levels else None

    level_parts = []
    if resistance is not None:
        distance = (resistance / price - 1.0) * 100.0
        level_parts.append(
            f"the next ceiling is {_format_currency(resistance, currency)} "
            f"({distance:.1f}% up)"
        )
    if support is not None:
        distance = (1.0 - support / price) * 100.0
        level_parts.append(
            f"the nearest floor is {_format_currency(support, currency)} "
            f"({distance:.1f}% down)"
        )
    if level_parts:
        level_sentence = "On past behaviour, " + " and ".join(level_parts) + "."
    else:
        level_sentence = ""

    signal_rows = df.loc[df["Signal"] != ""]
    if len(signal_rows):
        last_signal = signal_rows.iloc[-1]
        last_date = signal_rows.index[-1]
        since = (price / float(last_signal["Close"]) - 1.0) * 100.0
        signal_label = f"{last_signal['Signal']} · {last_date:%d %b %Y}"
        signal_detail = f"{since:+.1f}% since"
        signal_tone = "bull" if last_signal["Signal"] == "Buy" else "bear"
    else:
        signal_label, signal_detail, signal_tone = "None yet", "no crossover in range", "neutral"

    move = _typical_daily_move(df)
    move_label = f"±{move:.1f}% a day" if move is not None else "No reading"

    chips = [
        {"label": "Trend", "value": trend, "tone": trend_tone},
        {"label": "Momentum (RSI)", "value": momentum, "tone": momentum_tone},
        {"label": "MACD", "value": macd_label, "tone": macd_tone},
        {"label": "Typical swing", "value": move_label, "tone": "neutral"},
        {"label": "Latest signal", "value": f"{signal_label} · {signal_detail}", "tone": signal_tone},
    ]
    sentences = [trend_sentence, momentum_sentence, level_sentence]
    headline = " ".join(part for part in sentences if part)
    return {
        "headline": headline,
        "chips": chips,
        "trend": trend,
        "trend_tone": trend_tone,
        "resistance": resistance,
        "support": support,
    }


# --------------------------------------------------------------------------- #
# Long-horizon synthesis
# --------------------------------------------------------------------------- #
def _tone_for(passed: Optional[bool]) -> str:
    if passed is None:
        return "neutral"
    return "bull" if passed else "bear"


def long_term_view(frame: pd.DataFrame, drawdown: dict, risk: dict,
                   momentum: dict, position: dict, faber: dict,
                   hurst_reading: dict, slope: Optional[float],
                   r_squared: Optional[float]) -> dict:
    """One readout of the long-horizon evidence, as a checklist plus a verdict.

    A CHECKLIST, NOT A SCORE. Compressing these into a single 0-100 number would
    make them look commensurable when they are not: "above the 200-day average"
    and "survived a 60% drawdown" are different kinds of fact, and averaging
    them produces a figure that cannot be argued with because it cannot be
    decomposed. Each line stands on its own and says which way it points.

    Nothing here is a recommendation. A long-term case is made on the business;
    this describes what the price history has done and how much pain holding it
    has required.
    """
    latest = frame.iloc[-1]
    close = float(latest["Close"])
    checks: list[dict] = []

    def add(label: str, passed: Optional[bool], detail: str, horizon: str = "long"):
        checks.append({"label": label, "passed": passed, "detail": detail,
                       "tone": _tone_for(passed), "horizon": horizon})

    # --- primary trend ----------------------------------------------------
    sma_200 = _last_valid(frame["SMA_200"])
    if sma_200 is not None:
        add("Above the 200-day average", close > sma_200,
            f"{(close / sma_200 - 1) * 100:+.1f}% versus the 200-day")
    else:
        add("Above the 200-day average", None, "needs 200 bars of history")

    if faber.get("usable"):
        add("Faber 10-month rule", faber["signal"] == "invested",
            f"monthly close {faber['distance'] * 100:+.1f}% versus its 10-month average, "
            f"{faber['monthsInStance']} months in this stance")
    else:
        add("Faber 10-month rule", None, "needs about a year of history")

    # --- momentum ---------------------------------------------------------
    twelve_one = momentum.get("momentum12_1")
    if twelve_one is not None:
        add("12-1 month momentum", twelve_one > 0,
            f"{twelve_one * 100:+.1f}% over 12 months ending a month ago")
    else:
        add("12-1 month momentum", None, "needs a year of history")

    # --- trend quality ----------------------------------------------------
    adx_value = _last_valid(frame["ADX"])
    plus_di = _last_valid(frame["PLUS_DI"])
    minus_di = _last_valid(frame["MINUS_DI"])
    if adx_value is not None and plus_di is not None and minus_di is not None:
        trending = adx_value >= 25
        add("Trend is strong enough to read", trending,
            f"ADX {adx_value:.0f} ({'trending' if trending else 'directionless'}), "
            f"+DI {plus_di:.0f} versus -DI {minus_di:.0f}")
    else:
        add("Trend is strong enough to read", None, "insufficient history")

    # THE VERDICT IS SAMPLE-SIZE AWARE, not a fixed 0.45-0.55 band. The band was
    # barely one standard error wide, so a genuine random walk tripped this line
    # a third of the time on five years of data. `hurst_estimate` widens it when
    # there is less history; "cannot tell" is scored as NO READING rather than
    # as a failure, because it is the absence of evidence, not evidence against.
    hurst = hurst_reading.get("hurst")
    verdict = hurst_reading.get("verdict")
    if hurst is not None and verdict != "unavailable":
        stderr = hurst_reading.get("stderr") or 0.0
        detail = f"Hurst {hurst:.2f} ± {stderr:.2f} — "
        if verdict == "persistent":
            add("Price series shows persistence", True,
                detail + "trending by more than the estimate's own error, so trend tools "
                         "have something to work with")
        elif verdict == "meanReverting":
            add("Price series shows persistence", False,
                detail + "mean-reverting; falls tend to be given back")
        else:
            low = hurst_reading.get("randomWalkLow") or 0.0
            high = hurst_reading.get("randomWalkHigh") or 0.0
            add("Price series shows persistence", None,
                detail + f"inside {low:.2f}-{high:.2f}, which is what a random walk produces "
                         f"at this sample size. Trend signals here are probably noise")
    else:
        add("Price series shows persistence", None, "needs ~100 bars")

    if slope is not None and r_squared is not None:
        add("Long-run trend line rising", slope > 0,
            f"{slope * 100:+.1f}% a year fitted, R2 {r_squared:.0%}"
            + ("" if r_squared >= 0.5 else " — a loose fit, so read the slope loosely"))
    else:
        add("Long-run trend line rising", None, "insufficient history")

    # --- position ---------------------------------------------------------
    if position.get("usable") and position.get("fromHigh52w") is not None:
        near_high = position["fromHigh52w"] > -0.10
        add("Near its 52-week high", near_high,
            f"{position['fromHigh52w'] * 100:+.1f}% from the 52-week high, "
            f"{position['fromAllTimeHigh'] * 100:+.1f}% from the record")

    # --- what holding cost ------------------------------------------------
    if drawdown.get("usable"):
        depth = drawdown["maxDrawdown"]
        tolerable = depth > -0.50
        add("Worst drawdown survivable", tolerable,
            f"{depth * 100:.0f}% peak to trough, longest {drawdown['timeUnderWaterDays']} "
            f"trading days under water", horizon="risk")

    if risk.get("usable") and risk.get("sortino") is not None:
        add("Paid for its downside risk", risk["sortino"] > 0.5,
            f"Sortino {risk['sortino']:.2f}, Calmar "
            + (f"{risk['calmar']:.2f}" if risk.get("calmar") is not None else "n/a"),
            horizon="risk")

    scored = [c for c in checks if c["passed"] is not None]
    passed = sum(1 for c in scored if c["passed"])

    if not scored:
        verdict, tone = "NO READING", "neutral"
        headline = "Not enough history to say anything about the long horizon."
    elif passed >= len(scored) * 0.75:
        verdict, tone = "CONSTRUCTIVE", "bull"
        headline = "The long-horizon evidence mostly points the same way, upward."
    elif passed <= len(scored) * 0.25:
        verdict, tone = "WEAK", "bear"
        headline = "The long-horizon evidence mostly points down."
    else:
        verdict, tone = "MIXED", "neutral"
        headline = "The long-horizon evidence is split."

    return {
        "verdict": verdict,
        "tone": tone,
        "headline": headline,
        "passed": passed,
        "scored": len(scored),
        "checks": checks,
        "caveat": (
            "A checklist of what the price history has done, not a recommendation. "
            "Every line here is computed from price and volume alone and knows "
            "nothing about the business — see the Value and Quality lenses for that."
        ),
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _benchmark_history(market_code: str, start: dt.date, end: dt.date):
    """Index closes for relative strength, cached for the day by riskmodel."""
    symbol = riskmodel.MARKET_INDEX.get((market_code or "US").upper(), "^GSPC")
    try:
        frame = fetch_data(symbol, start, end)
    except Exception:
        return symbol, None
    return symbol, (frame["Close"] if frame is not None and not frame.empty else None)


def analyze(ticker: str, range_key: str = "1y", sr_window: int = 10,
            sr_levels: int = 6, market_code: str = "US") -> dict:
    days = RANGE_PRESETS.get(range_key, RANGE_PRESETS["1y"])
    end_date = dt.date.today()
    start_date = end_date - dt.timedelta(days=days)

    data = fetch_data(ticker, start_date, end_date)
    if data.empty:
        raise TechnicalError(
            f"No market data came back for '{ticker}'. Check the spelling, add the pair "
            "suffix for crypto (BTC-USD) or the exchange suffix for non-US listings, "
            "then try a wider date range."
        )

    data = calculate_indicators(data)
    data = generate_signals(data)
    levels = calculate_support_resistance(data, window=sr_window, max_levels=sr_levels)
    currency = fetch_currency(ticker)
    summary = summarise_market(data, levels, currency, ticker)

    latest = data.iloc[-1]
    price = float(latest["Close"])
    previous_close = float(data["Close"].iloc[-2]) if len(data) > 1 else float(latest["Open"])
    change = price - previous_close
    change_pct = (change / previous_close * 100.0) if previous_close else 0.0

    series = [
        {
            "date": index.strftime("%Y-%m-%d"),
            "open": row["Open"], "high": row["High"], "low": row["Low"],
            "close": row["Close"], "volume": row["Volume"],
            "sma50": row["SMA_50"], "sma200": row["SMA_200"],
            "bbUpper": row["BB_UPPER"], "bbMid": row["BB_MID"], "bbLower": row["BB_LOWER"],
            "rsi": row["RSI"], "macd": row["MACD"],
            "macdSignal": row["MACD_SIGNAL"], "macdHist": row["MACD_HIST"],
            "sma20": row["SMA_20"], "sma100": row["SMA_100"],
            "kcUpper": row["KC_UPPER"], "kcLower": row["KC_LOWER"],
            "dcUpper": row["DC_UPPER"], "dcLower": row["DC_LOWER"],
            "ichiSpanA": row["ICHI_SPAN_A"], "ichiSpanB": row["ICHI_SPAN_B"],
            "adx": row["ADX"], "plusDi": row["PLUS_DI"], "minusDi": row["MINUS_DI"],
            "drawdown": row["DRAWDOWN"], "atrPct": row["ATR_PCT"],
            "cmf": row["CMF"], "obv": row["OBV"],
            "signal": row["Signal"] or None,
        }
        for index, row in data.iterrows()
    ]

    events = data.loc[data["Signal"] != ""]
    signals = [
        {
            "date": index.strftime("%Y-%m-%d"),
            "type": row["Signal"],
            "description": (
                "Golden cross · fast average moved above slow"
                if row["Signal"] == "Buy"
                else "Death cross · fast average moved below slow"
            ),
            "price": float(row["Close"]),
            "changeSince": (price / float(row["Close"]) - 1.0) * 100.0,
        }
        for index, row in events.iloc[::-1].iterrows()
    ]

    # ---------------- long-horizon layer ----------------
    close_series = data["Close"].astype("float64")
    enough = len(data) >= MIN_LONGTERM_BARS

    drawdown = lt.drawdown_profile(close_series) if enough else {"usable": False}
    # Sharpe and Sortino used to divide by a risk-free rate of ZERO, which is not
    # the textbook ratio and flatters every name by roughly rf/volatility. That
    # went unnoticed while the panel printed the bare number; the moment it
    # started saying "above 1.0 is good" the reader needed the number to mean
    # what that sentence claims. The market convention is the same constant the
    # valuation engine discounts with, so the two lenses now agree on what money
    # costs.
    risk_free = MARKETS.get((market_code or "US").upper(), MARKETS["US"])["risk_free_default"]
    risk = lt.risk_metrics(close_series, risk_free=risk_free) if enough else {"usable": False}
    rolling = lt.rolling_returns(close_series) if enough else []
    seasonality = lt.monthly_seasonality(close_series) if enough else {"usable": False, "months": []}
    momentum = lt.time_series_momentum(close_series)
    position = lt.price_position(close_series, data["High"], data["Low"])
    faber = lt.faber_timing(close_series) if enough else {"usable": False}
    calendar = lt.calendar_returns(close_series) if enough else []

    hurst_reading = (ind.hurst_estimate(close_series) if enough
                     else {"hurst": None, "verdict": "unavailable"})
    hurst = hurst_reading.get("hurst")
    slope, r_squared, reg_lower, reg_mid, reg_upper = (
        ind.linear_regression_channel(close_series, REGRESSION_WINDOW)
        if enough else (None, None, None, None, None)
    )

    benchmark_symbol, benchmark_close = (
        _benchmark_history(market_code, start_date, end_date) if enough else (None, None)
    )
    relative = (lt.relative_strength(close_series, benchmark_close, benchmark_symbol)
                if benchmark_close is not None
                else {"usable": False, "benchmark": benchmark_symbol})

    monthly_close = close_series.resample("ME").last().dropna()
    coppock = ind.coppock_curve(monthly_close) if len(monthly_close) >= 25 else pd.Series(dtype=float)
    coppock_points = [
        {"date": date.strftime("%Y-%m-%d"), "value": float(value)}
        for date, value in coppock.dropna().items()
    ]

    view = long_term_view(data, drawdown, risk, momentum, position, faber,
                          hurst_reading, slope, r_squared)

    regression = None
    if reg_mid is not None:
        regression = {
            "slopePerYear": slope, "rSquared": r_squared,
            "lower": float(reg_lower.iloc[-1]), "mid": float(reg_mid.iloc[-1]),
            "upper": float(reg_upper.iloc[-1]),
            "position": float((price - reg_lower.iloc[-1])
                              / max(reg_upper.iloc[-1] - reg_lower.iloc[-1], 1e-9)),
        }

    long_term = {
        "view": view,
        "drawdown": drawdown,
        "risk": risk,
        "rollingReturns": rolling,
        "calendarReturns": calendar,
        "seasonality": seasonality,
        "momentum": momentum,
        "position": position,
        "faber": faber,
        "relativeStrength": relative,
        "hurst": hurst,
        "hurstReading": hurst_reading,
        "regression": regression,
        "coppock": coppock_points,
    }
    # Plain-language layer. Built here rather than in the component because every
    # clause is conditional on a number existing and on which side of a threshold
    # it falls — see `_lib/explain.py` for why that belongs somewhere testable.
    if enough:
        long_term["plainEnglish"] = ex.long_horizon_story(ticker, long_term)
        long_term["explain"] = ex.for_long_term(long_term, ticker=ticker,
                                                risk_free=risk_free, currency=currency)
    else:
        long_term["plainEnglish"] = None
        long_term["explain"] = {}

    # ---------------- shorter horizons ----------------
    # Both run off the SAME frame the chart uses, so they cost no extra fetch.
    # `analyse` withholds a horizon rather than computing it from too few bars,
    # which is why a 3-month range returns a mid-term section that says so.
    horizons = swing.analyse(data)
    def money(value):
        return _format_currency(float(value), currency)

    for block in horizons.values():
        if block.get("usable"):
            block["plainEnglish"] = ex.horizon_story(ticker, block, currency_format=money)
            block["explain"] = ex.for_horizon(block, currency_format=money)
        else:
            block["plainEnglish"] = None
            block["explain"] = {}

    indicator_notes = ex.for_indicators(
        {
            "sma50": _last_valid(data["SMA_50"]), "sma100": _last_valid(data["SMA_100"]),
            "sma200": _last_valid(data["SMA_200"]),
            "adx": _last_valid(data["ADX"]), "plusDi": _last_valid(data["PLUS_DI"]),
            "minusDi": _last_valid(data["MINUS_DI"]),
            "aroonUp": _last_valid(data["AROON_UP"]), "aroonDown": _last_valid(data["AROON_DOWN"]),
            "rsi": _last_valid(data["RSI"]),
            "stochK": _last_valid(data["STOCH_K"]), "stochD": _last_valid(data["STOCH_D"]),
            "williamsR": _last_valid(data["WILLIAMS_R"]), "cci": _last_valid(data["CCI"]),
            "macd": _last_valid(data["MACD"]), "macdSignal": _last_valid(data["MACD_SIGNAL"]),
            "bbPercentB": _last_valid(data["BB_PERCENT_B"]),
            "bbBandwidth": _last_valid(data["BB_BANDWIDTH"]),
            "bbBandwidthPercentile": _percentile_of_last(data["BB_BANDWIDTH"], 252),
            "atr": _last_valid(data["ATR"]), "atrPct": _last_valid(data["ATR_PCT"]),
            "mfi": _last_valid(data["MFI"]), "cmf": _last_valid(data["CMF"]),
            "volumeTrend": _last_valid(data["VOLUME_TREND"]),
            "roc63": _last_valid(data["ROC_63"]), "roc252": _last_valid(data["ROC_252"]),
        },
        price=price,
    )

    return {
        "ticker": ticker,
        "currency": currency,
        "range": range_key,
        "bars": len(data),
        "hasSma200": bool(data["SMA_200"].notna().sum() > 0),
        "hasLongTerm": bool(enough),
        "longTerm": long_term,
        "shortTerm": horizons["short"],
        "midTerm": horizons["mid"],
        "indicators": {
            "adx": _last_valid(data["ADX"]),
            "plusDi": _last_valid(data["PLUS_DI"]),
            "minusDi": _last_valid(data["MINUS_DI"]),
            "aroonUp": _last_valid(data["AROON_UP"]),
            "aroonDown": _last_valid(data["AROON_DOWN"]),
            "rsi": _last_valid(data["RSI"]),
            "stochK": _last_valid(data["STOCH_K"]),
            "stochD": _last_valid(data["STOCH_D"]),
            "williamsR": _last_valid(data["WILLIAMS_R"]),
            "cci": _last_valid(data["CCI"]),
            "macd": _last_valid(data["MACD"]),
            "macdSignal": _last_valid(data["MACD_SIGNAL"]),
            "atr": _last_valid(data["ATR"]),
            "atrPct": _last_valid(data["ATR_PCT"]),
            "bbPercentB": _last_valid(data["BB_PERCENT_B"]),
            "bbBandwidth": _last_valid(data["BB_BANDWIDTH"]),
            "bbBandwidthPercentile": _percentile_of_last(data["BB_BANDWIDTH"], 252),
            "cmf": _last_valid(data["CMF"]),
            "mfi": _last_valid(data["MFI"]),
            "volumeTrend": _last_valid(data["VOLUME_TREND"]),
            "roc63": _last_valid(data["ROC_63"]),
            "roc252": _last_valid(data["ROC_252"]),
            "sma20": _last_valid(data["SMA_20"]),
            "sma50": _last_valid(data["SMA_50"]),
            "sma100": _last_valid(data["SMA_100"]),
            "sma200": _last_valid(data["SMA_200"]),
            "donchianUpper": _last_valid(data["DC_UPPER"]),
            "donchianLower": _last_valid(data["DC_LOWER"]),
            "ichimokuSpanA": _last_valid(data["ICHI_SPAN_A"]),
            "ichimokuSpanB": _last_valid(data["ICHI_SPAN_B"]),
            "ichimokuConversion": _last_valid(data["ICHI_CONVERSION"]),
            "ichimokuBase": _last_valid(data["ICHI_BASE"]),
        },
        "indicatorsExplain": indicator_notes,
        "latest": {
            "date": data.index[-1].strftime("%Y-%m-%d"),
            "close": price,
            "change": change,
            "changePct": change_pct,
            "high": float(latest["High"]),
            "low": float(latest["Low"]),
            "volume": float(latest["Volume"]),
        },
        "summary": summary,
        "levels": levels,
        "series": series,
        "signals": signals,
    }
