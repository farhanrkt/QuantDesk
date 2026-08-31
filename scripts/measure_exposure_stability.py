#!/usr/bin/env python3
"""
measure_exposure_stability.py
=============================
Does a factor beta measured in one year describe the next one?

WHY THIS RUNS BEFORE THE SINGLE-NAME EXPOSURE READING, NOT AFTER
-----------------------------------------------------------------
The portfolio driver label shipped without a gate because it DESCRIBES: it says
what a set of holdings had in common over a stated window, informs no size, and
makes no claim about tomorrow. "This stock moves 0.7x as hard as the energy
complex" is a different sentence. Printed beside a single ticker it invites
forward use, and that is a predictive claim — which this codebase does not ship
unmeasured. The ranking tier carries its own null for exactly this reason.

So this measures it first and the answer decides what ships. If betas do not
persist, the single-name reading either says so on screen or does not ship, and
the null is published either way.

THE PRECEDENT IS `measure_correlation_stability.py` AND THIS MIRRORS IT
-----------------------------------------------------------------------
That script established that pairwise correlations persist — rank correlation
0.50 to 0.65 year over year at t-statistics from +9.5 to +15.7 — which is what
licensed the portfolio panel to inform position size. The shape is copied
deliberately, so the two numbers can be read against each other:

  * returns cut into consecutive NON-OVERLAPPING blocks, because overlapping
    windows share observations and a t-statistic computed as though they did not
    overstates itself;
  * within each block, a cross-section — there, every pair's correlation; here,
    every name's beta on one factor;
  * consecutive blocks' cross-sections rank correlated, so the question is "are
    the names that loaded hardest last year the ones that load hardest this
    year", which is the assumption a forward-looking beta rests on;
  * the mean and t-statistic across transitions reported as the answer.

WEEKLY, AND WHY THAT IS NOT A FREE CHOICE
------------------------------------------
Every factor here settles in a different time zone from an IDX close, and at
daily frequency the mismatch eats the signal — measured at 0.17 daily against
0.52 weekly on a concentrated coal book. But weekly was chosen on five hand-
picked pairs, which is too thin to carry a design decision, so `frequency()`
below re-tests it across every name and reports where the three treatments
disagree rather than asserting the answer.

WHAT ELSE IS MEASURED, AND WHY EACH ONE IS HERE
------------------------------------------------
1. PER-NAME HISTORY, REPORTED AND EXCLUDED BY NAME. MBMA and NCKL listed in
   April 2023 and have three blocks against the eight a 2017 listing has. A
   study that quietly ran on fewer blocks for some names than others would
   report a single persistence number computed from different quantities. Names
   short of `MIN_BLOCKS` are dropped and listed, not silently averaged in.

2. TIERS. The brief asked whether stability differs between commodity names,
   banks and the illiquid tail, and the coverage table in RESEARCH_ROADMAP.md
   §15 already shows IDX behaving differently from US on a neighbouring
   question. Split by market, by membership of the curated resources list, and
   by median dollar volume, because a beta that only persists on the liquid half
   is a different product than one that persists everywhere.

3. UPSIDE AND DOWNSIDE BETAS, AND WHETHER THE GAP ITSELF PERSISTS. Three of five
   coal names showed a downside beta materially above their upside one, all in
   the same direction. Whether that survives is what decides between printing
   two numbers with an interpretation and printing two numbers without one.
   SPLIT BY REGIME AS WELL AS BY HALF, because a sample straddling one large
   one-directional move produces unstable asymmetry for mechanical reasons and a
   half-split cannot tell that from the asymmetry not being real.

4. EXPLANATORY POWER IN STRESS. WHOLE WINDOWS, NEVER SELECTED WEEKS. Selecting
   the worst weeks and computing an R-squared inside them conditions on the size
   of the common factor and truncates its variance, so the number moves for a
   reason that has nothing to do with markets — Forbes & Rigobon (2002). The
   first attempt at this during design made exactly that mistake and reported
   explanatory power FALLING in stress on every name, which is the selection
   doing the work. `measure_correlation_stability.stress()` carries the same
   warning; this is the third place it has bitten.

WHAT THIS CANNOT ANSWER
-----------------------
Whether a beta measured on today's index constituents describes a name that was
not in the index. Survivorship applies here as everywhere in this repo: these
are today's members, so every name measured is one that survived.

And it measures PERSISTENCE, not accuracy. A beta that reliably predicts next
year's beta is still a description of a relationship, not a forecast of a
return, and nothing here licenses the second.

USAGE
    python scripts/measure_exposure_stability.py
    python scripts/measure_exposure_stability.py --dry-run
    python scripts/measure_exposure_stability.py --years 9
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import sys
import time
from itertools import pairwise
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from _lib import exposure  # noqa: E402
from _lib import market_data  # noqa: E402
from _lib import universes  # noqa: E402

OUTPUT = ROOT / "api" / "_lib" / "exposure_stability.json"

# Nine years of weekly returns is 467 bars, which is 8.98 years — eight full
# 52-week blocks and seven transitions. The correlation study got six per
# universe, so this is comparable and the two t-statistics can be read together.
YEARS = 9
BLOCK_WEEKS = 52
MIN_BLOCKS = 8

# A name needs this many weeks inside a block before its beta is estimated from
# it. Forty of fifty-two allows a suspension or a late listing inside the year
# without letting a name contribute a beta from a quarter of one.
MIN_WEEKS_IN_BLOCK = 40

# Below this many names a block's cross-section is too thin to rank correlate.
# Same floor as the correlation study's MIN_NAMES and for the same reason.
MIN_NAMES = 10

# What counts as a name actually LOADING on a factor, rather than carrying a
# beta that is estimation noise. Same screen the coverage work used: R-squared
# at or above this, which at 52 weekly observations needs |t| around 1.6.
MATERIAL_R2 = 0.05

# Fetch in chunks with a pause. yfinance throttles a caller that asks for two
# hundred symbols in quick succession, and a throttled response is not an error
# — it is a short frame, which would silently become a name with too little
# history. Slower and correct.
CHUNK = 40
PAUSE_SECONDS = 6


def _weekly(frames: dict) -> pd.DataFrame:
    """Weekly log returns, one column per symbol.

    Summed from daily rather than re-differenced from Friday closes, because log
    returns add and summing keeps a week whose market shut for a holiday instead
    of dropping it.
    """
    closes = pd.DataFrame({s: f["Close"].astype("float64") for s, f in frames.items()})
    daily = np.log(closes.sort_index() / closes.sort_index().shift(1))
    return exposure.to_weekly(daily)


def _blocks(returns: pd.DataFrame, size: int = BLOCK_WEEKS) -> list:
    """Consecutive non-overlapping windows, most recent last, whole ones only."""
    out = [returns.iloc[i:i + size] for i in range(0, len(returns) - size + 1, size)]
    return [b for b in out if len(b) == size]


def _beta(y: pd.Series, x: pd.Series) -> float:
    """OLS slope of `y` on `x`, or NaN when the pair cannot support one."""
    paired = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(paired) < MIN_WEEKS_IN_BLOCK:
        return np.nan
    centred = paired["x"] - paired["x"].mean()
    sxx = float((centred ** 2).sum())
    if sxx <= 0:
        return np.nan
    return float((centred * (paired["y"] - paired["y"].mean())).sum() / sxx)


def _r_squared(y: pd.Series, x: pd.Series) -> float:
    paired = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(paired) < MIN_WEEKS_IN_BLOCK:
        return np.nan
    if paired["y"].std(ddof=1) <= 0 or paired["x"].std(ddof=1) <= 0:
        return np.nan
    return float(paired["y"].corr(paired["x"]) ** 2)


def persistence(betas: pd.DataFrame,
                r_squared: Optional[pd.DataFrame] = None) -> dict:
    """Rank correlation between consecutive blocks' cross-sections of beta.

    `betas` is names x blocks. Each column is one year's cross-section: which
    names loaded hardest on this factor. Consecutive columns are rank correlated
    over the names present in BOTH, so a name that joins late contributes to the
    transitions it can and to no others.

    High means the ordering persists — the names that loaded hardest last year
    are the ones that load hardest this year, which is what a forward-looking
    beta assumes and what a panel would be asserting by printing one.

    THE UNCONDITIONAL VERSION LARGELY MEASURES WHETHER NOISE PERSISTS, and that
    is not a subtlety, it is most of the sample. Run across every name, this
    asks whether AAPL's gold beta this year predicts AAPL's gold beta next year
    — and AAPL has no gold exposure, so both numbers are estimation error and
    the honest answer is no. Measured: gold reads +0.03 across 157 names.
    Correlations did not have this problem, because every PAIR of stocks has a
    real correlation; not every stock has a real factor loading.

    So `r_squared` turns on the version the decision actually rests on: the
    cross-section is restricted to names that materially loaded IN THE FIRST
    BLOCK OF EACH TRANSITION, and persistence is then measured into the second.
    Selecting on block t and testing on block t+1 uses no information from the
    future, and it is exactly the situation a panel is in — it prints a beta
    because it sees a loading now, and the question is whether that loading is
    still there next year. The same gold figure is +0.22 under that condition.
    """
    scores, pairs_used = [], []
    for first, second in pairwise(betas.columns):
        a, b = betas[first], betas[second]
        shared = a.notna() & b.notna()
        if r_squared is not None:
            # Block t only. Conditioning on t+1 as well would be selecting on
            # the answer and would inflate this without bound.
            shared &= r_squared[first] >= MATERIAL_R2
        if int(shared.sum()) < MIN_NAMES:
            continue
        x, y = a[shared], b[shared]
        if np.ptp(x) == 0 or np.ptp(y) == 0:
            continue
        rho = stats.spearmanr(x, y).statistic
        if np.isfinite(rho):
            scores.append(float(rho))
            pairs_used.append({"from": str(first), "to": str(second),
                               "names": int(shared.sum()), "rho": float(rho)})

    if len(scores) < 3:
        return {"usable": False,
                "reason": f"Only {len(scores)} consecutive block pairs with "
                          f"{MIN_NAMES}+ shared names."}

    values = np.array(scores, dtype="float64")
    n = len(values)
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    t = mean / (sd / np.sqrt(n)) if sd > 0 else float("nan")
    return {
        "usable": True, "transitions": n,
        "meanRankCorrelation": mean, "stdev": sd,
        "tStat": float(t) if np.isfinite(t) else None,
        "min": float(values.min()), "max": float(values.max()),
        "byTransition": pairs_used,
    }


def dispersion(betas: pd.DataFrame) -> dict:
    """How much a single name's beta moves between blocks.

    The rank correlation answers whether the ORDERING holds. This answers
    whether the NUMBER does, and they can disagree: an ordering that survives
    while every beta halves is a real finding about relative exposure and a
    useless one for anybody reading a magnitude off a panel.
    """
    spread = betas.std(axis=1, ddof=1).dropna()
    if spread.empty:
        return {"usable": False}
    level = betas.mean(axis=1).abs().replace(0.0, np.nan).dropna()
    return {
        "usable": True,
        "medianWithinNameSd": float(spread.median()),
        "medianAbsBeta": float(level.median()) if len(level) else None,
        "names": len(spread),
    }


def asymmetry(weekly: pd.DataFrame, factor: pd.Series, names: list) -> dict:
    """Upside and downside betas, and whether the GAP between them persists.

    SPLIT BY REGIME AS WELL AS BY HALF. A sample straddling one large
    one-directional move produces unstable asymmetry for mechanical reasons, so
    a half-split alone cannot tell "the gap is not real" from "the gap was
    measured across a spike". Regimes here are the factor's own up years and
    down years, which is the split that separates those two explanations.
    """
    blocks = _blocks(weekly)
    if len(blocks) < 4:
        return {"usable": False, "reason": "Too few blocks for a regime split."}

    def gap(rows: pd.DataFrame, name: str) -> float:
        paired = pd.concat([rows[name].rename("y"),
                            factor.reindex(rows.index).rename("x")], axis=1).dropna()
        up, down = paired[paired["x"] > 0], paired[paired["x"] <= 0]
        if len(up) < 15 or len(down) < 15:
            return np.nan
        return _beta(down["y"], down["x"]) - _beta(up["y"], up["x"])

    half = len(blocks) // 2
    early = pd.concat(blocks[:half])
    late = pd.concat(blocks[half:])

    # Regimes: the blocks where the factor rose, against the blocks where it fell.
    rising = [b for b in blocks if float(factor.reindex(b.index).sum()) > 0]
    falling = [b for b in blocks if float(factor.reindex(b.index).sum()) <= 0]
    if not rising or not falling:
        return {"usable": False, "reason": "The factor did not both rise and fall."}

    rows = []
    for name in names:
        if name not in weekly.columns:
            continue
        entry = {
            "ticker": name,
            "earlyGap": gap(early, name), "lateGap": gap(late, name),
            "risingGap": gap(pd.concat(rising), name),
            "fallingGap": gap(pd.concat(falling), name),
        }
        if any(not np.isfinite(v) for k, v in entry.items() if k != "ticker"):
            continue
        rows.append(entry)

    if len(rows) < MIN_NAMES:
        return {"usable": False, "reason": f"Only {len(rows)} names with both regimes."}

    def agreement(a: str, b: str) -> dict:
        first = np.array([r[a] for r in rows])
        second = np.array([r[b] for r in rows])
        same = float(np.mean(np.sign(first) == np.sign(second)))
        rho = stats.spearmanr(first, second).statistic
        return {"signAgreement": same,
                "rankCorrelation": float(rho) if np.isfinite(rho) else None}

    return {
        "usable": True, "names": len(rows),
        "byHalf": agreement("earlyGap", "lateGap"),
        "byRegime": agreement("risingGap", "fallingGap"),
        "medianGapEarly": float(np.median([r["earlyGap"] for r in rows])),
        "medianGapLate": float(np.median([r["lateGap"] for r in rows])),
        "medianGapRising": float(np.median([r["risingGap"] for r in rows])),
        "medianGapFalling": float(np.median([r["fallingGap"] for r in rows])),
        "risingBlocks": len(rising), "fallingBlocks": len(falling),
    }


def stress(weekly: pd.DataFrame, factor: pd.Series, names: list) -> dict:
    """Does a factor explain MORE of a name in the blocks the factor fell hardest?

    WHOLE BLOCKS, NEVER SELECTED WEEKS, and the distinction is the whole
    measurement. Picking the worst weeks and computing an R-squared inside them
    conditions on the size of the common factor and truncates its variance,
    which moves the number for a reason that has nothing to do with markets
    (Forbes & Rigobon 2002). Done that way during design it reported explanatory
    power FALLING in stress on every name — the selection doing the work, not a
    finding. Each whole block keeps its own full distribution of factor
    realisations, and the question becomes the one worth asking anyway.
    """
    blocks = _blocks(weekly)
    if len(blocks) < 4:
        return {"usable": False, "reason": "Too few blocks."}

    scored = [(float(factor.reindex(b.index).sum()), b) for b in blocks]
    scored.sort(key=lambda row: row[0])
    quartile = max(1, len(scored) // 4)
    worst = pd.concat([b for _, b in scored[:quartile]])
    rest = pd.concat([b for _, b in scored[quartile:]])

    pairs = []
    for name in names:
        if name not in weekly.columns:
            continue
        a = _r_squared(worst[name], factor.reindex(worst.index))
        b = _r_squared(rest[name], factor.reindex(rest.index))
        if np.isfinite(a) and np.isfinite(b):
            pairs.append((a, b))
    if len(pairs) < MIN_NAMES:
        return {"usable": False, "reason": f"Only {len(pairs)} names measurable."}

    worst_r2 = float(np.mean([a for a, _ in pairs]))
    rest_r2 = float(np.mean([b for _, b in pairs]))
    return {
        "usable": True, "names": len(pairs),
        "worstBlocksRSquared": worst_r2, "restRSquared": rest_r2,
        "rise": worst_r2 - rest_r2,
        "worstBlocks": quartile, "totalBlocks": len(scored),
    }


def frequency(daily: pd.DataFrame, factor_daily: pd.Series,
              weekly: pd.DataFrame, factor_weekly: pd.Series,
              names: list) -> dict:
    """Daily, daily-plus-one-lag and weekly betas across every name.

    THE DESIGN DECISION THIS RE-TESTS WAS MADE ON FIVE PAIRS. Weekly was chosen
    because a coal book read 0.17 daily against 0.52 weekly, and two clean cases
    is not enough to carry a frequency choice for every name and factor. This
    reports the three side by side and, more usefully, how often they DISAGREE
    IN SIGN — which is the failure that matters, since a beta whose sign depends
    on the sampling interval should not be printed at all.
    """
    rows = []
    for name in names:
        if name not in daily.columns or name not in weekly.columns:
            continue
        d = _beta(daily[name], factor_daily)
        lag = _beta(daily[name], factor_daily.shift(1))
        w = _beta(weekly[name], factor_weekly)
        if not all(np.isfinite(v) for v in (d, lag, w)):
            continue
        rows.append({"daily": d, "dimson": d + lag, "weekly": w})
    if len(rows) < MIN_NAMES:
        return {"usable": False, "reason": f"Only {len(rows)} names measurable."}

    daily_b = np.array([r["daily"] for r in rows])
    dimson_b = np.array([r["dimson"] for r in rows])
    weekly_b = np.array([r["weekly"] for r in rows])
    return {
        "usable": True, "names": len(rows),
        "medianAbsDaily": float(np.median(np.abs(daily_b))),
        "medianAbsDimson": float(np.median(np.abs(dimson_b))),
        "medianAbsWeekly": float(np.median(np.abs(weekly_b))),
        # The number that decides whether one frequency may be preferred quietly.
        "signDisagreeDailyWeekly": float(np.mean(np.sign(daily_b) != np.sign(weekly_b))),
        "signDisagreeDimsonWeekly": float(np.mean(np.sign(dimson_b) != np.sign(weekly_b))),
        "weeklyOverDaily": float(np.median(np.abs(weekly_b)) / np.median(np.abs(daily_b)))
        if np.median(np.abs(daily_b)) > 0 else None,
    }


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def _fetch(symbols: list, start: dt.date, end: dt.date) -> dict:
    frames, noise = {}, io.StringIO()
    for i in range(0, len(symbols), CHUNK):
        chunk = symbols[i:i + CHUNK]
        with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
            frames.update(market_data.ohlcv_batch(chunk, start, end))
        print(f"    fetched {min(i + CHUNK, len(symbols))}/{len(symbols)} "
              f"({len(frames)} usable)")
        if i + CHUNK < len(symbols):
            time.sleep(PAUSE_SECONDS)
    return frames


def _tiers(frames: dict, idx_names: set, resource_names: set) -> dict:
    """Which names go in which bucket, and the liquidity split.

    Liquidity is median dollar volume over the whole window, split at the
    median of the market's own names — an absolute threshold would put every
    Indonesian listing in the illiquid tier and answer nothing.
    """
    liquidity = {}
    for symbol, frame in frames.items():
        value = float((frame["Close"] * frame["Volume"]).median())
        if np.isfinite(value) and value > 0:
            liquidity[symbol] = value

    idx = sorted(n for n in frames if n in idx_names)
    us = sorted(n for n in frames if n not in idx_names)
    tiers = {
        "all": sorted(frames),
        "US": us,
        "ID": idx,
        "resources": sorted(n for n in frames if n in resource_names),
        "nonResources": sorted(n for n in frames if n not in resource_names),
    }
    for label, members in (("ID", idx), ("US", us)):
        scored = [(liquidity[n], n) for n in members if n in liquidity]
        if len(scored) >= 2 * MIN_NAMES:
            scored.sort()
            half = len(scored) // 2
            tiers[f"{label}-illiquidHalf"] = sorted(n for _, n in scored[:half])
            tiers[f"{label}-liquidHalf"] = sorted(n for _, n in scored[half:])
    return {k: v for k, v in tiers.items() if len(v) >= MIN_NAMES}


def _beta_table(weekly: pd.DataFrame, factor: pd.Series,
                names: list) -> tuple[pd.DataFrame, pd.DataFrame]:
    """names x blocks of betas, and the matching R-squareds.

    Both, because `persistence` needs the second to tell a name that loads on
    this factor from one whose beta is estimation error — see its docstring.
    """
    blocks = _blocks(weekly)
    betas, fits = {}, {}
    for i, block in enumerate(blocks):
        column, fit = {}, {}
        for name in names:
            if name not in weekly.columns:
                continue
            series = block[name]
            column[name] = _beta(series, factor.reindex(block.index))
            fit[name] = _r_squared(series, factor.reindex(block.index))
        betas[f"y{i + 1}"] = column
        fits[f"y{i + 1}"] = fit
    return pd.DataFrame(betas), pd.DataFrame(fits)


def _headline(results: dict, kill_at: float) -> str:
    """The sentence a panel would print, chosen by the measurement itself."""
    usable = [(key, block["all"]["persistenceWhereLoaded"])
              for key, block in results.items()
              if block.get("all", {}).get("persistenceWhereLoaded", {}).get("usable")]
    if not usable:
        return ("Exposure beta persistence could not be measured, so nothing in this app "
                "may print a forward-looking factor beta.")
    means = [p["meanRankCorrelation"] for _, p in usable]
    ts = [p["tStat"] for _, p in usable if p.get("tStat") is not None]
    low, high = min(means), max(means)
    strongest = max(usable, key=lambda row: row[1]["meanRankCorrelation"])

    # Every branch is quoted against the correlation study's 0.50 floor, because
    # a number with no scale beside it invites the reader to supply their own.
    scale = ("For scale, the pairwise correlations that licensed the portfolio panel "
             "to inform position size persist at 0.50 to 0.65.")
    if high < kill_at:
        return (f"Factor betas do not persist: among the names that actually load on a "
                f"factor, rank correlations run {low:.2f} to {high:.2f} year over year, "
                f"below the {kill_at:.2f} this study set in advance as the line under "
                f"which a measured beta describes history only. On this evidence a "
                f"single-name exposure beta must not be printed as a forward-looking "
                f"number. {scale}")
    if low < kill_at:
        return (f"Factor beta persistence depends on the factor: among names that "
                f"actually load, rank correlations run {low:.2f} to {high:.2f} year over "
                f"year, so some factors clear the {kill_at:.2f} line set in advance and "
                f"others do not. The strongest is {strongest[0]} at "
                f"{strongest[1]['meanRankCorrelation']:.2f}"
                + (f", and t-statistics run {min(ts):+.1f} to {max(ts):+.1f}" if ts else "")
                + f". A beta may be printed for the factors that clear it, with its own "
                  f"persistence stated, and must not be for the rest. {scale}")
    return (f"Factor betas persist among the names that load on them: rank correlations "
            f"of {low:.2f} to {high:.2f} year over year across every tested factor"
            + (f" at t-statistics from {min(ts):+.1f} to {max(ts):+.1f}" if ts else "")
            + f". {scale} These sit below that, so a printed beta is a weaker claim "
              f"than a printed correlation and must carry its own number.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--years", type=int, default=YEARS)
    # The line is set BEFORE the numbers are seen. Choosing it afterwards would
    # be choosing whether the feature ships, which is not what a gate is.
    parser.add_argument("--kill-at", type=float, default=0.25,
                        help="Rank correlation below which a beta describes history only.")
    args = parser.parse_args()

    end = dt.date.today()
    start = end - dt.timedelta(days=int(365.25 * args.years) + 30)

    idx_names, us_names = set(), set()
    for universe_id in ("idx30", "lq45", "idxresources"):
        idx_names.update(universes.get(universe_id)["tickers"])
    for universe_id in ("dow30", "nasdaq100"):
        us_names.update(universes.get(universe_id)["tickers"])
    resource_names = set(universes.get("idxresources")["tickers"])
    equities = sorted(idx_names | us_names)

    print(f"Exposure beta stability — {args.years}y, {len(equities)} names")
    print(f"  kill criterion set in advance: rank correlation < {args.kill_at:.2f}\n")

    print("  equities")
    frames = _fetch(equities, start, end)
    factor_symbols = sorted(set(exposure.reference_symbols("US"))
                            | set(exposure.reference_symbols("ID")))
    print("  factors")
    factor_frames = _fetch(factor_symbols, start, end)

    if len(frames) < MIN_NAMES or not factor_frames:
        print("\nNothing measurable. Nothing written.")
        return 1

    weekly = _weekly(frames)
    factor_weekly = _weekly(factor_frames)
    closes = pd.DataFrame({s: f["Close"].astype("float64") for s, f in frames.items()})
    daily = np.log(closes.sort_index() / closes.sort_index().shift(1))
    factor_closes = pd.DataFrame({s: f["Close"].astype("float64")
                                  for s, f in factor_frames.items()})
    factor_daily = np.log(factor_closes.sort_index() / factor_closes.sort_index().shift(1))

    blocks = _blocks(weekly)
    print(f"\n  {len(weekly)} weeks, {len(blocks)} whole {BLOCK_WEEKS}-week blocks, "
          f"{max(0, len(blocks) - 1)} transitions")

    # --- per-name history, reported and excluded by name -------------------
    history = {name: int(weekly[name].notna().sum()) for name in weekly.columns}
    long_enough = sorted(n for n, w in history.items()
                         if w >= MIN_BLOCKS * BLOCK_WEEKS * 0.9)
    excluded = sorted(set(weekly.columns) - set(long_enough))
    print(f"  {len(long_enough)} names with {MIN_BLOCKS} blocks of history; "
          f"{len(excluded)} excluded")
    if excluded:
        shown = ", ".join(f"{n} ({history[n] // BLOCK_WEEKS}b)" for n in excluded[:12])
        print(f"    excluded: {shown}{' ...' if len(excluded) > 12 else ''}")

    usable_frames = {s: f for s, f in frames.items() if s in long_enough}
    tiers = _tiers(usable_frames, idx_names, resource_names)
    print(f"  tiers: {', '.join(f'{k} ({len(v)})' for k, v in tiers.items())}\n")

    results: dict = {}
    for reference in exposure.REFERENCES:
        symbol = reference.symbol
        if symbol not in factor_weekly.columns:
            print(f"  {reference.label}: no data")
            continue
        series = factor_weekly[symbol]
        print(f"  {reference.label} ({symbol})")
        block: dict = {}
        for tier, members in tiers.items():
            table, fits = _beta_table(weekly, series, members)
            unconditional = persistence(table)
            loaded = persistence(table, r_squared=fits)
            block[tier] = {"names": len(members),
                           # The one the decision rests on, named so it cannot be
                           # confused with the all-names figure beside it.
                           "persistenceWhereLoaded": loaded,
                           "persistenceAllNames": unconditional,
                           "dispersion": dispersion(table)}
            everything = (f"all {unconditional['meanRankCorrelation']:+.3f}"
                          if unconditional["usable"] else "all n/a")
            if loaded["usable"]:
                shown = int(np.median([p["names"] for p in loaded["byTransition"]]))
                print(f"    {tier:20} loaded {loaded['meanRankCorrelation']:+.3f} "
                      f"(t {loaded['tStat']:+.1f}, ~{shown} names)   {everything}")
            else:
                print(f"    {tier:20} loaded: {loaded['reason']}   {everything}")

        block["stress"] = stress(weekly, series, tiers["all"])
        block["asymmetry"] = asymmetry(weekly, series, tiers["all"])
        block["frequency"] = frequency(
            daily, factor_daily[symbol], weekly, series, tiers["all"])
        if block["stress"]["usable"]:
            s = block["stress"]
            print(f"    {'stress':20} worst blocks R2 {s['worstBlocksRSquared']:.3f} "
                  f"vs rest {s['restRSquared']:.3f} ({s['rise']:+.3f})")
        if block["asymmetry"]["usable"]:
            a = block["asymmetry"]
            print(f"    {'up/down gap':20} sign holds {a['byHalf']['signAgreement']:.0%} "
                  f"by half, {a['byRegime']['signAgreement']:.0%} by regime")
        if block["frequency"]["usable"]:
            f = block["frequency"]
            print(f"    {'frequency':20} |beta| daily {f['medianAbsDaily']:.3f} "
                  f"dimson {f['medianAbsDimson']:.3f} weekly {f['medianAbsWeekly']:.3f}; "
                  f"sign disagrees {f['signDisagreeDailyWeekly']:.0%}")
        results[reference.key] = {"label": reference.label, "symbol": symbol, **block}
        print()

    if not results:
        print("No factor was measurable. Nothing written.")
        return 1

    payload = {
        "measuredOn": dt.date.today().isoformat(),
        "years": args.years,
        "blockWeeks": BLOCK_WEEKS,
        "blocks": len(blocks),
        "transitions": max(0, len(blocks) - 1),
        "weeks": len(weekly),
        "killAt": args.kill_at,
        "namesMeasured": len(long_enough),
        "namesExcludedForShortHistory": {n: history[n] for n in excluded},
        "tiers": {k: len(v) for k, v in tiers.items()},
        "factors": results,
        "headline": _headline(results, args.kill_at),
        "caveats": [
            "Today's index constituents, so every name measured is one that survived.",
            "Persistence, not accuracy. A beta that predicts next year's beta is still "
            "a description of a relationship, not a forecast of a return.",
            "Non-overlapping blocks, so the t-statistics do not share weeks. One "
            "history, one regime.",
            "The stress comparison selects whole blocks rather than the worst weeks, "
            "which removes the worst of the conditioning bias (Forbes & Rigobon 2002) "
            "but not all of it — a block is still chosen on its own realised return.",
            "Names with fewer than eight 52-week blocks are excluded by name rather "
            "than averaged in, and the exclusions are listed in this file.",
        ],
    }

    print(payload["headline"])
    if args.dry_run:
        print("\n--- would write ---")
        print(json.dumps(payload, indent=2)[:1200])
        return 0
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nWrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
