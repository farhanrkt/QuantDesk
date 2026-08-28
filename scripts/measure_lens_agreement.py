#!/usr/bin/env python3
"""
measure_lens_agreement.py
=========================
Measure how much the four lenses actually agree, and record the answer.

THE CLAIM BEING TESTED
-----------------------
The confluence rail says, on every run and in the largest type on the page,
that four lenses rest on two independent bodies of data — and therefore that
agreement between those two "is not one fact counted twice". Both the rail and
`explain._agreement` then admit the grouping is "a stated assumption about what
shares a source, not a measured correlation", with the reason given as: *"the
ranking panel measures its own overlap because a scan gives it a cross-section
to measure from, and a single ticker does not."*

That reason is true of a request and false of a script. This is the script.

WHY IT RUNS THE PRODUCTION ENGINES RATHER THAN A CHEAPER APPROXIMATION
------------------------------------------------------------------------
`calibrate_checks.py` measures its price-family checks from a single batched
OHLCV download, calling the same estimator functions the engines call. That
works there because a check is three estimator calls deep.

A lens VOTE is not. It is the end of a chain — fetch, engineer features, fit an
Isolation Forest, classify the flow bias — and reassembling that chain outside
`whale_payload` and `technical_payload` would be a second implementation of the
thing under measurement. This whole exercise is a measurement of what THIS APP
says about many companies; a number measured from a lookalike of the app would
answer a question nobody asked.

So this imports `api/index.py` and calls the four payload builders `/api/
confluence` itself calls, with the parameters the UI actually sends (`INITIAL`
in `app/page.tsx`: a 2y anomaly window, a 5y chart range, threshold detection at
-0.10). The votes then come out of `explain.for_synthesis`, and the family votes
out of `explain._family_votes` — the exact function the synthesis uses, not a
copy of its rule, because the grouping under test has to be the grouping that
ships.

The cost is that nothing batches: two OHLCV fetches per symbol (the two lenses
want different windows) plus one company fetch that the value and quality
lenses share through `market_data.company`'s day cache. Four universes is a
quarter of an hour or so against an endpoint with no SLA, which is exactly why
this is a script, is outside CI, and writes a stamped file.

Symbols are deduplicated before anything runs. IDX30 is a subset of LQ45 and
the Dow overlaps the Nasdaq-100, so measuring per universe would push a third
of the names through every engine twice and weight them twice in the result.

A LENS THAT COULD NOT READ DOES NOT VOTE
-----------------------------------------
`None`, never 0. A bank's accounting screens are refused rather than neutral,
and recording that refusal as a neutral vote would manufacture agreement with
every other lens that happened to be quiet — the same "absence is not evidence"
error the pre-trade panel keeps a separate `notChecked` list to avoid. A
reading whose tone is `none` is the app saying it declined to answer, so it is
dropped here rather than counted.

WHAT COMES OUT
--------------
`api/_lib/lens_agreement.json`, stamped with its date and the universes it was
taken over, holding for each population — all names, and each market on its
own — the six pairwise lens agreements, the one that matters (price family
against filings family), and the effective number of independent lenses.

RE-RUN IT whenever a lens's VERDICT logic changes: `explain._read_flow`,
`_read_trend`, `_read_value`, `_read_quality`, `_family_votes`, or anything
upstream that moves a verdict band. A stale agreement number attached to
changed votes is worse than none, because the panel prints it with a date that
makes it look checked.

USAGE
    python scripts/measure_lens_agreement.py                # measure and write
    python scripts/measure_lens_agreement.py --dry-run      # print, write nothing
    python scripts/measure_lens_agreement.py --limit 12     # a quick smoke run
    python scripts/measure_lens_agreement.py --universes dow30 idx30
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

import index as api  # noqa: E402  — the production payload builders, deliberately

from _lib import explain  # noqa: E402
from _lib import lensagreement as agreement  # noqa: E402
from _lib import universes  # noqa: E402

OUTPUT = ROOT / "api" / "_lib" / "lens_agreement.json"

DEFAULT_UNIVERSES = ("dow30", "nasdaq100", "idx30", "lq45")

# Exactly what the ticker bar sends on a first run (`INITIAL` in app/page.tsx).
# Measuring the votes a different configuration produces would be measuring an
# app nobody is looking at — the same reason `calibrate_checks.py` pins its
# window to `INITIAL.range`.
ANOMALY_PERIOD = "2y"
CHART_RANGE = "5y"
DETECTION_MODE = "threshold"
SCORE_THRESHOLD = -0.10


def _legs(symbol: str, market: str) -> dict:
    """The four confluence legs for one symbol, each reporting its own failure.

    Mirrors the `leg()` helper inside `/api/confluence` rather than sharing it,
    because that one is an async closure over a FastAPI request. What matters is
    that the SHAPE is identical — `{"ok": bool, "data"|"error"}` — since that is
    the contract `explain.for_synthesis` reads, and a leg recorded as absent
    where the route would record it as failed would change the vote.
    """
    legs: dict = {}
    builders = {
        "anomaly": lambda: api.whale_payload(
            symbol, period=ANOMALY_PERIOD, mode=DETECTION_MODE,
            score_threshold=SCORE_THRESHOLD),
        "technical": lambda: api.technical_payload(
            symbol, range_key=CHART_RANGE, market_code=market),
        "valuation": lambda: api.valuation_payload(symbol, market_code=market),
        "quality": lambda: api.quality_payload(symbol),
    }
    for name, build in builders.items():
        try:
            legs[name] = {"ok": True, "data": build()}
        except Exception as exc:            # one leg must not sink the others
            legs[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return legs


def _votes(legs: dict) -> tuple[dict, dict]:
    """One symbol's lens votes and family votes, as the app itself computes them.

    `for_synthesis` is the public entry point and `_family_votes` is the private
    helper it uses; both are called rather than reimplemented. The grouping of
    lenses into families is the assumption under test here, so measuring it
    against a second copy of that grouping would test nothing.

    A reading whose tone is `none` is a refusal, not a neutral vote — see the
    module docstring. It comes back as None and is excluded pairwise.
    """
    # `agreement_measurement=None` deliberately: the synthesis would otherwise
    # load the artifact THIS SCRIPT WRITES. The votes do not depend on it, so
    # nothing would actually go round in a circle — but a measurement that reads
    # its own previous output is the shape of a bug worth never having, and the
    # warrant sentence it would build is thrown away here anyway.
    synthesis = explain.for_synthesis(legs, agreement_measurement=None)
    readings = synthesis.get("readings") or []

    lens_votes = {key: None for key in agreement.LENS_ORDER}
    for reading in readings:
        if reading.get("tone") != "none":
            lens_votes[reading["key"]] = int(reading["vote"])

    families = explain._family_votes(readings)
    family_votes = {name: (families[name]["vote"] if name in families else None)
                    for name in ("price", "filings")}
    return lens_votes, family_votes


def _population(rows: list[dict], label: str) -> dict:
    """The whole measurement over one set of names.

    COVERAGE IS PER POPULATION, NOT GLOBAL, and that is the whole reason this
    function takes a subset at all. Every pairwise `n` below is bounded by how
    often the two lenses could read anything, and on the Indonesian lists that
    bound is the finding rather than the footnote — a filings lens that reads on
    four names in five is measuring its agreement on four names in five, and a
    reader comparing the two markets' kappas needs to see that before comparing
    them. A single blended coverage figure would hide exactly the gap
    `calibrate_checks.py` had to split its firing rates over.
    """
    lens_votes = {lens: [row["lenses"][lens] for row in rows]
                  for lens in agreement.LENS_ORDER}
    family_votes = {name: [row["families"][name] for row in rows]
                    for name in ("price", "filings")}
    coverage = {lens: sum(1 for vote in votes if vote is not None)
                for lens, votes in lens_votes.items()}
    measured = agreement.measure(lens_votes, family_votes)
    return {"label": label, "names": len(rows), "coverage": coverage, **measured}


def _label(names: list[str]) -> str:
    """The universes named the way a sentence would name them.

    Interpolated straight into "Measured across 141 names in ___", so it has to
    read as English in that slot and has to name the group — the same
    requirement, and the same reason, as `calibrate_checks._label`.
    """
    if not names:
        return "the calibration universes"
    named = [n if n.lower().startswith("the ") else f"the {n}" for n in names]
    if len(named) == 1:
        return named[0]
    return ", ".join(named[:-1]) + f" and {named[-1]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure lens agreement.")
    parser.add_argument("--dry-run", action="store_true", help="print without writing")
    parser.add_argument("--universes", nargs="*", default=list(DEFAULT_UNIVERSES))
    parser.add_argument("--limit", type=int, default=None,
                        help="only the first N unique symbols — a smoke run, "
                             "not a measurement worth stamping")
    args = parser.parse_args()

    # Unique symbols first, each remembering which market and which lists it
    # came through. IDX30 is a subset of LQ45; measuring per universe would run
    # every Indonesian large cap twice and weight it twice in the combined
    # number, which is the same deduplication `calibrate_checks.summarise`
    # exists to get right.
    plan: dict[str, dict] = {}
    covered: list[str] = []
    for universe_id in args.universes:
        entry = universes.get(universe_id)
        if entry is None:
            print(f"  unknown universe {universe_id!r} — skipped")
            continue
        for symbol in entry["tickers"]:
            record = plan.setdefault(symbol, {"market": entry["market"], "lists": []})
            record["lists"].append(universe_id)
        covered.append(entry["name"])

    symbols = list(plan)
    if args.limit:
        symbols = symbols[:args.limit]
    if not symbols:
        print("Nothing to measure. Nothing written.")
        return 1

    print(f"{len(symbols)} unique symbols across {len(covered)} universes.")
    print("Every one runs all four production engines — roughly three upstream")
    print(f"calls each, so expect about {len(symbols) * 4 // 60 + 1} minutes.\n")

    noise = io.StringIO()
    rows: list[dict] = []
    failed: list[str] = []
    started = time.monotonic()

    for position, symbol in enumerate(symbols, start=1):
        market = plan[symbol]["market"]
        try:
            with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
                legs = _legs(symbol, market)
                lens_votes, family_votes = _votes(legs)
        except Exception as exc:            # a symbol must not sink the run
            failed.append(f"{symbol}: {type(exc).__name__}")
            continue

        rows.append({"symbol": symbol, "market": market,
                     "lenses": lens_votes, "families": family_votes})
        if position % 10 == 0 or position == len(symbols):
            elapsed = time.monotonic() - started
            print(f"  {position:4d}/{len(symbols)}  {elapsed / position:.1f}s per name "
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
        "anomalyPeriod": ANOMALY_PERIOD,
        "chartRange": CHART_RANGE,
        "minPairSample": agreement.MIN_PAIR_SAMPLE,
        "bootstrapDraws": agreement.BOOTSTRAP_DRAWS,
        "populations": populations,
    }

    for key, population in populations.items():
        total = population["names"]
        print(f"\n{key} — {population['label']} ({total} names)")
        print("  read at all: " + "  ".join(
            f"{agreement.LENS_LABEL[lens]} {count}/{total} ({count / total:.0%})"
            for lens, count in population["coverage"].items()))
        families = population.get("families")
        if families and families.get("usable"):
            print(f"  price vs filings   κ = {families['kappa']:+.3f}  "
                  f"[{families['low']:+.3f}, {families['high']:+.3f}]  "
                  f"observed {families['observed']:.1%} vs chance "
                  f"{families['chance']:.1%}  n = {families['n']}")
        else:
            print("  price vs filings   not usable on this population")
        for pair in population.get("pairs") or []:
            mark = " " if pair["usable"] else "!"
            kappa = f"{pair['kappa']:+.3f}" if pair["kappa"] is not None else "  n/a"
            tau = f"{pair['tauB']:+.3f}" if pair["tauB"] is not None else "  n/a"
            print(f" {mark}{pair['a']:8}/{pair['b']:8} κ = {kappa}  τb = {tau}  "
                  f"n = {pair['n']:4d}")
        lenses = population.get("lenses") or {}
        if lenses.get("available"):
            print(f"  effective lenses   {lenses['effectiveLenses']:.2f} of "
                  f"{lenses['measuredLenses']} on {lenses['completeCases']} "
                  f"complete cases")
        else:
            print(f"  effective lenses   withheld — {lenses.get('reason')}")

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
