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

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "IDR": "Rp", "AUD": "A$"}

RANGE_PRESETS = {
    "3mo": 91,
    "6mo": 182,
    "1y": 365,
    "2y": 730,
    "5y": 1826,
}

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
    frame = df.copy()
    close = frame["Close"].astype("float64")
    frame["SMA_50"] = _sma(close, 50)
    frame["SMA_200"] = _sma(close, 200)
    lower, middle, upper = _bbands(close, 20, 2.0)
    frame["BB_LOWER"] = lower
    frame["BB_MID"] = middle
    frame["BB_UPPER"] = upper
    frame["RSI"] = _rsi(close, 14)
    macd_line, macd_signal, macd_hist = _macd(close, 12, 26, 9)
    frame["MACD"] = macd_line
    frame["MACD_SIGNAL"] = macd_signal
    frame["MACD_HIST"] = macd_hist
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
    valid_previous = valid.shift(1).fillna(False).astype(bool)
    above = (fast > slow) & valid
    above_previous = above.shift(1).fillna(False).astype(bool)

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
# Orchestration
# --------------------------------------------------------------------------- #
def analyze(ticker: str, range_key: str = "1y", sr_window: int = 10,
            sr_levels: int = 6) -> dict:
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

    return {
        "ticker": ticker,
        "currency": currency,
        "range": range_key,
        "bars": len(data),
        "hasSma200": bool(data["SMA_200"].notna().sum() > 0),
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
