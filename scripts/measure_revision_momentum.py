#!/usr/bin/env python3
"""
measure_revision_momentum.py
============================
Measure whether the expectations lens's signal led the price, and record the
answer whichever way it comes out.

WHAT IS BEING TESTED, AND WHY IT HAD TO BE TESTED FIRST
--------------------------------------------------------
`expectations.py` votes, and a vote reaches the confluence rail's headline where
agreement between families reads as corroborating evidence. That is a predictive
claim about estimate revisions, and this repo's rule is that such a claim is
measured offline and published including nulls, or it does not ship.

The full argument for the design — and its severe limitation, which is that the
source supplies exactly one usable window — is in `_lib/revisionmomentum.py`.
The short version:

  signal   how far the consensus level for the current fiscal year moved
           between 90 and 60 days ago, from `eps_trend`
  outcome  the market-adjusted return over the 60 days since
  bridge   whether that level drift moves with the revision COUNT, which is the
           quantity that actually votes and which has no history at all

The signal is complete 60 days before the outcome window opens, so nothing here
can see the future. What it cannot do is see more than one window.

WHY IT DOES NOT RUN THE PRODUCTION ENGINES
-------------------------------------------
`measure_lens_agreement.py` imports `api/index.py` and calls the payload
builders, because a lens vote is the end of a long chain and reassembling it
outside the app would measure a lookalike. This measures something different:
two functions in `_lib/expectations.py`, called directly, on a record fetched by
`_lib/market_data.estimates`. Both are the production code paths. There is no
chain to reassemble, so there is nothing to be gained by paying for four engines
per name.

That makes this run cheap by comparison — one estimates fetch per name, plus a
single batched OHLCV download for the whole universe.

USAGE
    python scripts/measure_revision_momentum.py                # measure and write
    python scripts/measure_revision_momentum.py --dry-run      # print, write nothing
    python scripts/measure_revision_momentum.py --limit 12     # a smoke run
    python scripts/measure_revision_momentum.py --universes dow30 idx30
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from _lib import expectations  # noqa: E402
from _lib import market_data  # noqa: E402
from _lib import revisionmomentum as rm  # noqa: E402
from _lib import universes  # noqa: E402

OUTPUT = ROOT / "api" / "_lib" / "revision_momentum.json"

DEFAULT_UNIVERSES = ("dow30", "nasdaq100", "idx30", "lq45")

# Extra calendar days fetched beyond the outcome window, so that a window whose
# start lands on a weekend or an exchange holiday still has a bar to anchor on.
# Ten is comfortably more than the longest run of consecutive non-trading days
# on either exchange, including the Idul Fitri closure on the IDX.
CALENDAR_SLACK = 10


def _return_over(frame, days: int) -> float | None:
    """The simple return over the last `days` CALENDAR days of a price frame.

    Anchored on the last bar at or before the cutoff rather than on a fixed
    number of ROWS, because the two markets do not share a trading calendar and
    a row count would silently measure a different span on each. The IDX loses
    about a week to Idul Fitri that no US exchange loses.
    """
    if frame is None or frame.empty or "Close" not in frame.columns:
        return None
    closes = frame["Close"].dropna()
    if len(closes) < 2:
        return None

    cutoff = closes.index[-1] - dt.timedelta(days=days)
    earlier = closes[closes.index <= cutoff]
    if earlier.empty:
        return None

    start, end = float(earlier.iloc[-1]), float(closes.iloc[-1])
    if not (start > 0):
        return None
    return end / start - 1.0


def _signal(record: dict) -> float | None:
    """The revision formed BEFORE the outcome window: 90 days ago to 60 days ago.

    Both columns are read off the same `eps_trend` snapshot, so this is the one
    place in the app where a historical signal exists at all. `revision_drift`
    is not reused here because it compares against `current` by construction,
    which would put the signal and the outcome in the same window.

    Same three outcomes as `revision_drift`, and for the same reasons: a level
    that crossed zero returns None rather than a percentage computed across it.
    """
    trend = record.get("eps_trend")
    before = expectations._cell(trend, "0y", f"{rm.SIGNAL_FROM_DAYS}daysAgo")
    after = expectations._cell(trend, "0y", f"{rm.SIGNAL_TO_DAYS}daysAgo")
    import numpy as np
    if not (np.isfinite(before) and np.isfinite(after)) or before == 0:
        return None
    if (before > 0) != (after > 0):
        return None
    return float((after - before) / abs(before))


def _population(rows: list[dict], label: str) -> dict:
    """The whole measurement over one set of names.

    The outcome is demeaned WITHIN MARKET even inside a single-market
    population, so the ALL population and the per-market ones are computed the
    same way rather than one of them quietly skipping the adjustment.
    """
    signals = [r["signal"] for r in rows]
    outcomes = rm.demean_within([r["outcome"] for r in rows],
                                [r["market"] for r in rows])
    breadth = [r["breadth"] for r in rows]
    drift = [r["drift"] for r in rows]

    return {
        "label": label,
        "names": len(rows),
        "coverage": {
            "estimatesRead": sum(1 for r in rows if r["applicable"]),
            "signalFormed": sum(1 for s in signals if s is not None),
            "outcomeAvailable": sum(1 for o in outcomes if o is not None),
        },
        # THE FORWARD TEST. Signal formed 60 days before the outcome opened.
        "forward": rm.association(
            "estimate revision (90d->60d) against the next 60 days, market-adjusted",
            signals, outcomes),
        # THE BRIDGE. Does the measurable proxy move with the quantity that votes?
        "bridge": rm.association(
            "estimate level drift against analyst revision breadth, same date",
            drift, breadth),
        "dispersion": rm.dispersion_frame([r["dispersion"] for r in rows]),
    }


def _label(names: list[str]) -> str:
    """The universes named the way a sentence would name them.

    Interpolated straight into "across 141 names in ___", so it has to read as
    English in that slot — same requirement and same reason as
    `measure_lens_agreement._label`.
    """
    if not names:
        return "the calibration universes"
    named = [n if n.lower().startswith("the ") else f"the {n}" for n in names]
    if len(named) == 1:
        return named[0]
    return ", ".join(named[:-1]) + f" and {named[-1]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure revision momentum.")
    parser.add_argument("--dry-run", action="store_true", help="print without writing")
    parser.add_argument("--universes", nargs="*", default=list(DEFAULT_UNIVERSES))
    parser.add_argument("--limit", type=int, default=None,
                        help="only the first N unique symbols — a smoke run, "
                             "not a measurement worth stamping")
    args = parser.parse_args()

    # Unique symbols first. IDX30 is a subset of LQ45 and the Dow overlaps the
    # Nasdaq-100; measuring per universe would weight a third of the names twice.
    plan: dict[str, dict] = {}
    covered: list[str] = []
    for universe_id in args.universes:
        entry = universes.get(universe_id)
        if entry is None:
            print(f"  unknown universe {universe_id!r} — skipped")
            continue
        for symbol in entry["tickers"]:
            plan.setdefault(symbol, {"market": entry["market"]})
        covered.append(entry["name"])

    symbols = list(plan)
    if args.limit:
        symbols = symbols[:args.limit]
    if not symbols:
        print("Nothing to measure. Nothing written.")
        return 1

    print(f"{len(symbols)} unique symbols across {len(covered)} universes.")
    print("One estimates fetch each, plus one batched price download.\n")

    # PRICES FIRST, AND IN ONE BATCH. The outcome window is the same for every
    # name, so this is a single `yf.download` per chunk rather than a per-symbol
    # round trip — the difference between seconds and minutes on this half.
    end = dt.date.today()
    start = end - dt.timedelta(days=rm.OUTCOME_DAYS + CALENDAR_SLACK)
    noise = io.StringIO()
    with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
        frames = market_data.ohlcv_batch(symbols, start, end)
    print(f"Prices came back for {len(frames)} of {len(symbols)} symbols.\n")

    rows: list[dict] = []
    failed: list[str] = []
    started = time.monotonic()

    for position, symbol in enumerate(symbols, start=1):
        try:
            with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
                record = market_data.estimates(symbol)
                reading = expectations.analyze(record, symbol=symbol)
                signal = _signal(record)
        except Exception as exc:            # a symbol must not sink the run
            failed.append(f"{symbol}: {type(exc).__name__}")
            continue

        applicable = bool(reading.get("applicable"))
        breadth = (reading.get("breadth") or {}).get("diffusion") if applicable else None
        drift = ((reading.get("drift") or {}).get("annual30") or {}).get("change") \
            if applicable else None
        dispersion = (reading.get("dispersion") or {}).get("spread") if applicable else None

        rows.append({
            "symbol": symbol,
            "market": plan[symbol]["market"],
            "applicable": applicable,
            "signal": signal,
            "outcome": _return_over(frames.get(symbol), rm.OUTCOME_DAYS),
            "breadth": breadth,
            "drift": drift,
            "dispersion": dispersion,
        })
        if position % 25 == 0 or position == len(symbols):
            elapsed = time.monotonic() - started
            print(f"  {position:4d}/{len(symbols)}  {elapsed / position:.2f}s per name "
                  f"({len(failed)} failed)")

    if not rows:
        print("\nNo symbol produced a reading. Nothing written.")
        return 1

    markets = sorted({row["market"] for row in rows})
    populations = {"ALL": _population(rows, _label(covered))}
    for market in markets:
        subset = [row for row in rows if row["market"] == market]
        names = [universes.get(u)["name"] for u in args.universes
                 if universes.get(u) and universes.get(u)["market"] == market]
        populations[market] = _population(subset, _label(names))

    payload = {
        "measuredOn": dt.date.today().isoformat(),
        "universeIds": [u for u in args.universes if universes.get(u)],
        "universes": covered,
        "universeLabel": _label(covered),
        "namesMeasured": len(rows),
        "namesFailed": len(failed),
        "window": {"signalFrom": rm.SIGNAL_FROM_DAYS, "signalTo": rm.SIGNAL_TO_DAYS,
                   "outcome": rm.OUTCOME_DAYS},
        "minSample": rm.MIN_SAMPLE,
        "bootstrapDraws": rm.BOOTSTRAP_DRAWS,
        "populations": populations,
    }

    for key, population in populations.items():
        total = population["names"]
        coverage = population["coverage"]
        print(f"\n{key} — {population['label']} ({total} names)")
        print(f"  estimates read {coverage['estimatesRead']}/{total} "
              f"({coverage['estimatesRead'] / total:.0%})   "
              f"signal formed {coverage['signalFormed']}   "
              f"outcome {coverage['outcomeAvailable']}")
        for name in ("forward", "bridge"):
            entry = population.get(name)
            if not entry:
                print(f"  {name:8} not computable on this population")
                continue
            mark = " " if entry["usable"] else "!"
            interval = (f"[{entry['low']:+.3f}, {entry['high']:+.3f}]"
                        if entry["low"] is not None else "[no interval]")
            print(f" {mark}{name:8} rho = {entry['rho']:+.3f}  {interval}  "
                  f"n = {entry['n']:4d}"
                  + ("  EXCLUDES ZERO" if entry["excludesZero"] else ""))
        spread = population.get("dispersion")
        if spread:
            print(f"  dispersion  median {spread['median']:.0%}  "
                  f"[{spread['p25']:.0%}, {spread['p75']:.0%}]  n = {spread['n']}")
        else:
            print("  dispersion  too few names to frame")
        print(f"  grade       {rm._grade(population.get('forward'), population.get('bridge'))}")

    if failed:
        print(f"\n{len(failed)} symbols produced nothing: {', '.join(failed[:12])}"
              + (" ..." if len(failed) > 12 else ""))

    if args.limit:
        print("\n--limit was set, so this is a smoke run. Not written.")
        return 0
    if args.dry_run:
        print("\n--- would write ---")
        print(json.dumps(payload, indent=2))
        return 0

    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nWrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
