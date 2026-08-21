"""
swing.py
========
Short-horizon (days to weeks) and mid-horizon (weeks to months) technical
structure — the two sections `longterm.py` deliberately does not answer.

WHY THIS MODULE EXISTS SEPARATELY, AND WHAT IT REFUSES TO DO
-----------------------------------------------------------
`longterm.py` answers "could I have held this?". This answers "if I were going
to buy it in the next few weeks, WHERE would the levels be?" — support and
resistance, a stop that reflects how much this particular stock moves, a
target, and the ratio between the last two.

It is the part of the app where the evidence is weakest, and the design follows
from that rather than apologising for it afterwards:

1. IT NEVER INVENTS A SETUP. Most stocks on most days are not in a recognisable
   setup, and the honest output then is "nothing here". A tool that always
   finds something is a tool that finds nothing.

2. LEVELS ARE STRUCTURAL FIRST, ARITHMETIC SECOND. A stop goes beyond the price
   the market actually defended, not at a round percentage. ATR is used to
   sanity-check that level and to size the position, which is the use of it
   with real support (Wilder 1978; the volatility-scaling literature since).

3. EVERY READING CARRIES ITS EVIDENCE GRADE. Donchian breakouts and moving-
   average trend rules sit on the time-series momentum literature and are
   graded accordingly. Candlestick patterns do not: Marshall, Young & Rose
   (2006) tested the standard set against a bootstrap of random OHLC series on
   DJIA components and found no value. They are still detected here, because a
   reader will see them on any chart and deserves to know what they are — but
   they are labelled weak and they are NEVER allowed to generate an entry, a
   stop or a target.

4. PATTERNS THAT CANNOT BE DETECTED RELIABLY ARE NAMED AND DECLINED. Head and
   shoulders, flags, pennants, wedges, cup-and-handle: Lo, Mamaysky & Wang
   (2000) needed nonparametric kernel regression with a cross-validated
   bandwidth just to DEFINE these shapes, and even then reported a shift in the
   return distribution rather than a tradeable edge. A fixed-threshold matcher
   for "flag" fires on noise several times a month on any liquid name. The
   panel says so by name rather than shipping one.

References
----------
Wilder, J. W. (1978). New Concepts in Technical Trading Systems. (ATR, RSI, ADX.)
Marshall, B., Young, M., & Rose, L. (2006). "Candlestick technical trading
    strategies: Can they create value for investors?" Journal of Banking &
    Finance 30(8), 2303-2323. (No value on DJIA components.)
Lo, A., Mamaysky, H., & Wang, J. (2000). "Foundations of Technical Analysis."
    Journal of Finance 55(4). (Kernel-regression pattern definition; some
    incremental distributional information, not a demonstrated net edge.)
Moskowitz, T., Ooi, Y. H., & Pedersen, L. H. (2012). "Time series momentum."
    Journal of Financial Economics 104(2). (The support under breakout rules.)
Jegadeesh, N. (1990). "Evidence of Predictable Behavior of Security Returns."
    Journal of Finance 45(3). (Short-term reversal: the one-month effect that
    makes very short horizons behave OPPOSITE to the 12-month one.)
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from . import indicators as ind

# Horizon parameters, kept in one place so the two readouts differ by data
# rather than by duplicated code.
#
# `stop_atr` is the multiple of the average daily range a stop sits beyond
# structure. The short-horizon number is tighter because the holding period is
# shorter, not because the trade is safer — a tight stop on a volatile name is
# a coin flip, which is why the readout refuses to place one below a floor.
HORIZONS = {
    "short": {
        "label": "Short term",
        "window": "days to a few weeks",
        "pivot_period": "W",          # last complete week
        "swing_order": 3,             # bars either side of a turning point
        "lookback": 90,
        "breakout_window": 20,        # Donchian
        "stop_atr": 1.5,
        "fast_ma": 8,
        "slow_ma": 21,
    },
    "mid": {
        "label": "Mid term",
        "window": "weeks to months",
        "pivot_period": "ME",         # last complete month
        "swing_order": 7,
        "lookback": 250,
        "breakout_window": 55,
        "stop_atr": 2.5,
        "fast_ma": 20,
        "slow_ma": 50,
    },
}

# Below this many bars a horizon is withheld rather than computed from noise.
MIN_BARS = {"short": 60, "mid": 160}

# A stop closer than this many average daily ranges is not a risk control, it is
# a lottery ticket on the next day's noise. When structure implies one tighter
# than this, the readout widens it and says why.
MIN_STOP_ATR = 1.0

# Default risk budget used to express position size. Expressed as a share of the
# account rather than a share count, because the app has no idea how much money
# anyone has and asking would be worse than the arithmetic it saves.
DEFAULT_RISK_BUDGET = 0.01


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


# ============================================================================ #
# Structure: swing points, support and resistance
# ============================================================================ #
def swing_points(high: pd.Series, low: pd.Series, order: int = 3) -> tuple[pd.Series, pd.Series]:
    """Local highs and lows that stood above/below `order` bars on each side.

    A pure fractal definition, not a smoothed one. That is a deliberate choice:
    smoothing the series first (as kernel-regression pattern finders do) makes
    prettier turning points but moves them in time, and a support level whose
    DATE is wrong is a level that was never actually defended.

    The last `order` bars can never qualify, because there is not yet enough
    history on the right-hand side. That lag is inherent — a turning point is
    only a turning point in hindsight — and the readout says so rather than
    pretending today's high is a confirmed swing.
    """
    highs = high.to_numpy(dtype="float64")
    lows = low.to_numpy(dtype="float64")
    n = len(highs)
    is_peak = np.zeros(n, dtype=bool)
    is_trough = np.zeros(n, dtype=bool)

    for i in range(order, n - order):
        window_high = highs[i - order:i + order + 1]
        window_low = lows[i - order:i + order + 1]
        if np.isfinite(highs[i]) and highs[i] >= np.nanmax(window_high):
            is_peak[i] = True
        if np.isfinite(lows[i]) and lows[i] <= np.nanmin(window_low):
            is_trough[i] = True

    # A flat stretch trips the >= test on every bar in it, which turns one
    # plateau into `order`-plus identical "turning points". That is not a
    # cosmetic problem: the divergence check compares the LAST TWO swings, and
    # two bars of the same plateau are the same price, so a real divergence
    # behind them becomes invisible. Thin each run down to its single extreme.
    return (_thin(is_peak, highs, order, keep="max", index=high.index),
            _thin(is_trough, lows, order, keep="min", index=low.index))


def _thin(mask: np.ndarray, values: np.ndarray, order: int,
          keep: str, index) -> pd.Series:
    """Collapse each run of flagged bars within `order` of each other to one.

    The survivor is the most extreme bar in the run — the actual high of the
    plateau — and ties resolve to the earliest, because that is where the level
    was first established.
    """
    positions = np.flatnonzero(mask)
    thinned = np.zeros_like(mask)
    if positions.size == 0:
        return pd.Series(thinned, index=index)

    run = [positions[0]]
    runs = []
    for position in positions[1:]:
        if position - run[-1] <= order:
            run.append(position)
        else:
            runs.append(run)
            run = [position]
    runs.append(run)

    for group in runs:
        subset = values[group]
        best = int(np.nanargmax(subset) if keep == "max" else np.nanargmin(subset))
        thinned[group[best]] = True
    return pd.Series(thinned, index=index)


def level_clusters(values: pd.Series, tolerance: float) -> list[dict]:
    """Group nearby swing prices into levels, counting how often each was tested.

    THE TOUCH COUNT IS THE POINT. A price the market turned at four times is a
    different object from one it turned at once, and the previous version of
    this app's support/resistance finder ranked purely by cluster size without
    ever showing the count. Reporting it lets a reader discount a level built
    from a single spike, which is most of them.
    """
    prices = sorted(float(v) for v in values.dropna())
    if not prices:
        return []

    clusters: list[list[float]] = [[prices[0]]]
    for price in prices[1:]:
        if price - clusters[-1][-1] <= tolerance:
            clusters[-1].append(price)
        else:
            clusters.append([price])

    return [{"price": float(np.mean(group)), "touches": len(group)} for group in clusters]


def support_resistance(frame: pd.DataFrame, order: int = 3,
                       max_levels: int = 4) -> dict:
    """The nearest defended levels above and below the current price.

    Tolerance is one average true range, so "nearby" means nearby FOR THIS
    STOCK. A fixed percentage merges four distinct levels on a quiet utility and
    splits one level into four on a volatile small-cap.
    """
    if len(frame) < 2 * order + 5:
        return {"usable": False, "supports": [], "resistances": []}

    peaks, troughs = swing_points(frame["High"], frame["Low"], order)
    price = float(frame["Close"].iloc[-1])
    tolerance = _finite(ind.atr(frame["High"], frame["Low"], frame["Close"]).iloc[-1])
    if not tolerance or tolerance <= 0:
        tolerance = price * 0.01

    resistance_candidates = level_clusters(frame["High"][peaks], tolerance)
    support_candidates = level_clusters(frame["Low"][troughs], tolerance)

    def dress(levels, side):
        out = []
        for level in levels:
            distance = level["price"] / price - 1.0
            out.append({
                "price": round(level["price"], 6),
                "touches": level["touches"],
                "distancePct": float(distance),
                "distanceAtr": float((level["price"] - price) / tolerance),
                "side": side,
            })
        return out

    above = [level for level in resistance_candidates if level["price"] > price * 1.001]
    below = [level for level in support_candidates if level["price"] < price * 0.999]

    # Nearest first — the level that matters is the one the price reaches next.
    resistances = sorted(dress(above, "resistance"), key=lambda r: r["price"])[:max_levels]
    supports = sorted(dress(below, "support"), key=lambda r: -r["price"])[:max_levels]

    return {
        "usable": True,
        "price": price,
        "atr": float(tolerance),
        "supports": supports,
        "resistances": resistances,
        "confirmationLag": int(order),
    }


# ============================================================================ #
# Pivot points
# ============================================================================ #
def pivot_points(high: float, low: float, close: float, style: str = "classic") -> dict:
    """Floor-trader pivots for the period that just closed.

    Arithmetic on last period's range, nothing more. They are included because
    a great many market participants watch them, which is the only mechanism by
    which they could work and is also the reason not to overstate them: a level
    is self-fulfilling only while enough people are looking at it, and there is
    no published evidence that these produce excess returns after costs.
    """
    if not all(np.isfinite([high, low, close])) or high < low:
        return {"usable": False}

    pivot = (high + low + close) / 3.0
    span = high - low

    if style == "fibonacci":
        levels = {
            "r3": pivot + 1.000 * span, "r2": pivot + 0.618 * span,
            "r1": pivot + 0.382 * span, "pivot": pivot,
            "s1": pivot - 0.382 * span, "s2": pivot - 0.618 * span,
            "s3": pivot - 1.000 * span,
        }
    else:
        levels = {
            "r3": high + 2.0 * (pivot - low), "r2": pivot + span,
            "r1": 2.0 * pivot - low, "pivot": pivot,
            "s1": 2.0 * pivot - high, "s2": pivot - span,
            "s3": low - 2.0 * (high - pivot),
        }
    return {"usable": True, "style": style, "periodHigh": float(high),
            "periodLow": float(low), "periodClose": float(close),
            **{k: float(v) for k, v in levels.items()}}


def period_pivots(frame: pd.DataFrame, period: str = "W", style: str = "classic") -> dict:
    """Pivots from the last COMPLETE calendar period.

    Resampling then dropping the final bucket matters: the current week is still
    being written, and pivots computed from a partial period change every day,
    which makes them useless as the fixed reference they are supposed to be.
    """
    if frame.empty:
        return {"usable": False}
    grouped = frame.resample(period).agg(
        {"High": "max", "Low": "min", "Close": "last"}).dropna()
    if len(grouped) < 2:
        return {"usable": False}
    last_complete = grouped.iloc[-2]
    result = pivot_points(float(last_complete["High"]), float(last_complete["Low"]),
                          float(last_complete["Close"]), style=style)
    if result.get("usable"):
        result["period"] = "week" if period.startswith("W") else "month"
    return result


# ============================================================================ #
# Volume-weighted average price
# ============================================================================ #
def anchored_vwap(frame: pd.DataFrame, anchor: pd.Timestamp) -> Optional[float]:
    """Volume-weighted average price since a chosen date.

    HONESTY ABOUT THE INPUT: a true VWAP weights every TRADE. This app has daily
    bars, so each day contributes one typical price (H+L+C)/3 weighted by that
    day's volume. Over a multi-week anchor the difference from a tick-accurate
    VWAP is small; over three days it is not, and nothing here anchors that
    short. It is best read as "the average price everyone who bought since the
    anchor has paid", which is the question people actually use it for.
    """
    span = frame.loc[frame.index >= anchor]
    if span.empty or span["Volume"].sum() <= 0:
        return None
    typical = (span["High"] + span["Low"] + span["Close"]) / 3.0
    weights = span["Volume"].astype("float64")
    total = float(weights.sum())
    if total <= 0:
        return None
    return float((typical * weights).sum() / total)


def vwap_profile(frame: pd.DataFrame) -> dict:
    """VWAP anchored at the points a position most plausibly began.

    The three anchors are the ones with a story attached: the 52-week low (where
    a recovery would have started), the 52-week high (where the last set of
    buyers got trapped), and a rolling quarter (recent participants). An anchor
    with no story is a line with no meaning.
    """
    if len(frame) < 25:
        return {"usable": False, "anchors": []}

    price = float(frame["Close"].iloc[-1])
    year = frame.tail(252)
    anchors = []

    for label, anchor_date, note in (
        ("52-week low", year["Low"].idxmin(), "where a recovery would have begun"),
        ("52-week high", year["High"].idxmax(), "the average price paid by the last buyers at the top"),
        ("Last 63 days", frame.index[max(0, len(frame) - 63)], "recent participants"),
    ):
        value = anchored_vwap(frame, anchor_date)
        if value is None or value <= 0:
            continue
        anchors.append({
            "label": label,
            "anchoredOn": anchor_date.strftime("%Y-%m-%d"),
            "vwap": float(value),
            "distancePct": float(price / value - 1.0),
            "above": bool(price > value),
            "note": note,
        })

    return {"usable": bool(anchors), "price": price, "anchors": anchors,
            "caveat": ("Computed from daily bars — each day contributes one typical price "
                       "weighted by its volume, which approximates but is not a tick-accurate "
                       "intraday VWAP.")}


# ============================================================================ #
# Candlestick patterns — detected, labelled weak, never allowed to place a stop
# ============================================================================ #
# Only single- and two-bar formations appear here, and that is the whole rule.
# They are the ones whose definition is arithmetic on OHLC and therefore
# reproducible: another implementation reading the same bars gets the same
# answer. Everything longer needs a judgement about where a "shoulder" or a
# "flagpole" begins, and two honest implementations disagree.
UNDETECTABLE_PATTERNS = [
    ("Head and shoulders", "needs a subjective decision about where each shoulder starts and "
                           "how symmetric is symmetric enough"),
    ("Flags and pennants", "requires identifying a 'flagpole' — a move that counts as sharp "
                           "enough — which no fixed threshold captures across different stocks"),
    ("Wedges and triangles", "two converging trend lines can be fitted to almost any 20 bars "
                             "if you are allowed to choose which highs and lows to use"),
    ("Cup and handle", "a shape defined by how it looks, with no numeric definition that "
                       "different practitioners agree on"),
    ("Double top / bottom", "detectable in principle, but the tolerance for 'the same level' "
                            "and the required separation change the hit rate enormously"),
]


def candlestick_patterns(frame: pd.DataFrame, atr_value: float) -> list[dict]:
    """Single- and two-bar formations on the most recent bar.

    Every threshold below is scaled by ATR or by the bar's own range rather than
    by a fixed percentage, so the same definition applies to a utility and a
    biotech. `evidence` is "weak" on every one of them, and that is not
    hedging — Marshall, Young & Rose (2006) bootstrapped random OHLC series and
    found the standard candlestick set produced no value on DJIA components.
    """
    if len(frame) < 2 or not atr_value or atr_value <= 0:
        return []

    last = frame.iloc[-1]
    prior = frame.iloc[-2]
    o, h, low_, c = (float(last["Open"]), float(last["High"]),
                     float(last["Low"]), float(last["Close"]))
    po, ph, pl, pc = (float(prior["Open"]), float(prior["High"]),
                      float(prior["Low"]), float(prior["Close"]))

    body = abs(c - o)
    span = h - low_
    if span <= 0:
        return []
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - low_
    found: list[dict] = []

    def add(name, direction, meaning):
        found.append({"name": name, "direction": direction, "meaning": meaning,
                      "date": frame.index[-1].strftime("%Y-%m-%d"), "evidence": "weak"})

    # --- two-bar ---------------------------------------------------------
    if c > o and pc < po and c >= po and o <= pc and body > abs(pc - po):
        add("Bullish engulfing", "up",
            "Today's up-bar completely covers yesterday's down-bar — buyers took back the "
            "whole of the previous day's selling.")
    if c < o and pc > po and c <= po and o >= pc and body > abs(pc - po):
        add("Bearish engulfing", "down",
            "Today's down-bar completely covers yesterday's up-bar.")
    if h <= ph and low_ >= pl:
        add("Inside bar", "none",
            "The whole day traded inside yesterday's range — a pause, with no directional "
            "information of its own. It says volatility contracted, nothing more.")
    if h > ph and low_ < pl:
        add("Outside bar", "none",
            "The day traded both above yesterday's high and below its low. Both sides were "
            "active; which one won is told by the close, not by the shape.")

    # --- single-bar ------------------------------------------------------
    # SHADOW TESTS COME FIRST, and they are measured against the bar's own RANGE
    # rather than against its body. Scaling by the body degenerates: any bar
    # with a tiny body satisfies "shadow >= 2x body" trivially, so a textbook
    # dragonfly — tiny body sitting on a long lower wick — was being reported as
    # a doji, which is the one reading that throws away its most distinctive
    # feature. Range-relative thresholds behave the same on every bar size.
    long_lower = lower_shadow >= 0.6 * span and upper_shadow <= 0.15 * span
    long_upper = upper_shadow >= 0.6 * span and lower_shadow <= 0.15 * span

    if long_lower and span >= 0.6 * atr_value:
        add("Hammer" if c >= o else "Hanging man", "up" if c >= o else "down",
            "Sold off hard during the day and closed back near the top. Buyers turned up "
            "somewhere down there — though the same shape appears constantly in noise.")
    elif long_upper and span >= 0.6 * atr_value:
        add("Shooting star" if c <= o else "Inverted hammer", "down" if c <= o else "up",
            "Rallied during the day and gave it all back by the close. Sellers were waiting "
            "up there.")
    elif body <= 0.1 * span:
        add("Doji", "none",
            "Opened and closed at almost the same price after ranging in between — "
            "indecision. On its own it means the day was a draw.")

    return found


# ============================================================================ #
# Gaps, squeezes, volume, divergence
# ============================================================================ #
def gap_analysis(frame: pd.DataFrame, atr_value: float, lookback: int = 60) -> dict:
    """Unfilled opening gaps larger than half an average daily range.

    A gap is 'filled' once the price later trades back through the previous
    close. Unfilled gaps are watched because there is a band of prices at which
    almost nobody transacted, so there is no established support inside it —
    which is a structural observation, not a prediction. The often-repeated
    claim that gaps 'always fill' is not supported; many never do.
    """
    if len(frame) < 5 or not atr_value or atr_value <= 0:
        return {"usable": False, "gaps": []}

    span = frame.tail(lookback)
    previous_close = span["Close"].shift(1)
    gap_size = span["Open"] - previous_close
    price = float(frame["Close"].iloc[-1])

    gaps = []
    for date, size in gap_size.dropna().items():
        if abs(size) < 0.5 * atr_value:
            continue
        reference = float(previous_close.loc[date])
        after = span.loc[span.index > date]
        if size > 0:
            filled = bool((after["Low"] <= reference).any()) if len(after) else False
        else:
            filled = bool((after["High"] >= reference).any()) if len(after) else False
        gaps.append({
            "date": date.strftime("%Y-%m-%d"),
            "direction": "up" if size > 0 else "down",
            "from": reference,
            "to": float(span.loc[date, "Open"]),
            "sizeAtr": float(abs(size) / atr_value),
            "filled": filled,
            "distancePct": float(reference / price - 1.0),
        })

    unfilled = [g for g in gaps if not g["filled"]]
    return {"usable": True, "gaps": gaps[-8:], "unfilled": unfilled[-4:],
            "count": len(gaps), "unfilledCount": len(unfilled)}


def squeeze_state(frame: pd.DataFrame, window: int = 252) -> dict:
    """Bollinger bandwidth against its own recent range, plus whether it fired.

    THE DIRECTIONAL CLAIM IS THE ONE TO REFUSE. Quiet periods being followed by
    loud ones is a real and well-documented property of volatility (it clusters).
    That a squeeze resolves UPWARD is not documented at all, and is the version
    of the idea most write-ups sell. This reports the contraction and, if the
    price has already broken out of the bands, which way — as an observation
    about what happened, not a forecast of what will.
    """
    close = frame["Close"].astype("float64")
    lower, middle, upper = ind.bollinger_bands(close, 20, 2.0)
    bandwidth = ind.bollinger_bandwidth(lower, middle, upper).dropna()
    if len(bandwidth) < 40:
        return {"usable": False}

    recent = bandwidth.tail(window)
    latest = float(recent.iloc[-1])
    percentile = float((recent < latest).mean())
    in_squeeze = percentile <= 0.15

    # "Fired" means the bands were tight within the last ten bars and the price
    # has now closed outside them. Both halves are required: a close outside the
    # bands during an already-wide regime is just a big day.
    was_tight = bool((recent.tail(11).iloc[:-1] <= recent.quantile(0.15)).any())
    price = float(close.iloc[-1])
    fired_up = was_tight and price > float(upper.iloc[-1])
    fired_down = was_tight and price < float(lower.iloc[-1])

    return {
        "usable": True,
        "bandwidth": latest,
        "percentile": percentile,
        "inSqueeze": bool(in_squeeze),
        "firedDirection": "up" if fired_up else "down" if fired_down else None,
        "upperBand": _finite(upper.iloc[-1]),
        "lowerBand": _finite(lower.iloc[-1]),
    }


def volume_confirmation(frame: pd.DataFrame, window: int = 20) -> dict:
    """Whether the latest bar carried more trade than a normal day.

    Volume confirms; it does not cause. A breakout on twice the usual volume
    involved more participants than one on half, and that is the whole of the
    claim being made here.
    """
    volume = frame["Volume"].astype("float64")
    if len(volume) < window + 1:
        return {"usable": False}
    average = float(volume.tail(window + 1).iloc[:-1].mean())
    latest = float(volume.iloc[-1])
    if average <= 0:
        return {"usable": False}
    ratio = latest / average
    return {"usable": True, "ratio": float(ratio), "average": average, "latest": latest,
            "confirms": bool(ratio >= 1.5), "anaemic": bool(ratio <= 0.6)}


def momentum_divergence(frame: pd.DataFrame, order: int = 5,
                        lookback: int = 120) -> dict:
    """Price making a new extreme that the momentum reading does not confirm.

    Compares the last two confirmed swing highs (and lows) in price against RSI
    at those same bars. A higher price high with a lower RSI high is 'bearish
    divergence' and the reverse is bullish.

    THE HONEST CAVEAT, which is stated on the panel: divergence is extremely
    sensitive to how a swing is defined. Change `order` from 5 to 7 and
    divergences appear and disappear. It is a description of two series
    disagreeing, and it can persist for months before anything happens — which
    is precisely how it is misused.
    """
    span = frame.tail(lookback)
    if len(span) < 40:
        return {"usable": False}

    rsi = ind.rsi(span["Close"].astype("float64"))
    peaks, troughs = swing_points(span["High"], span["Low"], order)

    def compare(mask, price_column, kind):
        dates = [d for d in span.index[mask.to_numpy()] if np.isfinite(rsi.get(d, np.nan))]
        if len(dates) < 2:
            return None
        first, second = dates[-2], dates[-1]
        price_first = float(span.loc[first, price_column])
        price_second = float(span.loc[second, price_column])
        rsi_first, rsi_second = float(rsi.loc[first]), float(rsi.loc[second])
        if kind == "bearish" and price_second > price_first and rsi_second < rsi_first:
            return {"kind": "bearish", "from": first.strftime("%Y-%m-%d"),
                    "to": second.strftime("%Y-%m-%d"),
                    "priceFrom": price_first, "priceTo": price_second,
                    "rsiFrom": rsi_first, "rsiTo": rsi_second}
        if kind == "bullish" and price_second < price_first and rsi_second > rsi_first:
            return {"kind": "bullish", "from": first.strftime("%Y-%m-%d"),
                    "to": second.strftime("%Y-%m-%d"),
                    "priceFrom": price_first, "priceTo": price_second,
                    "rsiFrom": rsi_first, "rsiTo": rsi_second}
        return None

    bearish = compare(peaks, "High", "bearish")
    bullish = compare(troughs, "Low", "bullish")
    return {
        "usable": True,
        "bearish": bearish,
        "bullish": bullish,
        "swingOrder": order,
        "caveat": ("Divergence depends heavily on how a turning point is defined. Widening the "
                   "definition by two bars makes some of these appear and others vanish, and a "
                   "divergence can persist for months without resolving."),
    }


# ============================================================================ #
# Setups
# ============================================================================ #
# A setup is a NAMED, pre-registered configuration. The list is short and fixed,
# and it is checked in order, because the alternative — scanning for whatever
# happens to look interesting today — is how a screen turns into a horoscope.
#
# Each carries the honest grade of the idea behind it, not of this particular
# instance:
#   trend-continuation / breakout   moderate  (time-series momentum literature)
#   pullback-to-support             weak      (folklore with a plausible mechanism)
#   squeeze                         weak      (volatility clusters; direction does not)
def _trend_state(frame: pd.DataFrame, fast: int, slow: int) -> dict:
    close = frame["Close"].astype("float64")
    fast_ma = ind.ema(close, fast)
    slow_ma = ind.ema(close, slow)
    long_ma = close.rolling(200, min_periods=100).mean()

    price = float(close.iloc[-1])
    fast_value = _finite(fast_ma.iloc[-1])
    slow_value = _finite(slow_ma.iloc[-1])
    long_value = _finite(long_ma.iloc[-1])

    # A rising slow average is checked over a month rather than a day: a
    # one-bar change in a 50-day mean is arithmetic, not a change of trend.
    slow_rising = None
    if len(slow_ma.dropna()) > 21:
        slow_rising = bool(slow_ma.iloc[-1] > slow_ma.iloc[-22])

    aligned_up = (fast_value is not None and slow_value is not None
                  and price > fast_value > slow_value)
    aligned_down = (fast_value is not None and slow_value is not None
                    and price < fast_value < slow_value)

    return {
        "fastLength": fast, "slowLength": slow,
        "fast": fast_value, "slow": slow_value, "long": long_value,
        "slowRising": slow_rising,
        "alignment": "up" if aligned_up else "down" if aligned_down else "mixed",
        "aboveLong": None if long_value is None else bool(price > long_value),
        "price": price,
    }


def _consolidation(frame: pd.DataFrame, window: int) -> dict:
    """Range height over the window BEFORE today, as a share of price.

    A tight range is what makes a 'breakout' meaningful — a break out of a range
    that was already 40% wide has not resolved anything.

    Today's bar is excluded on purpose. Including it lets a breakout day's own
    high inflate the range it is breaking out of, which then inflates the
    measured-move target derived from that range: the projection quietly grows
    with the size of the move that triggered it.
    """
    span = frame.iloc[:-1].tail(window)
    if len(span) < max(10, window // 2):
        return {"usable": False}
    high = float(span["High"].max())
    low = float(span["Low"].min())
    price = float(frame["Close"].iloc[-1])
    if low <= 0:
        return {"usable": False}
    return {"usable": True, "high": high, "low": low, "height": high - low,
            "heightPct": float((high - low) / price), "bars": len(span),
            "tight": bool((high - low) / price < 0.15)}


def detect_setup(frame: pd.DataFrame, config: dict, levels: dict,
                 squeeze: dict, volume: dict) -> dict:
    """Which of the pre-registered configurations, if any, this price is in.

    Returns `name: None` when none of them fits, which is the most common
    answer and the one the panel is designed to display without embarrassment.
    """
    close = frame["Close"].astype("float64")
    price = float(close.iloc[-1])
    trend = _trend_state(frame, config["fast_ma"], config["slow_ma"])
    breakout_window = config["breakout_window"]
    consolidation = _consolidation(frame, breakout_window)
    rsi_value = _finite(ind.rsi(close).iloc[-1])
    atr_value = levels.get("atr") or 0.0

    # Donchian channel EXCLUDING today, so "broke out" means it cleared a level
    # that existed before this bar rather than a level it set itself.
    prior = frame.iloc[:-1].tail(breakout_window)
    channel_high = float(prior["High"].max()) if len(prior) else np.nan
    channel_low = float(prior["Low"].min()) if len(prior) else np.nan

    # --- 1. breakout ------------------------------------------------------
    if np.isfinite(channel_high) and price > channel_high and trend["alignment"] != "down":
        confirmed = volume.get("confirms", False)
        return {
            "name": f"{breakout_window}-day breakout",
            "direction": "long",
            "evidence": "moderate",
            "reason": (f"The price closed above the highest point of the previous "
                       f"{breakout_window} trading days ({channel_high:,.2f}), which is the "
                       f"classic breakout rule. "
                       + ("Volume on the day was heavier than usual, which is the "
                          "confirmation this rule normally asks for."
                          if confirmed else
                          "Volume was not unusually heavy, so the break is less well "
                          "supported than the rule would like.")),
            "anchor": channel_high,
            # INVALIDATION IS THE LEVEL THAT WAS BROKEN, not the far side of the
            # range. This first shipped pointing at `channel_low`, which put the
            # stop at the BOTTOM of the range the price had just cleared — 14.8%
            # and 3.1 average daily ranges away on a planted breakout, on a
            # horizon designed around 1.5. Two things were wrong with it. A
            # breakout fails when the price closes back INSIDE the range, not
            # when it traverses the whole of it; and a stop that wide drags the
            # reward-for-risk under 1 by construction, so a perfectly ordinary
            # setup was being reported as a bad one because of where the stop
            # was put rather than because of anything the price did.
            "invalidation": channel_high if np.isfinite(channel_high) else None,
            "consolidation": consolidation,
            "trend": trend,
        }

    # --- 2. breakdown -----------------------------------------------------
    if np.isfinite(channel_low) and price < channel_low and trend["alignment"] != "up":
        return {
            "name": f"{breakout_window}-day breakdown",
            "direction": "short",
            "evidence": "moderate",
            "reason": (f"The price closed below the lowest point of the previous "
                       f"{breakout_window} trading days ({channel_low:,.2f}). This app does "
                       f"not plan short positions, so the readout below describes where the "
                       f"structure sits rather than a trade."),
            "anchor": channel_low,
            "invalidation": channel_high if np.isfinite(channel_high) else None,
            "consolidation": consolidation,
            "trend": trend,
        }

    # --- 3. pullback within an uptrend ------------------------------------
    nearest_support = levels["supports"][0] if levels.get("supports") else None
    if (trend["alignment"] != "down" and trend.get("slowRising") and trend.get("aboveLong")
            and rsi_value is not None and rsi_value < 55
            and trend["slow"] is not None and atr_value > 0
            and abs(price - trend["slow"]) <= 2.0 * atr_value):
        return {
            "name": "Pullback to trend support",
            "direction": "long",
            "evidence": "weak",
            "reason": (f"The longer trend is still up — the {config['slow_ma']}-day average is "
                       f"rising and the price is above its 200-day — but the price has eased "
                       f"back to within reach of that average (RSI {rsi_value:.0f}). This is the "
                       f"'buy the dip in an uptrend' setup. It is widely used and thinly "
                       f"evidenced; the mechanism is plausible, the published support is not."),
            "anchor": trend["slow"],
            "invalidation": nearest_support["price"] if nearest_support else None,
            "consolidation": consolidation,
            "trend": trend,
        }

    # --- 4. volatility squeeze -------------------------------------------
    if squeeze.get("usable") and squeeze.get("inSqueeze"):
        return {
            "name": "Volatility squeeze",
            "direction": "none",
            "evidence": "weak",
            "reason": ("Price movement has contracted to the quietest it has been in about a "
                       "year. Quiet periods are genuinely followed by louder ones more often "
                       "than chance — volatility clusters. But nothing here says WHICH WAY the "
                       "loud move goes, and no entry can be planned from it. Wait for the break."),
            "anchor": None,
            "invalidation": None,
            "consolidation": consolidation,
            "trend": trend,
        }

    # --- 5. nothing -------------------------------------------------------
    return {
        "name": None,
        "direction": "none",
        "evidence": None,
        "reason": ("None of the setups this app looks for is present. The price is not breaking "
                   "out of its recent range, is not pulling back inside an established uptrend, "
                   "and is not unusually quiet. That is the ordinary state of most stocks on "
                   "most days, and inventing something here would be worse than saying so."),
        "anchor": None,
        "invalidation": None,
        "consolidation": consolidation,
        "trend": trend,
    }


# ============================================================================ #
# The risk plan: entry, stop, targets, and the ratio between them
# ============================================================================ #
def build_plan(setup: dict, levels: dict, config: dict,
               risk_budget: float = DEFAULT_RISK_BUDGET) -> dict:
    """Where the levels sit, if someone were to trade this setup.

    THE STOP IS PLACED BY STRUCTURE, WIDENED BY VOLATILITY. The order matters.
    A stop belongs just beyond a price the market actually defended, because
    that is the level whose failure would mean the reason for the trade was
    wrong. ATR then does two jobs: it buys a buffer past that level so ordinary
    noise does not trigger it, and it enforces a floor (`MIN_STOP_ATR`) below
    which a stop is not a risk control but a bet on tomorrow's randomness.

    THE TARGET IS THE NEXT LEVEL, NOT A ROUND NUMBER. Resistance overhead is
    where the last sellers were; projecting past it because the arithmetic gives
    a nicer risk/reward is how a 3:1 ratio gets manufactured. When there is no
    resistance overhead — the price is at a high — the target falls back to a
    measured move, and the readout says which one it used.

    POSITION SIZE IS EXPRESSED AS A SHARE OF THE ACCOUNT, per unit of risk
    budget, because this app does not know how much money anyone has. Risking
    1% with a stop 8% away means a position of 12.5% of the account. That is
    the arithmetic people most often get wrong in the direction that hurts.
    """
    if setup["direction"] != "long":
        return {"usable": False, "reason": (
            "No long setup, so there is nothing to place levels around. The support and "
            "resistance below still describe where the structure sits.")}

    price = float(levels["price"])
    atr_value = float(levels["atr"])
    if atr_value <= 0:
        return {"usable": False, "reason": "No usable range estimate to size a stop with."}

    entry = price
    stop_atr = float(config["stop_atr"])

    # --- stop -------------------------------------------------------------
    structural = None
    if setup.get("invalidation") is not None and setup["invalidation"] < entry:
        structural = float(setup["invalidation"])
    elif levels.get("supports"):
        structural = float(levels["supports"][0]["price"])

    volatility_stop = entry - stop_atr * atr_value
    widened = False
    if structural is not None:
        # A quarter of a range below the level, so a wick through it does not
        # count as a break of it.
        candidate = structural - 0.25 * atr_value
        floor = entry - MIN_STOP_ATR * atr_value
        stop = min(candidate, floor)
        basis = "structure"
        # Recording this was missed at first: taking the min() already applies
        # the floor, so a structural stop that sat inside daily noise was
        # silently widened and reported as though structure had chosen it.
        widened = candidate > floor
    else:
        stop = volatility_stop
        basis = "volatility"

    if entry - stop < MIN_STOP_ATR * atr_value:
        stop = entry - MIN_STOP_ATR * atr_value
        widened = True
    if stop <= 0:
        return {"usable": False, "reason": "A sensible stop would fall below zero."}

    risk_per_share = entry - stop

    # --- targets ----------------------------------------------------------
    targets = []
    for level in (levels.get("resistances") or [])[:2]:
        targets.append({
            "label": f"Next resistance ({level['touches']} prior "
                     f"turn{'s' if level['touches'] != 1 else ''})",
            "price": float(level["price"]),
            "basis": "structure",
        })
    consolidation = setup.get("consolidation") or {}
    if not targets and consolidation.get("usable") and setup.get("anchor"):
        # Measured move: a range that breaks is conventionally projected by its
        # own height. It is a convention, not a finding, and is labelled as one.
        projected = float(setup["anchor"]) + float(consolidation["height"])
        targets.append({"label": "Measured move (range height projected)",
                        "price": projected, "basis": "measured move"})
    if not targets:
        targets.append({"label": "Two average daily ranges up",
                        "price": entry + 2.0 * atr_value, "basis": "volatility"})

    for target in targets:
        target["rMultiple"] = float((target["price"] - entry) / risk_per_share)
        target["distancePct"] = float(target["price"] / entry - 1.0)

    first = targets[0]
    risk_reward = float(first["rMultiple"])

    return {
        "usable": True,
        "entry": float(entry),
        "entryNote": ("The current price. This app does not tell you to buy — it shows where "
                      "the levels would sit if you did."),
        "stop": float(stop),
        "stopBasis": basis,
        "stopWidened": widened,
        "stopDistancePct": float(risk_per_share / entry),
        "stopDistanceAtr": float(risk_per_share / atr_value),
        "structuralLevel": structural,
        "volatilityStop": float(volatility_stop),
        "targets": targets,
        "riskReward": risk_reward,
        # Share of the account that risks exactly `risk_budget` of it if the
        # stop is hit. Capped at 1.0 because "125% of the account" is leverage,
        # and the honest answer there is that the stop is too tight for the size.
        "riskBudget": float(risk_budget),
        "positionShare": float(min(1.0, risk_budget / (risk_per_share / entry))),
        "positionUncapped": float(risk_budget / (risk_per_share / entry)),
        "atr": atr_value,
    }


# ============================================================================ #
# Horizon assembly
# ============================================================================ #
def analyse_horizon(frame: pd.DataFrame, horizon: str,
                    risk_budget: float = DEFAULT_RISK_BUDGET) -> dict:
    """One complete readout: setup, levels, plan, context, and its own caveats."""
    config = HORIZONS[horizon]
    minimum = MIN_BARS[horizon]
    if len(frame) < minimum:
        return {"usable": False, "horizon": horizon, "label": config["label"],
                "window": config["window"],
                "reason": (f"The {config['label'].lower()} readout needs at least {minimum} "
                           f"trading days and this range has {len(frame)}. Widen the chart "
                           f"range rather than reading a number built from too little data.")}

    span = frame.tail(max(config["lookback"], minimum))
    atr_series = ind.atr(frame["High"], frame["Low"], frame["Close"])
    atr_value = _finite(atr_series.iloc[-1]) or 0.0

    levels = support_resistance(span, order=config["swing_order"])
    squeeze = squeeze_state(frame)
    volume = volume_confirmation(frame)
    setup = detect_setup(frame, config, levels, squeeze, volume)
    plan = build_plan(setup, levels, config, risk_budget=risk_budget)

    return {
        "usable": True,
        "horizon": horizon,
        "label": config["label"],
        "window": config["window"],
        "price": float(frame["Close"].iloc[-1]),
        "atr": atr_value,
        "atrPct": float(atr_value / float(frame["Close"].iloc[-1])) if atr_value else None,
        "setup": setup,
        "levels": levels,
        "plan": plan,
        "pivots": {
            "classic": period_pivots(frame, config["pivot_period"], "classic"),
            "fibonacci": period_pivots(frame, config["pivot_period"], "fibonacci"),
        },
        "vwap": vwap_profile(frame),
        "squeeze": squeeze,
        "volume": volume,
        "gaps": gap_analysis(frame, atr_value),
        "divergence": momentum_divergence(frame, order=config["swing_order"]),
        "candlesticks": candlestick_patterns(frame, atr_value),
        "undetectable": [{"name": name, "why": why} for name, why in UNDETECTABLE_PATTERNS],
    }


def analyse(frame: pd.DataFrame, risk_budget: float = DEFAULT_RISK_BUDGET) -> dict:
    """Both shorter horizons, from one already-fetched OHLCV frame."""
    return {
        "short": analyse_horizon(frame, "short", risk_budget=risk_budget),
        "mid": analyse_horizon(frame, "mid", risk_budget=risk_budget),
    }
