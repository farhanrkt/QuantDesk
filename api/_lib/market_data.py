"""
market_data.py
==============
The only module in this codebase that imports yfinance.

WHY THIS EXISTS, ARGUED FROM BUGS RATHER THAN ARCHITECTURE
----------------------------------------------------------
Before this module there were six importers of yfinance and four different ways
to fetch a price. An audit of that arrangement found four bugs, and all four
lived in the same seam:

  * `fast_info.get("last_price")` returned None on EVERY valuation, because
    FastInfo tests membership against camel-case keys and only translates snake
    case afterwards. The primary price source was dead code for months and the
    engine silently fell through to the slow `.info` scrape.
  * The company cache handed out its own dict, so the manual-price rescue form
    rewrote the day's cached price for every later request on that instance.
  * Two confluence legs raced the same empty cache and both ran the full fetch,
    doubling the load the cache existed to halve.
  * The valuation read Yahoo's QUOTE endpoint while the technical and flow
    lenses read its CHART endpoint. The two disagree intermittently — 308.37
    against 309.35 on one observed request, at rest — so the rail reported a gap
    to fair value using a price no other panel displayed.

None of those is a mistake in an engine. Each is what happens when four modules
each invent their own idea of "get me the data for this symbol". One module that
owns the boundary is the fix for the class, not for the four instances.

THREE THINGS IT BUYS BEYOND TIDINESS
------------------------------------
1. ONE NORMALISATION. `whale.py` used to hand back whatever yfinance returned,
   tz-aware index and all, which is why `index.py` had to tz-localize its frames
   by hand before the event study could use them. Every frame that leaves here
   satisfies the same contract, so no caller compensates for the source.

2. ONE PLACE TO PUT A CACHE. Today the caches are in-process dicts, which on a
   serverless platform means per-instance. Moving them behind Redis or Vercel KV
   is now a change in this file rather than in five.

3. ONE PLACE TO SWAP THE PROVIDER. yfinance is an unofficial scraper of an
   undocumented endpoint with no service guarantee. That is fine for a personal
   tool and disqualifying the moment anyone depends on it. Swapping to a
   licensed feed is now a one-file change instead of a rewrite.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not interpret. No indicator, no score, no judgement — it fetches,
normalises, and reports failure in one consistent way. Anything that reads
meaning into the numbers belongs in the engine that owns that meaning.
"""

from __future__ import annotations

import datetime as dt
import threading
from typing import Optional, Sequence

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "yfinance is required. Install with `pip install -r requirements.txt`."
    ) from exc

from . import symbols

OHLCV = ("Open", "High", "Low", "Close", "Volume")

# One batch request covers this many symbols. Chunking bounds the blast radius:
# an error takes out fifty names rather than the whole scan, and each response
# stays small enough to parse well inside the function's memory budget.
CHUNK_SIZE = 50


class MarketDataError(Exception):
    """A fetch that produced nothing usable.

    ONE ERROR TYPE FOR THE BOUNDARY. The engines used to raise `DataFetchError`,
    `TechnicalError` and `ValuationError` for the identical upstream failure, so
    a caller wanting to treat "no data" uniformly had to know all three. Engines
    still raise their own type where the failure is theirs; this one means the
    data never arrived.
    """


# --------------------------------------------------------------------------- #
# The OHLCV contract
# --------------------------------------------------------------------------- #
def normalise(frame: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Clean one symbol's history into the shape every engine expects.

    TZ-NAIVE, DEDUPED, NUMERIC, FORWARD-FILLED, POSITIVE. Each step is here
    because some caller used to do it and some other caller did not:

    * a tz-aware index compares unequal against a naive one, which is why the
      event study had to strip the zone from three frames by hand;
    * yfinance occasionally repeats a session, and a duplicated index silently
      double-counts a day in every rolling window;
    * a column can arrive as object dtype, where arithmetic quietly produces
      objects rather than raising;
    * a missing OHLC value forward-fills, because a gap in the middle of a bar
      is a reporting artefact rather than a real price of zero — while Volume
      fills with 0, because no trades IS zero volume;
    * a non-positive close breaks every log and ratio downstream.

    Returns None rather than an empty frame when nothing survives, so callers
    branch on one thing.
    """
    if frame is None or frame.empty:
        return None
    if isinstance(frame.columns, pd.MultiIndex):
        # FIND THE LEVEL HOLDING THE FIELD NAMES; DO NOT ASSUME ITS POSITION.
        # yfinance nests columns two different ways depending on the call, and
        # they are transposes of each other: `download(sym)` yields
        # (field, ticker) while `download(list, group_by="ticker")` yields
        # (ticker, field). Dropping a fixed level therefore works for one shape
        # and silently produces a frame of ticker-named columns for the other —
        # which fails the field check below and drops the symbol without a word.
        # That is exactly how the technical lens lost every US ticker the first
        # time this module was wired in.
        fields = set(OHLCV)
        for level in range(frame.columns.nlevels):
            if fields & set(frame.columns.get_level_values(level)):
                frame = frame.copy()
                frame.columns = frame.columns.get_level_values(level)
                frame = frame.loc[:, ~frame.columns.duplicated(keep="first")]
                break
        else:
            return None
    if not {"Open", "High", "Low", "Close"}.issubset(set(frame.columns)):
        return None

    out = frame.loc[:, [c for c in OHLCV if c in frame.columns]].copy()
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
    out.index.name = "Date"
    return out if not out.empty else None


def ohlcv(symbol: str, *, period: Optional[str] = None,
          start: Optional[dt.date] = None, end: Optional[dt.date] = None,
          auto_adjust: bool = True) -> Optional[pd.DataFrame]:
    """Daily history for one symbol, normalised. None when nothing came back.

    Takes either a `period` ("2y") or a `start`/`end` pair, because the two
    call sites in this app genuinely want different things: the flow lens thinks
    in look-back windows and the technical lens in explicit ranges. `end` is
    inclusive here — yfinance treats it as exclusive, and every caller that
    forgot cost itself the most recent bar.
    """
    ticker = (symbol or "").strip().upper()
    if not ticker:
        return None
    try:
        if period:
            raw = yf.Ticker(ticker).history(period=period, auto_adjust=auto_adjust)
        else:
            raw = yf.download(
                ticker, start=start,
                end=(end + dt.timedelta(days=1)) if end else None,
                interval="1d", auto_adjust=auto_adjust, actions=False,
                progress=False, threads=False,
            )
    except Exception:
        return None
    return normalise(raw)


def ohlcv_batch(symbols_list: Sequence[str], start: dt.date, end: dt.date,
                chunk_size: int = CHUNK_SIZE) -> dict[str, pd.DataFrame]:
    """Daily history for many symbols in as few upstream calls as possible.

    THIS IS WHAT MAKES THE BREADTH TIER POSSIBLE. The per-symbol path costs one
    round trip each; this costs one per chunk. A symbol that fails to fetch is
    simply absent from the result — a scan should not abort because one name was
    delisted last week.
    """
    frames: dict[str, pd.DataFrame] = {}
    unique = list(dict.fromkeys(s.strip().upper() for s in symbols_list if s and s.strip()))

    for position in range(0, len(unique), chunk_size):
        chunk = unique[position:position + chunk_size]
        try:
            raw = yf.download(
                chunk, start=start, end=end + dt.timedelta(days=1), interval="1d",
                auto_adjust=True, actions=False, progress=False,
                group_by="ticker", threads=True,
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
                cleaned = normalise(raw[symbol])
                if cleaned is not None:
                    frames[symbol] = cleaned
        elif len(chunk) == 1:
            cleaned = normalise(raw)
            if cleaned is not None:
                frames[chunk[0]] = cleaned
    return frames


# --------------------------------------------------------------------------- #
# Quote fields
# --------------------------------------------------------------------------- #
def fast_value(fast_info, key: str):
    """Read one field from a yfinance `FastInfo`, which is NOT a dict.

    `FastInfo.get()` looks the key up in `self.keys()` before translating it,
    and `keys()` is CAMEL CASE — `lastPrice`, not `last_price`. Subscripting
    translates snake case; `.get()` does not. So `fast_info.get("last_price")`
    silently returns the default while `fast_info["last_price"]` returns 309.35.

    That is not a hypothetical. `.get("last_price")` was returning None on every
    single valuation, so the primary price source was dead and the engine always
    fell through to `info["currentPrice"]`. On a thin listing where `info` has no
    quote field — precisely the IDX names the manual-rescue form exists for — the
    user was sent to that form for a price fast_info was holding all along.

    `shares` and `currency` were unaffected only by luck: those two keys happen
    to be spelled identically in both conventions.
    """
    try:
        return fast_info[key]
    except Exception:
        return None


def currency(symbol: str, default: str = "USD") -> str:
    """Reporting currency for a symbol, or the default when unavailable."""
    try:
        value = fast_value(yf.Ticker(symbol).fast_info, "currency")
    except Exception:
        return default
    return value.upper() if isinstance(value, str) and value else default


def earnings_dates(symbol: str) -> list:
    """Announced and historical earnings dates, or [] when unavailable.

    Used to tag an anomaly that sits beside an earnings print, where the drift
    afterwards is a documented effect rather than anyone's footprint.
    """
    try:
        table = yf.Ticker(symbol).earnings_dates
        return list(table.index) if table is not None else []
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Index history, cached for the day
# --------------------------------------------------------------------------- #
_INDEX_CACHE: dict[tuple[str, str, str], pd.DataFrame] = {}
_INDEX_LOCK = threading.Lock()


def index_history(symbol: str, period: str = "2y") -> Optional[pd.DataFrame]:
    """A benchmark index's history, normalised and cached for the current day.

    The benchmark is fetched by the beta estimator, the relative-strength
    section and the event study, often within one request. Caching by
    (symbol, period, date) keeps a confluence run from paying three times.
    """
    key = ((symbol or "").upper(), period, dt.date.today().isoformat())
    with _INDEX_LOCK:
        cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached

    frame = ohlcv(symbol, period=period)
    if frame is None:
        return None
    with _INDEX_LOCK:
        if len(_INDEX_CACHE) > 64:
            _INDEX_CACHE.clear()      # only ever hold the current day
        _INDEX_CACHE[key] = frame
    return frame


# --------------------------------------------------------------------------- #
# Fundamentals, cached for the day
# --------------------------------------------------------------------------- #
_COMPANY_CACHE: dict[tuple[str, str], dict] = {}

# Guards `_COMPANY_CACHE` and `_COMPANY_LOCKS` below. Held for dictionary
# operations only, NEVER across a network call — a global lock spanning the
# fetch would serialise unrelated symbols.
_COMPANY_GUARD = threading.Lock()
_COMPANY_LOCKS: dict[tuple[str, str], threading.Lock] = {}


def _company_lock(key: tuple[str, str]) -> threading.Lock:
    """One lock per cache key, so two callers race only when they want the
    same symbol."""
    with _COMPANY_GUARD:
        if len(_COMPANY_LOCKS) > 256 and key not in _COMPANY_LOCKS:
            # Bound the table. A lock currently held stays alive in its holder's
            # own frame; dropping it here only means a concurrent caller for
            # that key would mint a fresh one and could double-fetch — the old
            # behaviour, at a boundary reached once per 256 distinct symbols in
            # one warm instance.
            _COMPANY_LOCKS.clear()
        return _COMPANY_LOCKS.setdefault(key, threading.Lock())


def _safe_float(value, default=np.nan) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if np.isfinite(out) else default


# Rows on a financial statement that are COUNTS rather than money. Scaling a
# share count by an exchange rate would be meaningless; every consumer uses them
# only in ratios, where uniform scaling is harmless, but excluding them keeps the
# converted statement honest line by line rather than merely arithmetically safe.
_COUNT_ROW_HINTS = ("shares", "share issued", "share number", "number")


def _convert_statements(data: dict, rate: float) -> None:
    """Scale money on the three statements into the trading currency, in place.

    ONLY THE STATEMENTS AND THE INFO FIGURE DERIVED FROM THEM. Verified against
    ITMG.JK, which reports in USD and trades in IDR: the income, balance and cash
    flow statements and `netIncomeToCommon` are all on the USD scale, while
    `price`, `market_cap`, `shares` and the dividend-per-share figures come from
    the quote feed already denominated in rupiah. Scaling the second group would
    replace one currency error with another.
    """
    for key in ("income", "balance", "cashflow"):
        frame = data.get(key)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        scaled = frame.copy()
        for label in scaled.index:
            name = str(label).lower()
            if any(hint in name for hint in _COUNT_ROW_HINTS):
                continue
            scaled.loc[label] = pd.to_numeric(scaled.loc[label], errors="coerce") * rate
        data[key] = scaled

    if np.isfinite(data.get("net_income_info", np.nan)):
        data["net_income_info"] = data["net_income_info"] * rate


def company(ticker: str) -> dict:
    """Statements, price and dividends for one symbol, cached for the day.

    Four or five network calls sit behind this. The quality lens reads the SAME
    statements the valuation does, so without a cache a confluence run would
    fetch every filing twice. Keyed by date because filings do not change
    intraday.

    THE CALLER GETS ITS OWN DICT, and that is not defensive habit — it is the
    fix for a cache-poisoning bug. `valuation.analyze` overwrites `data["price"]`
    when the user supplies a manual price through the rescue form. While this
    returned the cached object itself, that assignment rewrote the cache: every
    later request for the same symbol on the same warm instance — including
    other people's, including the quality lens, which never asked for an
    override — was valued at a price one user typed into a form.

    The copy is SHALLOW, which is exactly the boundary needed: the
    mutable-by-assignment fields are the top-level scalars, and the statement
    frames underneath are read-only everywhere. Deep-copying three DataFrames
    per call would buy nothing and cost real time.

    CONCURRENT CALLERS FOR THE SAME SYMBOL FETCH ONCE, NOT TWICE.
    `/api/confluence` launches the valuation and quality legs simultaneously, so
    both looked at an empty cache in the same instant, both missed, and both ran
    the full fetch — doubling the heaviest leg's load on a rate-limited scraper
    at the exact moment the cache was meant to halve it. The second caller now
    waits on the first and re-checks.
    """
    key = (ticker.upper(), dt.date.today().isoformat())

    cached = _COMPANY_CACHE.get(key)
    if cached is not None:
        return dict(cached)

    with _company_lock(key):
        # Re-read: whoever held this lock before us has already filled it in.
        cached = _COMPANY_CACHE.get(key)
        if cached is not None:
            return dict(cached)

        result = _company_uncached(ticker)
        with _COMPANY_GUARD:
            if len(_COMPANY_CACHE) > 128:
                _COMPANY_CACHE.clear()
            _COMPANY_CACHE[key] = result

    return dict(result)


def _company_uncached(ticker: str) -> dict:
    try:
        tk = yf.Ticker(ticker)
    except Exception:
        tk = None

    info = {}
    if tk is not None:
        try:
            info = tk.info or {}
        except Exception:
            info = {}

    price, shares, ccy = np.nan, np.nan, None
    if tk is not None:
        try:
            fi = tk.fast_info
            price = _safe_float(fast_value(fi, "last_price"))
            shares = _safe_float(fast_value(fi, "shares"))
            ccy = fast_value(fi, "currency")
        except Exception:
            pass

    if not np.isfinite(price):
        price = _safe_float(info.get("currentPrice"), _safe_float(info.get("regularMarketPrice")))
    if not np.isfinite(shares):
        shares = _safe_float(info.get("sharesOutstanding"))

    # THE PRICE EVERY OTHER LENS DISPLAYS WINS.
    #
    # The two figures above come from Yahoo's QUOTE endpoint. The technical and
    # flow lenses read its CHART endpoint, and the two do not always agree: on
    # one observed AAPL request the quote said 308.37 while the chart's last bar
    # said 309.35, at rest, in the same request. The rail then reported how far
    # the market price sat from fair value using a number no other panel on the
    # page displayed — one ticker in the header, two prices underneath, no error.
    #
    # So the last daily bar close is canonical and the quote is the fallback.
    # This costs nothing in freshness: during a session the daily series carries
    # a forming bar whose close IS the last trade, and outside one the bar close
    # is the official close, the right anchor for a valuation regardless.
    price_source = "quote endpoint (fast_info)" if np.isfinite(price) else None
    price_as_of = None
    bars = ohlcv(ticker, period="5d")
    if bars is not None and len(bars):
        bar_close = _safe_float(bars["Close"].iloc[-1])
        if np.isfinite(bar_close) and bar_close > 0:
            price = bar_close
            price_source = "last daily close"
            price_as_of = bars.index[-1].strftime("%Y-%m-%d")

    def statement(attr):
        if tk is None:
            return pd.DataFrame()
        try:
            df = getattr(tk, attr)
            return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    ttm_dividend, div_history = np.nan, pd.DataFrame()
    if tk is not None:
        try:
            divs = tk.dividends
            if divs is not None and len(divs):
                divs = divs.copy()
                divs.index = pd.to_datetime(divs.index, utc=True).tz_localize(None)
                cutoff = divs.index.max() - pd.Timedelta(days=365)
                ttm_dividend = float(divs[divs.index > cutoff].sum())
                annual = divs.groupby(divs.index.year).sum().sort_index(ascending=False)
                div_history = pd.DataFrame(
                    {"Year": annual.index.astype(str), "Dividend / Share": annual.values}
                ).head(6)
        except Exception:
            pass

    # `ok` MEANS "THIS SYMBOL RESOLVED TO SOMETHING REAL", and it used to be
    # `bool(info) or isfinite(price)`. yfinance returns a non-empty `info` dict
    # even for a symbol that does not exist, so that test was true whenever the
    # scrape returned anything at all — a delisted ticker came back ok=True with
    # a NaN price and three empty statements. The valuation engine caught it
    # anyway by checking the price itself, but the quality lens trusted the flag
    # and reported "no financial statements came back for this listing", which
    # reads as "this company files nothing" rather than "this company does not
    # exist". Conflating a designed refusal with a failed lookup devalues the
    # refusal, which is one of the more useful things this app does.
    usable_statements = any(
        isinstance(df, pd.DataFrame) and not df.empty
        for df in (statement("income_stmt"), statement("balance_sheet"),
                   statement("cashflow"))
    )
    trading_ccy = (ccy or info.get("currency") or "").upper() or None
    financial_ccy = (info.get("financialCurrency") or "").upper() or None

    out = {
        "ok": bool(np.isfinite(price) or usable_statements),
        "name": info.get("longName") or info.get("shortName") or ticker,
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
        "price": price,
        "shares": shares,
        "beta": _safe_float(info.get("beta")),
        "currency": trading_ccy or "",
        # THE CURRENCY THE STATEMENTS ARE WRITTEN IN, which is not always the
        # one the shares trade in. Yahoo reports both and the app used to read
        # only the first, so a company reporting in USD and trading in IDR was
        # valued in dollars and labelled in rupiah — out by the exchange rate,
        # which for that pair is a factor of about seventeen thousand.
        "financial_currency": financial_ccy,
        "market_cap": _safe_float(info.get("marketCap")),
        "dividend_rate": _safe_float(info.get("dividendRate")),
        "trailing_dividend_rate": _safe_float(info.get("trailingAnnualDividendRate")),
        "dividend_yield_raw": _safe_float(info.get("dividendYield")),
        "trailing_dividend_yield_raw": _safe_float(info.get("trailingAnnualDividendYield")),
        "payout_ratio": _safe_float(info.get("payoutRatio")),
        "roe_info": _safe_float(info.get("returnOnEquity")),
        "net_income_info": _safe_float(info.get("netIncomeToCommon")),
        "ttm_dividend": ttm_dividend,
        "dividend_history": div_history,
        "price_source": price_source,
        "price_as_of": price_as_of,
        "income": statement("income_stmt"),
        "balance": statement("balance_sheet"),
        "cashflow": statement("cashflow"),
        # The rate applied, or None when none was needed or none was available.
        # A consumer that cannot tolerate mixed currencies checks this rather
        # than re-deriving the question.
        "fx_rate": None,
    }

    # CONVERT AT THE BOUNDARY, so everything downstream sees ONE currency. This
    # is thirteen of the forty-six names in the IDX30 and LQ45 — coal, nickel and
    # gas producers that sell in dollars and report in dollars while their shares
    # trade in rupiah. When no rate can be fetched the statements are left alone
    # and `fx_rate` stays None, which is the signal for the valuation engine to
    # refuse rather than quietly mix the two.
    if financial_ccy and trading_ccy and financial_ccy != trading_ccy:
        rate = fx_rate(financial_ccy, trading_ccy)
        if rate:
            _convert_statements(out, rate)
            out["fx_rate"] = rate

    return out


def last_close(symbol: str, period: str = "5d") -> Optional[float]:
    """The most recent close for a symbol, without the full OHLCV contract.

    For quote-like series — a yield, an index level — where a caller wants one
    number and the four-column bar the OHLCV contract insists on would be an
    obstacle rather than a guarantee.
    """
    try:
        history = yf.Ticker((symbol or "").strip().upper()).history(period=period)
    except Exception:
        return None
    if history is None or history.empty or "Close" not in history:
        return None
    close = history["Close"].dropna()
    if not len(close):
        return None
    value = _safe_float(close.iloc[-1])
    return float(value) if np.isfinite(value) else None


# --------------------------------------------------------------------------- #
# Foreign exchange
# --------------------------------------------------------------------------- #
_FX_CACHE: dict[tuple[str, str, str], float] = {}


def fx_rate(base: str, quote: str) -> Optional[float]:
    """Spot rate to convert one unit of `base` into `quote`. None if unavailable.

    WHY A VALUATION APP NEEDS THIS AT ALL. A company can report its accounts in
    one currency and trade in another, and on the Indonesian exchange that is not
    an edge case: thirteen of the forty-six names in the IDX30 and LQ45 report in
    US dollars because they sell coal, nickel or gas priced in dollars, while
    their shares trade in rupiah. Valuing dollar cash flows and comparing the
    result against a rupiah share price is out by the exchange rate — a factor of
    roughly seventeen thousand, which is not a rounding error but does produce a
    confident, plausible-looking number.

    Yahoo spells USD pairs both ways, `IDR=X` and `USDIDR=X`, and only the second
    form generalises to crosses, so the explicit pair is tried first.
    """
    base, quote = (base or "").strip().upper(), (quote or "").strip().upper()
    if not base or not quote:
        return None
    if base == quote:
        return 1.0

    key = (base, quote, dt.date.today().isoformat())
    cached = _FX_CACHE.get(key)
    if cached is not None:
        return cached

    for symbol in (f"{base}{quote}=X", f"{quote}=X" if base == "USD" else None):
        if not symbol:
            continue
        value = last_close(symbol)
        if value is not None and value > 0:
            if len(_FX_CACHE) > 64:
                _FX_CACHE.clear()          # only ever hold the current day
            _FX_CACHE[key] = float(value)
            return float(value)
    return None


# --------------------------------------------------------------------------- #
# Risk-free rate, cached for the day
# --------------------------------------------------------------------------- #
_RATE_CACHE: dict[str, tuple[float, str]] = {}


def risk_free_rate(market_code: str, fallback: float) -> tuple[float, str]:
    """The rate every discount rate is built on, with its provenance.

    Only the US rate is live; the IDX figure is a static assumption and says so
    in its own label rather than implying a measurement.
    """
    if market_code != "US":
        return fallback, "IndoGB 10Y proxy (static assumption)"

    today = dt.date.today().isoformat()
    cached = _RATE_CACHE.get(today)
    if cached is not None:
        return cached

    # NOT through `ohlcv`. That contract requires a full OHLC bar and forward
    # fills against it, which is right for a price series an indicator will read
    # and needlessly strict for a yield quote where only the last Close matters.
    # Demanding four columns to obtain one number would make the discount rate
    # fail for a shape that is perfectly usable.
    close = last_close("^TNX", period="5d")
    if close is not None:
        result = (close / 100.0, "US 10Y Treasury (^TNX, live)")
        _RATE_CACHE.clear()          # only ever hold the current day
        _RATE_CACHE[today] = result
        return result
    # A FAILED FETCH IS NOT CACHED. Pinning the fallback for the rest of the day
    # would turn one bad moment into a day of quietly wrong discount rates.
    return fallback, "US 10Y Treasury (fallback default)"


def base_symbol(symbol: str) -> str:
    """Re-exported so callers need not import `symbols` for this alone."""
    return symbols.base_code(symbol)
