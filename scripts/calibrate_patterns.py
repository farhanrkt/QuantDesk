#!/usr/bin/env python3
"""
calibrate_patterns.py
=====================
Do the chart patterns predict anything, and how often do they fire anyway?

    python scripts/calibrate_patterns.py
    python scripts/calibrate_patterns.py --market ID --sample 250 --years 6

DELIBERATELY OUTSIDE CI, like the other network scripts here, and stamped with
the date it ran.

WHAT THIS DECIDES
-----------------
Everything. `patterns.py` detects ten Lo-Mamaysky-Wang formations and scores
NOTHING until this script has run — and then it scores only the patterns whose
forward returns survived a correction across every pattern and horizon tested.
`swing.py` declines these shapes partly on the grounds that LMW found "some
incremental distributional information, not a demonstrated net edge", and the
only honest way to ship them is to put that question to the data and abide by
the answer.

THE TWO NUMBERS, AND WHY BOTH ARE NEEDED
-----------------------------------------
FIRING RATE answers the objection `swing.py` actually raises: a matcher that
fires on a third of names every quarter is describing the market, not the
company. It is measured as the share of scanned names showing the pattern at
least once, and it is published whether it flatters the feature or not.

FORWARD EXCESS RETURN answers whether it matters. For every detection, the
stock's return over the next N sessions minus the market's over the same
sessions, starting from the day AFTER detection — because a detection made on
the close of day t is not actionable until day t+1, and starting on day t itself
would hand the study a free day of hindsight.

THE MULTIPLE-TESTING PROBLEM IS THE WHOLE PROBLEM
--------------------------------------------------
Ten patterns times three horizons is thirty tests, and at a 5% bar roughly one
and a half of them clear by chance alone before anything real is measured.
Quoting the best of thirty would be the exact error `ranking.validation` exists
to avoid — it reports "1 of 24 tests cleared before correction, against 1.2
expected" rather than the winner. So every p-value here goes through
Benjamini-Hochberg together, and `significant` means survived that, not
"p < 0.05".

TWO WAYS THIS MEASUREMENT LIED BEFORE IT WAS FIXED
---------------------------------------------------
Both produced large, confident, entirely spurious edges, and both are worth
writing down because the second one is the same mistake `tape.py` makes a whole
docstring about.

1. THE OBSERVATIONS ARE NOT INDEPENDENT. The first version pooled every
   detection into one t-test. Bottom patterns fire together — a market-wide
   selloff puts dozens of names into a double bottom in the same fortnight, and
   the recovery that follows is ONE event counted a hundred times. So detections
   are now COLLAPSED BY CALENDAR MONTH: every detection of one pattern in one
   month contributes a single monthly mean, and the test runs on those. Six
   years gives about seventy separate market episodes rather than a large sample
   of one.

2. THE NULL WAS ZERO, AND ZERO IS NOT THE BASELINE. This is the error that
   mattered. Measured across sixty Indonesian names over five years, the
   UNCONDITIONAL mean 63-day excess return over the index is +13.4% — because
   the scanned names are the large caps, they outran the index over that
   stretch, and equity returns are right-skewed enough that a few enormous
   winners drag the mean far above the +0.7% median. Against a null of zero,
   every pattern looks brilliant. The version of this script that tested that
   way reported triangle bottoms beating the market by 12.2% a quarter with five
   patterns surviving correction — when 12.2% is BELOW the 13.4% a randomly
   chosen day would have given.

   So each detection is now measured against the CROSS-SECTIONAL MEAN OF ITS OWN
   MONTH: the average forward excess across every name in the sample over the
   same window, whether or not any pattern fired. The question becomes "did the
   names showing this pattern beat the names that did not, in the same month",
   which is the only version of it that is not answered by the sample's own
   drift.

One residual limitation, stated rather than corrected: monthly means still
overlap at the 63-day horizon, so the effective sample is smaller than the month
count suggests and the p-values are somewhat optimistic. The artifact publishes
the month count so the reader can discount accordingly.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import numpy as np                                                   # noqa: E402
import pandas as pd                                                  # noqa: E402
from scipy import stats                                              # noqa: E402

from _lib import (artifacts, eventstudy, listings, market_data,      # noqa: E402
                  patterns, riskmodel, universes)

ARTIFACT = ROOT / "api" / "_lib" / "patterns_calibration.json"

# Forward horizons in trading days: a fortnight, a month, a quarter. LMW measure
# at one day and report distributional shifts; a personal scanner cannot trade a
# one-day horizon after costs, so the shortest here is the shortest that could
# actually be held.
HORIZONS = (10, 21, 63)

# The false-discovery bar. Same 10% `eventstudy.screener_significance` uses, and
# for the same reason: rejecting a few false positives among many screening
# tests is an acceptable trade where Bonferroni would reject everything.
ALPHA = 0.10

# Below this many detections a pattern's mean forward return is not a
# measurement. Thirty is the floor `pretrade` and `calibrate_tape` both use.
MIN_OBSERVATIONS = 30

# And below this many distinct calendar months there are not enough separate
# market episodes to test on, however many detections they contain. Twenty-four
# is two years of monthly means.
MIN_MONTHS = 24

# The window the scanner reads, and therefore the window the useful firing rate
# is measured over. `patterns.read` defaults to the same quarter.
RECENT_WINDOW = 63

POPULATION = {
    "ID": {"kind": "listing", "label": "the Indonesian listed market"},
    "US": {"kind": "universes", "ids": ["nasdaq100", "dow30"],
           "label": "the Nasdaq-100 and the Dow"},
}


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


def forward_excess(prices: np.ndarray, index: np.ndarray,
                   start: int, horizon: int) -> float | None:
    """Stock return minus index return over `horizon` sessions from `start`.

    `start` is the day AFTER detection. A detection made on the close of day t
    cannot be acted on before day t+1, and measuring from day t would credit the
    pattern with a move that had already happened when it was found.
    """
    end = start + horizon
    if start < 1 or end >= len(prices) or end >= len(index):
        return None
    if prices[start - 1] <= 0 or index[start - 1] <= 0:
        return None
    stock = prices[end] / prices[start - 1] - 1.0
    market = index[end] / index[start - 1] - 1.0
    value = stock - market
    return float(value) if np.isfinite(value) else None


def measure(market: str, sample: int, years: int, quiet: bool = False) -> dict:
    picked, label = symbols_for(market, sample)
    say = (lambda *a: None) if quiet else (lambda *a: print(*a, flush=True))

    end = dt.date.today()
    start = end - dt.timedelta(days=int(years * 365.25))
    say(f"\n{market}: fetching {len(picked)} histories over {years} years ...")
    frames = market_data.ohlcv_batch(picked, start, end)
    say(f"  {len(frames)} returned usable history")

    benchmark_symbol = riskmodel.MARKET_INDEX.get(market, "^GSPC")
    index_frames = market_data.ohlcv_batch([benchmark_symbol], start, end)
    if benchmark_symbol not in index_frames:
        raise SystemExit(f"Could not fetch the benchmark {benchmark_symbol}; "
                         f"an excess return needs one and a raw return is not a "
                         f"substitute.")
    benchmark = index_frames[benchmark_symbol]["Close"].astype("float64")

    # observations[pattern][horizon] -> list of (month, excess return)
    observations: dict[str, dict[int, list[tuple[str, float]]]] = {
        name: {h: [] for h in HORIZONS} for name in patterns.CATALOGUE}
    # THE BASELINE: every name-day's forward excess, grouped by month, whether
    # or not a pattern fired. This is what a detection is compared against —
    # see failure 2 in the module docstring.
    baseline: dict[tuple[str, int], list[float]] = {}
    names_fired: dict[str, set[str]] = {name: set() for name in patterns.CATALOGUE}
    # Names showing the pattern in their FINAL quarter — the window the scanner
    # actually looks at, and the only firing rate that says whether a detection
    # today is unusual. "Showed it at least once in six years" is a description
    # of having a price series: it came out at 97% for head-and-shoulders.
    names_recent: dict[str, set[str]] = {name: set() for name in patterns.CATALOGUE}
    detections_per_name: dict[str, list[int]] = {name: [] for name in patterns.CATALOGUE}
    scanned = 0
    total_detections = 0
    total_years = 0.0

    for symbol, frame in frames.items():
        found = patterns.detect(frame, lookback=None)
        if not found["available"]:
            continue
        scanned += 1

        # ALIGNED ON DATES, NOT ON POSITION. The stock and the index have
        # different holiday calendars, and lining them up by row number is how a
        # study comes to measure a stock's Tuesday against the index's Monday.
        close = frame["Close"].astype("float64")
        joined = pd.concat([close, benchmark], axis=1, join="inner").dropna()
        joined.columns = ["stock", "index"]
        if len(joined) < patterns.MIN_BARS:
            continue
        stock_values = joined["stock"].to_numpy(dtype="float64")
        index_values = joined["index"].to_numpy(dtype="float64")
        position_of = {stamp: i for i, stamp in enumerate(joined.index)}

        total_years += len(frame) / 252.0
        recent_cutoff = found["sessions"] - RECENT_WINDOW
        per_name = {name: 0 for name in patterns.CATALOGUE}

        # --- the unconditional baseline for this name -----------------------
        # Vectorised over every day at once: the forward excess from day t is
        # the stock's H-session return minus the index's, and the whole vector
        # comes from two shifted divisions rather than a loop.
        months = np.array([f"{stamp.year:04d}-{stamp.month:02d}"
                           for stamp in joined.index])
        for horizon in HORIZONS:
            if len(stock_values) <= horizon + 1:
                continue
            excess = ((stock_values[horizon + 1:] / stock_values[1:-horizon] - 1.0)
                      - (index_values[horizon + 1:] / index_values[1:-horizon] - 1.0))
            # Position i of `excess` is the outcome of acting on a detection
            # made at day i — entered at i+1, held `horizon` sessions.
            stamps = months[:len(excess)]
            for month, value in zip(stamps, excess, strict=True):
                if np.isfinite(value):
                    baseline.setdefault((month, horizon), []).append(float(value))

        for detection in found["detections"]:
            total_detections += 1
            name = detection["pattern"]
            names_fired[name].add(symbol)
            per_name[name] += 1
            if detection["detectedIndex"] >= recent_cutoff:
                names_recent[name].add(symbol)

            stamp = pd.Timestamp(detection["detectedAt"])
            where = position_of.get(stamp)
            if where is None:
                continue
            month = f"{stamp.year:04d}-{stamp.month:02d}"
            for horizon in HORIZONS:
                value = forward_excess(stock_values, index_values, where + 1, horizon)
                if value is not None:
                    observations[name][horizon].append((month, value))

        for name, count in per_name.items():
            detections_per_name[name].append(count)

    if scanned < MIN_OBSERVATIONS:
        say(f"  only {scanned} names produced a reading — no row written for {market}")
        return {}

    # --- one p-value per pattern per horizon, then one correction over all ---
    #
    # THE TEST RUNS ON MONTHLY MEANS, not on individual detections. See the
    # module docstring: pooling turned a handful of market episodes into
    # hundreds of "independent" observations and manufactured a 10.9% edge.
    baseline_mean = {key: float(np.mean(values)) for key, values in baseline.items()
                     if values}

    tests: list[dict] = []
    for name in patterns.CATALOGUE:
        for horizon in HORIZONS:
            rows = [(month, value) for month, value in observations[name][horizon]
                    if (month, horizon) in baseline_mean]
            if len(rows) < MIN_OBSERVATIONS:
                continue
            frame = pd.DataFrame(rows, columns=["month", "excess"])
            # ABNORMAL = the detection's excess minus what an average name in
            # the sample earned that month. Zero means "did no better than the
            # rest of the market that month", which is the null that matters.
            frame["abnormal"] = frame["excess"] - frame["month"].map(
                {month: baseline_mean[(month, horizon)]
                 for month in frame["month"].unique()})
            monthly = frame.groupby("month")["abnormal"].mean().to_numpy(dtype="float64")
            if len(monthly) < MIN_MONTHS:
                continue
            _, p_value = stats.ttest_1samp(monthly, 0.0)
            if not np.isfinite(p_value):
                continue
            tests.append({
                "pattern": name, "horizonDays": horizon,
                "meanExcess": float(monthly.mean()),
                "pValue": float(p_value),
                "months": len(monthly),
                "observations": len(rows),
                # Both kept so the size of each correction stays visible rather
                # than being quietly applied. `rawExcess` is what the broken
                # version of this script reported.
                "rawExcess": float(frame["excess"].mean()),
                "medianAbnormal": float(frame["abnormal"].median()),
            })

    correction = eventstudy.benjamini_hochberg([t["pValue"] for t in tests], alpha=ALPHA)
    raw_hits = sum(1 for t in tests if t["pValue"] < 0.05)

    # --- assemble, keeping the BEST SURVIVING horizon per pattern ------------
    rows: dict[str, dict] = {}
    for position, test in enumerate(tests):
        rejected = correction["rejected"][position]
        q_value = correction["qValues"][position]
        entry = rows.setdefault(test["pattern"],
                                {"tested": [], "significant": False, "forward": None})
        entry["tested"].append({**test, "qValue": q_value, "survived": bool(rejected)})
        # The reported effect is the surviving horizon with the largest absolute
        # mean — and ONLY a surviving one. Quoting the best of three horizons
        # regardless of the correction is the same error the correction exists
        # to prevent, one level down.
        if rejected and (entry["forward"] is None
                         or abs(test["meanExcess"]) > abs(entry["forward"]["meanExcess"])):
            entry["significant"] = True
            entry["forward"] = {"horizonDays": test["horizonDays"],
                                "meanExcess": test["meanExcess"],
                                "pValue": test["pValue"], "qValue": q_value,
                                "months": test["months"],
                                "rawExcess": test["rawExcess"],
                                "medianAbnormal": test["medianAbnormal"]}

    out_patterns: dict[str, dict] = {}
    for name, spec in patterns.CATALOGUE.items():
        entry = rows.get(name, {"tested": [], "significant": False, "forward": None})
        fired = len(names_fired[name])
        recent = len(names_recent[name])
        counts = detections_per_name[name]
        total = sum(len(observations[name][h]) for h in HORIZONS)
        out_patterns[name] = {
            "label": spec["label"],
            "textbookBias": spec["bias"],
            "namesFired": fired,
            "everFiredRate": fired / scanned if scanned else None,
            # THE FIRING RATE THAT MATTERS: share of names showing this in the
            # last quarter, which is the window the scanner reads. The
            # ever-fired rate is kept beside it because the gap between the two
            # is the point — 97% against 12% says the pattern is universal over
            # six years and uncommon in any given quarter.
            "firingRate": recent / scanned if scanned else None,
            "namesRecent": recent,
            "recentWindow": RECENT_WINDOW,
            "perNameYear": (sum(counts) / total_years) if total_years else None,
            "observations": max((len(observations[name][h]) for h in HORIZONS),
                                default=0),
            "tested": entry["tested"],
            "significant": entry["significant"],
            "forward": entry["forward"],
            "verdict": _verdict(entry, recent, scanned, total),
        }

    # The number the whole measurement turns on, published so the correction is
    # checkable rather than asserted.
    unconditional = {str(horizon): float(np.mean(
        [v for (m, h), values in baseline.items() if h == horizon for v in values]))
        for horizon in HORIZONS
        if any(h == horizon for _, h in baseline)}

    row = {
        "names": scanned,
        "unconditionalMeanExcess": unconditional,
        "population": label,
        "measuredOn": dt.date.today().isoformat(),
        "years": years,
        "benchmark": benchmark_symbol,
        "horizons": list(HORIZONS),
        "alpha": ALPHA,
        "detections": total_detections,
        "tests": len(tests),
        "rawHits": raw_hits,
        "expectedByChance": round(len(tests) * 0.05, 1),
        "survived": correction["discoveries"],
        "patterns": out_patterns,
    }

    say(f"  {scanned} names, {total_detections} detections over "
        f"{total_years:.0f} name-years, {len(tests)} tests")
    say("  unconditional mean excess by horizon: "
        + ", ".join(f"{h}d {v * 100:+.1f}%" for h, v in unconditional.items())
        + "  <- the null every pattern is measured against")
    say(f"  {raw_hits} cleared p<0.05 before correction against "
        f"{len(tests) * 0.05:.1f} expected by chance")
    say(f"  {correction['discoveries']} survived Benjamini-Hochberg at "
        f"{ALPHA:.0%}")
    for entry in out_patterns.values():
        if entry["firingRate"] is None:
            continue
        mark = "*" if entry["significant"] else " "
        best = entry["forward"]
        detail = (f"{best['meanExcess'] * 100:+.2f}% abnormal over "
                  f"{best['horizonDays']}d (q={best['qValue']:.3f}, "
                  f"{best['months']} months)" if best else "no surviving horizon")
        say(f"   {mark} {entry['label']:26} "
            f"{entry['perNameYear']:.1f}/name/yr, "
            f"{entry['firingRate'] * 100:5.1f}% in a quarter "
            f"({entry['everFiredRate'] * 100:.0f}% ever) — {detail}")
    return row


def _verdict(entry: dict, recent: int, scanned: int, total: int) -> str:
    """One sentence per pattern, written from its own numbers."""
    rate = recent / scanned if scanned else 0.0
    if not entry["tested"]:
        return (f"Too few occurrences to test: {total} across {scanned} names, under the "
                f"{MIN_OBSERVATIONS} detections and {MIN_MONTHS} separate months needed "
                f"before a mean is a measurement.")
    if entry["significant"]:
        best = entry["forward"]
        return (f"Survived correction: {best['meanExcess'] * 100:+.2f}% against the market "
                f"over {best['horizonDays']} sessions, averaged across {best['months']} "
                f"separate months (q = {best['qValue']:.3f}). Present in "
                f"{rate * 100:.0f}% of names in a given quarter.")
    return (f"No forward return that survives correcting for every pattern and horizon "
            f"tested, once detections are collapsed by month so that one market episode "
            f"counts once. Present in {rate * 100:.0f}% of names in a given quarter.")


def headline(markets: dict) -> str:
    parts = []
    for row in markets.values():
        parts.append(
            f"{row['survived']} of {row['tests']} tests survived correction across "
            f"{row['detections']} detections in {row['population']} "
            f"({row['rawHits']} cleared p<0.05 before correction, against "
            f"{row['expectedByChance']} expected by chance)")
    if not parts:
        return "No market produced enough detections to measure."
    return ("Chart patterns, measured rather than assumed: " + "; ".join(parts)
            + ". A pattern that did not survive contributes nothing to any score.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--market", action="append", default=None, choices=["ID", "US"])
    parser.add_argument("--sample", type=int, default=250)
    parser.add_argument("--years", type=int, default=6,
                        help="History per name (default 6). More years is more "
                             "detections and a wider span of market conditions.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    markets: dict = {}
    for market in (args.market or ["ID", "US"]):
        row = measure(market, args.sample, args.years, quiet=args.quiet)
        if row:
            markets[market] = row

    if not markets:
        print("Nothing measured; the artifact was left alone.", file=sys.stderr)
        return 1

    payload = {
        "measuredOn": dt.date.today().isoformat(),
        "window": patterns.WINDOW,
        "confirmLag": patterns.CONFIRM_LAG,
        "horizons": list(HORIZONS),
        "alpha": ALPHA,
        "headline": headline(markets),
        "refused": [{"name": name, "reason": reason} for name, reason in patterns.REFUSED],
        "markets": markets,
    }
    # MERGED, NOT OVERWRITTEN. Running this for one market used to delete
    # every other market's measurement — see `_lib/artifacts` for the day that
    # happened and what it cost.
    merged = artifacts.write_markets(ARTIFACT, payload)
    if not args.quiet:
        print(f"\n{payload['headline']}")
        print(f"\nwritten to {ARTIFACT} — {artifacts.note(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
