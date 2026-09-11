#!/usr/bin/env python3
"""
backtest_verdict.py
===================
Does the blended verdict score predict returns? Measured on the half of it that
can be reconstructed honestly, and silent about the other half.

    python scripts/backtest_verdict.py --market ID --years 6

DELIBERATELY OUTSIDE CI, like the other network scripts here, and stamped with
the date it ran.

WHY THIS EXISTS
---------------
`verdict.provenance()` has admitted since the scanner shipped that "the blend of
them has never been backtested at all". That is the one measurement the whole
private tier rests on, and until now the app said so and left it there. This
closes as much of the gap as the data honestly allows.

WHAT IT CAN MEASURE, AND WHAT IT CANNOT
----------------------------------------
A backtest must reconstruct the score AS IT WOULD HAVE STOOD on a past date,
using only information available then. Four of the nine components survive that
requirement:

    priceRank   cross-sectional percentiles of price signals, computable from
                any truncated price history
    tape        heavy-session close location, a function of the trailing window
    patterns    already detected in a rolling window with a confirmation lag,
                and already carrying the date each was detectable
    issuance    the share-count series arrives DATED, so the count as of a past
                day is knowable

Five do not, and the reason is the same for all of them:

    value       the discounted cash flow reads the latest statements. Yahoo
    quality     serves current filings with no as-of, so reconstructing either
                on a 2023 date would read numbers published in 2026.
    trend       needs the full technical pipeline per symbol per date
    flow        needs an Isolation Forest fit per symbol per date
    float       the insider-held share arrives as a single current figure with
                no history at all

The first two are the ones that matter, and they are not a cost problem — they
are unobtainable. Running this on all nine by using today's filings would
produce a beautiful result built on information from the future. So the score
reconstructed here is a SUBSET and the artifact says so in every field: 2.2 of
the 4.9 base weight, about 45% of the intended evidence, and all of it from the
price family plus one register component.

The remaining half can only be measured by writing down what the scanner said
and waiting. That is what `_lib/scanlog.py` is for.

HOW THE WALK-FORWARD IS ARRANGED
---------------------------------
At each rebalance date the universe is truncated to that date, every surviving
component is recomputed from the truncated history, the components are blended
by the same family arithmetic `verdict.py` uses, and the resulting order is
measured against what happened next.

TWO THINGS THAT WOULD HAVE MADE IT WRONG, BOTH GUARDED:

1. THE TAPE'S BASELINE. `tape.read` tests a name against its market's median
   lift, and that median comes from a calibration measured on TODAY'S data. Used
   naively, every past date would be scored against a future baseline. So the
   baseline is recomputed from the truncated cross-section at each date.

2. THE PATTERN STUDY'S SURVIVORS. `patterns.read` scores only formations whose
   forward returns survived correction — a fact established by a study that
   used the whole sample. Feeding that back into a backtest of the same sample
   is circular. Here the pattern component is scored by PRESENCE with a fixed
   sign, and the artifact records that this differs from the live path.

The information coefficient is Spearman between the score and the forward
return, computed within each date and then averaged, with a t-test on the
per-date coefficients. The quintile spread is the top fifth minus the bottom
fifth. Both are corrected together across horizons with Benjamini-Hochberg —
the same treatment `backtest_ranking.py` gives the price composite, so the two
results are comparable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import numpy as np                                                   # noqa: E402
import pandas as pd                                                  # noqa: E402
from scipy import stats                                              # noqa: E402

from _lib import (artifacts, eventstudy, listings, market_data,      # noqa: E402
                  microstructure, ownership, patterns, ranking, riskmodel,
                  structure, tape, universes, verdict)

ARTIFACT = ROOT / "api" / "_lib" / "verdict_backtest.json"

# Which components can be reconstructed without reading the future, and what
# each is worth in `verdict.COMPONENTS`. Read from there rather than restated,
# so a weight change in one place cannot leave this describing a blend the app
# no longer computes.
RECONSTRUCTIBLE = ("priceRank", "tape", "patterns", "issuance")

# Rebalance every this many sessions. A month: short enough for a six-year
# sample to give seventy-odd dates, long enough that consecutive scores are not
# the same score with two days of noise on it.
REBALANCE = 21

# Forward horizons, matching `backtest_ranking.py` so the two are comparable.
HORIZONS = (21, 63, 126)

ALPHA = 0.10

# Below this many names on a date, a cross-sectional percentile is not one.
MIN_NAMES = 30

# Below this many dates, the mean of the per-date coefficients is not a mean.
MIN_DATES = 24

# Concurrent register fetches. The same width `scan_market.py` uses, and for the
# same reason: above about six the provider starts throttling and the run takes
# longer rather than shorter.
REGISTER_WORKERS = 4

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


def component_weights() -> dict:
    """The base weight of each reconstructible component, from `verdict`."""
    return {spec["key"]: spec["weight"] for spec in verdict.COMPONENTS
            if spec["key"] in RECONSTRUCTIBLE}


# --------------------------------------------------------------------------- #
# Per-date reconstruction
# --------------------------------------------------------------------------- #
def price_rank_scores(frames: dict, upto: int, benchmark) -> dict:
    """`ranking`'s composite percentile, recomputed on truncated history."""
    truncated = {}
    for symbol, frame in frames.items():
        window = frame.iloc[:upto]
        if len(window) >= ranking.MIN_BARS:
            truncated[symbol] = window
    if len(truncated) < MIN_NAMES:
        return {}
    index = benchmark.iloc[:upto] if benchmark is not None else None
    result = ranking.rank_universe(truncated, benchmark=index)
    return {row["ticker"]: row["composite"] for row in result["rows"]
            if row["composite"] is not None}


def tape_scores(frames: dict, upto: int) -> dict:
    """The heavy-session reading, against a baseline recomputed on this date.

    THE BASELINE IS THE WHOLE POINT. `tape.read` normally tests against a median
    from `tape_calibration.json`, which was measured on today's data — using it
    here would score 2023 against a 2026 null. The cross-section available at
    `upto` supplies its own.
    """
    raw = {}
    for symbol, frame in frames.items():
        window = frame.iloc[:upto]
        if len(window) < tape.MIN_BARS:
            continue
        statistics = tape.statistics(window)
        if statistics.get("available"):
            raw[symbol] = statistics
    if len(raw) < MIN_NAMES:
        return {}

    lifts = np.array([s["lift"] for s in raw.values()], dtype="float64")
    baseline = float(np.median(lifts))
    spread = float(np.std(lifts, ddof=1)) or tape.UNCALIBRATED_LIFT_SD

    scores = {}
    for symbol, statistics in raw.items():
        _, p_value = stats.ttest_ind(
            statistics["heavyValues"] - baseline, statistics["ordinaryValues"],
            equal_var=False)
        excess = statistics["lift"] - baseline
        score = 50.0
        if np.isfinite(p_value) and p_value < tape.ALPHA and excess != 0:
            score += (1.0 if excess > 0 else -1.0) * tape.LIFT_SWING * (
                0.5 + 0.5 * min(1.0, abs(excess) / (spread * tape.LIFT_SATURATION_SIGMA)))
        scores[symbol] = float(np.clip(score, 0.0, 100.0))
    return scores


def pattern_scores(detections: dict, upto: int, lookback: int = 63) -> dict:
    """Presence of any formation in the trailing window, scored by a FIXED sign.

    NOT BY THE STUDY'S SURVIVORS. `patterns.read` scores only formations whose
    forward returns survived a correction computed on the whole sample, and
    feeding that back into a backtest of the same sample is circular — the
    survivors were chosen because they predicted, so of course they predict.

    Here every formation counts the same and the sign is fixed at the one the
    study reported: presence marks a name that underperformed. That is still
    informed by the study and the artifact says so; what it is not is a
    per-pattern selection made with hindsight.
    """
    scores = {}
    for symbol, found in detections.items():
        recent = [d for d in found
                  if upto - lookback <= d["detectedIndex"] < upto]
        scores[symbol] = 50.0 - verdict.PATTERN_BACKTEST_POINTS if recent else 50.0
    return scores


def issuance_scores(registers: dict, upto_date: dt.date) -> dict:
    """The share-count trend as of a past date, from the dated series."""
    scores = {}
    for symbol, register in registers.items():
        records = [r for r in (register.get("shares") or [])
                   if r.get("date") and r["date"] <= upto_date.isoformat()]
        if len(records) < ownership.MIN_SHARE_POINTS:
            continue
        result = ownership.issuance({"shares": records})
        if result.get("available") and result.get("score") is not None:
            scores[symbol] = float(result["score"])
    return scores


def blend(per_component: dict, weights: dict) -> dict:
    """The family arithmetic `verdict.score` uses, over what was reconstructed.

    Three of the four live in the price family and one in the register, so this
    is a two-family blend with each family weighted by its own coverage — the
    same rule, applied to a subset. It is NOT the live score and the artifact
    never calls it one.
    """
    families = {"price": ["priceRank", "tape", "patterns"], "register": ["issuance"]}
    names = set().union(*(set(scores) for scores in per_component.values())) \
        if per_component else set()

    out = {}
    for name in names:
        family_scores = []
        for keys in families.values():
            present = [(k, per_component[k][name]) for k in keys
                       if k in per_component and name in per_component[k]]
            if not present:
                continue
            total = sum(weights[k] for k, _ in present)
            if total <= 0:
                continue
            value = sum(weights[k] * v for k, v in present) / total
            base = sum(weights[k] for k in keys if k in weights)
            coverage = total / base if base else 0.0
            family_scores.append((value, max(verdict.MIN_FAMILY_VOTE,
                                             min(1.0, coverage))))
        if not family_scores:
            continue
        vote_total = sum(vote for _, vote in family_scores)
        out[name] = sum(value * vote for value, vote in family_scores) / vote_total
    return out


# --------------------------------------------------------------------------- #
# The walk-forward
# --------------------------------------------------------------------------- #
def measure(market: str, sample: int, years: int, quiet: bool = False) -> dict:
    picked, label = symbols_for(market, sample)
    say = (lambda *a: None) if quiet else (lambda *a: print(*a, flush=True))

    end = dt.date.today()
    start = end - dt.timedelta(days=int(years * 365.25) + 400)
    say(f"\n{market}: fetching {len(picked)} histories ...")
    frames = market_data.ohlcv_batch(picked, start, end)
    say(f"  {len(frames)} returned usable history")

    benchmark_symbol = riskmodel.MARKET_INDEX.get(market, "^GSPC")
    index_frames = market_data.ohlcv_batch([benchmark_symbol], start, end)
    benchmark = (index_frames[benchmark_symbol]["Close"].astype("float64")
                 if benchmark_symbol in index_frames else None)

    # A COMMON CALENDAR. Every name is reindexed onto the union of trading days
    # so that "position `upto`" means the same date for all of them — without
    # it, truncating by row number compares different dates across names.
    calendar = sorted(set().union(*(set(f.index) for f in frames.values())))
    aligned = {symbol: frame.reindex(calendar).ffill()
               for symbol, frame in frames.items()}
    index_series = (benchmark.reindex(calendar).ffill()
                    if benchmark is not None else None)

    say(f"  {len(calendar)} sessions on the common calendar")

    # Patterns are detected ONCE per name: `patterns.detect` already works in a
    # rolling window with a confirmation lag, so every detection already carries
    # the date it was knowable. Re-detecting per rebalance would repeat the same
    # work seventy times for the same answer.
    say("  detecting formations (once per name; already look-ahead free) ...")
    detections = {}
    for symbol, frame in aligned.items():
        found = patterns.detect(frame, lookback=None)
        if found.get("available"):
            detections[symbol] = found["detections"]

    # ONE CALL PER NAME AND IT IS THE SLOWEST STEP HERE — about two seconds
    # each, so two hundred names is seven minutes before any arithmetic starts.
    # Threaded at the same width the scanner uses, for the same reason: above
    # about six the provider throttles and the whole thing takes longer.
    say(f"  fetching {len(aligned)} share registers ({REGISTER_WORKERS} at a time) ...")
    registers = {}
    with ThreadPoolExecutor(max_workers=REGISTER_WORKERS) as pool:
        futures = {pool.submit(market_data.share_register, symbol): symbol
                   for symbol in aligned}
        for done, future in enumerate(as_completed(futures), start=1):
            symbol = futures[future]
            try:
                registers[symbol] = future.result()
            except Exception:
                continue
            if done % 50 == 0:
                say(f"    {done}/{len(aligned)}")

    weights = component_weights()
    warm = max(ranking.MIN_BARS, tape.MIN_BARS, patterns.MIN_BARS) + 21
    dates = list(range(warm, len(calendar) - max(HORIZONS), REBALANCE))
    say(f"  {len(dates)} rebalance dates from "
        f"{pd.Timestamp(calendar[warm]).date()} onward")

    rows: list[dict] = []
    for step, upto in enumerate(dates, start=1):
        as_of = pd.Timestamp(calendar[upto - 1]).date()
        per_component = {}
        scores = price_rank_scores(aligned, upto, index_series)
        if scores:
            per_component["priceRank"] = scores
        scores = tape_scores(aligned, upto)
        if scores:
            per_component["tape"] = scores
        per_component["patterns"] = pattern_scores(detections, upto)
        scores = issuance_scores(registers, as_of)
        if scores:
            per_component["issuance"] = scores

        blended = blend(per_component, weights)
        if len(blended) < MIN_NAMES:
            continue

        for symbol, score in blended.items():
            close = aligned[symbol]["Close"].to_numpy(dtype="float64")
            entry = {"date": as_of.isoformat(), "ticker": symbol, "score": score}
            base = close[upto - 1]
            index_base = (float(index_series.iloc[upto - 1])
                          if index_series is not None else None)
            for horizon in HORIZONS:
                ahead = upto - 1 + horizon
                if ahead >= len(close) or not np.isfinite(base) or base <= 0:
                    entry[f"fwd{horizon}"] = None
                    continue
                value = close[ahead] / base - 1.0
                if index_series is not None and index_base:
                    value -= float(index_series.iloc[ahead]) / index_base - 1.0
                entry[f"fwd{horizon}"] = float(value) if np.isfinite(value) else None
            rows.append(entry)

        if step % 10 == 0:
            say(f"    {step}/{len(dates)} dates, {len(rows)} observations")

    if not rows:
        say("  nothing measurable; no row written")
        return {}

    frame = pd.DataFrame(rows)
    tests = []
    for horizon in HORIZONS:
        column = f"fwd{horizon}"
        usable = frame.dropna(subset=[column])
        per_date_ic, per_date_spread = [], []
        for _, group in usable.groupby("date"):
            if len(group) < MIN_NAMES:
                continue
            ic = group["score"].corr(group[column], method="spearman")
            if np.isfinite(ic):
                per_date_ic.append(float(ic))
            quintile = max(1, len(group) // 5)
            ordered = group.sort_values("score")
            spread = (ordered[column].tail(quintile).mean()
                      - ordered[column].head(quintile).mean())
            if np.isfinite(spread):
                per_date_spread.append(float(spread))

        if len(per_date_ic) < MIN_DATES:
            continue
        ic_values = np.array(per_date_ic, dtype="float64")
        spread_values = np.array(per_date_spread, dtype="float64")
        _, ic_p = stats.ttest_1samp(ic_values, 0.0)
        _, spread_p = stats.ttest_1samp(spread_values, 0.0)
        tests.append({
            "horizonDays": horizon, "dates": len(ic_values),
            "observations": len(usable),
            "icMean": float(ic_values.mean()),
            "icT": float(ic_values.mean() / (ic_values.std(ddof=1) / np.sqrt(len(ic_values)))),
            "icP": float(ic_p),
            "spreadMean": float(spread_values.mean()),
            "spreadP": float(spread_p),
        })

    # WHERE THE TWO STATISTICS DISAGREE ABOUT THE SIGN, SAY SO.
    #
    # The information coefficient is a rank correlation across the whole
    # cross-section; the quintile spread is the top fifth minus the bottom
    # fifth. They can point opposite ways, and on the first trial run they did:
    # a +0.050 IC at 126 sessions alongside a -6.4% quintile spread. That is not
    # a rounding difference, it means the relationship is not monotone — the
    # middle of the distribution carries the correlation while the extremes,
    # which are the only part anybody would trade, go the other way.
    #
    # A backtest that reported the surviving IC and let the reader discover the
    # spread later would be quoting the flattering half of its own result.
    for test in tests:
        test["signsAgree"] = bool(
            np.sign(test["icMean"]) == np.sign(test["spreadMean"])
            or test["spreadMean"] == 0)

    correction = eventstudy.benjamini_hochberg(
        [t["icP"] for t in tests] + [t["spreadP"] for t in tests], alpha=ALPHA)
    for position, test in enumerate(tests):
        test["icQ"] = correction["qValues"][position]
        test["icSurvived"] = bool(correction["rejected"][position])
        test["spreadQ"] = correction["qValues"][len(tests) + position]
        test["spreadSurvived"] = bool(correction["rejected"][len(tests) + position])

    # --- WHAT IT COSTS TO ACT ON THIS ---------------------------------------
    # A quintile spread is a GROSS number and quoting one without the round trip
    # beside it is the quietest way to overstate a result. A long-only top-quintile
    # portfolio rebalanced every `REBALANCE` sessions turns over a large share of
    # itself each time; at one round trip per rebalance the annual cost is the
    # spread crossed twice, times the rebalances in a year.
    costs = []
    attempted = 0
    for frame in aligned.values():
        try:
            profile = microstructure.liquidity_profile(frame.tail(252))
        except Exception:
            continue
        attempted += 1
        estimate = structure.round_trip_cost(profile)
        if estimate.get("available"):
            costs.append(float(estimate["roundTrip"]))
    median_round_trip = float(np.median(costs)) if costs else None
    resolved_share = (len(costs) / attempted) if attempted else None

    # THE COST ESTIMATE IS AN UPPER BOUND AND MUST BE LABELLED ONE.
    #
    # `microstructure` resolves a spread only where the estimate clears its own
    # noise floor — 40% of daily volatility — which happens for the WIDEST names
    # and almost nowhere else. On 200 Indonesian listings it resolved for
    # ELEVEN, and the median of those eleven is the median of the eleven widest,
    # not of the market. An earlier version of this script deducted it anyway
    # and turned a +2.19% monthly gross spread into -3.31% net, killing a live
    # result on the strength of a badly selected sample.
    #
    # So the artifact reports a BREAKEVEN instead: the round trip at which each
    # gross spread reaches zero. That is a number this data can support. "The
    # typical spread on IDX" is not, and pretending otherwise would be the same
    # error in the opposite direction from the one it was trying to avoid.
    say(f"  round trip resolved for {len(costs)} of {attempted} names"
        + (f"; median of those {median_round_trip * 100:.2f}%"
           if median_round_trip else "")
        + " — resolution selects for the widest spreads, so this is an upper bound")

    for test in tests:
        # One round trip per rebalance, scaled to the test's own horizon so a
        # 21-day and a 126-day spread are compared against the trading each
        # would actually require.
        rebalances = max(1.0, test["horizonDays"] / REBALANCE)
        test["rebalancesPerHorizon"] = rebalances
        # The cost at which this spread reaches zero. Positive spreads only — a
        # negative one has no breakeven, it is already a loss before costs.
        test["breakevenRoundTrip"] = (test["spreadMean"] / rebalances
                                      if test["spreadMean"] > 0 else None)
        if median_round_trip is not None:
            test["costUpperBound"] = median_round_trip * rebalances
            test["spreadNetUpperBound"] = test["spreadMean"] - test["costUpperBound"]
            test["survivesUpperBound"] = bool(
                test["spreadSurvived"] and test["signsAgree"]
                and test["spreadNetUpperBound"] > 0)

    intended = sum(spec["weight"] for spec in verdict.COMPONENTS)
    covered = sum(weights.values())
    row = {
        "names": len(aligned),
        "population": label,
        "measuredOn": dt.date.today().isoformat(),
        "years": years,
        "benchmark": benchmark_symbol,
        "rebalanceDays": REBALANCE,
        "horizons": list(HORIZONS),
        "alpha": ALPHA,
        "dates": len(dates),
        "observations": len(rows),
        "components": list(RECONSTRUCTIBLE),
        "componentsTotal": len(verdict.COMPONENTS),
        "weightCovered": covered,
        "weightIntended": intended,
        "coverage": covered / intended if intended else None,
        "excluded": {
            "value": "the discounted cash flow reads the latest statements; this "
                     "source serves no point-in-time filings",
            "quality": "the same — reconstructing Piotroski on a past date would read "
                       "numbers published years later",
            "trend": "needs the full technical pipeline per symbol per date",
            "flow": "needs an Isolation Forest fit per symbol per date",
            "float": "the insider-held share arrives as one current figure with no "
                     "history at all",
        },
        "tests": tests,
        "survived": sum(1 for t in tests if t["icSurvived"] or t["spreadSurvived"]),
        "contradicted": sum(1 for t in tests
                            if (t["icSurvived"] or t["spreadSurvived"])
                            and not t["signsAgree"]),
        "rawHits": sum(1 for t in tests
                       if t["icP"] < 0.05) + sum(1 for t in tests if t["spreadP"] < 0.05),
        "expectedByChance": round(len(tests) * 2 * 0.05, 1),
        "medianRoundTrip": median_round_trip,
        "roundTripResolved": len(costs),
        "roundTripAttempted": attempted,
        "roundTripResolvedShare": resolved_share,
        "roundTripIsUpperBound": True,
        "survivesUpperBound": sum(1 for t in tests if t.get("survivesUpperBound")),
    }
    row["headline"] = _headline(row)

    say(f"\n  {len(rows)} observations across {len(dates)} dates")
    for test in tests:
        say(f"   {test['horizonDays']:4}d  IC {test['icMean']:+.4f} "
            f"(t={test['icT']:+.2f}, q={test['icQ']:.3f})"
            f"{'  SURVIVED' if test['icSurvived'] else ''}"
            f"   quintile spread {test['spreadMean'] * 100:+.2f}%"
            f" (q={test['spreadQ']:.3f})"
            f"{'  SURVIVED' if test['spreadSurvived'] else ''}"
            f"{'   <- SIGNS DISAGREE' if not test['signsAgree'] else ''}"
            + (f"   breakeven round trip "
               f"{test['breakevenRoundTrip'] * 100:.2f}%"
               if test.get("breakevenRoundTrip") else ""))
    say(f"\n  {row['headline']}")
    return row


def _headline(row: dict) -> str:
    tests = row["tests"]
    survived = row["survived"]
    scope = (f"{row['coverage'] * 100:.0f}% of the score's intended evidence "
             f"({', '.join(row['components'])}); the value and quality components "
             f"cannot be reconstructed at all because this data source publishes no "
             f"point-in-time filings")
    if not tests:
        return (f"Not enough rebalance dates to measure anything. Scope: {scope}.")
    if not survived:
        best = min(tests, key=lambda t: t["icQ"])
        return (
            f"Across {len(tests) * 2} tests over {row['observations']} observations and "
            f"{row['dates']} rebalance dates, NONE showed a relationship between the "
            f"blended score and subsequent excess returns that survives correcting for "
            f"having run them all. {row['rawHits']} cleared the conventional 5% cutoff "
            f"before correction against {row['expectedByChance']} expected by chance. "
            f"The strongest was a mean information coefficient of "
            f"{best['icMean']:+.3f} at {best['horizonDays']} sessions. Measured on "
            f"{scope}.")
    winners = [t for t in tests if t["icSurvived"] or t["spreadSurvived"]]
    text = (
        f"{survived} of {len(tests) * 2} tests survived correction across "
        f"{row['observations']} observations and {row['dates']} rebalance dates. "
        + "; ".join(f"{t['horizonDays']}d IC {t['icMean']:+.3f} "
                    f"(q={t['icQ']:.3f})" for t in winners)
        + ". ")

    contradicted = [t for t in winners if not t["signsAgree"]]
    if contradicted:
        first = contradicted[0]
        text += (
            f"READ THAT WITH THE NEXT SENTENCE. At "
            f"{first['horizonDays']} sessions the rank correlation is "
            f"{first['icMean']:+.3f} while the top-minus-bottom quintile spread is "
            f"{first['spreadMean'] * 100:+.1f}% — they point OPPOSITE ways, so the "
            f"relationship is not monotone. The correlation lives in the middle of "
            f"the distribution and the extremes, which are the only part anybody "
            f"would act on, go the other way. A surviving coefficient with a "
            f"contradicting spread is not a tradeable finding. ")

    # THE NUMBER THAT DECIDES WHETHER ANY OF IT IS ACTIONABLE, and it goes in
    # the headline rather than a footnote. A quintile spread is gross; a
    # personal account pays the spread twice on every rebalance.
    # WHAT IT COSTS TO ACT, AS A BREAKEVEN RATHER THAN A DEDUCTION. The spread
    # estimator resolves only for the widest names, so a median over the
    # resolved ones overstates the typical cost by an unknown multiple. A
    # breakeven is a number this data can actually support.
    breakeven = [t for t in tests
                 if t["spreadSurvived"] and t.get("signsAgree")
                 and t.get("breakevenRoundTrip")]
    if breakeven:
        text += ("Those are gross, before trading: " + "; ".join(
            f"the {t['horizonDays']}d spread of {t['spreadMean'] * 100:+.2f}% survives "
            f"only if a round trip costs under {t['breakevenRoundTrip'] * 100:.2f}%"
            for t in breakeven) + ". ")
        resolved = row.get("roundTripResolved") or 0
        attempted_names = row.get("roundTripAttempted") or 0
        cost = row.get("medianRoundTrip")
        if cost is not None:
            text += (f"The spread could only be resolved for {resolved} of "
                     f"{attempted_names} names — the estimator clears its noise floor on "
                     f"the widest ones and almost nowhere else — and the median of those "
                     f"was {cost * 100:.2f}%. That is an UPPER BOUND on a typical cost "
                     f"rather than a measurement of one, and at it nothing here "
                     f"survives. Whether the result lives or dies therefore turns on a "
                     f"quantity this data cannot pin down; a reader who knows their own "
                     f"dealing costs can settle it against the breakeven above. ")
    elif tests:
        text += "No surviving quintile spread to compare against trading costs. "

    return text + f"Measured on {scope}."


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--market", action="append", default=None, choices=["ID", "US"])
    parser.add_argument("--sample", type=int, default=200)
    parser.add_argument("--years", type=int, default=6)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    markets: dict = {}
    for market in (args.market or ["ID"]):
        row = measure(market, args.sample, args.years, quiet=args.quiet)
        if row:
            markets[market] = row

    if not markets:
        print("Nothing measured; the artifact was left alone.", file=sys.stderr)
        return 1

    payload = {
        "measuredOn": dt.date.today().isoformat(),
        "rebalanceDays": REBALANCE,
        "horizons": list(HORIZONS),
        "alpha": ALPHA,
        "scope": ("A SUBSET OF THE LIVE SCORE. Four of nine components can be "
                  "reconstructed without reading the future; the other five cannot, "
                  "and the two that matter most — value and quality — are unobtainable "
                  "rather than merely expensive, because this data source publishes no "
                  "point-in-time filings. The remaining half is measured prospectively "
                  "by _lib/scanlog.py, which takes months to say anything."),
        "markets": markets,
    }
    # MERGED, NOT OVERWRITTEN. Running this for one market used to delete
    # every other market's measurement — see `_lib/artifacts` for the day that
    # happened and what it cost.
    merged = artifacts.write_markets(ARTIFACT, payload)
    if not args.quiet:
        print(f"\nwritten to {ARTIFACT} — {artifacts.note(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
