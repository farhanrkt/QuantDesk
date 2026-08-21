"""
ranking.py
==========
The breadth tier: score a whole universe on price-derived signals and rank it.

THE ARCHITECTURE, AND WHY IT IS SHAPED LIKE THIS
------------------------------------------------
The existing screener capped at twenty names because each one cost a separate
yfinance fetch plus an Isolation Forest fit inside a sixty-second serverless
function. The unlock is that yfinance will fetch MANY symbols in one call —
`yf.download(["AAPL","MSFT",...])` is one round trip per chunk rather than one
per name — so a hundred symbols of daily history costs a handful of upstream
requests instead of a hundred.

What does NOT batch is fundamentals. `Ticker.financials` and `.info` are one
call per symbol and take seconds each, so quality and valuation cannot be
computed universe-wide inside a request. This module therefore ranks on price
and volume ONLY, and the deepen step (`api/index.py`) runs the expensive lenses
on a shortlist the reader picks. The panel says so rather than showing an empty
"Quality" column for four hundred names.

RANKS, NOT SCORES
-----------------
Every signal is converted to its CROSS-SECTIONAL PERCENTILE within the scanned
universe before anything is combined. Two reasons.

First, the raw units are incommensurable: a 12-1 momentum of 0.34, a volatility
of 0.28 and a Chaikin money flow of 0.06 cannot be averaged into anything
meaningful. Percentiles can.

Second, and more importantly, a percentile states what the number actually
supports. "This is in the top decile of the Nasdaq-100 on momentum" is a claim
about this universe on this date. "This scores 78/100 on momentum" implies an
absolute scale that was never calibrated. The composite is a weighted mean of
ranks and is reported as such.

THE SIGNALS ARE NOT INDEPENDENT, AND THE OUTPUT PROVES IT
---------------------------------------------------------
Momentum, distance from the 52-week high, and relative strength against the
index are three ways of saying "it went up". Averaging them triple-counts one
fact and produces a composite that looks like a consensus of three tests when
it is closer to one. Rather than assert this in a footnote, `signal_correlation`
computes the actual rank correlation between every pair of signals ACROSS THE
SCANNED UNIVERSE and returns it, so a reader can see the double-counting in the
data in front of them.

MISSING SIGNALS ARE NEVER IMPUTED
---------------------------------
A name with too little history for 12-1 momentum gets `None`, not the universe
median. The composite is then a weighted mean over the signals that exist, with
the weights renormalised, and the row reports its own coverage. Filling a gap
with the median silently moves a name toward the middle of the pack and calls
it a measurement.

References
----------
Jegadeesh, N., & Titman, J. (1993). "Returns to Buying Winners and Selling
    Losers." Journal of Finance 48(1). (Cross-sectional momentum.)
George, T., & Hwang, C. (2004). "The 52-Week High and Momentum Investing."
    Journal of Finance 59(5).
Moskowitz, T., Ooi, Y. H., & Pedersen, L. H. (2012). "Time series momentum."
    Journal of Financial Economics 104(2).
Baker, M., Bradley, B., & Wurgler, J. (2011). "Benchmarks as Limits to
    Arbitrage: Understanding the Low-Volatility Anomaly." Financial Analysts
    Journal 67(1).
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from . import indicators as ind
from . import longterm as lt
from . import riskmodel

TRADING_DAYS = 252

# yfinance batches internally, but one enormous request is a single point of
# failure for the whole scan: any error and every name is lost. Chunking bounds
# the blast radius to fifty symbols and keeps each request's response small
# enough to parse well inside the function's memory budget.
CHUNK_SIZE = 50

# EVERY WINDOW-DEPENDENT SIGNAL IS MEASURED OVER EXACTLY THIS MANY BARS.
#
# This is not a tuning parameter, it is a correctness requirement, and getting it
# wrong is invisible in the output. The first version measured volatility, the
# worst drawdown and the distance from the high over "whatever history this
# symbol has". Two names with the IDENTICAL recent price path then scored
# differently purely because one listed earlier: on a planted pair, holdability
# came out 0.44 for the long-listed name and 0.34 for the young one, because the
# older name's window reached back far enough to include a crash the younger
# one's did not. In a CROSS-SECTIONAL ranking that is a systematic bias in
# favour of recently listed names, dressed up as a measurement about the stock.
#
# One year, the same year, for everyone.
RANK_WINDOW = 252

# Below this many bars a symbol is dropped rather than ranked on whatever
# fraction of its signals happened to compute. It is set by the hungriest
# signal, not by taste: the trend slope reads a genuine 200-day average across
# the last quarter, so it needs 200 + 63 bars before it means what it says.
MIN_BARS = 280


# ============================================================================ #
# Signal definitions
# ============================================================================ #
# `label` is the prose name used wherever there is room for it; `short` is the
# table-header form, because a twelve-column table scrolls sideways and long
# headers reveal a few letters at a time.
#
# `direction` is +1 when a HIGH raw value should rank well and -1 when a LOW one
# should. It is applied once, when the percentile is taken, so nothing
# downstream re-decides it — the same discipline as `_lib/explain.py`, and for
# the same reason: half of these are low-is-good and they sit in one table.
#
# `weight` is set by how well the underlying effect is supported, not by how
# interesting it is. That mapping (strong 1.0 / moderate 0.7 / weak 0.4) is a
# judgement, it is stated in the payload, and equal weighting would be a
# judgement too — there is no neutral choice here, only a declared one.
SIGNALS: list[dict] = [
    {
        "key": "momentum",
        "label": "Momentum",
        "short": "Momentum",
        "question": "Has it been going up over the past year?",
        "direction": 1,
        "evidence": "strong",
        "weight": 1.0,
        "detail": ("Return over the twelve months ending one month ago. The recent month is "
                   "skipped because very short-term moves tend to snap back and would "
                   "pollute the reading."),
    },
    {
        "key": "trend",
        "label": "Trend",
        "short": "Trend",
        "question": "Is the long-run average itself rising?",
        "direction": 1,
        "evidence": "moderate",
        "weight": 0.7,
        "detail": ("How fast the 200-day average has been rising over the last quarter, as an "
                   "annual rate. A price above a FALLING average is a bounce; above a rising "
                   "one is a trend."),
    },
    {
        "key": "nearHigh",
        "label": "Near its high",
        "short": "Near high",
        "question": "Is it close to the best price of the past year?",
        "direction": 1,
        "evidence": "moderate",
        "weight": 0.7,
        "detail": ("Distance from the 52-week high, where zero is at the high. Nearness to the "
                   "52-week high is a documented momentum variable in its own right."),
    },
    {
        "key": "lowVolatility",
        "label": "Steadiness",
        "short": "Steady",
        "question": "Does it get there without wild swings?",
        "direction": -1,
        "evidence": "moderate",
        "weight": 0.7,
        "detail": ("Annualised volatility, ranked so that CALMER scores better. Low-volatility "
                   "stocks have historically delivered better risk-adjusted returns than the "
                   "textbook says they should."),
    },
    {
        "key": "shallowDrawdown",
        "label": "Holdability",
        "short": "Holdable",
        "question": "How painful has owning it been?",
        "direction": -1,
        # Graded WEAK deliberately, and it is the grade that decides the weight.
        # This first shipped as "moderate" carrying a weak signal's weight of
        # 0.4, which is an inconsistency a test caught. Resolving it downward is
        # the honest direction: a shallow past drawdown says something real
        # about whether a holder could sit through it, and nothing much about
        # what the price does next. It is context that earns a small vote.
        "evidence": "weak",
        "weight": 0.4,
        "detail": ("The worst peak-to-trough fall in the scanned window, ranked so that a "
                   "SHALLOWER fall scores better. This is about whether you could have held "
                   "on, not about what it will return."),
    },
    {
        "key": "relativeStrength",
        "label": "Versus the index",
        "short": "Vs index",
        "question": "Has it beaten the market it belongs to?",
        "direction": 1,
        "evidence": "strong",
        "weight": 1.0,
        "detail": ("Six-month return minus the index's return over the same stretch. The real "
                   "alternative was never cash — it was the index fund."),
    },
    {
        "key": "flow",
        "label": "Money flow",
        "short": "Flow",
        "question": "Are recent days closing strong on volume?",
        "direction": 1,
        "evidence": "weak",
        "weight": 0.4,
        "detail": ("Chaikin money flow: whether recent days have closed near the top of their "
                   "range with volume behind them. Weak evidence — included because it is the "
                   "one volume-based signal that batches, and it is weighted accordingly."),
    },
]

SIGNAL_KEYS = [signal["key"] for signal in SIGNALS]
SIGNAL_BY_KEY = {signal["key"]: signal for signal in SIGNALS}


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


# ============================================================================ #
# Batch fetching
# ============================================================================ #
def _normalise(frame: pd.DataFrame) -> Optional[pd.DataFrame]:
    """One symbol's slice of a batch download, cleaned to the OHLCV contract."""
    if frame is None or frame.empty:
        return None
    needed = {"Open", "High", "Low", "Close"}
    if not needed.issubset(set(frame.columns)):
        return None

    out = frame.loc[:, [c for c in ("Open", "High", "Low", "Close", "Volume")
                        if c in frame.columns]].copy()
    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    for column in out.columns:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if "Volume" not in out.columns:
        out["Volume"] = 0.0
    out[["Open", "High", "Low", "Close"]] = out[["Open", "High", "Low", "Close"]].ffill()
    out["Volume"] = out["Volume"].fillna(0.0)
    out = out.dropna(subset=["Open", "High", "Low", "Close"])
    out = out[out["Close"] > 0]
    return out if not out.empty else None


def batch_download(symbols: list[str], start: dt.date, end: dt.date,
                   chunk_size: int = CHUNK_SIZE) -> dict[str, pd.DataFrame]:
    """Daily history for many symbols in as few upstream calls as possible.

    THIS IS THE WHOLE UNLOCK for the breadth tier. The per-symbol path costs one
    HTTP round trip each; this costs one per chunk. A symbol that fails to fetch
    is simply absent from the result — a scan should not abort because one name
    was delisted last week.
    """
    frames: dict[str, pd.DataFrame] = {}
    unique = list(dict.fromkeys(s.strip().upper() for s in symbols if s and s.strip()))

    for position in range(0, len(unique), chunk_size):
        chunk = unique[position:position + chunk_size]
        try:
            raw = yf.download(
                chunk,
                start=start,
                end=end + dt.timedelta(days=1),
                interval="1d",
                auto_adjust=True,
                actions=False,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception:
            continue
        if raw is None or raw.empty:
            continue

        # DO NOT special-case a one-symbol chunk on the assumption it arrives
        # flat. With `group_by="ticker"` yfinance returns a two-level column
        # index even for a single ticker, so the "obvious" shortcut handed a
        # MultiIndex frame to the normaliser, failed its column check and
        # dropped the symbol without a word. That silently lost the benchmark
        # index on every scan, and would lose the last chunk of any universe
        # whose length is one more than a multiple of the chunk size. Branch on
        # the SHAPE that came back, never on the length of the request.
        if isinstance(raw.columns, pd.MultiIndex):
            present = set(raw.columns.get_level_values(0))
            for symbol in chunk:
                if symbol not in present:
                    continue
                cleaned = _normalise(raw[symbol])
                if cleaned is not None:
                    frames[symbol] = cleaned
        elif len(chunk) == 1:
            cleaned = _normalise(raw)
            if cleaned is not None:
                frames[chunk[0]] = cleaned
    return frames


# ============================================================================ #
# Per-symbol signals
# ============================================================================ #
def price_signals(frame: pd.DataFrame,
                  benchmark: Optional[pd.Series] = None) -> dict:
    """Every rankable signal for one symbol, or None where history is too short.

    Nothing here is imputed and nothing is clipped. A signal that cannot be
    computed comes back as None and is excluded from that row's composite.
    """
    close = frame["Close"].astype("float64")
    high = frame["High"].astype("float64")
    low = frame["Low"].astype("float64")
    volume = frame["Volume"].astype("float64")
    if len(close) < MIN_BARS:
        return {key: None for key in SIGNAL_KEYS}

    # The common window. Every signal below that depends on a lookback reads
    # from these, never from the full fetched history — see RANK_WINDOW.
    window_close = close.tail(RANK_WINDOW)
    window_high = high.tail(RANK_WINDOW)

    out: dict[str, Optional[float]] = {}

    # --- momentum: 12 months ending one month ago -------------------------
    out["momentum"] = (_finite(close.iloc[-22] / close.iloc[-253] - 1.0)
                       if len(close) > 253 else None)

    # --- trend: annualised slope of the 200-day average over a quarter ----
    # `min_periods=200` rather than a shorter warm-up: an average computed from
    # 150 bars is a 150-day average, and comparing one name's 150-day slope with
    # another's 200-day slope is the same category of error RANK_WINDOW exists
    # to prevent. MIN_BARS guarantees there is enough history for the real thing.
    average = close.rolling(200, min_periods=200).mean().dropna()
    if len(average) > 63 and float(average.iloc[-64]) > 0:
        quarterly = float(average.iloc[-1] / average.iloc[-64] - 1.0)
        out["trend"] = _finite((1.0 + quarterly) ** 4 - 1.0)
    else:
        out["trend"] = None

    # --- distance from the 52-week high -----------------------------------
    year_high = float(window_high.max())
    out["nearHigh"] = (_finite(float(close.iloc[-1]) / year_high - 1.0)
                       if year_high > 0 else None)

    # --- volatility and drawdown, over the same year for every name --------
    returns = window_close.pct_change().dropna()
    out["lowVolatility"] = (_finite(returns.std(ddof=1) * np.sqrt(TRADING_DAYS))
                            if len(returns) > 20 else None)
    profile = lt.drawdown_profile(window_close)
    out["shallowDrawdown"] = (abs(_finite(profile.get("maxDrawdown")) or 0.0)
                              if profile.get("usable") else None)

    # --- six-month excess return against the index ------------------------
    out["relativeStrength"] = None
    if benchmark is not None and len(close) > 126:
        joined = pd.concat([close, benchmark], axis=1, join="inner").dropna()
        joined.columns = ["stock", "index"]
        if len(joined) > 126:
            stock = float(joined["stock"].iloc[-1] / joined["stock"].iloc[-127] - 1.0)
            market = float(joined["index"].iloc[-1] / joined["index"].iloc[-127] - 1.0)
            out["relativeStrength"] = _finite(stock - market)

    # --- money flow --------------------------------------------------------
    if float(volume.sum()) > 0:
        cmf = ind.chaikin_money_flow(high, low, close, volume).dropna()
        out["flow"] = _finite(cmf.iloc[-1]) if len(cmf) else None
    else:
        out["flow"] = None

    return out


# ============================================================================ #
# Cross-sectional ranking
# ============================================================================ #
def percentile_ranks(values: list[Optional[float]], direction: int) -> list[Optional[float]]:
    """Where each value sits within the universe, as 0-100, missing preserved.

    Ties share the average rank, which is what `pandas.rank(method="average")`
    does and is the right behaviour: three names with identical momentum should
    not be ordered by whichever happened to be fetched first.
    """
    series = pd.Series(values, dtype="float64")
    if series.notna().sum() < 2:
        return [None] * len(values)
    ranked = series.rank(pct=True, ascending=(direction > 0), method="average") * 100.0
    return [None if pd.isna(v) else float(v) for v in ranked]


def signal_correlation(rows: list[dict]) -> dict:
    """Rank correlation between every pair of signals, across this scan.

    The honest counterweight to a composite score. Momentum, nearness to the
    52-week high and relative strength are three phrasings of "it went up"; when
    they correlate at 0.8 the composite is not averaging three independent
    opinions, and this table is what lets a reader see that rather than take the
    caveat on trust.
    """
    frame = pd.DataFrame([
        {key: (row["signals"].get(key) or {}).get("percentile") for key in SIGNAL_KEYS}
        for row in rows
    ])
    usable = [key for key in SIGNAL_KEYS if frame[key].notna().sum() >= 5]
    if len(usable) < 2:
        return {"available": False,
                "reason": "Too few names with complete signals to measure overlap."}

    matrix = frame[usable].corr(method="spearman")
    pairs = []
    for i, first in enumerate(usable):
        for second in usable[i + 1:]:
            value = _finite(matrix.loc[first, second])
            if value is not None:
                pairs.append({"a": first, "b": second, "correlation": value})
    pairs.sort(key=lambda p: -abs(p["correlation"]))

    strongest = pairs[0] if pairs else None

    # HOW MANY OPINIONS IS THIS COMPOSITE ACTUALLY AVERAGING?
    #
    # Seven columns look like seven tests. When momentum and trend correlate at
    # 0.98 they are one test wearing two labels, and the composite silently
    # gives that single fact nearly double weight. The participation ratio of
    # the correlation matrix's eigenvalues answers the question numerically:
    #
    #     effective N = (sum of eigenvalues)^2 / sum(eigenvalues^2)
    #
    # It equals the column count when the signals are independent and collapses
    # toward 1 as they become redundant. Reporting it turns the caveat from an
    # assertion into a measurement the reader can check.
    effective = None
    try:
        eigenvalues = np.linalg.eigvalsh(matrix.to_numpy(dtype="float64"))
        eigenvalues = eigenvalues[np.isfinite(eigenvalues)]
        eigenvalues = np.clip(eigenvalues, 0.0, None)
        denominator = float(np.sum(eigenvalues ** 2))
        if denominator > 0:
            effective = float(np.sum(eigenvalues) ** 2 / denominator)
    except np.linalg.LinAlgError:
        effective = None

    return {
        "available": True,
        "signals": usable,
        "matrix": {first: {second: _finite(matrix.loc[first, second]) for second in usable}
                   for first in usable},
        "pairs": pairs,
        "effectiveSignals": effective,
        "measuredSignals": len(usable),
        "reading": _overlap_reading(strongest, effective, len(usable)),
    }


def _overlap_reading(strongest: Optional[dict], effective: Optional[float],
                     measured: int) -> str:
    if strongest is None:
        return "No pair of signals could be compared on this scan."
    text = (f"The most overlapping pair is {SIGNAL_BY_KEY[strongest['a']]['label']} and "
            f"{SIGNAL_BY_KEY[strongest['b']]['label']}, correlated at "
            f"{strongest['correlation']:+.2f} across this scan. ")
    text += ("They are measuring close to the same thing, so the composite is counting that "
             "fact more than once. "
             if abs(strongest["correlation"]) > 0.7 else
             "Nothing here is duplicating another signal badly. ")
    if effective is not None:
        text += (f"Across all of them, the {measured} signals carry about "
                 f"{effective:.1f} signals' worth of independent information — "
                 + ("so the table is closer to one opinion than to a consensus of many."
                    if effective < measured * 0.5 else
                    "which is a fair spread for measures built from the same price series."))
    return text


def rank_universe(frames: dict[str, pd.DataFrame],
                  benchmark: Optional[pd.Series] = None,
                  weights: Optional[dict[str, float]] = None) -> dict:
    """Score and order every symbol that fetched, with a full breakdown per row."""
    active = {key: (weights or {}).get(key, SIGNAL_BY_KEY[key]["weight"])
              for key in SIGNAL_KEYS}

    raw: dict[str, dict] = {}
    for symbol, frame in frames.items():
        if len(frame) >= MIN_BARS:
            raw[symbol] = price_signals(frame, benchmark)

    symbols = sorted(raw)
    if not symbols:
        return {"rows": [], "signals": SIGNALS, "weights": active,
                "correlation": {"available": False,
                                "reason": "No symbol had enough history to rank."}}

    ranks: dict[str, list[Optional[float]]] = {}
    for key in SIGNAL_KEYS:
        ranks[key] = percentile_ranks([raw[s][key] for s in symbols],
                                      SIGNAL_BY_KEY[key]["direction"])

    rows = []
    for position, symbol in enumerate(symbols):
        breakdown = {}
        weighted_total = 0.0
        weight_total = 0.0
        for key in SIGNAL_KEYS:
            percentile = ranks[key][position]
            breakdown[key] = {
                "raw": raw[symbol][key],
                "percentile": percentile,
                "weight": active[key],
            }
            if percentile is not None and active[key] > 0:
                weighted_total += percentile * active[key]
                weight_total += active[key]

        # Renormalising over the AVAILABLE weights rather than the full set is
        # what keeps a name with two missing signals from being dragged toward
        # zero for the crime of being newly listed. `coverage` reports how much
        # of the intended weight actually contributed.
        composite = weighted_total / weight_total if weight_total > 0 else None
        frame = frames[symbol]
        rows.append({
            "ticker": symbol,
            "composite": _finite(composite),
            "coverage": float(weight_total / sum(active.values())) if active else 0.0,
            "signalsAvailable": sum(1 for key in SIGNAL_KEYS
                                    if breakdown[key]["percentile"] is not None),
            "signalsTotal": len(SIGNAL_KEYS),
            "signals": breakdown,
            "latestClose": float(frame["Close"].iloc[-1]),
            "bars": len(frame),
            "asOf": frame.index[-1].strftime("%Y-%m-%d"),
        })

    rows.sort(key=lambda r: (r["composite"] is None, -(r["composite"] or 0.0)))
    for position, row in enumerate(rows, start=1):
        row["rank"] = position

    return {
        "rows": rows,
        "signals": SIGNALS,
        "weights": active,
        "correlation": signal_correlation(rows),
    }


def scan(symbols: list[str], market_code: str = "US", period_days: int = 500,
         weights: Optional[dict[str, float]] = None) -> dict:
    """Fetch a universe in batch and rank it. One entry point for the route."""
    end_date = dt.date.today()
    start_date = end_date - dt.timedelta(days=int(period_days * 1.5))

    frames = batch_download(symbols, start_date, end_date)

    benchmark_symbol = riskmodel.MARKET_INDEX.get((market_code or "US").upper(), "^GSPC")
    benchmark = None
    index_frames = batch_download([benchmark_symbol], start_date, end_date)
    if benchmark_symbol in index_frames:
        benchmark = index_frames[benchmark_symbol]["Close"].astype("float64")

    result = rank_universe(frames, benchmark=benchmark, weights=weights)
    requested = list(dict.fromkeys(s.strip().upper() for s in symbols if s and s.strip()))
    ranked = {row["ticker"] for row in result["rows"]}

    result.update({
        "requested": len(requested),
        "fetched": len(frames),
        "ranked": len(result["rows"]),
        "benchmark": benchmark_symbol if benchmark is not None else None,
        # Named, not counted. "17 symbols were dropped" is unactionable; the
        # list tells the reader whether it was a typo or a delisting.
        "missing": [s for s in requested if s not in ranked],
        "minBars": MIN_BARS,
        "window": RANK_WINDOW,
    })
    return result
