#!/usr/bin/env python3
"""
calibrate_checks.py
===================
Measure how often each pre-trade check fires, and record the answer.

WHY A CHECK WITHOUT A FIRING RATE IS NOT SHIPPABLE
---------------------------------------------------
"Altman says distress" is unreadable on its own. Whether it is a finding about
this company or a description of the equity market depends entirely on how often
it is true of companies in general, and nothing in this repo knew that number.
Presenting nine conditions as nine alarms without it recreates exactly the
multiple-testing problem `eventstudy.screener_significance` already corrects on
the anomaly screener — a scan produces hits by construction, and the hit count
means nothing until you know how many were expected.

So `_lib/pretrade.py` refuses to render a check that has no measured rate, and
demotes one that fires on more than a third of the universe from a flag to a
stated base condition. This script is what supplies those rates.

WHY IT IS A SCRIPT AND NOT A REQUEST, AND WHY IT IS NOT IN CI
--------------------------------------------------------------
Two reasons, and they are the same two that put `backtest_ranking.py` and
`check_data_invariants.py` outside CI.

It needs the network, and CI must never be reddened by a Yahoo outage. And the
filings half does not batch: `Ticker.financials` is one call per symbol at
seconds each, so four universes is roughly ten minutes of sequential fetching
against an endpoint with no SLA. That is a research measurement about the checks,
not a per-user computation, so it is measured here, written to
`api/_lib/check_calibration.json`, and served from there with its date.

RE-RUN IT WHENEVER A CHECK CHANGES — a new condition, a moved threshold, a
different predicate. A stale rate attached to a changed check is worse than no
rate, because it is a number the panel will present with confidence.

HOW THE TWO HALVES ARE MEASURED
--------------------------------
The predicates in `pretrade.py` read the ASSEMBLED confluence payload, so this
script builds that payload shape rather than reimplementing any threshold. That
is load-bearing: a calibration that recomputed "is Altman below 4.35" separately
from the check would drift from it silently, and the drift would be invisible
because both numbers would look plausible.

  PRICE checks are measured from a batched OHLCV download — the same
  `market_data.ohlcv_batch` the ranking tier uses — with the exact estimator
  calls `technical.analyze` and `whale_payload` make. A hundred names is a
  handful of upstream requests.

  FILINGS checks need `fetch_company` per symbol. `market_data.company` caches
  per symbol per day, so quality and valuation together cost ONE fetch each.

COULD-NOT-RUN IS COUNTED SEPARATELY FROM DID-NOT-FIRE
------------------------------------------------------
A bank whose accounting screens are refused has not passed them. The firing rate
is over the names where the check could actually be evaluated, and the count of
names where it could not is recorded beside it — otherwise a check that is
inapplicable to half the universe would report an artificially low rate and be
promoted from base condition to flag by its own coverage gap.

USAGE
    python scripts/calibrate_checks.py               # measure and write
    python scripts/calibrate_checks.py --dry-run     # print, write nothing
    python scripts/calibrate_checks.py --universes dow30 idx30
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from _lib import expectations as expectations_engine  # noqa: E402
from _lib import indicators as ind  # noqa: E402
from _lib import longterm as lt  # noqa: E402
from _lib import market_data  # noqa: E402
from _lib import microstructure  # noqa: E402
from _lib import pretrade  # noqa: E402
from _lib import quality as quality_engine  # noqa: E402
from _lib import ranking  # noqa: E402
from _lib import universes  # noqa: E402
from _lib import valuation  # noqa: E402

OUTPUT = ROOT / "api" / "_lib" / "check_calibration.json"

# Five years, because that is the range the app itself loads by default
# (`INITIAL.range` in app/page.tsx) and the one `hasLongTerm` is normally
# satisfied by. Calibrating on a different window would measure a different
# question from the one the panel asks.
YEARS = 5

DEFAULT_UNIVERSES = ("dow30", "nasdaq100", "idx30", "lq45")


def _price_legs(frame) -> dict:
    """The confluence legs a price-family check reads, from a batched frame.

    Every call here is the one the production engine makes:
    `technical.analyze` calls `lt.drawdown_profile` and `ind.hurst_estimate` on
    the close series behind `hasLongTerm`, and `whale_payload` calls
    `microstructure.liquidity_profile` on the OHLCV frame. Nothing is
    reimplemented, so a threshold can only live in one place.
    """
    close = frame["Close"].astype("float64")
    enough = len(frame) >= 252          # technical.MIN_LONGTERM_BARS
    return {
        "technical": {"ok": True, "data": {
            "hasLongTerm": bool(enough),
            "longTerm": {
                "hurstReading": (ind.hurst_estimate(close) if enough
                                 else {"verdict": "unavailable"}),
                "drawdown": (lt.drawdown_profile(close) if enough
                             else {"usable": False}),
            },
        }},
        "anomaly": {"ok": True, "data": {
            "liquidity": microstructure.liquidity_profile(frame),
        }},
    }


def _filings_legs(symbol: str) -> dict:
    """The confluence legs a filings-family check reads, for one symbol.

    Both lenses go through `fetch_company`, which `market_data.company` caches
    per symbol per day — so the second one costs no second network call.
    """
    legs: dict = {}
    try:
        company = market_data.company(symbol)
    except Exception as exc:
        return {"quality": {"ok": False, "error": str(exc)},
                "valuation": {"ok": False, "error": str(exc)}}

    if not company.get("ok"):
        legs["quality"] = {"ok": False, "error": "no company data"}
    else:
        try:
            legs["quality"] = {"ok": True, "data": quality_engine.analyze(company)}
        except Exception as exc:
            legs["quality"] = {"ok": False, "error": str(exc)}

    market_code = "ID" if symbol.upper().endswith(".JK") else "US"
    try:
        legs["valuation"] = {"ok": True,
                             "data": valuation.analyze(symbol, market_code=market_code)}
    except Exception as exc:
        legs["valuation"] = {"ok": False, "error": str(exc)}
    return legs


def _estimates_legs(symbol: str) -> dict:
    """The confluence leg an estimates-family check reads, for one symbol.

    One fetch per symbol, like the filings half and for the same reason: the
    analyst tables are scraped per listing and nothing batches them. It is the
    cheaper of the two — one call rather than five — but it is still why this
    script is a script.

    NO `ok: False` BRANCH ON AN UNCOVERED LISTING. A company nobody follows
    produces a perfectly good reading whose `applicable` is false, and the
    predicate turns that into `unchecked` with the count in the reason. Failing
    the leg here instead would report the same names as an ENGINE failure, and
    `summarise` counts those identically — so the distinction would survive in
    the payload and die in the calibration.
    """
    try:
        record = market_data.estimates(symbol)
    except Exception as exc:
        return {"expectations": {"ok": False, "error": str(exc)}}
    try:
        return {"expectations": {"ok": True,
                                 "data": expectations_engine.analyze(record, symbol=symbol)}}
    except Exception as exc:
        return {"expectations": {"ok": False, "error": str(exc)}}


# OUTCOMES ARE KEYED BY SYMBOL, NOT COUNTED AS THEY ARRIVE, and that is not
# bookkeeping fussiness. IDX30 is a SUBSET of LQ45: adding four universes' counts
# together would weight every Indonesian large cap twice and quietly tilt every
# combined rate toward one market. The per-universe breakdown is still per
# universe; the headline rate is over the DEDUPLICATED union of symbols.
def summarise(states: dict) -> dict:
    """Fired / did-not-fire / could-not-be-tested for one check, kept apart.

    `sampleSize` is the count of names where the check could actually be
    evaluated. Could-not-run is reported beside it rather than folded in: a
    check that is inapplicable to half the universe would otherwise report an
    artificially low firing rate and be promoted from base condition to flag by
    its own coverage gap.
    """
    fired = sum(1 for state in states.values() if state == "fired")
    quiet = sum(1 for state in states.values() if state == "quiet")
    unchecked = len(states) - fired - quiet
    evaluated = fired + quiet
    return {"fired": fired, "sampleSize": evaluated, "couldNotRun": unchecked,
            "firingRate": (fired / evaluated) if evaluated else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print without writing")
    parser.add_argument("--universes", nargs="*", default=list(DEFAULT_UNIVERSES))
    parser.add_argument("--years", type=int, default=YEARS)
    args = parser.parse_args()

    predicates = pretrade.predicates()
    price_ids = [c["id"] for c in pretrade.CHECKS if c["family"] == "price"]
    filings_ids = [c["id"] for c in pretrade.CHECKS if c["family"] == "filings"]
    estimates_ids = [c["id"] for c in pretrade.CHECKS if c["family"] == "estimates"]

    end = dt.date.today()
    start = end - dt.timedelta(days=int(365.25 * args.years) + 30)

    combined: dict = {}
    covered: list[str] = []
    # Which universes belong to which market, so the per-market rate can be
    # labelled with the group it is a percentage OF.
    markets_seen: dict = {}
    noise = io.StringIO()

    for universe_id in args.universes:
        entry = universes.get(universe_id)
        if entry is None:
            print(f"  unknown universe {universe_id!r} — skipped")
            continue
        symbols = entry["tickers"]
        print(f"\n{entry['name']} ({len(symbols)} names)")
        # {check_id: {symbol: state}} — see the note above `summarise`.
        states: dict = {check_id: {} for check_id in predicates}

        # --- price half: one batch download for the whole universe ---------
        print("  price checks ...", end="", flush=True)
        with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
            frames = market_data.ohlcv_batch(symbols, start, end)
        for symbol, frame in frames.items():
            if len(frame) < ranking.MIN_BARS:
                continue
            legs = _price_legs(frame)
            for check_id in price_ids:
                states[check_id][symbol] = predicates[check_id](legs)["state"]
        print(f" {len(frames)} frames")

        # --- filings half: one fetch per symbol, which is why this is a script
        print(f"  filings checks (one fetch per name, ~{len(symbols) * 3}s) ...",
              end="", flush=True)
        for index, symbol in enumerate(symbols, start=1):
            with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
                legs = _filings_legs(symbol)
            for check_id in filings_ids:
                states[check_id][symbol] = predicates[check_id](legs)["state"]
            if index % 10 == 0:
                print(".", end="", flush=True)
        print(" done")

        # --- estimates half: one fetch per symbol, cheaper than the filings one
        if estimates_ids:
            print(f"  estimate checks (one fetch per name, ~{len(symbols) * 2}s) ...",
                  end="", flush=True)
            for index, symbol in enumerate(symbols, start=1):
                with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
                    legs = _estimates_legs(symbol)
                for check_id in estimates_ids:
                    states[check_id][symbol] = predicates[check_id](legs)["state"]
                if index % 10 == 0:
                    print(".", end="", flush=True)
            print(" done")

        for check_id in sorted(states):
            summary = summarise(states[check_id])
            if summary["firingRate"] is None:
                print(f"    {check_id:26} no evaluable names")
            else:
                print(f"    {check_id:26} {summary['firingRate']:6.1%} "
                      f"of {summary['sampleSize']:3d}  "
                      f"({summary['couldNotRun']} not testable)")

        for check_id, per_symbol in states.items():
            entry_states = combined.setdefault(
                check_id, {"states": {}, "universes": {}, "markets": {}})
            entry_states["universes"][universe_id] = summarise(per_symbol)
            # Last write wins on a symbol seen in two universes, which is
            # correct: the outcome is a property of the company, not of the list
            # it was reached through.
            entry_states["states"].update(per_symbol)
            entry_states["markets"].setdefault(entry["market"], {}).update(per_symbol)
        covered.append(entry["name"])
        markets_seen.setdefault(entry["market"], []).append(entry["name"])

    if not combined:
        print("\nNothing measurable. Nothing written.")
        return 1

    # A RATE BLENDED ACROSS TWO MARKETS IS THE WRONG NUMBER FOR A COMPANY IN
    # EITHER, and this run is what proved it. "Scores built from incomplete
    # data" came out at 10% of the Dow and 80% of IDX30: Yahoo's coverage of
    # smaller Indonesian filings is the app's biggest known fragility, and it is
    # a fact about the data source, not about any company. The blend lands near
    # 40% — alarming for a US large cap where the condition is genuinely
    # unusual, reassuring for an IDX one where it is the norm.
    #
    # So each check carries a per-market rate as well as the combined one, and
    # `pretrade._rate_for` prefers the market the reader is actually looking at.
    def classify(summary: dict) -> str:
        rate, sample = summary["firingRate"], summary["sampleSize"]
        if rate is None or sample < pretrade.MIN_CALIBRATION_SAMPLE:
            return "uncalibrated"
        return "base" if rate > pretrade.BASE_RATE_MAX else "flag"

    checks = {}
    for check_id, entry in combined.items():
        summary = summarise(entry["states"])
        checks[check_id] = {
            **summary,
            "namesMeasured": len(entry["states"]),
            "classification": classify(summary),
            "markets": {
                market: {**summarise(per_symbol),
                         "classification": classify(summarise(per_symbol))}
                for market, per_symbol in entry["markets"].items()
            },
            "universes": entry["universes"],
        }

    payload = {
        "measuredOn": dt.date.today().isoformat(),
        "years": args.years,
        "universeIds": [u for u in args.universes if universes.get(u)],
        "universeLabel": _label(covered),
        "universes": covered,
        # Interpolated into "Fires on 8% of ___", so it has to read as English
        # in that slot and has to name the group without ambiguity.
        "marketLabels": {market: _label(names)
                         for market, names in markets_seen.items()},
        "markets": markets_seen,
        "baseRateMax": pretrade.BASE_RATE_MAX,
        "minSampleSize": pretrade.MIN_CALIBRATION_SAMPLE,
        "checks": checks,
    }

    if args.dry_run:
        print("\n--- would write ---")
        print(json.dumps(payload, indent=2))
        return 0

    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nWrote {OUTPUT.relative_to(ROOT)}")
    for market in sorted(markets_seen):
        print(f"\n  {market} — {payload['marketLabels'][market]}")
        for label, name in (("base", "    ordinary for this market"),
                            ("uncalibrated", "    withheld, no usable rate")):
            hit = sorted(k for k, v in checks.items()
                         if (v["markets"].get(market) or {}).get("classification") == label)
            if hit:
                print(f"{name}: {', '.join(hit)}")
    return 0


# The label is interpolated straight into "Fires on 8% of ___", so it has to read
# as English in that slot AND it has to name the group. "two index universes" is
# grammatical and useless — a reader cannot tell whether their company was
# compared against US large caps or Indonesian ones, which is precisely the
# distinction the per-market rates exist to draw. So a short list is spelled out
# and only a long one collapses to a count.
_WORDS = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def _label(names: list[str]) -> str:
    """The universe named the way a sentence would name it."""
    if not names:
        return "the calibration universe"
    named = [n if n.lower().startswith("the ") else f"the {n}" for n in names]
    if len(named) == 1:
        return named[0]
    if len(named) <= 3:
        return " and ".join([", ".join(named[:-1]), named[-1]]) if len(named) > 2 \
            else " and ".join(named)
    return f"{_WORDS.get(len(names), len(names))} index universes"


if __name__ == "__main__":
    raise SystemExit(main())
