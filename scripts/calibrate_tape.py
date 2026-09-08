#!/usr/bin/env python3
"""
calibrate_tape.py
=================
Measure the cross-sectional baselines `tape.py` tests against, per market.

    python scripts/calibrate_tape.py
    python scripts/calibrate_tape.py --market ID --sample 250

DELIBERATELY OUTSIDE CI, like the other network scripts here. It re-runs when
somebody thinks the baselines have moved, and the artifact it writes carries the
date it was taken so a stale number is visible rather than assumed.

WHY THIS EXISTS AT ALL — THE BUG IT REMOVES
--------------------------------------------
The first version of `tape.py` tested each name's heavy-day close location
against ZERO. Measured afterwards across 120 Indonesian listings, the median
name reads +0.08: heavy sessions close higher in their range than ordinary ones
almost everywhere, because volume arrives with up-moves. Testing against zero
therefore called the MEDIAN STOCK an accumulation candidate — a confident,
plausible, universally wrong reading.

The same measurement found the two scale constants were wrong by a factor of
three between markets, and that the volume-concentration bands, which had been
guessed, sat at the 75th percentile of one market and the 99th of another.

So all four are measured here and none is a literal in the reading code.

WHAT THE ARTIFACT SAYS ABOUT THE SIGNAL ITSELF
-----------------------------------------------
`significantShare` is the fraction of a market where the test fires at the
conventional 5% bar. Against chance alone that number should BE 5%. It is not
the same in the two markets this app covers, and the difference is the most
interesting thing the script produces — see the README section on the scanner.
Publish it whichever way it comes out; a market where the number is 5% is a
market where this signal does not exist, and that has to be sayable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import numpy as np                                                   # noqa: E402
import pandas as pd                                                  # noqa: E402
from scipy import stats                                              # noqa: E402

from _lib import listings, market_data, tape, universes              # noqa: E402

ARTIFACT = ROOT / "api" / "_lib" / "tape_calibration.json"

# Which population each market is measured on. IDX uses the fetched whole-market
# listing because that is the population the scanner actually sweeps; the US
# uses the two hardcoded index lists, because there is no cached US listing on
# most checkouts and those two are what the other stamped artifacts already
# describe.
POPULATION = {
    "ID": {"kind": "listing", "label": "the Indonesian listed market"},
    "US": {"kind": "universes", "ids": ["nasdaq100", "dow30"],
           "label": "the Nasdaq-100 and the Dow"},
}

# Below this many usable names a percentile is not a measurement. Thirty is the
# same floor `pretrade.MIN_CALIBRATION_SAMPLE` uses, and for the same reason: a
# baseline quoted from twenty names is quoting noise.
MIN_SAMPLE = 30

HISTORY_DAYS = 600


def symbols_for(market: str, sample: int) -> tuple[list[str], str]:
    spec = POPULATION[market]
    if spec["kind"] == "listing":
        picked = listings.symbols_for(market, limit=sample)
        if not picked:
            raise SystemExit(
                f"No cached listing for {market}. Run:\n"
                f"    python scripts/refresh_listings.py --market {market}")
        return picked, spec["label"]

    out: list[str] = []
    for universe_id in spec["ids"]:
        entry = universes.get(universe_id)
        if entry:
            out.extend(entry["tickers"])
    return list(dict.fromkeys(out))[:sample], spec["label"]


def measure(market: str, sample: int, quiet: bool = False) -> dict:
    picked, label = symbols_for(market, sample)
    say = (lambda *a: None) if quiet else (lambda *a: print(*a, flush=True))

    say(f"\n{market}: fetching {len(picked)} histories ...")
    end = dt.date.today()
    frames = market_data.ohlcv_batch(picked, end - dt.timedelta(days=HISTORY_DAYS), end)
    say(f"  {len(frames)} returned usable history")

    lifts: list[float] = []
    wicks: list[float] = []
    tops: list[float] = []
    p_values: list[float] = []

    for frame in frames.values():
        raw = tape.statistics(frame)
        if not raw["available"]:
            continue
        lifts.append(raw["lift"])
        if raw["wick"] is not None:
            wicks.append(raw["wick"])
        top = (raw["concentration"] or {}).get("topFiveShare")
        if top is not None:
            tops.append(float(top))

    if len(lifts) < MIN_SAMPLE:
        say(f"  only {len(lifts)} names produced a reading — below the {MIN_SAMPLE} "
            f"floor, so no row is written for {market}")
        return {}

    lift_series = pd.Series(lifts, dtype="float64")
    median = float(lift_series.median())

    # THE SIGNIFICANCE RATE IS MEASURED AGAINST THE BASELINE THIS RUN PRODUCES,
    # not against zero. Quoting a firing rate computed under a null the reading
    # code does not use would describe a different test from the one that ships.
    for frame in frames.values():
        raw = tape.statistics(frame)
        if not raw["available"]:
            continue
        _, p_value = stats.ttest_ind(
            raw["heavyValues"] - median, raw["ordinaryValues"], equal_var=False)
        if np.isfinite(p_value):
            p_values.append(float(p_value))

    fired = sum(1 for p in p_values if p < tape.ALPHA)
    wick_series = pd.Series(wicks, dtype="float64")
    top_series = pd.Series(tops, dtype="float64")

    row = {
        "names": len(lifts),
        "population": label,
        "measuredOn": dt.date.today().isoformat(),
        "liftMedian": median,
        "liftSd": float(lift_series.std(ddof=1)),
        "liftP05": float(lift_series.quantile(0.05)),
        "liftP95": float(lift_series.quantile(0.95)),
        "wickSd": float(wick_series.std(ddof=1)) if len(wick_series) > 1 else None,
        "wickMedian": float(wick_series.median()) if len(wick_series) else None,
        "significantShare": (fired / len(p_values)) if p_values else None,
        "significantCount": fired,
        "tested": len(p_values),
        # The bands are percentiles of the market being scanned, so a "caution"
        # is by construction the top quarter of it and a "severe" the top
        # twentieth. That is what stops a band from describing the market
        # instead of the company — the argument `pretrade.py` makes about every
        # flag it demotes to a base condition.
        "concentration": {
            "caution": float(top_series.quantile(0.75)) if len(top_series) else None,
            "severe": float(top_series.quantile(0.95)) if len(top_series) else None,
            "median": float(top_series.median()) if len(top_series) else None,
        },
    }

    say(f"  {len(lifts)} names read")
    say(f"  lift median {row['liftMedian']:+.3f}, sd {row['liftSd']:.3f}")
    say(f"  wick sd {row['wickSd']:.3f}" if row["wickSd"] else "  wick sd unavailable")
    say(f"  concentration caution {row['concentration']['caution']:.3f}, "
        f"severe {row['concentration']['severe']:.3f}")
    say(f"  fires on {fired}/{len(p_values)} "
        f"({row['significantShare'] * 100:.1f}%) against {tape.ALPHA * 100:.0f}% "
        f"expected by chance")
    return row


def headline(markets: dict) -> str:
    """The finding, in the terms the README and the report quote it in."""
    parts = []
    for row in markets.values():
        share = row.get("significantShare")
        if share is None:
            continue
        parts.append(f"{share * 100:.0f}% of {row['population']} ({row['names']} names)")
    if not parts:
        return "No market produced enough names to measure."
    return (
        "Share of each market where heavy-session close location differs from that "
        "market's own median at the 5% bar: " + "; ".join(parts) + ". Chance alone "
        f"predicts {tape.ALPHA * 100:.0f}%. A market at that number is a market where "
        "this signal does not exist.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--market", action="append", default=None, choices=["ID", "US"],
                        help="Repeatable. Defaults to both.")
    parser.add_argument("--sample", type=int, default=250,
                        help="Largest N listings per market (default 250).")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    markets: dict = {}
    for market in (args.market or ["ID", "US"]):
        row = measure(market, args.sample, quiet=args.quiet)
        if row:
            markets[market] = row

    if not markets:
        print("Nothing measured; the artifact was left alone.", file=sys.stderr)
        return 1

    payload = {
        "measuredOn": dt.date.today().isoformat(),
        "window": tape.WINDOW,
        "heavyQuantile": tape.HEAVY_QUANTILE,
        "alpha": tape.ALPHA,
        "headline": headline(markets),
        "markets": markets,
    }
    ARTIFACT.write_text(json.dumps(payload, indent=1))
    if not args.quiet:
        print(f"\n{payload['headline']}")
        print(f"\nwritten to {ARTIFACT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
