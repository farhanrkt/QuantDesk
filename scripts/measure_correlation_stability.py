#!/usr/bin/env python3
"""
measure_correlation_stability.py
================================
Does a correlation measured on past prices describe the next period's?

WHY THIS RUNS BEFORE THE PORTFOLIO FEATURE, NOT AFTER
------------------------------------------------------
Reporting that a candidate correlates 0.82 with something already held is a
DESCRIPTION of history and needs no defence. The moment that number is used to
size a position, it becomes a claim about the future: that the correlation
observed over the last year is informative about the correlation over the next
one. That is a predictive claim, and this codebase does not ship predictive
claims it has not measured — the ranking tier carries its own null result for
exactly this reason.

So this measures it first and the answer decides what ships. If correlations do
not persist, the panel reports them as history and refuses to size on them.

WHAT IS MEASURED
----------------
1. PERSISTENCE. Daily returns are cut into consecutive NON-OVERLAPPING windows.
   Within each window every pair of names gets a correlation; the upper triangle
   of that matrix becomes a vector. Consecutive windows' vectors are then rank
   correlated. High means "the pairs that moved together last period are the
   pairs that move together this period" — which is the assumption a
   correlation-aware position size rests on, stated as a number.

   Windows are non-overlapping for the same reason `backtest.py` spaces its
   rebalances: overlapping windows share days, so the observations are
   correlated and a t-statistic computed as though they were not overstates
   itself.

2. STRESS BEHAVIOUR. The folklore is that correlations go to one in a crash,
   which if true is a much more serious problem than imprecision: it means the
   diversification a portfolio appears to have is largest exactly when it is
   least needed. Measured directly — the mean pairwise correlation across the
   worst decile of days for the universe, against the mean across all days.

WHAT THIS CANNOT ANSWER
-----------------------
Whether the correlations hold for THIS reader's portfolio, which is not an index
and may be concentrated in ways these universes are not. The measurement is a
property of large-cap equity indices over the sample, and it is reported as
that.

Survivorship applies here as everywhere in this repo: these are today's
constituents, so every name measured is one that survived.

USAGE
    python scripts/measure_correlation_stability.py
    python scripts/measure_correlation_stability.py --dry-run
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import sys
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from _lib import market_data  # noqa: E402
from _lib import universes  # noqa: E402

OUTPUT = ROOT / "api" / "_lib" / "correlation_stability.json"

# Quarterly, half-yearly and yearly. The panel measures over a year, so 252 is
# the window whose answer governs; the shorter ones are there to show whether
# the answer depends on the choice.
WINDOWS = (63, 126, 252)
YEARS = 8

# A pair needs both names present. Below this many names a window's correlation
# matrix is too thin to be worth a rank correlation.
MIN_NAMES = 10


def _returns(frames: dict) -> pd.DataFrame:
    """Aligned daily log returns, one column per symbol."""
    closes = pd.DataFrame({s: f["Close"].astype("float64") for s, f in frames.items()})
    closes = closes.sort_index()
    return np.log(closes / closes.shift(1)).dropna(how="all")


def _upper(matrix: pd.DataFrame) -> pd.Series:
    """The distinct pairs of a correlation matrix, keyed by pair."""
    values = {}
    columns = list(matrix.columns)
    for i, first in enumerate(columns):
        for second in columns[i + 1:]:
            value = matrix.loc[first, second]
            if np.isfinite(value):
                values[(first, second)] = float(value)
    return pd.Series(values, dtype="float64")


def persistence(returns: pd.DataFrame, window: int) -> dict:
    """Rank correlation between consecutive windows' pairwise correlations."""
    blocks = [returns.iloc[i:i + window]
              for i in range(0, len(returns) - window + 1, window)]
    blocks = [b for b in blocks if len(b) == window]

    vectors = []
    means = []
    for block in blocks:
        usable = block.dropna(axis=1, thresh=int(window * 0.9))
        if usable.shape[1] < MIN_NAMES:
            vectors.append(None)
            continue
        pairs = _upper(usable.corr())
        vectors.append(pairs if len(pairs) >= 10 else None)
        means.append(float(pairs.mean()) if len(pairs) else np.nan)

    scores = []
    for first, second in pairwise(vectors):
        if first is None or second is None:
            continue
        shared = first.index.intersection(second.index)
        if len(shared) < 10:
            continue
        a, b = first.loc[shared], second.loc[shared]
        if np.ptp(a) == 0 or np.ptp(b) == 0:
            continue
        rho = stats.spearmanr(a, b).statistic
        if np.isfinite(rho):
            scores.append(float(rho))

    if len(scores) < 3:
        return {"usable": False, "reason": f"Only {len(scores)} consecutive window pairs."}

    values = np.array(scores, dtype="float64")
    n = len(values)
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    t = mean / (sd / np.sqrt(n)) if sd > 0 else float("nan")
    return {
        "usable": True, "windowDays": window, "periods": n,
        "meanRankCorrelation": mean,
        "stdev": sd,
        "tStat": float(t) if np.isfinite(t) else None,
        "min": float(values.min()), "max": float(values.max()),
        "meanPairwiseCorrelation": float(np.nanmean(means)) if means else None,
    }


def stress(returns: pd.DataFrame, window: int = 63) -> dict:
    """Correlation in the quarters this market fell hardest, against the rest.

    THE OBVIOUS MEASUREMENT IS THE WRONG ONE, and the first version of this made
    the mistake. Selecting the worst DAYS and computing a correlation within
    them conditions on the size of the common factor, which truncates that
    factor's variance inside the subsample while leaving each name's
    idiosyncratic variance alone — so the measured correlation moves for a
    reason that has nothing to do with the market. It reported correlations
    FALLING in a crash, which is not a finding about markets; it is the
    selection doing the work. Forbes & Rigobon (2002) is the canonical statement
    of the problem, and it is why so many "contagion" results evaporate.

    Selecting whole WINDOWS avoids it. Each window keeps its own full
    distribution of factor realisations, and the question becomes the one worth
    asking anyway: in the quarters when this market fell hardest, were its names
    more correlated than usual?

    The conditioning is on the window's realised return, so a milder version of
    the same objection still applies and is stated on the panel rather than
    argued away.
    """
    usable = returns.dropna(axis=1, thresh=int(len(returns) * 0.9))
    if usable.shape[1] < MIN_NAMES:
        return {"usable": False, "reason": "Too few names with complete history."}

    blocks = [usable.iloc[i:i + window]
              for i in range(0, len(usable) - window + 1, window)]
    blocks = [b for b in blocks if len(b) == window]
    if len(blocks) < 8:
        return {"usable": False,
                "reason": f"Only {len(blocks)} non-overlapping {window}-day windows."}

    scored = []
    for block in blocks:
        pairs = _upper(block.corr())
        if len(pairs) < 10:
            continue
        scored.append((float(block.mean(axis=1).sum()), float(pairs.mean())))
    if len(scored) < 8:
        return {"usable": False, "reason": "Too few windows with a usable matrix."}

    scored.sort(key=lambda row: row[0])
    quartile = max(2, len(scored) // 4)
    worst = [c for _, c in scored[:quartile]]
    rest = [c for _, c in scored[quartile:]]
    overall = float(np.mean([c for _, c in scored]))

    return {
        "usable": True,
        "windowDays": window,
        "windows": len(scored),
        "allWindows": overall,
        "worstQuartile": float(np.mean(worst)),
        "restOfWindows": float(np.mean(rest)),
        "rise": float(np.mean(worst) - np.mean(rest)),
        "worstWindowReturn": scored[0][0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--years", type=int, default=YEARS)
    args = parser.parse_args()

    end = dt.date.today()
    start = end - dt.timedelta(days=int(365.25 * args.years))
    noise = io.StringIO()
    results = {}

    for universe_id in ("dow30", "nasdaq100", "idx30", "lq45"):
        entry = universes.get(universe_id)
        print(f"\n{entry['name']} ({len(entry['tickers'])} names)")
        with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
            frames = market_data.ohlcv_batch(entry["tickers"], start, end)
        if len(frames) < MIN_NAMES:
            print("  too few frames")
            continue
        returns = _returns(frames)
        print(f"  {len(frames)} names, {len(returns)} days")

        block = {"universe": entry["name"], "market": entry["market"],
                 "names": len(frames), "days": len(returns), "windows": {}}
        for window in WINDOWS:
            outcome = persistence(returns, window)
            block["windows"][str(window)] = outcome
            if outcome["usable"]:
                print(f"    {window:3}d  rank corr {outcome['meanRankCorrelation']:+.3f} "
                      f"(t {outcome['tStat']:+.1f}, {outcome['periods']} periods)  "
                      f"mean pairwise {outcome['meanPairwiseCorrelation']:.2f}")
            else:
                print(f"    {window:3}d  {outcome['reason']}")
        block["stress"] = stress(returns)
        if block["stress"]["usable"]:
            s = block["stress"]
            print(f"    stress  worst quarter {s['worstQuartile']:.2f} vs the rest "
                  f"{s['restOfWindows']:.2f}  ({s['rise']:+.2f}, "
                  f"{s['windows']} windows)")
        else:
            print(f"    stress  {block['stress']['reason']}")
        results[universe_id] = block

    if not results:
        print("\nNothing measurable. Nothing written.")
        return 1

    yearly = [b["windows"]["252"]["meanRankCorrelation"] for b in results.values()
              if b["windows"].get("252", {}).get("usable")]
    rises = [b["stress"]["rise"] for b in results.values() if b["stress"]["usable"]]

    payload = {
        "measuredOn": dt.date.today().isoformat(),
        "years": args.years,
        "windows": list(WINDOWS),
        "universes": results,
        "headline": _headline(yearly, rises),
        "yearlyPersistence": {"mean": float(np.mean(yearly)) if yearly else None,
                              "min": float(np.min(yearly)) if yearly else None,
                              "max": float(np.max(yearly)) if yearly else None},
        "stressRise": {"mean": float(np.mean(rises)) if rises else None,
                       "min": float(np.min(rises)) if rises else None,
                       "max": float(np.max(rises)) if rises else None},
        "caveats": [
            "Today's index constituents, so every name measured is one that survived.",
            "A property of large-cap index members over this sample, not of any "
            "particular reader's portfolio, which may be concentrated in ways these "
            "universes are not.",
            "Non-overlapping windows, so the t-statistics do not share days. One "
            "history, one regime.",
            "The stress comparison conditions on each window's own return, which biases "
            "any correlation measured inside it (Forbes & Rigobon 2002). Whole windows "
            "are compared rather than selected days, which removes the worst of that, "
            "but not all of it.",
        ],
    }

    if args.dry_run:
        print("\n--- would write ---")
        print(json.dumps(payload, indent=2)[:1500])
        return 0

    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\n{payload['headline']}")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


def _headline(yearly: list, rises: list) -> str:
    """The sentence the portfolio panel prints without further interpretation."""
    if not yearly:
        return ("Correlation persistence could not be measured, so nothing in this app "
                "may size a position on a correlation.")
    low, high = min(yearly), max(yearly)
    stress_text = ""
    if rises:
        mean_rise = float(np.mean(rises))
        if mean_rise >= 0.03:
            stress_text = (f" In the worst quarter of quarters for these markets the mean "
                           f"pairwise correlation is {mean_rise:+.2f} higher than in the "
                           f"rest, so the diversification a correlation implies is smallest "
                           f"exactly when it matters most.")
        else:
            stress_text = (f" In the worst quarter of quarters for these markets the mean "
                           f"pairwise correlation differs by {mean_rise:+.2f} from the rest "
                           f"— no material rise in this sample, though conditioning on "
                           f"returns at all biases such comparisons and the effect is "
                           f"widely reported elsewhere.")
    if low >= 0.4:
        return (f"Pairwise correlations persist: over a one-year window the pairs that moved "
                f"together in one year are largely the pairs that move together in the next, "
                f"with rank correlations of {low:.2f} to {high:.2f} across four index "
                f"universes. That is far more stable than anything this app has measured "
                f"about returns, which is why a correlation may inform position size where a "
                f"return forecast may not.{stress_text}")
    return (f"Pairwise correlations are only weakly persistent year to year — rank "
            f"correlations of {low:.2f} to {high:.2f} across four index universes. On this "
            f"evidence a correlation measured on past prices is a description of that "
            f"history rather than a usable input to position size.{stress_text}")


if __name__ == "__main__":
    raise SystemExit(main())
