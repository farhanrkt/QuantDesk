"""
marketboard.py
==============
What moved the markets, each move set against what that instrument ordinarily
does.

WHY A BOARD, AND WHY BESIDE THE TICKER
--------------------------------------
Every lens in this app reads one company. None of them says that crude fell
four percent this morning or that the ten-year yield jumped, and a reader
working through a coal miner or a bank on such a day is reading it without the
fact most likely to be moving it. This is that context: the stock indices,
volatility, US rates, the dollar and the rupiah, energy, metals and bitcoin, in
one fetch shared by every reader.

It is not a lens. It casts no vote, nothing in `explain.for_synthesis` or
`pretrade.assess` reads it, and it carries no ticker: the request names nothing,
so every reader is served the same cached answer, and which of these a stock
actually moves with is matched in the browser from the exposure figures the
Trend tab already measured.

CALIBRATION, NOT COLOUR
-----------------------
A day's move has no good or bad. Crude falling helps an airline and hurts a
coal miner; a stronger dollar is good news for an exporter's revenue and bad
news for anyone carrying dollar debt. So nothing here is coloured by sign, and
every row's tone is neutral.

What a newcomer cannot do unaided is tell an ordinary move from an alarming
one, the same gap `/api/peers` closes for a stock's own figures. Each move is
therefore placed among that instrument's OWN daily moves over the past year, by
size: "larger than 97% of its days" means the same thing for the VIX, a yield
and bitcoin, without any of them borrowing another's scale. Each instrument is
read on its own sessions, so a year is 251 S&P sessions, 239 Jakarta ones and
365 bitcoin ones, and there is no annualisation constant to get wrong.

UNUSUAL, AND HOW OFTEN "UNUSUAL" HAPPENS
-----------------------------------------
A move at or above the 95th percentile of its own past year is called unusual.
By construction that happens on about one day in twenty for each instrument,
and with about twenty instruments on the board, something on it is unusual on a
large share of ordinary days. A flag that fires most days and does not say so
is the failure `screendomain.py` exists to prevent, so the board reports its own
base rate: the share of the past year's days on which at least one of these
instruments moved this much.

DECLARED ORDER, NEVER A LEADERBOARD
-----------------------------------
Rows come back in the order declared below and in fixed groups. A list sorted by
the size of today's move would be the strength ranking `exposure.py` refuses
for the same reason: it invites reading the top line as the day's real story,
when two moves at the 96th and 97th percentile are not distinguishable.

WHAT THIS SOURCE CANNOT SUPPLY
------------------------------
Several prices that matter most to the Indonesian exchange are not available
from this data source: Newcastle coal, nickel, tin, palm oil and the
Indonesian ten-year yield. They are named in `MISSING` with the reason rather
than left out, because a board without coal reads as a board that checked coal.

MEASURED BEFORE IT WAS WIRED, 1 NOVEMBER 2026
---------------------------------------------
* Every symbol below returned fresh daily bars over two years, and one batch of
  26 symbols took 1.6 seconds. Neither coal contract the source lists, `NCF=F`
  and `MTF=F`, returned anything.
* In one batch with `BTC-USD`, every weekday instrument came back with 208
  weekend bars, each a 0.00% day forward-filled from Friday. A distribution of
  daily moves padded with a hundred zeros puts every real move in a higher
  percentile than it earned. Hence `market_data.ohlcv_batch(own_sessions=True)`.
* `USDIDR=X` carried one Saturday bar, 31 October, with open, high, low and
  close all at 18,120 and no volume: an indicative quote on a closed market,
  which would have read as a +0.27% rupiah move. Instruments that do not trade
  at weekends drop weekend prints.
* Sessions in the past year, each on its own calendar: S&P 500 251, Jakarta
  Composite 239, Shanghai 242, Hang Seng 246, EUR/USD 259, bitcoin 365.

WHAT IT DOES NOT CLAIM
----------------------
No move here forecasts anything, including the next day's move in the same
instrument. The percentile describes the size of one day against one year; it
does not say the move was caused by anything, and the headlines shown beside the
board are labelled as mentioning a market, never as explaining it. Quotes are
the provider's, delayed by up to about twenty minutes, and the board says when
it fetched them.
"""

from __future__ import annotations

import copy
import datetime as dt
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from . import exposure, market_data

# A move at or above this percentile of its own past year is "unusual".
UNUSUAL_AT = 95.0

# Sessions in the past year needed before a percentile means anything. Below it
# the reading is a refusal, not a guess from a short sample.
MIN_HISTORY = 120

# The comparison window, in CALENDAR days, so each instrument contributes its
# own sessions rather than a fixed bar count borrowed from the US calendar.
YEAR_DAYS = 365

# What is fetched: two years, so "the largest fall since ..." can look further
# back than the comparison window.
HISTORY_DAYS = 730

# About three months of each instrument's own sessions, for the sparkline.
SPARK_SESSIONS = 63

MARKETS = ("US", "ID")

GROUPS: tuple[tuple[str, str], ...] = (
    ("stocks", "Stocks"),
    ("volatility", "Volatility"),
    ("rates", "US rates"),
    ("fx", "The dollar and currencies"),
    ("energy", "Energy"),
    ("metals", "Metals"),
    ("crypto", "Crypto"),
)

NO_QUOTE = ("The provider returned no recent price for it, so it is left blank rather "
            "than shown with an old one.")


@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    symbol: str
    group: str
    # How a move is measured: "pct" for prices, "bp" for yields quoted in
    # percent, "points" for an index whose level is itself a percentage.
    change: str
    unit: str
    markets: tuple[str, ...]
    # Which markets' compact strip shows it. At most eight per market.
    strip: tuple[str, ...] = ()
    note: str = ""
    # Whether it trades on Saturdays and Sundays. A weekend print on anything
    # that does not is an artefact and is dropped (see the module docstring).
    weekends: bool = False
    # The `exposure.REFERENCES` key this quote stands for, so the stock page can
    # mark it when the stock measurably moves with that reference.
    exposure_key: Optional[str] = None
    # Which headline topic in `news.HEADLINE_TOPICS` covers it.
    topic: str = "market"
    digits: int = 2
    # What the compact strip calls it, where "Dow Jones Industrial Average" does
    # not fit. Indonesian readers know the Jakarta Composite as IHSG.
    short: str = ""


# THE FOUR EXPOSURE REFERENCES ARE READ FROM `exposure.py`, NOT RE-TYPED. The
# stock page marks "this stock moves with ..." by matching keys, and a symbol
# typed twice is a symbol that will one day differ.
_REFERENCE = {reference.key: reference for reference in exposure.REFERENCES}


def _reference(key: str, name: str, group: str, unit: str, markets: tuple[str, ...],
               strip: tuple[str, ...], topic: str, note: Optional[str] = None,
               digits: int = 2, short: str = "") -> Instrument:
    reference = _REFERENCE[key]
    return Instrument(key=key, name=name, symbol=reference.symbol, group=group,
                      change="pct", unit=unit, markets=markets, strip=strip,
                      note=reference.note if note is None else note,
                      exposure_key=key, topic=topic, digits=digits, short=short)


US, ID, BOTH = ("US",), ("ID",), ("US", "ID")

INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument("sp500", "S&P 500", "^GSPC", "stocks", "pct", "index points", BOTH, BOTH,
               note="Five hundred large US companies, weighted by size."),
    Instrument("nasdaq", "Nasdaq Composite", "^IXIC", "stocks", "pct", "index points", US, US,
               note="Every stock listed on the Nasdaq, heavy in technology.", short="Nasdaq"),
    Instrument("dow", "Dow Jones Industrial Average", "^DJI", "stocks", "pct", "index points",
               US, note="Thirty large US companies, weighted by share price.", short="Dow"),
    Instrument("russell", "Russell 2000", "^RUT", "stocks", "pct", "index points", US,
               note="Two thousand smaller US companies."),
    Instrument("jkse", "Jakarta Composite", "^JKSE", "stocks", "pct", "index points", ID, ID,
               note="Every stock listed in Jakarta.", short="IHSG"),
    Instrument("lq45", "LQ45", "^JKLQ45", "stocks", "pct", "index points", ID,
               note="The forty-five most liquid Jakarta listings."),
    Instrument("hangseng", "Hang Seng", "^HSI", "stocks", "pct", "index points", ID,
               note="The largest companies listed in Hong Kong."),
    Instrument("shanghai", "Shanghai Composite", "000001.SS", "stocks", "pct", "index points",
               ID, note="Mainland China's main exchange.", short="Shanghai"),
    Instrument("vix", "VIX", "^VIX", "volatility", "points", "percent a year", BOTH, US,
               note=("How much option prices imply the S&P 500 will swing over the next 30 "
                     "days, as an annual percentage.")),
    Instrument("t13w", "US 13-week Treasury bill", "^IRX", "rates", "bp", "% yield", US,
               topic="rates", digits=3,
               note=("The shortest yield here. It sits close to the Federal Reserve's "
                     "policy rate."), short="US 3M"),
    Instrument("t10y", "US 10-year Treasury", "^TNX", "rates", "bp", "% yield", BOTH, BOTH,
               topic="rates", digits=3,
               note="The rate this app's US valuations build their discount rate on.", short="US 10Y"),
    Instrument("t30y", "US 30-year Treasury", "^TYX", "rates", "bp", "% yield", US,
               topic="rates", digits=3, note="The longest yield here.", short="US 30Y"),
    _reference("dollar", "Dollar index", "fx", "index", BOTH, BOTH, topic="dollar",
               note="The dollar against six major currencies.", short="DXY"),
    Instrument("usdidr", "USD/IDR", "USDIDR=X", "fx", "pct", "rupiah per dollar", ID, ID,
               topic="rupiah", digits=0,
               note="Rupiah per dollar, so a rise is a weaker rupiah."),
    Instrument("eurusd", "EUR/USD", "EURUSD=X", "fx", "pct", "dollars per euro", US,
               topic="dollar", digits=4,
               note="Dollars per euro, so a rise is a weaker dollar."),
    _reference("oil", "WTI crude", "energy", "dollars a barrel", BOTH, BOTH, topic="oil", short="WTI"),
    Instrument("brent", "Brent crude", "BZ=F", "energy", "pct", "dollars a barrel", BOTH,
               topic="oil", note="The international crude benchmark.", short="Brent"),
    Instrument("natgas", "US natural gas", "NG=F", "energy", "pct", "dollars per MMBtu", US,
               topic="gas", digits=3,
               note="Henry Hub, the US benchmark. It is not what Asian buyers pay for LNG.", short="Nat gas"),
    _reference("gold", "Gold", "metals", "dollars an ounce", BOTH, BOTH, topic="gold",
               note="Gold futures, in dollars per troy ounce."),
    Instrument("silver", "Silver", "SI=F", "metals", "pct", "dollars an ounce", BOTH,
               topic="silver", note="Silver futures, in dollars per troy ounce."),
    _reference("copper", "Copper", "metals", "dollars a pound", BOTH, ID, topic="copper",
               digits=3, note="Copper futures, in dollars per pound."),
    Instrument("bitcoin", "Bitcoin", "BTC-USD", "crypto", "pct", "dollars", BOTH, US,
               topic="bitcoin", weekends=True, digits=0,
               note=("Trades every day, weekends included, so its year is 365 sessions "
                     "rather than about 250.")),
)

# What the board would show if the source had it, and why it does not.
MISSING: tuple[dict, ...] = (
    {"key": "coal", "name": "Newcastle coal", "markets": ID,
     "reason": ("Neither coal contract this source lists returned prices when this was "
                "built. Coal companies on the Trend tab are measured against WTI crude "
                "instead, which was the closest tradeable stand-in the exposure study found.")},
    {"key": "nickel", "name": "Nickel", "markets": ID,
     "reason": "No London Metal Exchange price in this source."},
    {"key": "tin", "name": "Tin", "markets": ID,
     "reason": "No London Metal Exchange price in this source."},
    {"key": "palmoil", "name": "Crude palm oil", "markets": ID,
     "reason": "The Bursa Malaysia contract is not in this source."},
    {"key": "idgb10", "name": "Indonesian 10-year bond", "markets": ID,
     "reason": ("Not in this source. The app's IDX valuations use a stated fixed "
                "assumption for it instead.")},
)


def _finite(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def moves(closes: pd.Series, change: str) -> pd.Series:
    """Each session's move, in the unit the board reports it in.

    Yields arrive quoted in percent (4.93 is 4.93%), so a change of 0.11 is 11
    basis points. Reporting a yield's move as a percentage of itself, "+2.3%",
    is a number nobody in a rates market uses and a newcomer would misread as the
    yield having risen by 2.3 points.
    """
    if change == "pct":
        out = closes / closes.shift(1) - 1.0
    elif change == "bp":
        out = (closes - closes.shift(1)) * 100.0
    elif change == "points":
        out = closes - closes.shift(1)
    else:
        raise ValueError(f"unknown change kind {change!r}")
    return out.dropna()


def own_calendar(frame: pd.DataFrame, instrument: Instrument) -> pd.DataFrame:
    """The sessions this instrument actually trades, with weekend prints dropped."""
    if instrument.weekends:
        return frame
    return frame[frame.index.dayofweek < 5]


def _base(instrument: Instrument) -> dict:
    return {
        "key": instrument.key,
        "name": instrument.name,
        "symbol": instrument.symbol,
        "group": instrument.group,
        "change": instrument.change,
        "unit": instrument.unit,
        "markets": list(instrument.markets),
        "note": instrument.note or None,
        "exposureKey": instrument.exposure_key,
        "topic": instrument.topic,
        "digits": instrument.digits,
        "short": instrument.short or instrument.name,
        "weekends": instrument.weekends,
        # A day's move has no good or bad; see the module docstring.
        "tone": "neutral",
    }


def read(instrument: Instrument, frame: Optional[pd.DataFrame]) -> tuple[dict, Optional[pd.Series]]:
    """One row of the board, and the instrument's moves for the base rate."""
    row = _base(instrument)
    if frame is None or frame.empty:
        return {**row, "available": False, "reason": NO_QUOTE}, None

    sessions = own_calendar(frame, instrument)
    closes = sessions["Close"].astype("float64").dropna()
    if len(closes) < 2:
        return {**row, "available": False,
                "reason": "Fewer than two sessions came back, so there is no move to report."}, None

    history = moves(closes, instrument.change)
    latest = float(history.iloc[-1])
    as_of = closes.index[-1]
    past = history.iloc[:-1]
    year = past[past.index > as_of - pd.Timedelta(days=YEAR_DAYS)]

    percentile = unusual = None
    if len(year) >= MIN_HISTORY:
        # Strictly smaller, so a day that ties the year's largest move is not
        # reported as larger than all of them.
        percentile = float((year.abs() < abs(latest)).mean() * 100.0)
        unusual = bool(percentile >= UNUSUAL_AT)

    # The most recent earlier move at least as large in the same direction.
    largest_since, largest_in_history = None, False
    if latest != 0.0:
        same_way = past[np.sign(past) == np.sign(latest)]
        as_large = same_way[same_way.abs() >= abs(latest)]
        if len(as_large):
            largest_since = as_large.index[-1].date().isoformat()
        else:
            largest_in_history = True

    spark = closes.tail(SPARK_SESSIONS)
    return {
        **row,
        "available": True,
        "asOf": as_of.date().isoformat(),
        "last": _finite(closes.iloc[-1]),
        "previous": _finite(closes.iloc[-2]),
        "move": _finite(latest),
        "direction": "up" if latest > 0 else "down" if latest < 0 else "flat",
        "percentile": percentile,
        "unusual": unusual,
        "yearSessions": len(year),
        "largestSince": largest_since,
        "largestInHistory": largest_in_history,
        "historyFrom": closes.index[0].date().isoformat(),
        "spark": [round(float(v), 6) for v in spark.to_numpy()],
        "sparkFrom": spark.index[0].date().isoformat(),
    }, history


def base_rate(histories: dict[str, pd.Series], as_of: Optional[pd.Timestamp] = None) -> Optional[dict]:
    """How often at least one of these instruments had a move this unusual.

    Each instrument's line is its own 95th percentile of the past year; a day
    counts when any instrument that traded that day crossed its line.

    WEEKDAYS ONLY. Bitcoin trades on Saturdays and Sundays and nothing else on
    the board does, so counting weekends added 104 days on which only one
    instrument could cross its line, and the first live run reported 29% where
    the weekday figure is the honest one. Bitcoin's weekday moves still count.
    """
    usable = {key: series for key, series in histories.items() if len(series) >= MIN_HISTORY}
    if len(usable) < 2:
        return None
    end = as_of or max(series.index[-1] for series in usable.values())
    start = end - pd.Timedelta(days=YEAR_DAYS)
    flagged, traded = set(), set()
    for series in usable.values():
        year = series[(series.index > start) & (series.index <= end)
                      & (series.index.dayofweek < 5)]
        if len(year) < MIN_HISTORY:
            continue
        line = float(np.quantile(year.abs().to_numpy(), UNUSUAL_AT / 100.0))
        traded.update(day.date() for day in year.index)
        flagged.update(day.date() for day in year.index[year.abs().to_numpy() >= line])
    if not traded:
        return None
    return {
        "share": len(flagged) / len(traded),
        "days": len(traded),
        "flaggedDays": len(flagged),
        "instruments": len(usable),
        "from": min(traded).isoformat(),
        "to": max(traded).isoformat(),
    }


def build(frames: dict[str, pd.DataFrame], fetched_at: Optional[str] = None) -> dict:
    """The whole board from frames already fetched. Pure, so it is tested offline."""
    rows, histories = [], {}
    for instrument in INSTRUMENTS:
        row, history = read(instrument, frames.get(instrument.symbol))
        rows.append(row)
        if history is not None:
            histories[instrument.key] = history

    markets = {}
    for code in MARKETS:
        members = [i for i in INSTRUMENTS if code in i.markets]
        markets[code] = {
            "strip": [i.key for i in INSTRUMENTS if code in i.strip],
            "unusual": [row["key"] for row in rows
                        if code in row["markets"] and row.get("unusual")],
            "unavailable": [row["key"] for row in rows
                            if code in row["markets"] and not row["available"]],
            "baseRate": base_rate({i.key: histories[i.key] for i in members
                                   if i.key in histories}),
        }

    return {
        # Declaration order, never move order — see the module docstring.
        "groups": [{"key": key, "label": label} for key, label in GROUPS],
        "rows": rows,
        "missing": [{**item, "markets": list(item["markets"])} for item in MISSING],
        "markets": markets,
        "unusualAt": UNUSUAL_AT,
        "minHistory": MIN_HISTORY,
        "fetchedAt": fetched_at,
        "source": "Yahoo Finance",
        "delay": ("Quotes come from the provider and can be up to about twenty minutes "
                  "behind the market."),
    }


# HELD IN THE PROCESS FOR FOUR MINUTES, under the edge's five. The edge serves
# almost every request, but each region misses separately and a warm instance
# would otherwise download two years of 22 series again for every miss. A board
# with nothing on it is never held, so one failed moment is not repeated.
CACHE_SECONDS = 240
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()


def fetch(today: Optional[dt.date] = None) -> dict:
    """Fetch every instrument in one batch and build the board."""
    with _CACHE_LOCK:
        held = _CACHE.get("board")
        if held and time.monotonic() - held[0] < CACHE_SECONDS:
            return copy.deepcopy(held[1])
        end = today or dt.date.today()
        frames = market_data.ohlcv_batch(
            [instrument.symbol for instrument in INSTRUMENTS],
            end - dt.timedelta(days=HISTORY_DAYS), end, own_sessions=True)
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
        board = build(frames, fetched_at=fetched_at)
        if any(row["available"] for row in board["rows"]):
            _CACHE["board"] = (time.monotonic(), board)
        return copy.deepcopy(board)
