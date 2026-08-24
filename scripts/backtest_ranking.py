#!/usr/bin/env python3
"""
backtest_ranking.py
===================
Measure whether the composite ranking predicts returns, and record the answer.

WHY THE RESULT IS STORED RATHER THAN COMPUTED PER REQUEST
---------------------------------------------------------
Running this costs a full universe download plus a ranking at every rebalance —
seconds per universe, and the same numbers every time until the market moves.
It is a research finding about the signals, not a per-user computation, so it is
measured here, written to `api/_lib/backtest_results.json`, and served from
there with the date it was taken. That is the same treatment `universes.py`
gives constituent lists, and for the same reason: a figure that decays slowly
should be stamped rather than recomputed.

Re-run it after changing anything in `ranking.py` — the weights, the signals,
the window — because those are exactly the changes that could move the answer,
and a stale finding attached to a changed model would be worse than none.

USAGE
    python scripts/backtest_ranking.py            # measure and write
    python scripts/backtest_ranking.py --dry-run  # print, write nothing
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

from _lib import backtest  # noqa: E402
from _lib import eventstudy  # noqa: E402
from _lib import universes  # noqa: E402

OUTPUT = ROOT / "api" / "_lib" / "backtest_results.json"

# Horizons a reader might plausibly hold for, in trading days.
HORIZONS = (21, 63, 126)
YEARS = 6


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print without writing")
    parser.add_argument("--years", type=int, default=YEARS)
    args = parser.parse_args()

    results = {}
    noise = io.StringIO()
    for universe_id in ("dow30", "nasdaq100", "idx30", "lq45"):
        entry = universes.get(universe_id)
        for horizon in HORIZONS:
            print(f"  {universe_id:10} {horizon:>3}d ...", end="", flush=True)
            # yfinance narrates delisted constituents to stdout; the table is
            # the output that matters here.
            with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
                outcome = backtest.run(entry["tickers"], market_code=entry["market"],
                                       horizon=horizon, years=args.years)
            if not outcome["usable"]:
                print(f" unusable ({outcome['reason'][:40]})")
                continue
            ic, spread = outcome["informationCoefficient"], outcome["quintileSpread"]
            print(f" IC {ic['mean']:+.4f} (t {ic['tStat']:+.2f})"
                  f"  spread {spread['mean']:+.2%} (p {spread['pValue']:.3f})")
            # The per-period detail is large and only interesting while
            # debugging; the summary is what gets served.
            outcome.pop("periods", None)
            results[f"{universe_id}:{horizon}"] = {
                "universe": entry["name"], "universeId": universe_id,
                "market": entry["market"], **outcome,
            }

    if not results:
        print("\nNothing measurable. Nothing written.")
        return 1

    # TWELVE TESTS PRODUCE A WINNER BY CONSTRUCTION, and this app corrects for
    # that everywhere else — the screener runs Benjamini-Hochberg over its scan
    # for exactly this reason. Four universes at three horizons is a family of
    # twelve, so at the conventional 5% cutoff more than half a "discovery" is
    # expected from chance alone. Reporting the best of twelve without saying so
    # is the single easiest way to manufacture an edge out of noise, and it
    # would be indefensible in the one module whose whole job is to check.
    #
    # Both statistics are corrected. The earlier version of this script tested
    # only the quintile spread and would have reported "0 of 12 significant"
    # while an information coefficient sat at t = +2.23 — the more sensitive of
    # the two measures, unexamined.
    keys = list(results)
    ic_p = [results[k]["informationCoefficient"]["pValue"] for k in keys]
    spread_p = [results[k]["quintileSpread"]["pValue"] for k in keys]
    ic_fdr = eventstudy.benjamini_hochberg(ic_p, alpha=0.10)
    spread_fdr = eventstudy.benjamini_hochberg(spread_p, alpha=0.10)

    for i, key in enumerate(keys):
        results[key]["informationCoefficient"]["qValue"] = ic_fdr["qValues"][i]
        results[key]["quintileSpread"]["qValue"] = spread_fdr["qValues"][i]

    def positive_and_below(alpha, use_q):
        out = []
        for i, key in enumerate(keys):
            for block, qs in (("informationCoefficient", ic_fdr),
                              ("quintileSpread", spread_fdr)):
                stat = results[key][block]
                value = qs["qValues"][i] if use_q else (stat["pValue"] or 1.0)
                if stat["mean"] > 0 and value < alpha:
                    out.append(f"{key}:{block}")
        return out

    raw_hits = positive_and_below(0.05, use_q=False)
    surviving = positive_and_below(0.10, use_q=True)

    payload = {
        "measuredOn": dt.date.today().isoformat(),
        "years": args.years,
        "tests": len(results) * 2,
        "rawHits": len(raw_hits),
        "rawHitNames": raw_hits,
        "significant": len(surviving),
        "expectedByChance": round(len(results) * 2 * 0.05, 1),
        "headline": _headline(len(results), surviving, raw_hits, results),
        "results": results,
    }

    if args.dry_run:
        print("\n--- would write ---")
        print(json.dumps(payload, indent=2)[:1200])
        return 0

    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\n{len(raw_hits)} of {len(results) * 2} raw hits at p<0.05 "
          f"({payload['expectedByChance']} expected by chance); "
          f"{len(surviving)} survive FDR correction.")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


def _headline(total: int, significant: list, raw_hits: list, results: dict) -> str:
    """One sentence the ranking panel can print without further interpretation."""
    if not significant:
        floors = [v["informationCoefficient"]["minimumDetectable"]
                  for v in results.values()
                  if v["informationCoefficient"].get("minimumDetectable")]
        floor = min(floors) if floors else None
        tail = (f" The most sensitive of them could only have detected a mean information "
                f"coefficient of about {floor:.2f}, and a useful one in this field is "
                f"nearer 0.03 — so this is 'no edge large enough to see here', not "
                f"'no edge'." if floor else "")
        chance = round(total * 2 * 0.05, 1)
        raw = ""
        if raw_hits:
            raw = (f" {len(raw_hits)} of the {total * 2} individual tests cleared the "
                   f"conventional 5% cutoff before correction, against {chance} expected "
                   f"from chance alone at that many tests — which is why the correction "
                   f"is applied rather than the best result quoted.")
        return (f"Across {total} backtests — four universes at three holding periods, two "
                f"statistics each — none showed a relationship between a name's rank and "
                f"its subsequent return that survives correcting for having run them "
                f"all.{raw}{tail}")
    return (f"{len(significant)} of {total} tests showed a positive relationship between "
            f"rank and subsequent return at p<0.05. Read them against the survivorship "
            f"and cost caveats before treating any as an edge.")


if __name__ == "__main__":
    raise SystemExit(main())
