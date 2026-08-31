#!/usr/bin/env python3
"""
build_glossary.py
=================
Regenerate the field manual's glossary from the app's own explanation layer.

WHY THIS EXISTS
---------------
`docs/field-manual.html` documents every metric the app can explain. Those
definitions are NOT transcribed — they are the exact strings `_lib/explain.py`
puts on screen, injected here as a JS array. That is the whole point: a manual
whose glossary is typed by hand is wrong the first time a metric changes wording,
and wrong silently, because nothing compares the two.

So the definitions have one source. Add a metric to `explain.py`, run this, and
the manual carries the same sentence the info icon does.

WHAT IT ENFORCES, BEYOND COPYING
--------------------------------
1. EVERY REGISTERED METRIC IS CLASSIFIED. `LENS` below maps each key to the part
   of the app it belongs to, and a key that is registered but unclassified — or
   classified but no longer registered — fails the run. Adding a metric without
   deciding where it belongs is the exact mistake that would otherwise ship a
   glossary quietly missing an entry.

2. EVERY METRIC PRODUCES A READING. An interpreter that returns None for every
   probe value is either broken or takes context arguments this script does not
   supply; either way the manual cannot document it and should say so loudly.

3. THE FILE STAYS PURE ASCII. The published page is wrapped in a head this repo
   does not control, so it cannot rely on a charset declaration. Every non-ASCII
   character in the prose is an HTML entity and every one in the script is a
   `\\uXXXX` escape. A stray em dash pasted in later would render as mojibake on
   whichever host serves it without UTF-8; this check is what stops that.

USAGE
-----
    python scripts/build_glossary.py            # rewrite docs/field-manual.html
    python scripts/build_glossary.py --check    # fail if it is out of date (CI)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

MANUAL = ROOT / "docs" / "field-manual.html"

# Which part of the app each metric belongs to. The manual's filter chips read
# these keys, so a new group needs a chip in the HTML as well as an entry here.
LENS: dict[str, str] = {}


def _group(name: str, keys: str) -> None:
    for key in keys.split():
        if key in LENS:
            raise SystemExit(f"{key!r} is classified twice")
        LENS[key] = name


_group("trend-long", """
    cagr volatility downsideDeviation sharpe sortino calmar var95 cvar95 skew kurtosis
    positiveDays worstDay bestDay maxDrawdown currentDrawdown timeUnderWaterDays ulcerIndex
    maxDrawdownRecoveryDays hurst momentum12_1 roc252 roc63 faberDistance fromHigh52w
    fromAllTimeHigh rangePosition regressionSlope regressionR2 relativeExcess
    benchmarkCorrelation rollingWorst""")
_group("trend-ind", """
    sma200 sma100 sma50 adx aroon rsi stochastic williamsR cci macd bbPercentB
    bbBandwidth atrPct mfi cmf volumeTrend coppock""")
_group("trend-swing", """
    riskReward stopDistance positionShare distanceToLevel vwapDistance
    squeezePercentile volumeRatio divergenceState gapState""")
_group("quality", "piotroski altman beneish altmanComponent beneishIndex")
_group("flow", "spread moveVsSpread yangZhangVol amihud anomalyRate qValue cusumEpisode flowBias")
_group("value", "upside probUndervalued terminalShare discountRate valuationSpread impliedGrowth")
_group("rank", "compositeRank signalRank signalOverlap")
_group("pretrade", "checkFiringRate")
_group("provenance", "validationDomain manipulationPosterior")
_group("portfolio", "holdingCorrelation effectiveHoldings riskShare "
                    "sharedDirection sharedDriver")

# Values chosen to land inside SOME band of every ladder in the registry. An
# interpreter is asked in turn until one returns a reading; the specific value
# does not matter because only `label`, `what` and `goodDirection` are used, and
# those do not vary by band.
PROBES = (1.0, 0.5, 50.0, 0.05, -0.2, 2.0, 25.0, 100.0, 8.0, -1.9, 0.004, 72.0)


def collect() -> list[dict]:
    from _lib import explain as E

    registered = set(E._REGISTRY)
    unclassified = registered - set(LENS)
    stale = set(LENS) - registered
    if unclassified or stale:
        raise SystemExit(
            "The glossary classification is out of sync with _lib/explain.py.\n"
            + (f"  registered but unclassified: {sorted(unclassified)}\n" if unclassified else "")
            + (f"  classified but not registered: {sorted(stale)}\n" if stale else "")
            + "  Fix LENS in this script, and add a filter chip to the manual if the\n"
              "  metric belongs to a group that does not exist yet."
        )

    rows = []
    for key, fn in E._REGISTRY.items():
        result = None
        for probe in PROBES:
            try:
                result = fn(probe)
            except Exception:
                continue
            if result:
                break
        if not result:
            raise SystemExit(
                f"{key!r} produced no reading for any probe value, so it cannot be "
                f"documented. Either its interpreter is broken or it needs context "
                f"arguments this script does not supply."
            )
        rows.append({"k": key, "t": result["label"], "d": result["what"],
                     "g": result["goodDirection"], "l": LENS[key]})

    rows.sort(key=lambda r: r["t"].lower())
    return rows


def render(html: str, rows: list[dict]) -> str:
    # ensure_ascii keeps the data as \uXXXX escapes. HTML entities would be wrong
    # here — they are not interpreted inside a JS string literal, and the page
    # escapes what it renders, so "&mdash;" would appear literally on screen.
    data = json.dumps(rows, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")

    # The array sits on ONE line. Matching to end-of-line rather than to the first
    # semicolon matters: a non-greedy `.*?;` stops at a semicolon inside the data
    # and leaves the tail behind.
    html, count = re.subn(r"const GLOSSARY = .*\n",
                          lambda _: f"const GLOSSARY = {data};\n", html, count=1)
    if count != 1:
        raise SystemExit("Could not find the `const GLOSSARY = ...` line in the manual.")

    # The count appears in the contents, the lede, the section intro and the
    # search placeholder. Leaving any of them stale is the kind of small lie that
    # makes a reader distrust the rest.
    n = len(rows)
    html = re.sub(r"\b\d+ terms\b", f"{n} terms", html)
    html = re.sub(r"\b\d+ metrics defined\b", f"{n} metrics defined", html)
    html = re.sub(r"\bAll \d+ metrics\b", f"All {n} metrics", html)
    return html


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if the manual is out of date")
    args = parser.parse_args()

    if not MANUAL.exists():
        raise SystemExit(f"{MANUAL} not found.")

    original = MANUAL.read_text(encoding="ascii")
    rows = collect()
    updated = render(original, rows)

    non_ascii = sorted({c for c in updated if ord(c) > 127})
    if non_ascii:
        raise SystemExit(
            f"Non-ASCII characters in the manual: {non_ascii}. Use an HTML entity in "
            f"the prose (&mdash;, &ldquo;) so the page does not depend on the host "
            f"declaring a charset."
        )

    if args.check:
        if updated != original:
            print("docs/field-manual.html is out of date. Run:\n"
                  "    python scripts/build_glossary.py", file=sys.stderr)
            return 1
        print(f"Manual is up to date ({len(rows)} metrics).")
        return 0

    if updated == original:
        print(f"No change ({len(rows)} metrics).")
        return 0

    MANUAL.write_text(updated, encoding="ascii")
    print(f"Updated {MANUAL.relative_to(ROOT)} ({len(rows)} metrics).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
