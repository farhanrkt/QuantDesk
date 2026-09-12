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
import json
import os
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

from _lib import (basket, chartlayers, listings, market_data,        # noqa: E402
                  microstructure, ownership, patterns, pretrade, ranking,
                  scanlog, structure, symbols, tape, universes, verdict,
                  volumeprofile)
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
        raw = [t.strip() for t in args.tickers.replace("\n", ",").split(",") if t.strip()]
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


def _looks_throttled(message: str) -> bool:
    text = (message or "")
    return any(marker.lower() in text.lower() for marker in _THROTTLE_MARKERS)


def cache_path(symbol: str, day: str) -> Path:
    return CACHE_DIR / day / f"{symbol.replace('/', '_')}.json"


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
            return json.loads(path.read_text())
        except ValueError:
            pass

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

    legs = {
        "anomaly": leg(lambda: whale_payload(symbol, period="2y")),
        "technical": leg(lambda: technical_payload(symbol, range_key="2y",
                                                   market_code=market)),
        "valuation": leg(lambda: valuation_payload(
            symbol, **_valuation_kwargs(market=market))),
        "quality": leg(lambda: quality_payload(symbol)),
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
    lens_reads: dict[str, int] = {}
    for legs in legs_by_ticker.values():
        for name, payload in (legs or {}).items():
            lens_reads[name] = lens_reads.get(name, 0) + int(bool(payload.get("ok")))
    attempted = len(legs_by_ticker)
    degraded = []
    if attempted:
        say("\nWhat actually came back, per lens:")
        for name in sorted(lens_reads):
            share = lens_reads[name] / attempted
            flag = "" if share >= LENS_HEALTHY else "   <-- mostly missing"
            if share < LENS_HEALTHY:
                degraded.append(name)
            say(f"  {name:10} {lens_reads[name]:>5} of {attempted} ({share * 100:4.0f}%)"
                f"{flag}")
        if degraded:
            say(f"\n  WARNING: {', '.join(degraded)} came back for fewer than "
                f"{LENS_HEALTHY * 100:.0f}% of names. This is almost always the provider "
                f"rate-limiting rather than missing filings — a missing component has "
                f"its weight removed from the blend, so names this lens would have "
                f"marked DOWN are scored too high. Re-run with --workers 1 before "
                f"trusting the ordering.")

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
        result["costs"] = structure.round_trip_cost(liquidity)
        result["tape"] = tape_result
        result["register"] = register_result
        result["patterns"] = pattern_result
        result["volumeProfile"] = profile_result
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

    verdicts.sort(key=lambda v: (v["score"] is None, -(v["score"] or 0.0)))

    # --- where each name sits inside its OWN sector -------------------------
    # A coal miner in the top decile of a coal rally and one in the top decile
    # of the whole market are different findings, and the second is the one the
    # overall rank reports. This adds the first without touching any score:
    # sector membership is not evidence about a company, and percentile-ing
    # inside a group of four would be arithmetic on noise.
    _rank_within_sector(verdicts, say)

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
                        help="A comma-separated list instead of a universe.")
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
