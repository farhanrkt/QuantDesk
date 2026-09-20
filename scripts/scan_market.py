#!/usr/bin/env python3
"""
scan_market.py
==============
Score a whole market and rank it by what to do about each name.

    python scripts/scan_market.py --market ID --deepen 40
    python scripts/scan_market.py --market ID --deepen all --hold BBCA,TLKM
    python scripts/scan_market.py --market ID --universe lq45 --deepen 45

WHY THIS IS A SCRIPT AND NOT A ROUTE
------------------------------------
The funnel below costs, for a full IDX sweep, about 17 batched price requests
plus one fundamentals fetch per deepened name at several seconds each. That is
minutes, and the serverless function this app deploys as has sixty seconds. The
breadth half of the funnel already ships as `/api/rank` because it fits; the
depth half already ships as `/api/rank/deepen` capped at a handful of names
because that is what fits. Scanning 837 listings and deepening forty of them
does not fit, and pretending otherwise would produce a route that times out on
exactly the input it was built for.

So it runs here, on a laptop, with a cache and a written report — which is also
the honest shape for a tool one person uses.

THE FUNNEL, AND WHY IT NARROWS IN THIS ORDER
--------------------------------------------
1. UNIVERSE. Every listing the provider knows about, from `listings.py`, with
   the date it was taken. Not recited from memory — see that module.

2. PRICE HISTORY, in batch. `market_data.ohlcv_batch` is what makes 837 names
   affordable: one request per fifty symbols rather than one per name.

3. TRADEABILITY, before anything expensive. This is deliberately the SECOND
   filter and not the last. Most of the Indonesian market cannot absorb a
   personal order, thin names carry the most extreme percentiles on every price
   signal, and a scan that ranked first and filtered afterwards would spend all
   its fundamentals budget on names it was about to discard. Filtering here also
   means the cross-sectional percentiles in step 4 are taken across the
   TRADEABLE universe, which is the only population the answer is about.

4. BREADTH RANK. `ranking.rank_universe` over the survivors: seven price signals,
   cross-sectional percentiles, one composite each.

5. DEPTH. The four lenses, one symbol at a time, on a shortlist — plus anything
   named with `--hold`, because a name already owned needs a reading whatever
   its rank, and a scan that only deepens its own favourites can never tell its
   owner to sell.

6. VERDICT. `verdict.py` blends what came back, shrinks it by how much evidence
   there actually was, subtracts calibrated pre-trade flags, and applies the
   gates. Then the report prints the published measurement of whether any of
   this predicts anything, at the top, before the table.

WHAT THE CACHE IS FOR
---------------------
The deepen step is the expensive one and its inputs move once a quarter. The
cache is keyed by symbol AND date, so re-running the scan on the same day to
change a threshold costs no network at all, and running it tomorrow refetches.
Delete `.scan_cache/` to force a cold run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import collections
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import numpy as np                                                  # noqa: E402
import pandas as pd                                                 # noqa: E402

from _lib import (basket, chartlayers, field, listings, market_data,  # noqa: E402
                  microstructure, neglect, ownership, patterns, pretrade,
                  ranking, scanlog, structure, symbols, tape, trackrecord,
                  universes, verdict, volumeprofile)
from _lib.jsonsafe import clean                                      # noqa: E402

# The four lens payloads are imported from the route module rather than
# reimplemented, so a scan computes byte-for-byte what the app's own pages show.
# A second implementation would drift, and the drift would be invisible: two
# plausible valuations for one company, one in the report and one on screen.
from index import (quality_payload, technical_payload,               # noqa: E402
                   valuation_payload, whale_payload, _valuation_kwargs)

CACHE_DIR = ROOT / ".scan_cache"

# How many days of cached lens payloads to keep. The cache is keyed by day so
# that a re-run on the same afternoon is free and a run tomorrow refetches, and
# that is the right freshness rule — but it means each day leaves a complete
# copy behind, and a full-market sweep is about 500MB of them.
#
# MEASURED, NOT GUESSED: three days of Indonesian scans came to 528MB, and a
# daily full sweep would reach the free space on this machine inside a month.
# Old days are never read — `cache_path` only ever looks at today — so keeping
# them is pure cost.
CACHE_KEEP_DAYS = 4


def prune_cache(keep: int = CACHE_KEEP_DAYS, today: str = "") -> list[str]:
    """Delete cached lens payloads older than the most recent `keep` days.

    Returns the day directories removed. Never touches today's, and never
    touches anything it cannot parse as a date — a stray directory in here is
    somebody's, and silently deleting it would be worse than leaving it.
    """
    if not CACHE_DIR.exists():
        return []
    days = []
    for child in CACHE_DIR.iterdir():
        if not child.is_dir():
            continue
        try:
            dt.date.fromisoformat(child.name)
        except ValueError:
            continue
        days.append(child)

    removed = []
    for stale in sorted(days, key=lambda path: path.name, reverse=True)[keep:]:
        if stale.name == today:
            continue
        shutil.rmtree(stale, ignore_errors=True)
        removed.append(stale.name)
    return removed
REPORT_DIR = ROOT / "reports"

# How much history to pull per name. `ranking.MIN_BARS` needs 280 bars and the
# long-horizon lens wants years, so this is generous — it is one batched request
# either way and the marginal cost of more history is bytes, not round trips.
HISTORY_DAYS = 900

# Turnover is measured over the same window `microstructure.liquidity_profile`
# uses, so the cheap pre-filter and the full gate cannot disagree about whether
# a name trades.
TURNOVER_WINDOW = 21

# Which rows get a drawn chart in the report. Everything directional: a reader
# who is being told to buy or to reduce is the one who needs to see the tape,
# and HOLD is what the scanner says when it has nothing to say.
CHARTED_ACTIONS = frozenset({"STRONG_BUY", "BUY", "REDUCE", "AVOID"})

# How many rows keep their chart in the written report. Sixty: enough to cover a
# buy list and the tail a reader checks for contrast, and about 700KB of SVG
# rather than the 27MB a 2,110-name US sweep produced when every directional row
# kept one.
MAX_CHARTS = 60


# --------------------------------------------------------------------------- #
# Stage 1-2: universe and prices
# --------------------------------------------------------------------------- #
def resolve_universe(args) -> tuple[list[str], dict]:
    """The symbols to scan, and a description of where they came from."""
    # Company names come from the cached listing whatever the universe is. A
    # report that prints bare codes for an index scan and full names for a
    # whole-market one would be two different documents, and "ADRO.JK" is not a
    # name anybody reads at a glance. Empty when nothing is cached — a missing
    # name degrades to the ticker rather than to an error.
    known_names = listings.names_for(args.market)

    if args.tickers:
        # `@path` READS THE LIST FROM A FILE, because the lists worth scanning
        # this way are long. The US names a specialist hunt has to cover are the
        # ones BELOW the turnover floor — measured: the uncovered share runs 0%
        # in the highest turnover quintile to 11% in the lowest — and there are
        # about 5,800 of them. That is a 40KB command line, which a shell will
        # accept and nobody can read, edit or repeat.
        source = args.tickers
        if source.startswith("@"):
            listed = Path(source[1:]).expanduser()
            if not listed.exists():
                raise SystemExit(f"No ticker list at {listed}")
            source = listed.read_text()
        # A `#` comment and blank lines are allowed, so a saved list can say
        # what it is and where it came from.
        source = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
        raw = [t.strip() for t in source.replace("\n", ",").split(",") if t.strip()]
        picked = [symbols.resolve(t, args.market) for t in raw]
        return picked, {"kind": "custom", "label": f"{len(picked)} pasted symbols",
                        "asOf": None, "staleness": None, "names": known_names}

    if args.universe:
        entry = universes.get(args.universe)
        if entry is None:
            raise SystemExit(f"Unknown universe '{args.universe}'. "
                             f"Known: {', '.join(u['id'] for u in universes.catalogue())}")
        return entry["tickers"], {"kind": "index", "label": entry["name"],
                                  "asOf": entry["asOf"], "note": entry["note"],
                                  "staleness": None, "names": known_names}

    payload = listings.load(args.market)
    if payload is None:
        raise SystemExit(
            f"No listed universe cached for {args.market}. Run:\n"
            f"    python scripts/refresh_listings.py --market {args.market}")
    picked = listings.symbols_for(args.market, limit=args.limit)
    return picked, {
        "kind": "wholeMarket",
        "label": f"Every {args.market} listing the provider knows",
        "asOf": payload["asOf"],
        "source": payload.get("source"),
        "listed": payload["count"],
        "staleness": listings.staleness(payload),
        "names": known_names,
    }


# Below this many names a within-sector percentile is arithmetic on noise: a
# "top quartile" among four is one name, and the rank changes if any of the
# other three had a different Tuesday.
MIN_SECTOR_NAMES = 8


def _rank_within_sector(verdicts: list[dict], say) -> None:
    """Add each name's percentile inside its own sector, in place.

    Groups smaller than `MIN_SECTOR_NAMES` get None rather than a percentile,
    and the row says so. Ranking four names against each other produces a
    number that looks like the others and means far less.
    """
    groups: dict[str, list[dict]] = {}
    for entry in verdicts:
        sector = entry.get("sector")
        if sector and entry.get("score") is not None:
            groups.setdefault(sector, []).append(entry)

    ranked = 0
    for sector, members in groups.items():
        if len(members) < MIN_SECTOR_NAMES:
            for entry in members:
                entry["sectorRank"] = {
                    "sector": sector, "names": len(members), "percentile": None,
                    "reason": (f"only {len(members)} scanned names in {sector}, under "
                               f"the {MIN_SECTOR_NAMES} a percentile needs")}
            continue
        order = sorted(members, key=lambda e: e["score"])
        for position, entry in enumerate(order):
            entry["sectorRank"] = {
                "sector": sector, "names": len(members),
                "percentile": 100.0 * (position + 1) / len(order),
                "rank": len(order) - position,
            }
        ranked += len(members)
    if ranked:
        say(f"  Ranked within sector where the group was large enough: {ranked} names "
            f"across {sum(1 for m in groups.values() if len(m) >= MIN_SECTOR_NAMES)} "
            f"sectors.")


def turnover_of(frame: pd.DataFrame, window: int = TURNOVER_WINDOW) -> Optional[float]:
    """Median daily turnover in the listing's own currency, or None.

    The cheap half of `microstructure.liquidity_profile`, computed inline
    because the full profile fits three spread estimators per name and the
    pre-filter runs on hundreds of names to answer one question.
    """
    if frame is None or len(frame) < 5:
        return None
    values = (frame["Close"].astype("float64")
              * frame["Volume"].astype("float64")).tail(window)
    if values.empty:
        return None
    median = float(values.median())
    return median if np.isfinite(median) else None


# --------------------------------------------------------------------------- #
POPULATION_NOTE = """\
WHAT --include-illiquid CHANGES, BEYOND HOW MANY ROWS YOU GET

By default this scan applies the turnover floor BEFORE ranking, so every
percentile in the output is taken across the tradeable population — the only
population the answer is about. "83rd percentile on momentum" means 83rd of the
names you could actually buy.

With --include-illiquid the floor is applied only as a GATE, and the ranking runs
across every listing with usable history. The same company will show a DIFFERENT
percentile in the two runs, and neither is wrong: they answer different questions.

  default            "of the names I can trade, where does this one sit"
  --include-illiquid "of every listing on this exchange, where does this one sit"

The second is a broader question and a weaker one for acting on, because the
population it ranks against includes hundreds of names nobody can buy. Thin
listings also carry the most extreme readings on every price signal — they gap,
they sit still for weeks, and a percentile computed against them moves everything
liquid toward the middle.

What does NOT change: the gates. A name below the floor comes back NO ACTION with
its score visible, whichever way the scan was run. Scanning more never means
recommending more.
"""


# Stage 5: the four lenses for one name, cached by symbol and date
# --------------------------------------------------------------------------- #
# How long to wait before retrying a leg that looks rate-limited.
RETRY_PAUSE = 2.0

# Below this share of names, a lens is reported as mostly missing and the run
# warns that its ordering cannot be trusted. Two thirds: enough of a shortfall
# that it is the provider rather than the filings, and not so tight that a
# market with genuinely patchy fundamentals trips it on every run.
LENS_HEALTHY = 0.67

# The shapes a throttle arrives in. Yahoo returns 401 "Invalid Crumb" and 401
# "User is unable to access this feature" for what is plainly rate limiting, so
# matching on the status alone would miss half of them and matching on every
# error would retry genuine 404s for delisted names.
_THROTTLE_MARKERS = ("401", "429", "Invalid Crumb", "Unauthorized", "Too Many Requests",
                     "rate limit", "temporarily unavailable")


def _place_in_field(verdicts: list[dict], say) -> dict:
    """Rank every name inside its own industry label, in place.

    Returns the whole standing for the report; each verdict gets its own
    position attached under `fieldPosition`. Names whose industry or revenue did
    not arrive get `None` there rather than a rank built on a guess — and the
    count of those is printed, because a field missing half its members hands
    the lead to whoever happens to have been fetched.
    """
    # THE SUMMARY IS NOT OPTIONAL HERE. `standings` reads it to leave entities
    # that describe themselves as funds unplaced, and omitting it made that
    # check inert for a whole US sweep: BTX came back ranked 132nd of 138 in
    # Asset Management rather than unplaced, because the test was reading None
    # on every name. The unit test passed throughout — it calls `standings`
    # directly and passes a summary — so the defect was entirely in the wiring.
    standing = field.standings([
        {"ticker": v["ticker"], "name": v.get("name"),
         "industry": v.get("industry"),
         "summary": (v.get("profile") or {}).get("summary"),
         "revenue": (v.get("revenue") or {}).get("value")}
        for v in verdicts])

    positions = standing["positions"]
    for entry in verdicts:
        entry["fieldPosition"] = positions.get(entry["ticker"])

    # THE WORDS THAT IDENTIFY THIS COMPANY AND FEW OTHERS. A corpus statistic,
    # so it belongs here with the other cross-name work rather than in a leg:
    # what counts as distinctive is a fact about the market, and it changes when
    # the population does.
    terms = field.distinctive_terms([
        {"ticker": v["ticker"], "name": v.get("name"),
         "summary": (v.get("profile") or {}).get("summary")}
        for v in verdicts])
    for entry in verdicts:
        entry["terms"] = terms.get(entry["ticker"]) or []
    if not terms and verdicts:
        # Said out loud rather than left as an empty column. Below
        # `field.MIN_CORPUS` descriptions there is nothing for a term to be
        # distinctive against, and a scan that quietly reported none would look
        # like a market of indistinguishable companies.
        say(f"  No distinctive terms: fewer than {field.MIN_CORPUS} descriptions "
            f"came back, and distinctive is a comparison.")

    leaders = sum(1 for v in verdicts if (v.get("fieldPosition") or {}).get("leads"))
    say(f"  Placed {standing['measured']} names in {len(standing['fields'])} fields "
        f"({standing['unplaced']} had no industry label or no comparable revenue); "
        f"{leaders} {'leads' if leaders == 1 else 'lead'} a field of "
        f"{field.MIN_PEERS}+ names by {field.LEAD_MARGIN:g}x or more.")
    return standing


def _specialists_summary(verdicts: list[dict]) -> dict:
    """Profitable, growing specialists that nobody is covering.

    THE INTERSECTION THE OWNER DESCRIBED, and the only one of the new readings
    that is a shortlist rather than a column. Three conditions, each of which is
    useless alone and each of which reports its own base rate on THIS scan
    rather than a remembered one:

      SPECIALIST — either the largest of the scanned names sharing its industry
      label, or the only one carrying it. The second is not a weaker version of
      the first: a company with no listed rival is the signature of a niche, and
      it is the state the name this was built for actually occupies.

      COMPOUNDING — profitable in every year the filings cover, with positive
      operating cash flow, growing revenue at or above the market's top
      quartile. Not "profitable", which two thirds of this exchange manages.

      UNATTENDED — the same attention reading `neglect.py` uses. This is the
      loosest of the three by a distance and is reported as such.

    MEASURED, ON 729 CACHED INDONESIAN RECORDS, BEFORE IT WAS BUILT: the three
    conditions hold together on 5. The top of that list by growth was KETR.JK —
    the company the owner named — at 28.6% a year on an 18.5% net margin, the
    only listed name carrying its industry label. That is not evidence the
    screen predicts anything. It is evidence it finds the thing it was
    described.

    NO PREDICTIVE CLAIM AND NO BACKTEST. Same wall as `neglect.py`: industry
    labels and the share register arrive as a current snapshot with no history,
    so there is no version of "unattended and unrivalled in March" to test on.
    `scanlog.py` records it prospectively instead.
    """
    def specialist(entry: dict) -> bool:
        place = entry.get("fieldPosition") or {}
        # `onlyRanked`, NOT `soleListing`. A company whose two listed peers
        # returned no filings is still the specialist; what is weakened is the
        # CLAIM about rivals, not the company. The row carries both flags and
        # the unmeasured count so the qualification travels with it.
        return bool(place.get("leads") or place.get("onlyRanked"))

    def compounding(entry: dict) -> bool:
        record = entry.get("trackRecord") or {}
        return bool(record.get("available") and record.get("everyYearProfitable")
                    and record.get("operatingCashFlowPositive")
                    and record.get("growing"))

    def unattended(entry: dict) -> bool:
        return bool(((entry.get("neglect") or {}).get("attention") or {})
                    .get("unattended"))

    selected = [v for v in verdicts
                if specialist(v) and compounding(v) and unattended(v)]

    def row(entry: dict) -> dict:
        place = entry.get("fieldPosition") or {}
        record = entry.get("trackRecord") or {}
        watch = (entry.get("neglect") or {}).get("attention") or {}
        return {
            "ticker": entry["ticker"], "name": entry.get("name"),
            "score": entry.get("score"), "action": entry.get("action"),
            "industry": entry.get("industry"),
            "summary": (entry.get("profile") or {}).get("summary"),
            "terms": entry.get("terms") or [],
            "soleListing": bool(place.get("soleListing")),
            "onlyRanked": bool(place.get("onlyRanked")),
            "unrankedRivals": place.get("unranked") or 0,
            "leadsField": bool(place.get("leads")),
            "fieldPeers": place.get("peers"),
            "revenueCagr": record.get("revenueCagr"),
            "netMargin": record.get("latestNetMargin"),
            "yearsProfitable": record.get("yearsProfitable"),
            "yearsAvailable": record.get("yearsAvailable"),
            "analysts": watch.get("analysts"),
            "institutionsHeld": watch.get("institutionsHeld"),
            # WHERE THE PRICE IS, AS CONTEXT AND NEVER AS A CRITERION — the same
            # rule `neglect.py` follows and for the same reason: filtering on it
            # would reintroduce the momentum bias these screens exist to escape.
            #
            # It is here because a growth rate without a price is misleading in
            # one specific direction. KETR.JK compounds revenue at 29% a year
            # and trades at 995 against a 52-week range of 388 to 1480; a reader
            # shown the first number and not the second could easily think the
            # screen had found something cheap. It has not looked at cheapness
            # at all — that is the screen next door — and the entry gate is what
            # says so.
            "latestClose": entry.get("latestClose"),
            "drawdown": (entry.get("neglect") or {}).get("drawdown"),
            # THE LABELS, NOT ONLY THE IDS. Every consumer of this list shows
            # the gate beside the name rather than instead of it, and "Poor
            # entry at this price" and "Below the turnover floor" are not the
            # same news: the first is about today, the second about the company.
            "gates": [{"id": g["id"], "label": g["label"]}
                      for g in (entry.get("gates") or [])],
            "recordReading": record.get("reading"),
            "fieldReading": place.get("reading"),
        }

    total = len(verdicts) or 1
    return {
        "selected": len(selected),
        # EACH INGREDIENT'S OWN SHARE OF THIS SCAN. Without these the
        # intersection looks like three demanding tests, and one of them admits
        # most of the market.
        "baseRates": {
            "scanned": len(verdicts),
            "specialist": sum(1 for v in verdicts if specialist(v)) / total,
            "compounding": sum(1 for v in verdicts if compounding(v)) / total,
            "unattended": sum(1 for v in verdicts if unattended(v)) / total,
        },
        "tradeable": sorted((row(v) for v in selected if not v.get("gates")),
                            key=lambda r: -(r["revenueCagr"] or 0)),
        "gated": sorted((row(v) for v in selected if v.get("gates")),
                        key=lambda r: -(r["revenueCagr"] or 0)),
        "note": ("The largest — or the only — scanned name carrying its industry label, "
                 "profitable in every year its filings cover, with cash behind the "
                 "profit and revenue growing in this market's top quartile, and nobody "
                 "covering it. A standing among SCANNED names is not market share, and "
                 "how many names could not be placed at all is reported beside the "
                 "field counts. NOTHING HERE IS MEASURED against future returns: "
                 "industry labels and the share register are a snapshot with no "
                 "history, so this cannot be backtested even in principle. It is "
                 "recorded in the scan log to be judged later."),
    }


def _neglected_summary(verdicts: list[dict]) -> dict:
    """The screened names, split by whether a reader could actually buy them.

    THE SPLIT IS THE USEFUL PART. On a full Indonesian sweep the screen selected
    46 names and 41 of them were GATED — mostly below the turnover floor, which
    is unsurprising: a company nobody covers is usually a company nobody trades.
    Reporting 46 as though they were a shortlist would be a list of things that
    cannot be bought.
    """
    selected = [v for v in verdicts if (v.get("neglect") or {}).get("selected")]
    tradeable = [v for v in selected if not v.get("gates")]
    gated = [v for v in selected if v.get("gates")]

    def row(entry: dict) -> dict:
        screen = entry["neglect"]
        watch = screen["attention"]
        place = entry.get("fieldPosition") or {}
        return {"ticker": entry["ticker"], "name": entry.get("name"),
                "score": entry.get("score"), "action": entry.get("action"),
                "value": screen.get("value"), "quality": screen.get("quality"),
                "institutionsHeld": watch.get("institutionsHeld"),
                "analysts": watch.get("analysts"),
                # WHAT IT SELLS AND WHETHER IT IS THE BIGGEST DOING SO. The
                # screen above answers "cheap, solid, unwatched"; this answers
                # "at what", which is the half a reader cannot get from any
                # ratio. It is carried, never screened on: leading a field is
                # not a criterion for selection and does not add one here.
                "industry": entry.get("industry"),
                "summary": (entry.get("profile") or {}).get("summary"),
                "leadsField": bool(place.get("leads")),
                "fieldRank": place.get("rank"),
                "fieldPeers": place.get("peers"),
                "soleListing": bool(place.get("soleListing")),
                "profitableEveryYear": bool((entry.get("trackRecord") or {})
                                            .get("everyYearProfitable")),
                "growing": bool((entry.get("trackRecord") or {}).get("growing")),
                "revenueCagr": (entry.get("trackRecord") or {}).get("revenueCagr"),
                "gates": [g["id"] for g in (entry.get("gates") or [])],
                "reading": screen.get("reading")}

    # LEADERS FIRST, WITHIN EACH LIST. A sort is not a filter: every selected
    # name is still here and none is promoted into the list by leading a field.
    # It is ordering, and it is the order the owner reads in.
    def order(entries: list[dict]) -> list[dict]:
        return sorted((row(v) for v in entries),
                      key=lambda r: (not r["leadsField"], -(r["score"] or 0)))

    return {
        "selected": len(selected),
        "leadTheirField": sum(1 for v in selected
                              if (v.get("fieldPosition") or {}).get("leads")),
        "tradeable": order(tradeable),
        "gated": order(gated),
        "thresholds": {"cheapAt": neglect.CHEAP_AT, "solidAt": neglect.SOLID_AT,
                       "unattendedHeld": neglect.UNATTENDED_HELD,
                       "unattendedAnalysts": neglect.UNATTENDED_ANALYSTS},
        "note": ("Cheap by the valuation lens, solid by the accounting screens, and "
                 "covered by nobody. This is the combination the blended score pulls "
                 "to the middle, because the price family scores a fallen stock badly "
                 "and falling is what makes it cheap. NOTHING HERE IS MEASURED: this "
                 "data source has no point-in-time filings and no history of who held "
                 "what, so the screen cannot be backtested even in principle. It is "
                 "recorded prospectively in the scan log instead."),
    }


def _reason_of(error) -> str:
    """The refusal, short enough to print beside a count.

    The legs hand back whatever their engine raised — sometimes a string,
    sometimes the `{"message": ...}` shape FastAPI's HTTPException carries — so
    the shape is normalised here rather than at four call sites.
    """
    text = str(error or "").strip()
    match = re.search(r"'message':\s*'([^']+)'", text)
    if match:
        text = match.group(1)
    text = re.sub(r"\s+", " ", text)
    return (text[:72] + "...") if len(text) > 75 else text or "no reason given"


def _looks_throttled(message: str) -> bool:
    text = (message or "")
    return any(marker.lower() in text.lower() for marker in _THROTTLE_MARKERS)


def cache_path(symbol: str, day: str) -> Path:
    return CACHE_DIR / day / f"{symbol.replace('/', '_')}.json"


# THE ONLY LEG THAT COSTS NOTHING TO RECOMPUTE, AND THE VERSION IS WHY THAT
# MATTERS. Every other leg in `deepen` is a network fetch, so a cached day is
# worth keeping whatever shape it is in. This one reads a company record that is
# already on disk, so when `field` or `trackrecord` learns to report something
# new, the right answer is to recompute it — not to reserve two hours of
# provider quota re-downloading filings that have not changed.
#
# Without a version the cache served the old shape silently: a full 771-name
# sweep came back with every net-debt figure null, because the leg payloads had
# been written the hour before the borrowings reading existed, and nothing said
# so. Bump this whenever the payload gains or loses a field.
#
# 4 — `trackrecord` stopped reporting a missing balance sheet as net cash, which
#     changes `netCash`/`netDebt` on any name whose sheet did not arrive.
PROFILE_LEG_VERSION = 4


def read_profile(symbol: str) -> dict:
    """What the company sells and what its filings say it has done.

    A MISS IS A GAP, NOT A REFUSAL, and it does not go on the retry path.
    `cached_company` is a peek: if the record is not in memory or on disk,
    asking again two seconds later reads the same empty cache. Saying so costs
    nothing and a pointless retry costs two seconds a name.
    """
    record = market_data.cached_company(symbol)
    if record is None:
        return {"version": PROFILE_LEG_VERSION, "available": False,
                "reason": ("the company record was not in hand when the business "
                           "profile was read, so what this company does is unknown "
                           "for this run rather than unpublished")}
    return {"version": PROFILE_LEG_VERSION,
            "available": True,
            "profile": field.profile(record),
            "revenue": field.revenue_of(record),
            # Same record, no further fetch. Profits, cash, growth and
            # borrowings over the years the filings cover — description, never a
            # score; see `trackrecord.py` for why "profitable" alone admits 67%
            # of this market and is therefore not a screen.
            "trackRecord": trackrecord.read(record)}


def refresh_free_legs(symbol: str, legs: dict) -> bool:
    """Recompute the legs that cost no fetch, in place. True if anything moved.

    Called on a CACHE HIT. The expensive legs are served as they were written;
    this one is rebuilt whenever its version has moved on, which costs a disk
    read and makes the descriptive half of the scan iterable without spending a
    day of provider quota to change a sentence.

    A REFRESH MAY NEVER DOWNGRADE, AND THE FIRST VERSION OF THIS FUNCTION DID.
    `read_profile` reads the fundamentals cache and returns a stated GAP when
    the record is not there. On the night the calendar rolled over, a
    `--fundamentals-days 1` run found every record one day old and therefore
    expired, so the rebuild came back unavailable for all 771 names — and this
    function wrote that over 771 good profile payloads and saved it to disk.
    Nothing failed, nothing was reported, and the next report had no business
    descriptions, no track records and an empty shortlist.

    A cache exists to hold what was expensive to learn. Replacing what it holds
    with "I could not find out" is the one thing it must never do, so a rebuild
    that knows LESS than the record it would replace is discarded and the stale
    payload is kept — stale and true beats fresh and empty.
    """
    current = (legs.get("profile") or {}).get("data") or {}
    if current.get("version") == PROFILE_LEG_VERSION:
        return False
    rebuilt = read_profile(symbol)
    if not rebuilt.get("available") and current.get("available"):
        return False
    legs["profile"] = {"ok": True, "data": rebuilt}
    return True


def deepen(symbol: str, market: str, day: str, use_cache: bool = True) -> dict:
    """Every per-symbol lens, in the `/api/confluence` leg shape.

    Each leg carries its own `ok` flag, so one failed lens becomes a stated gap
    in the verdict rather than a lost name. That contract is what lets the scan
    score a company whose dividend history is missing without discarding
    everything else known about it.
    """
    path = cache_path(symbol, day)
    if use_cache and path.exists():
        try:
            legs = json.loads(path.read_text())
        except ValueError:
            legs = None
        if legs is not None:
            # The free leg is rebuilt if its shape has moved on; everything
            # expensive is served as written. See `refresh_free_legs`.
            if refresh_free_legs(symbol, legs):
                path.write_text(json.dumps(clean(legs), default=str))
            return legs

    def leg(fn):
        # ONE RETRY, AFTER A PAUSE, BECAUSE MOST FAILURES HERE ARE THE RATE
        # LIMIT RATHER THAN THE DATA. Measured: 24 liquid names whose quality
        # lens came back empty in a four-worker sweep returned it on 20 of 24
        # when refetched one at a time. The company had not changed; the
        # provider had been asked too fast.
        for attempt in (0, 1):
            try:
                return {"ok": True, "data": fn()}
            except Exception as exc:
                detail = getattr(exc, "detail", None)
                message = str(detail or f"{type(exc).__name__}: {exc}")
                if attempt == 0 and _looks_throttled(message):
                    time.sleep(RETRY_PAUSE)
                    continue
                return {"ok": False, "error": message}

    def quality_leg():
        # "NO SECTOR CAME BACK" IS A THROTTLE WEARING A REFUSAL'S CLOTHES.
        #
        # `quality.py` cannot tell whether the models apply without a sector, so
        # it declines — correctly. But the leg still returns ok, so the lens
        # counter saw a success, the retry never fired, and the cache stored the
        # decline for the day.
        #
        # It is a fetch failure. Measured on eight US names whose sector came
        # back empty in a two-worker sweep — six operating companies and two
        # closed-end funds — ALL EIGHT returned a sector on an unhurried refetch,
        # funds included. Yahoo has the field; it was being asked too fast.
        #
        # Raising here puts it back on the retry path, where it belongs.
        payload = quality_payload(symbol)
        if (isinstance(payload, dict) and not payload.get("applicable")
                and payload.get("cause") == "unknown-sector"):
            raise RuntimeError("429 no sector returned — rate limited, not refused")
        return payload

    legs = {
        "anomaly": leg(lambda: whale_payload(symbol, period="2y")),
        "technical": leg(lambda: technical_payload(symbol, range_key="2y",
                                                   market_code=market)),
        "valuation": leg(lambda: valuation_payload(
            symbol, **_valuation_kwargs(market=market))),
        "quality": leg(quality_leg),
        # WHAT THE COMPANY SELLS, AND HOW MUCH OF IT. Immediately after the
        # quality leg, and that ordering is the whole design: `quality_payload`
        # has just fetched this company's record, so `cached_company` reads it
        # out of memory. It never fetches — see its docstring — so this leg adds
        # nothing to a sweep the provider is already rate-limiting.
        "profile": leg(lambda: read_profile(symbol)),
        # The share register is the third body of data and it is fetched here
        # rather than beside the price batch because, like the filings, it is one
        # call per symbol and does not batch. It is cached with the four lenses
        # for the same reason: it moves on a filing cycle, not intraday.
        "register": leg(lambda: market_data.share_register(symbol)),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(legs), default=str))
    return legs


# --------------------------------------------------------------------------- #
# The scan
# --------------------------------------------------------------------------- #
def run(args) -> dict:
    started = time.time()
    market = args.market.upper()
    day = dt.date.today().isoformat()

    # THE FUNDAMENTALS CACHE IS OPTED INTO HERE AND NOWHERE ELSE. It is off by
    # default in `market_data` because the deployed app is serverless and has no
    # persistent disk. This script is the one caller that runs for hours on a
    # machine that does, and it is the one that cannot work without it: the US
    # universe is 9,997 listings, about twelve hours at the rate the provider
    # tolerates, so a sweep that refetched quarterly statements every calendar
    # day could never finish one.
    if args.fundamentals_days > 0:
        os.environ["QUANTDESK_FUNDAMENTALS_TTL_DAYS"] = str(args.fundamentals_days)

    dropped = prune_cache(keep=args.cache_days, today=day)

    picked, provenance_universe = resolve_universe(args)
    def say(*parts):
        # `flush=True` is not cosmetic. Python line-buffers a tty and block-
        # buffers a pipe, so `scan_market.py > log` showed nothing for minutes
        # while the scan ran — indistinguishable from a hang, on the one command
        # here that legitimately takes minutes.
        if not args.quiet:
            print(*parts, flush=True)

    if dropped:
        say(f"\nPruned {len(dropped)} day{'' if len(dropped) == 1 else 's'} of cached "
            f"lens payloads ({', '.join(dropped)}); keeping the most recent "
            f"{args.cache_days}.")

    say(f"\nUniverse: {provenance_universe['label']} — {len(picked)} symbols")
    if provenance_universe.get("staleness"):
        say(f"  {provenance_universe['staleness']['text']}")

    # --- prices, in batch ---------------------------------------------------
    end = dt.date.today()
    start = end - dt.timedelta(days=HISTORY_DAYS)
    say(f"Fetching {len(picked)} price histories in batches of "
        f"{market_data.CHUNK_SIZE} ...")
    frames = market_data.ohlcv_batch(picked, start, end)
    say(f"  {len(frames)} returned usable history; {len(picked) - len(frames)} did not")

    # --- tradeability, BEFORE the ranking ----------------------------------
    # TWO THRESHOLDS THAT USED TO BE ONE, AND CONFLATING THEM WAS THE BUG.
    #
    # `gate_floor` is the turnover below which `verdict.score` refuses to
    # recommend a name: a fact about whether an order can be filled. `scan_floor`
    # is the turnover below which this script does not bother LOOKING at a name:
    # a decision about where to spend a fetch budget.
    #
    # They were the same variable, so the only way to widen the sweep was
    # `--turnover-floor 0`, which also silenced the gate — every thin listing in
    # the market would have come back ungated, and the ones with the most extreme
    # price percentiles are exactly the thin ones. Scanning more must never mean
    # recommending more.
    gate_floor = args.turnover_floor
    if gate_floor is None:
        gate_floor = verdict.TURNOVER_FLOOR.get(market, 0.0)
    scan_floor = 0.0 if args.include_illiquid else gate_floor
    tick = verdict.TICK_FLOOR.get(market, 0.0)

    tradeable: dict[str, pd.DataFrame] = {}
    rejected: list[dict] = []
    for symbol, frame in frames.items():
        turnover = turnover_of(frame)
        close = float(frame["Close"].iloc[-1])
        if len(frame) < ranking.MIN_BARS:
            rejected.append({"ticker": symbol, "why": "history",
                             "detail": f"{len(frame)} bars, needs {ranking.MIN_BARS}"})
        elif turnover is None:
            rejected.append({"ticker": symbol, "why": "turnoverUnknown",
                             "detail": "no usable volume history"})
        elif turnover < scan_floor:
            rejected.append({"ticker": symbol, "why": "illiquid",
                             "detail": f"{turnover:,.0f} median daily turnover",
                             "turnover": turnover})
        elif close <= tick:
            rejected.append({"ticker": symbol, "why": "tickFloor",
                             "detail": f"resting at {close:,.0f}"})
        else:
            tradeable[symbol] = frame

    if args.include_illiquid:
        below = sum(1 for symbol in tradeable
                    if (turnover_of(frames[symbol]) or 0.0) < gate_floor)
        say(f"Scoring every listing with usable history: {len(tradeable)} of "
            f"{len(frames)} — {below} of them below the {gate_floor:,.0f} turnover "
            f"floor and therefore gated as untradeable")
        say("  Every percentile below is taken across ALL of them, not across the "
            "tradeable subset. A name's price rank is a claim about a population, "
            "and this is a different population from the default scan's.")
    else:
        say(f"Tradeable after the turnover floor ({scan_floor:,.0f}) and the tick "
            f"floor: {len(tradeable)} of {len(frames)}")
    by_reason: dict[str, int] = {}
    for entry in rejected:
        by_reason[entry["why"]] = by_reason.get(entry["why"], 0) + 1
    for reason, count in sorted(by_reason.items(), key=lambda kv: -kv[1]):
        say(f"  dropped {count:>4} for {reason}")

    if not tradeable:
        raise SystemExit("Nothing in this universe cleared the tradeability floor.")

    # --- breadth rank, across the TRADEABLE population ----------------------
    say(f"Ranking {len(tradeable)} names on seven price signals ...")
    benchmark_symbol = ranking.riskmodel.MARKET_INDEX.get(market, "^GSPC")
    index_frames = market_data.ohlcv_batch([benchmark_symbol], start, end)
    benchmark = (index_frames[benchmark_symbol]["Close"].astype("float64")
                 if benchmark_symbol in index_frames else None)
    # THE MARKET THIS LIST WAS PRODUCED IN, from the same benchmark the relative
    # strength is measured against. It scores nothing and gates nothing — see
    # `structure.regime` — but a ranked table produced in a falling market looks
    # identical to one produced in a rising one, and that is worth a sentence at
    # the top rather than a discovery later.
    market_regime = structure.regime(
        index_frames.get(benchmark_symbol), symbol=benchmark_symbol)
    if market_regime.get("available"):
        # The first SENTENCE, not the text before the first full stop — the
        # reading opens with "9.1% below its 200-day average" and splitting on
        # "." truncated it to "^JKSE is declining: 9."
        first = market_regime["reading"].split(". ")[0].rstrip(".")
        say(f"  Market regime: {first}.")

    ranked = ranking.rank_universe(tradeable, benchmark=benchmark)
    rows_by_ticker = {row["ticker"]: row for row in ranked["rows"]}
    say(f"  {len(ranked['rows'])} ranked against {benchmark_symbol}")
    if ranked["correlation"].get("available"):
        say(f"  {ranked['correlation']['reading']}")

    # --- who gets deepened --------------------------------------------------
    held = [symbols.resolve(t.strip(), market)
            for t in (args.hold or "").replace("\n", ",").split(",") if t.strip()]
    order = [row["ticker"] for row in ranked["rows"]]
    # `args.deepen is None` means every tradeable name. `order[:None]` is the
    # whole list, which is why this reads as a plain slice rather than a branch.
    shortlist = list(dict.fromkeys(
        order[:args.deepen]
        + (order[-args.deepen_bottom:] if args.deepen_bottom else [])
        + [h for h in held if h in rows_by_ticker]))
    missing_holdings = [h for h in held if h not in rows_by_ticker]

    say(f"\nDeepening {len(shortlist)} names with the four lenses and the share "
        f"register ({args.workers} at a time). This is the slow part.")
    if missing_holdings:
        say(f"  NOTE: {', '.join(missing_holdings)} could not be deepened — not in the "
            f"tradeable ranked set. See the report's rejected list for why.")

    legs_by_ticker: dict[str, dict] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(deepen, s, market, day, not args.no_cache): s
                   for s in shortlist}
        for future in as_completed(futures):
            symbol = futures[future]
            done += 1
            try:
                legs_by_ticker[symbol] = future.result()
            except Exception as exc:
                legs_by_ticker[symbol] = {}
                say(f"  [{done}/{len(shortlist)}] {symbol} FAILED: {exc}")
                continue
            fetched = legs_by_ticker[symbol]
            ok_count = sum(1 for leg in fetched.values()
                           if isinstance(leg, dict) and leg.get("ok"))
            # LEGS, NOT LENSES. There are five now — the four lenses plus the
            # share register — and the denominator is taken from what was
            # actually fetched rather than written as a literal, which is how
            # this line came to read "5/4 lenses" the day the register landed.
            say(f"  [{done}/{len(shortlist)}] {symbol}: {ok_count}/{len(fetched)} legs")

    # --- did the data actually arrive? --------------------------------------
    # THE RUN THAT PROMPTED THIS LOOKED PERFECTLY HEALTHY. It printed a tidy
    # funnel, scored 775 names, and produced a buy list — while the quality lens
    # had come back empty on 686 of them because the provider was throttling.
    # Nothing in the output said so, and the effect was not neutral: a missing
    # component has its weight REMOVED from the blend rather than imputed, so a
    # name whose quality reading was bad gets PROMOTED when that fetch fails.
    # NEST went from 48.1 HOLD to 67.2 BUY overnight on exactly that, its
    # quality score of 22 having simply vanished.
    #
    # A degraded run must therefore announce itself. This is the cheapest
    # possible version of that and it would have caught the whole episode.
    # A SHORTFALL IS NOT AUTOMATICALLY A THROTTLE, and the first version of this
    # warning said it was. On the sequential IDX sweep it fired on `valuation` at
    # 48% and advised re-running with --workers 1 — which is what that run
    # already was. All 402 failures were refusals: 205 names had no usable
    # cash-flow statement and 194 had negative free cash flow, which a
    # growth-multiple DCF genuinely cannot value. Nothing was rate-limited.
    #
    # That matters beyond tidiness. A warning that cries wolf on a lens which is
    # working correctly is how the NEXT one gets ignored — and the next one was
    # `quality` at 10%, which silently promoted names by losing the evidence
    # against them. So the two are counted separately and only one of them
    # raises an alarm.
    lens_reads: dict[str, int] = {}
    lens_throttled: dict[str, int] = {}
    lens_declined: dict[str, collections.Counter] = {}
    for legs in legs_by_ticker.values():
        for name, payload in (legs or {}).items():
            lens_reads.setdefault(name, 0)
            lens_throttled.setdefault(name, 0)
            lens_declined.setdefault(name, collections.Counter())
            if payload.get("ok"):
                lens_reads[name] += 1
            elif _looks_throttled(str(payload.get("error") or "")):
                lens_throttled[name] += 1
            else:
                lens_declined[name][_reason_of(payload.get("error"))] += 1

    attempted = len(legs_by_ticker)
    throttled_lenses = []
    if attempted:
        say("\nWhat actually came back, per lens:")
        for name in sorted(lens_reads):
            share = lens_reads[name] / attempted
            note = ""
            if lens_throttled[name] and lens_throttled[name] / attempted > 1 - LENS_HEALTHY:
                throttled_lenses.append(name)
                note = f"   <-- {lens_throttled[name]} rate-limited"
            elif share < LENS_HEALTHY and lens_declined[name]:
                reason, count = lens_declined[name].most_common(1)[0]
                note = f"   declined {count}x: {reason}"
            say(f"  {name:10} {lens_reads[name]:>5} of {attempted} ({share * 100:4.0f}%)"
                f"{note}")

        if throttled_lenses:
            say(f"\n  WARNING: {', '.join(throttled_lenses)} was RATE-LIMITED on a "
                f"large share of names — these are fetches that failed, not filings "
                f"that are missing. A missing component has its weight removed from "
                f"the blend, so names this lens would have marked DOWN are scored too "
                f"high. Re-run with --workers 1 before trusting the ordering.")
        elif any(lens_reads[n] / attempted < LENS_HEALTHY for n in lens_reads):
            say("\n  The lenses below the line above DECLINED rather than failed — the "
                "model does not apply, or the filing genuinely is not there. That is a "
                "refusal, not a gap, and re-running will not change it.")

    # --- verdicts -----------------------------------------------------------
    say("\nScoring ...")
    names = provenance_universe.get("names") or {}
    verdicts = []
    tape_fired = 0
    tape_tested = 0
    for symbol in shortlist:
        row = rows_by_ticker.get(symbol)
        legs = legs_by_ticker.get(symbol) or {}
        frame = tradeable[symbol]
        liquidity = microstructure.liquidity_profile(frame, window=TURNOVER_WINDOW)
        checks = pretrade.assess(legs, market=symbols.market_of(symbol))
        volatility = ((row or {}).get("signals", {}).get("lowVolatility", {}) or {}).get("raw")

        # THE TAPE READS THE BATCHED FRAME, not a second download. It is the one
        # new component that costs nothing per name: the price history is already
        # in memory from step 2, so a whole-market tape reading is free where a
        # whole-market fundamentals reading is minutes.
        tape_result = tape.read(frame, market_code=symbols.market_of(symbol))
        if tape_result.get("available") and tape_result.get("calibrated"):
            tape_tested += 1
            tape_fired += int(bool(tape_result.get("significant")))

        # Both of these read data already in hand — the batched price frame and
        # the assembled technical leg — so a whole-market sweep gets them for
        # nothing. Neither costs a fetch.
        pattern_result = patterns.read(frame, market_code=symbols.market_of(symbol))
        technical_leg = legs.get("technical") or {}
        structure_result = structure.read(
            technical=technical_leg.get("data") if technical_leg.get("ok") else None)
        # Also free from the batched frame. It scores nothing and gates nothing
        # — see `volumeprofile`'s docstring for the measurement that decided
        # that — and it is what the report's chart shades.
        profile_result = volumeprofile.build(
            frame, market_code=symbols.market_of(symbol))

        register_leg = legs.get("register") or {}
        register_raw = register_leg.get("data") if register_leg.get("ok") else None
        # No share count is passed: `ownership.read` takes the last observation
        # from the register's own history, which is the same number from the
        # same fetch. Asking the company cache for it here would be one extra
        # request per name, past that cache's eviction bound.
        register_result = ownership.read(
            register_raw,
            median_volume=float(frame["Volume"].tail(TURNOVER_WINDOW).median()))

        result = verdict.score(
            symbol,
            legs=legs,
            rank_row=row,
            pretrade_result=checks,
            liquidity=liquidity,
            market=market,
            name=names.get(symbol),
            annual_volatility=volatility,
            latest_close=float(frame["Close"].iloc[-1]),
            risk_budget=args.risk_budget,
            max_weight=args.max_weight,
            # ALWAYS THE REAL FLOOR, never `scan_floor`. A name let through the
            # funnel by --include-illiquid must still be gated by it.
            turnover_floor=gate_floor,
            tape_result=tape_result,
            register_result=register_result,
            pattern_result=pattern_result,
            structure_result=structure_result,
        )
        result["rank"] = (row or {}).get("rank")
        result["held"] = symbol in held
        # The sector comes off the quality leg, which already read it from the
        # company record. Fetching it again would be a second source for one
        # string.
        quality_leg = legs.get("quality") or {}
        result["sector"] = ((quality_leg.get("data") or {}).get("sector")
                            if quality_leg.get("ok") else None)
        # WHAT THE COMPANY DOES. Description only: nothing here scores, gates or
        # shifts a verdict, and the industry label is carried beside the sector
        # because a rank inside "Thermal Coal" says something a rank inside
        # "Energy" does not.
        profile_leg = legs.get("profile") or {}
        profile_data = profile_leg.get("data") if profile_leg.get("ok") else None
        if isinstance(profile_data, dict) and profile_data.get("available"):
            result["profile"] = profile_data["profile"]
            result["revenue"] = profile_data["revenue"]
            result["industry"] = profile_data["profile"].get("industry")
            result["trackRecord"] = profile_data.get("trackRecord")
        else:
            result["profile"] = None
            result["revenue"] = None
            result["industry"] = None
            result["trackRecord"] = None
        result["costs"] = structure.round_trip_cost(liquidity)
        result["tape"] = tape_result
        result["register"] = register_result
        result["patterns"] = pattern_result
        result["volumeProfile"] = profile_result
        # THE SCREEN FOR WHAT THE BLEND CANNOT SEE. It reads components the
        # verdict just computed and changes none of them — see `neglect.py` for
        # the measurement that showed 82 cheap-and-solid names in one sweep and
        # not a single buy among them.
        result["neglect"] = neglect.screen(
            result, register_result,
            technical=(technical_leg.get("data") if technical_leg.get("ok") else None),
            # WHERE THE COMPANY IS DOMICILED, so a foreign depositary receipt is
            # not read as uncovered. Its US institutional holding describes the
            # receipt, not the company — see `neglect.attention`, which found
            # all 26 US selections were ADRs of the most watched companies in
            # Europe and Asia.
            country=(result.get("profile") or {}).get("country"),
            market_code=symbols.market_of(symbol))
        # THE CHART GEOMETRY IS BUILT ONLY FOR ROWS THAT SAY TO DO SOMETHING.
        # It is cheap per name but not free — the pattern curves are refitted
        # per detection — and a hundred-name report carrying a chart for every
        # Hold would be a ten-megabyte file nobody scrolls. The rows a reader
        # acts on get one; the rest keep their numbers.
        if result.get("action") in CHARTED_ACTIONS:
            result["chart"] = chartlayers.build(
                frame, technical=(technical_leg.get("data")
                                  if technical_leg.get("ok") else None),
                structure_result=structure_result, pattern_result=pattern_result,
                tape_result=tape_result, volume_profile=profile_result,
                ticker=symbol)
        result["preTrade"] = {"flags": len(checks.get("flags") or []),
                              "baseConditions": len(checks.get("baseConditions") or []),
                              "notChecked": len(checks.get("notChecked") or [])}
        verdicts.append(result)

    # WHAT SCORED, WHICH IS NOT WHAT RETURNED.
    #
    # The per-lens counter above reads each leg's `ok` flag, and that misses the
    # failure mode it was built for. `quality_payload` returns ok while declining
    # to score — "no sector came back", which is a throttle — so a US sweep
    # reported quality at 100% while the COMPONENT was a gap on 1,180 of 3,364
    # names, and 175 of the 287 buys rested on its absence. The instrument said
    # the run was healthy and the run had the same defect it was built to catch.
    #
    # A component that REFUSED is fine: the models genuinely do not apply to a
    # bank. A component that is a GAP is a fetch that failed, and its weight was
    # removed from the blend — so names it would have marked DOWN are too high.
    scored_counts: dict[str, collections.Counter] = {}
    for entry in verdicts:
        for component in entry.get("components") or []:
            state = ("scored" if component.get("available")
                     else "refused" if component.get("refused") else "gap")
            scored_counts.setdefault(component["key"], collections.Counter())[state] += 1

    if verdicts:
        say("\nWhat actually SCORED, per component:")
        gapped = []
        for key in sorted(scored_counts):
            counts = scored_counts[key]
            total = sum(counts.values())
            gap_share = counts["gap"] / total if total else 0.0
            note = ""
            if gap_share > 1 - LENS_HEALTHY:
                gapped.append(key)
                note = f"   <-- {counts['gap']} GAPS (fetches that failed)"
            elif counts["refused"]:
                note = f"   ({counts['refused']} refused — models do not apply)"
            say(f"  {key:12} scored {counts['scored']:>5} of {total}"
                f" ({counts['scored'] / total * 100:4.0f}%){note}")
        if gapped:
            say(f"\n  WARNING: {', '.join(gapped)} is MISSING rather than refused on a "
                f"large share of names. Its weight was removed from the blend, so any "
                f"name it would have marked DOWN is scored too high and may appear in "
                f"the buy list for that reason alone. Re-run with --workers 1.")

    verdicts.sort(key=lambda v: (v["score"] is None, -(v["score"] or 0.0)))

    # ONLY THE ENDS OF THE LIST KEEP THEIR CHART.
    #
    # The geometry is attached to every directional row while scoring, because
    # at that point there is no ranking to select on. The REPORT is a different
    # question: on a 2,110-name US sweep, 758 rows came back directional and the
    # resulting file was 27MB. That is not a document anybody opens — the charts
    # stop being an aid and become the reason the page will not scroll.
    #
    # Both ends, not just the top. A reader checks what the scanner liked most
    # and what it liked least; the six hundred names in the middle marked HOLD
    # or mildly REDUCE are exactly the ones nobody expands.
    charted = [v for v in verdicts if v.get("chart")]
    if len(charted) > args.max_charts:
        half = max(1, args.max_charts // 2)
        keep = {id(v) for v in charted[:half]} | {id(v) for v in charted[-half:]}
        dropped = 0
        for entry in charted:
            if id(entry) not in keep:
                entry.pop("chart", None)
                dropped += 1
        say(f"  Charted the {min(half, len(charted))} highest and "
            f"{min(half, len(charted))} lowest of {len(charted)} directional rows; "
            f"dropped {dropped} to keep the report openable.")

    # --- where each name sits inside its OWN sector -------------------------
    # A coal miner in the top decile of a coal rally and one in the top decile
    # of the whole market are different findings, and the second is the one the
    # overall rank reports. This adds the first without touching any score:
    # sector membership is not evidence about a company, and percentile-ing
    # inside a group of four would be arithmetic on noise.
    _rank_within_sector(verdicts, say)

    # --- and where it sits among the names doing the SAME THING -------------
    # A different question from the sector percentile above, and a more useful
    # one for the thing this was built for: a sector rank says "top decile of
    # Energy", a field standing says "the largest of the seven scanned names in
    # thermal coal". See `field.py` for what that is and, at length, what it is
    # not — it is not market share.
    field_standing = _place_in_field(verdicts, say)

    # --- is this buy list one bet? ------------------------------------------
    buys = [v for v in verdicts if v["action"] in ("BUY", "STRONG_BUY")]
    concentration = basket.analyse(
        tradeable,
        [v["ticker"] for v in buys],
        weights={v["ticker"]: (v["sizing"] or {}).get("weight") for v in buys},
        sectors={v["ticker"]: v.get("sector") for v in buys})
    if concentration.get("available"):
        say(f"\n  {concentration['reading'].split('. ')[0]}.")

    return {
        "generatedAt": dt.datetime.now().isoformat(timespec="seconds"),
        "market": market,
        "elapsedSeconds": round(time.time() - started, 1),
        "universe": {k: v for k, v in provenance_universe.items() if k != "names"},
        "counts": {
            "requested": len(picked),
            "fetched": len(frames),
            "tradeable": len(tradeable),
            "ranked": len(ranked["rows"]),
            "deepened": len(shortlist),
            "rejected": len(rejected),
            "rejectedByReason": by_reason,
        },
        "settings": {
            "turnoverFloor": gate_floor,
            "scanFloor": scan_floor,
            "includedIlliquid": bool(args.include_illiquid),
            "tickFloor": tick,
            "deepenTop": args.deepen if args.deepen is not None else "all",
            "deepenBottom": args.deepen_bottom,
            "riskBudget": args.risk_budget,
            "maxWeight": args.max_weight,
            "benchmark": benchmark_symbol if benchmark is not None else None,
            "historyDays": HISTORY_DAYS,
        },
        "provenance": verdict.provenance(),
        # THE SECOND MEASUREMENT, and the one that is actually about the score
        # this report prints. `provenance` covers the price composite; this
        # covers the blend, on the four components that can be reconstructed
        # without reading the future.
        "blendBacktest": verdict.blend_validation(market),
        "regime": market_regime,
        "signalOverlap": ranked["correlation"],
        # WHETHER THE THREE FAMILIES ARE ACTUALLY THREE SOURCES. The score
        # weights them equally on the argument that they read different data;
        # this is the measurement that checks it rather than the assertion that
        # assumes it. See `verdict.family_overlap`.
        "familyOverlap": verdict.family_overlap(verdicts),
        # WHETHER THE BUY LIST IS ONE BET. A property of the SET, invisible from
        # any row, and the only place it can be computed is here — after the
        # list exists.
        "concentration": concentration,
        # How often the tape test fired against how often chance predicts it
        # would. One name's p-value needs no correction; a scan of hundreds does,
        # and this is the count that makes the correction legible.
        "patternStudy": patterns.calibration_for(market),
        "tapeSignificance": {
            "tested": tape_tested,
            "fired": tape_fired,
            "expectedByChance": round(tape_tested * tape.ALPHA, 1),
            "alpha": tape.ALPHA,
            "note": (f"The heavy-session test fired on {tape_fired} of {tape_tested} "
                     f"names against {tape_tested * tape.ALPHA:.1f} expected by chance "
                     f"alone. The excess is the real signal; the rest are false "
                     f"positives and there is no way to tell which is which."
                     if tape_tested else
                     "No name had a calibrated tape reading on this scan."),
        },
        # THE BLIND SPOT, AS A LIST. Names that are cheap by the valuation lens,
        # solid by the accounting screens, and that nobody is covering — the
        # combination the blend's disagreement-shrink pulls to the middle. It
        # makes no predictive claim; see `neglect.py` for why no backtest of it
        # is possible with this data.
        "neglected": _neglected_summary(verdicts),
        # THE INTERSECTION OF THE THREE NEW READINGS: a specialist, compounding,
        # and uncovered. See `_specialists_summary` for the measurement that
        # found five of them on 729 cached names, KETR.JK at the top.
        "specialists": _specialists_summary(verdicts),
        # WHAT EACH COMPANY SELLS AND WHO ELSE SELLS IT. Description, not a
        # score: no verdict moves on any of it. `basis` travels inside the
        # payload because a rank of 1 rendered without it reads as market share,
        # which is a claim nothing here measured.
        "fields": {key: value for key, value in field_standing.items()
                   if key != "unplacedDetail"},
        "verdicts": verdicts,
        "rejected": sorted(rejected, key=lambda r: r["why"]),
        "notDeepened": [
            {"ticker": row["ticker"], "rank": row["rank"], "composite": row["composite"]}
            for row in ranked["rows"] if row["ticker"] not in set(shortlist)
        ],
        "missingHoldings": missing_holdings,
    }


# --------------------------------------------------------------------------- #
# Terminal summary
# --------------------------------------------------------------------------- #
ACTION_ORDER = ["STRONG_BUY", "BUY", "HOLD", "REDUCE", "AVOID", "NO_ACTION"]


def print_summary(report: dict) -> None:
    print("\n" + "=" * 78)
    print("WHAT THIS ORDERING IS WORTH, BEFORE YOU READ IT")
    print("=" * 78)
    print(_wrap(report["provenance"].get("headline", ""), 78))
    if report["provenance"].get("appliesTo"):
        print("\nApplies to " + _wrap(report["provenance"]["appliesTo"], 78))

    print("\n" + "=" * 78)
    counts = report["counts"]
    print(f"{report['market']} scan — {counts['requested']} listed, "
          f"{counts['tradeable']} tradeable, {counts['deepened']} deepened, "
          f"{report['elapsedSeconds']}s")
    print("=" * 78)

    print(f"{'':2}{'TICKER':<11}{'SCORE':>6}{'ACT':>12}{'CONV':>8}{'RK':>5}"
          f"{'COV':>6}{'X':>3}  NAME")
    print("-" * 78)
    for entry in report["verdicts"]:
        score = "  -  " if entry["score"] is None else f"{entry['score']:5.1f}"
        mark = "*" if entry["held"] else " "
        # "X" is the cross-check column: whether both bodies of data read at all.
        # A blank here on a BUY means the whole verdict came from price history.
        crossed = "y" if entry.get("crossChecked") else "-"
        print(f"{mark} {entry['ticker']:<11}{score:>6}"
              f"{entry['actionLabel']:>12}{entry['conviction']:>8}"
              f"{entry['rank'] or 0:>5}{entry['coverage'] * 100:>5.0f}%{crossed:>3}  "
              f"{(entry['name'] or '')[:26]}")

    tally: dict[str, int] = {}
    for entry in report["verdicts"]:
        tally[entry["action"]] = tally.get(entry["action"], 0) + 1
    print("-" * 78)
    print("  " + "   ".join(f"{a.replace('_', ' ').title()}: {tally[a]}"
                            for a in ACTION_ORDER if a in tally))
    one_family = [v for v in report["verdicts"] if not v.get("crossChecked")]
    print("  * = a name you told the scan you hold; X = both bodies of data read")
    if one_family:
        print(f"  {len(one_family)} of these rest on ONE body of data "
              f"({', '.join(v['ticker'] for v in one_family[:8])}"
              f"{'...' if len(one_family) > 8 else ''}) — usually no published "
              f"statements.")
    # ONLY TRUE WHEN A SHORTLIST WAS TAKEN. With `--deepen all` every tradeable
    # name got the lenses, there is no selection, and printing the warning anyway
    # would teach the reader to ignore it on the runs where it matters.
    if report["counts"]["deepened"] < report["counts"]["tradeable"]:
        print(f"  The {report['counts']['deepened']} deepened names were PRE-SELECTED "
              f"on the price rank out of")
        print(f"  {report['counts']['tradeable']} tradeable, so that component is high "
              f"for nearly all of them by")
        print("  construction. What separates these rows is mostly the other four.")


def _wrap(text: str, width: int) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(text or "", width))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--market", default="ID", choices=["ID", "US"])
    parser.add_argument("--universe", default=None,
                        help="A named index instead of the whole market "
                             "(idx30, lq45, dow30, nasdaq100, idxresources).")
    parser.add_argument("--tickers", default=None,
                        help="A comma-separated list instead of a universe, or "
                             "@path to read one from a file (commas or newlines, "
                             "# comments allowed).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Scan only the N largest listings by market cap.")
    parser.add_argument("--deepen", default="40",
                        help="How many top-ranked names get the four lenses (default 40), "
                             "or 'all' for every tradeable name. 'all' costs one "
                             "fundamentals fetch per name — a few minutes for IDX — and "
                             "is cached per day, so the second run is free.")
    parser.add_argument("--deepen-bottom", type=int, default=0,
                        help="Also deepen the N worst-ranked names, to see what a "
                             "genuinely bad reading looks like (default 0).")
    parser.add_argument("--hold", default=None,
                        help="Names you already own. Always deepened whatever their "
                             "rank, because a scan that only examines its own favourites "
                             "can never tell you to sell.")
    parser.add_argument("--turnover-floor", type=float, default=None,
                        help="Median daily turnover, in the listing's currency, below "
                             "which a name is untradeable. Defaults to "
                             f"{verdict.TURNOVER_FLOOR}.")
    parser.add_argument("--include-illiquid", action="store_true",
                        help="Score every listing, including the ones below the "
                             "turnover floor. They are still GATED as untradeable — "
                             "this widens what gets looked at, never what gets "
                             "recommended. Note that it also changes what every "
                             "percentile is taken against: see --help-population.")
    parser.add_argument("--help-population", action="store_true",
                        help="Explain what --include-illiquid does to the percentiles, "
                             "and exit.")
    parser.add_argument("--risk-budget", type=float, default=0.02,
                        help="Annualised risk contribution per position, for sizing.")
    parser.add_argument("--max-weight", type=float, default=0.10,
                        help="Cap on any one position's suggested weight.")
    parser.add_argument("--workers", type=int, default=2,
                        help="Concurrent deepen fetches. MEASURED, not guessed: at 4 a "
                             "775-name sweep got the quality lens on 10%% of names, and "
                             "24 of those refetched one at a time returned it on 20. "
                             "Speed here is bought with data, and the trade is bad — the "
                             "missing lens is the one that marks names DOWN. Use 1 for a "
                             "full-market sweep you intend to act on.")
    parser.add_argument("--max-charts", type=int, default=MAX_CHARTS,
                        help=f"How many rows keep a drawn chart in the report "
                             f"(default {MAX_CHARTS}, taken from both ends of the "
                             f"ranking). Every directional row is charted until this "
                             f"bites; 758 of them made a 27MB file.")
    parser.add_argument("--fundamentals-days", type=int,
                        default=market_data.FUNDAMENTALS_TTL_DAYS,
                        help=f"Days to reuse cached STATEMENTS across runs "
                             f"(default {market_data.FUNDAMENTALS_TTL_DAYS}, 0 to "
                             f"disable). Filings move quarterly, so this is what "
                             f"makes a multi-day whole-market sweep possible. The "
                             f"price and the FX rate are always refetched.")
    parser.add_argument("--cache-days", type=int, default=CACHE_KEEP_DAYS,
                        help=f"Days of cached lens payloads to keep (default "
                             f"{CACHE_KEEP_DAYS}). A full-market sweep leaves about "
                             f"500MB behind per day and older days are never read.")
    parser.add_argument("--no-cache", action="store_true",
                        help="Ignore today's cached lens payloads and refetch.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--out", default=None,
                        help="Report path without extension. Defaults to "
                             "reports/scan-<market>-<date>.")
    args = parser.parse_args()

    if getattr(args, "help_population", False):
        print(POPULATION_NOTE)
        return 0

    raw = str(args.deepen).strip().lower()
    if raw in {"all", "-1"}:
        # None means "no ceiling"; the slice below reads it as the whole list.
        args.deepen = None
    else:
        try:
            args.deepen = max(0, int(raw))
        except ValueError:
            parser.error(f"--deepen takes a whole number or 'all', not {args.deepen!r}")

    report = run(args)

    stem = args.out or str(REPORT_DIR / f"scan-{args.market.upper()}-"
                                        f"{dt.date.today().isoformat()}")
    json_path = Path(f"{stem}.json")
    html_path = Path(f"{stem}.html")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(clean(report), indent=1))

    # THE SCREEN PRINTS AFTER THE TABLE, NOT INSIDE IT. These names are, almost
    # by definition, not near the top of the ranking — the blend has no opinion
    # about them, which is the entire reason the screen exists. Folding them
    # into the ordered list would hide them again.
    neglected = report.get("neglected") or {}
    if not args.quiet and neglected.get("selected"):
        rows = neglected.get("tradeable") or []
        print(f"\n  Cheap, solid and uncovered — {neglected['selected']} selected, "
              f"{len(rows)} of them tradeable:")
        if rows:
            print(f"    {'ticker':10} {'score':>5} {'action':10} {'value':>5} "
                  f"{'qual':>5} {'inst%':>6}  field")
            # Already ordered leaders-first by `_neglected_summary`; not re-sorted
            # here, so the terminal and the report agree on what comes first.
            for row in rows:
                held = row.get("institutionsHeld")
                mark = "*" if row.get("leadsField") else " "
                where = row.get("industry") or "field unknown"
                if row.get("fieldRank") and row.get("fieldPeers"):
                    where += f" ({row['fieldRank']}/{row['fieldPeers']})"
                print(f"  {mark} {row['ticker']:10} {(row.get('score') or 0):5.1f} "
                      f"{row.get('action')!s:10} {(row.get('value') or 0):5.0f} "
                      f"{(row.get('quality') or 0):5.0f} "
                      f"{(held * 100 if held is not None else 0):5.1f}%  "
                      f"{where[:38]}")
                if row.get("summary"):
                    print(f"      {str(row['summary'])[:96]}")
        else:
            print("    none of them clears the gates, which is the usual outcome: "
                  "a company nobody covers is usually a company nobody trades.")
        leads = neglected.get("leadTheirField") or 0
        if leads:
            print(f"    * = the largest of the scanned names carrying its industry "
                  f"label — {leads} of the {neglected['selected']} selected. That is a "
                  f"standing among measured peers, not market share: private and "
                  f"overseas competitors are not in it.")
        held_back = len(neglected.get("gated") or [])
        print(f"    {held_back} more {'was' if held_back == 1 else 'were'} selected "
              f"and gated.")
        print("    Nothing here is measured — no point-in-time filings exist to "
              "backtest it against. Recorded in the scan log to be judged later.")

    # THE INTERSECTION, FIRST, because it is the answer to the question the rest
    # of this report only supplies parts of. It is printed above the field
    # leaders and the cheap-and-uncovered screen rather than below them: those
    # two are the ingredients, and a reader who wanted the ingredients can read
    # on.
    specialists = report.get("specialists") or {}
    if not args.quiet and specialists.get("selected"):
        base = specialists.get("baseRates") or {}
        # EVERY SELECTED NAME, GATED OR NOT, WITH THE GATE BESIDE IT.
        #
        # Printing only the tradeable ones hid the whole list on the first full
        # sweep: all seven were gated, and the top of them — the name this was
        # built to find — was gated on `poorEntry` alone, which is a statement
        # about today's price and not about the company. A screen for companies
        # nobody trades that hides everything nobody trades has no output.
        rows = list(specialists.get("tradeable") or []) + list(
            specialists.get("gated") or [])
        tradeable = len(specialists.get("tradeable") or [])
        print(f"\n  Profitable specialists nobody is covering — "
              f"{specialists['selected']} of {base.get('scanned', 0)} scanned, "
              f"{tradeable} of them clear every gate:")
        for row in rows:
            if row["soleListing"]:
                where = "no listed rival in"
            elif row["onlyRanked"]:
                where = f"only measurable of {row['unrankedRivals'] + 1} in"
            else:
                where = "largest in"
            print(f"    {row['ticker']:10} {(row.get('score') or 0):5.1f} "
                  f"{row.get('action')!s:10} "
                  f"{(row.get('revenueCagr') or 0) * 100:6.1f}%/yr  "
                  f"margin {(row.get('netMargin') or 0) * 100:5.1f}%  "
                  f"{row['yearsProfitable']}/{row['yearsAvailable']} yrs  "
                  f"{where} {str(row.get('industry'))[:26]}")
            if row.get("gates"):
                print(f"      gated: "
                      f"{'; '.join(g['label'] for g in row['gates'])}")
            if row.get("summary"):
                print(f"      {str(row['summary'])[:100]}")
        # THE BASE RATES, BECAUSE THE INTERSECTION LOOKS LIKE THREE DEMANDING
        # TESTS AND ONE OF THEM ADMITS MOST OF THE MARKET.
        print(f"    Ingredients on this scan: "
              f"{base.get('specialist', 0) * 100:.0f}% are the largest or only name in "
              f"their field, {base.get('compounding', 0) * 100:.0f}% are profitable "
              f"every year with cash behind it and growing in the top quartile, and "
              f"{base.get('unattended', 0) * 100:.0f}% are uncovered — which is the "
              f"loosest of the three by a distance.")
        print("    Nothing here is measured against future returns; see the note in "
              "the report.")

    # THE FIELD LEADERS, WHETHER OR NOT ANYTHING ELSE LIKES THEM. Separate from
    # the screen above because it answers a different question: that list is
    # "cheap, solid and unwatched", this one is "the biggest of the names doing
    # this thing", and a reader hunting an underrated champion wants to see both
    # halves rather than only their intersection.
    fields = report.get("fields") or {}
    if not args.quiet and fields.get("leaders"):
        found = len(fields["leaders"])
        print(f"\n  Largest scanned name in its field — {found} of "
              f"{len(fields.get('fields') or {})} fields "
              f"{'has' if found == 1 else 'have'} one:")
        by_ticker = {v["ticker"]: v for v in report.get("verdicts") or []}
        for industry in fields["leaders"][:12]:
            block = fields["fields"][industry]
            entry = by_ticker.get(block["leader"]) or {}
            place = entry.get("fieldPosition") or {}
            share = place.get("share")
            print(f"    {block['leader']:10} {(entry.get('score') or 0):5.1f} "
                  f"{entry.get('action')!s:10} {block['leaderMargin']:5.1f}x next, "
                  f"{(share * 100 if share else 0):4.0f}% of {block['peers']:3} "
                  f"peers   {industry[:34]}")
        missing = fields.get("unplaced") or 0
        if missing:
            print(f"    {missing} name{'' if missing == 1 else 's'} could not be placed "
                  f"at all — no industry label or no comparable revenue — so any thin "
                  f"field above may simply be missing its real leader.")

    # WHAT THE SCANNER SAID, WRITTEN DOWN ON THE DAY IT SAID IT. The value and
    # quality components cannot be reconstructed as they stood on a past date —
    # this data source has no point-in-time filings — so a prospective log is
    # the only honest way they will ever be measured. It produces nothing
    # useful for months and that is the nature of the instrument, not a fault.
    logged = scanlog.record(REPORT_DIR, args.market.upper(), report["verdicts"],
                            regime=report.get("regime"))

    from render_scan import render
    html_path.write_text(render(report))

    if not args.quiet:
        print_summary(report)
        print(f"\n  {json_path}")
        print(f"  {html_path}")
        print(f"  {logged['path']} — {logged['added']} calls recorded, "
              f"{logged['total']} in the log")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
