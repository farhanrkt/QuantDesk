"""
listings.py
===========
The whole-market universe: every listed name, cached with the date it was taken.

WHY A CACHE FILE RATHER THAN A FETCH PER SCAN
---------------------------------------------
The universe is the one input to a scan that changes on a timescale of months
while everything else changes daily. Re-fetching it on every run costs four
upstream requests to learn a fact that was true yesterday, and — worse — makes
the scanned population silently different between two runs an hour apart. A
report that says "ranked 812 of 837" is only checkable if the 837 is pinned.

So the universe is fetched deliberately, written to disk with an `asOf` date,
and every scan reads the file. Refreshing is an explicit act:

    python scripts/refresh_listings.py --market ID

That is the same discipline the five stamped artifacts in this directory follow,
and for the same reason `universes.py` gives: a slowly decaying fact should be
dated, not silently refreshed.

WHAT THE `asOf` DATE ACTUALLY MEANS, AND WHAT IT DOES NOT
---------------------------------------------------------
It means: on this date, the provider listed these symbols. It does NOT mean the
exchange listed them, and it does not mean they all still trade. The provider
carries delisted names for a while and picks up new ones late. That gap is
invisible from the output of a scan, which is why `staleness()` exists and why
the report prints the age of the universe in days rather than the date alone —
"taken 4 days ago" is readable; "2026-09-04" requires arithmetic the reader
should not have to do to notice a problem.

THE UNIVERSE IS NOT THE SCANNABLE SET
-------------------------------------
Of the ~840 Indonesian listings, a large minority cannot be analysed by this app
at all: too little history for a 252-day window, no volume, or a price pinned at
the exchange's Rp 50 tick floor. Those are dropped by `ranking.MIN_BARS` and by
the liquidity gate in `verdict.py`, and BOTH numbers are reported. A scan that
quietly ranked 300 of 837 and printed only the 300 would be claiming a
whole-market sweep while showing a third of it.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from . import market_data

# One file per market, beside the stamped measurement artifacts. Named by market
# code rather than by provider so swapping the source later does not orphan the
# cache — see `market_data`'s point 3 about owning the boundary.
_DIRECTORY = Path(__file__).parent

# Beyond this the universe is old enough that a reader should be told in words
# rather than left to read a date. Two months is roughly one IDX index review
# cycle, which is the shortest interval at which membership demonstrably moves.
STALE_AFTER_DAYS = 60

_CACHE: dict[str, dict] = {}


def path_for(market_code: str) -> Path:
    return _DIRECTORY / f"listings_{(market_code or '').strip().upper()}.json"


def refresh(market_code: str = "ID") -> dict:
    """Fetch the current listed universe and write it to disk. Network."""
    market = (market_code or "").strip().upper()
    rows = market_data.listed_equities(market)
    payload = {
        "market": market,
        "asOf": dt.date.today().isoformat(),
        "source": "Yahoo Finance equity screener, region filter",
        "count": len(rows),
        "note": ("Every common equity the provider listed for this market on `asOf`. "
                 "Not the exchange's official register: delisted names linger and new "
                 "ones arrive late. Ordered by market capitalisation, largest first."),
        "rows": rows,
    }
    target = path_for(market)
    target.write_text(json.dumps(payload, indent=1, sort_keys=False))
    _CACHE.pop(market, None)
    return payload


def load(market_code: str = "ID") -> Optional[dict]:
    """The cached universe for one market, or None if it was never fetched.

    Returns None rather than fetching. A function that silently reached the
    network when a file was missing would make a scan's population depend on
    whether someone had run the refresh script — the exact ambiguity the file
    exists to remove.
    """
    market = (market_code or "").strip().upper()
    if market in _CACHE:
        return _CACHE[market]
    try:
        payload = json.loads(path_for(market).read_text())
    except (OSError, ValueError):
        return None
    if not payload.get("rows"):
        return None
    _CACHE[market] = payload
    return payload


def staleness(payload: Optional[dict]) -> dict:
    """How old this universe is, in the terms the report prints it in."""
    if not payload or not payload.get("asOf"):
        return {"known": False, "days": None, "stale": None,
                "text": "No universe file — the scanned population is unknown."}
    try:
        taken = dt.date.fromisoformat(payload["asOf"])
    except ValueError:
        return {"known": False, "days": None, "stale": None,
                "text": f"Universe date {payload['asOf']!r} is unreadable."}

    days = (dt.date.today() - taken).days
    stale = days > STALE_AFTER_DAYS
    if days <= 0:
        text = "Universe list taken today."
    else:
        text = (f"Universe list taken {days} day{'' if days == 1 else 's'} ago "
                f"({payload['asOf']}).")
    if stale:
        text += (f" That is past {STALE_AFTER_DAYS} days: names delisted since then are "
                 f"still being scanned, and names listed since then are missing entirely. "
                 f"Re-run scripts/refresh_listings.py.")
    return {"known": True, "days": days, "stale": stale, "asOf": payload["asOf"],
            "text": text}


def symbols_for(market_code: str = "ID", limit: Optional[int] = None,
                min_market_cap: Optional[float] = None) -> list[str]:
    """The scannable symbol list, largest first, or an empty list if uncached.

    `limit` truncates from the SMALL end because the rows are capitalisation
    ordered — see `market_data.listed_equities` for why that is the right end to
    lose. `min_market_cap` is a separate knob and not a substitute: a name whose
    capitalisation the provider does not report has `None`, and dropping it for
    that would silently exclude every recent listing.
    """
    payload = load(market_code)
    if payload is None:
        return []
    rows = payload["rows"]
    if min_market_cap is not None:
        rows = [r for r in rows
                if r.get("marketCap") is None or r["marketCap"] >= min_market_cap]
    if limit is not None and limit > 0:
        rows = rows[:limit]
    return [r["symbol"] for r in rows]


SEARCH_MARKETS = ("US", "ID")
SEARCH_MAX = 20


def search(query: str, market_code: Optional[str] = None, limit: int = 8) -> list[dict]:
    """Listings matching what someone is typing into the command palette.

    WHY THIS IS HERE AND NOT A FETCH. The palette asks on every pause in typing.
    A call to the provider's lookup per keystroke would be slow, rate-limited
    and one more place the app talks to Yahoo; the committed listing files
    already hold every equity the provider listed for both markets, with names,
    and they ship in the function bundle. So this reads them and nothing else —
    and it does not touch `market_data`, which a test asserts.

    ORDERED BY HOW THE TEXT MATCHES, THEN BY THE FILE'S OWN ORDER. Match classes,
    best first: the symbol or its bare code exactly ("BBCA" finds both BBCA.JK
    and the US BBCA), a symbol prefix, a word in the name starting with the text,
    the text anywhere in the name. Within a class the file's order decides,
    which is market capitalisation, largest first.

    NEVER BY MARKET CAP ACROSS MARKETS. The US file is in dollars and the IDX
    file in rupiah; comparing those numbers would rank every Indonesian name
    above every American one by a factor of sixteen thousand. Across markets the
    tie breaks on the order the caller asked for — its own market first.

    Funds, indices, crypto and recent listings are not in the files. The palette
    always offers "open as typed" for that reason; this is a finder, not a gate.
    """
    text = (query or "").strip()
    if not text:
        return []
    upper = text.upper()
    lower = text.lower()
    limit = max(1, min(int(limit), SEARCH_MAX))
    preferred = (market_code or "").strip().upper()
    order = ([preferred] if preferred in SEARCH_MARKETS else []) + \
        [m for m in SEARCH_MARKETS if m != preferred]

    scored: list[tuple[int, int, int, dict]] = []
    for market_rank, market in enumerate(order):
        payload = load(market)
        if payload is None:
            continue
        suffix = ".JK" if market == "ID" else ""
        for index, row in enumerate(payload["rows"]):
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            base = symbol[: -len(suffix)] if suffix and symbol.endswith(suffix) else symbol
            name = str(row.get("name") or "")
            if upper in (symbol, base):
                match = 0
            elif symbol.startswith(upper):
                match = 1
            elif (" " + name.lower()).find(" " + lower) >= 0:
                # At a word boundary, so "bank central" finds "PT Bank Central
                # Asia" and "corp" does not find every "Incorporated".
                match = 2
            elif len(lower) >= 3 and lower in name.lower():
                match = 3
            else:
                continue
            scored.append((match, index, market_rank, {
                "symbol": symbol, "name": name or symbol, "market": market,
                "exchange": row.get("exchange"),
                "match": ("symbol", "prefix", "name", "contains")[match],
            }))
    scored.sort(key=lambda t: (t[0], t[2] if t[0] == 0 else 0, t[1], t[2]))
    return [row for *_, row in scored[:limit]]


def names_for(market_code: str = "ID") -> dict[str, str]:
    """Symbol to company name, for a report that should not print bare codes."""
    payload = load(market_code)
    if payload is None:
        return {}
    return {r["symbol"]: r.get("name") or r["symbol"] for r in payload["rows"]}


# --------------------------------------------------------------------------- #
# The cached listing, in the shape the ranking tier already speaks
#
# WHY IT IS TRUNCATED AND WHY THE TRUNCATION IS IN THE NAME.
#
# The ranking route scans up to 250 symbols per request because that is what
# fits in a serverless function's budget, and IDX has ~840 listings. Something
# has to give, and there are only two honest options: refuse the whole market
# through this route, or serve a stated prefix of it. Serving 250 while calling
# it "the Indonesian market" is the option that is not available — it is the
# same error `universes.py` refuses for the S&P 500, where the output looks
# right and the population is wrong.
#
# So the name carries the number, `truncated` is a field rather than a comment,
# and the full sweep stays in `scripts/scan_market.py`, which has no time limit
# and says so.
# --------------------------------------------------------------------------- #
def as_universe(market_code: str = "ID", limit: int = 250) -> Optional[dict]:
    """The cached listing as a `universes.get`-shaped entry, or None."""
    payload = load(market_code)
    if payload is None:
        return None
    market = (market_code or "").strip().upper()
    tickers = symbols_for(market, limit=limit)
    total = payload["count"]
    truncated = total > len(tickers)
    return {
        "id": f"{market.lower()}market",
        "name": (f"{market} market — {len(tickers)} largest"
                 if truncated else f"{market} market — all {total}"),
        "market": market,
        "asOf": payload["asOf"],
        "count": len(tickers),
        "listed": total,
        "truncated": truncated,
        "note": (
            f"Every {market} equity the provider listed on {payload['asOf']}, by market "
            f"capitalisation. "
            + (f"TRUNCATED: {len(tickers)} of {total}, because the ranking tier scans "
               f"at most that many per request. The smallest {total - len(tickers)} "
               f"listings are absent — most of them would not clear a turnover floor "
               f"anyway, but their absence here is a limit of this route, not a "
               f"judgement. `scripts/scan_market.py` sweeps all {total}."
               if truncated else
               "Not an index and not the exchange's register: delisted names linger "
               "and new ones arrive late.")),
        "tickers": tickers,
    }


def catalogue_entry(market_code: str = "ID", limit: int = 250) -> Optional[dict]:
    """The same entry without the ticker list, for the universe picker."""
    entry = as_universe(market_code, limit=limit)
    if entry is None:
        return None
    return {k: v for k, v in entry.items() if k != "tickers"}
