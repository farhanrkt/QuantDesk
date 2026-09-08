"""
tape.py
=======
Who wins the heavy days — the readable part of "somebody is working this stock".

WHAT THIS IS, AND THE THING IT IS NOT
-------------------------------------
The Indonesian practice of *bandarmology* reads the exchange's BROKER SUMMARY:
for each session, which broker codes net-bought the stock and how much of that
was foreign money. That file is the method. Everything else people call
bandarmology is inference about what the broker summary would have said.

This module does not have the broker summary and cannot get it — the exchange
publishes it behind a bot check and no provider this app can reach redistributes
it. So this is NOT bandarmology. It is the OHLCV shadow of one question
bandarmology asks, and the difference is stated wherever the output renders
rather than left for the reader to work out.

What is missing, and what it would settle:

  * WHO. A broker summary names the accumulating desk. Nothing here can
    distinguish one determined buyer from four hundred small ones.
  * FOREIGN VERSUS DOMESTIC. The most-watched split on IDX. Absent.
  * CROSSINGS. Blocks arranged off the order book sit inside the daily volume
    here with no mark saying they were pre-arranged.

WHAT SURVIVES THE MISSING DATA
------------------------------
One question, and it is the useful one:

    ON THE DAYS WHEN THE MOST SHARES CHANGED HANDS, WHO FINISHED IN CONTROL?

A session's close within its own high-low range says who won that session.
Averaged over a year's heaviest sessions and compared against its ordinary ones,
it says whether size arrives to buy or to sell. It cannot say who, and it does
not need to: a stock that closes near its low on ordinary days and near its high
whenever volume trebles is being bought by somebody working to a schedule.

THREE THINGS THE FIRST VERSION OF THIS FILE GOT WRONG
------------------------------------------------------
All three were found by measuring the output across 247 real listings rather
than by reading the code, and all three produced a plausible number.

1. IT TESTED AGAINST ZERO. The median IDX listing reads a lift of +0.08 —
   heavy days close higher in their range than ordinary ones almost everywhere,
   because volume arrives with up-moves. Testing against zero therefore called
   the MEDIAN STOCK an accumulation candidate. The null is now the market's own
   measured median, so the claim is "unlike its market", not "unlike nothing".

2. THE SECONDARY WICK TERM SATURATED FOR EVERYONE. It was scaled to a fixed
   0.10, and the IDX cross-section has a standard deviation of 0.091 while the
   Nasdaq-100's is 0.027 — so the term pinned at its cap for a quarter of IDX
   names and never moved at all for US ones. It is now scaled in standard
   deviations of the market it is measured in.

3. THE CONCENTRATION BANDS WERE GUESSED. They are now the measured 75th and
   95th percentiles of the market being scanned. A "caution" that fires on a
   quarter of a market is a description of the market, which is the argument
   `pretrade.py` already makes about every flag it demotes.

AND THE FINDING THAT CAME OUT OF FIXING THEM
---------------------------------------------
This signal is an EMERGING-MARKET PHENOMENON, and the calibration says so out
loud rather than leaving it flattering. Against each market's own median, at the
conventional 5% bar, the test fires on 13.3% of 188 Indonesian listings — 2.7
times chance — and on 4.2% of 120 US large caps, which IS chance. That is the
shape you would expect if thin, lightly arbitraged books let one operator leave
a footprint and deep ones do not.

Two consequences, and both ship:

  * ON US MARKETS THIS COMPONENT IS MEASURING NOTHING. It still renders, still
    reports its statistic, and `verdict.py` still weights it as weak evidence —
    but the calibration beside it says the market-wide firing rate is
    indistinguishable from chance, and no reader should take a US accumulation
    verdict from it.
  * EVEN ON IDX, ROUGHLY TWO IN FIVE HITS ARE FALSE. 13.3% observed against 5%
    expected leaves about 8 points of real signal in 13, so a third to a half of
    the names that fire are noise. `tape_calibration.json` publishes that and
    the scanner restates it as a count of names against a count expected.

WHAT DOES NOT VOTE
------------------
Volume concentration — the share of the year traded on its five biggest days —
is computed, reported, and deliberately kept OUT of the score. It is not
directional: a stock whose year happened in five sessions is not thereby good or
bad, it is unsizeable, and that belongs with the gates. It matters — on a real
IDX sweep the name that ranked FIRST overall traded a quarter of its year in
five days.

OVERLAP WITH THE FLOW LENS IS REAL, AND MEASURED RATHER THAN DENIED
--------------------------------------------------------------------
`whale.py` finds point anomalies and `accumulation.py` finds sustained regimes,
both from price and volume. This reads the same two series. It asks a different
question — those two ask *when* something happened, this asks *who won* — but
nobody should take independence on trust, which is why `verdict.py` files this
inside the price-and-volume family rather than beside it, and why the scanner
prints the measured rank correlation between every pair of components.

References
----------
Wyckoff, R. D. (1931). The Richard D. Wyckoff Method of Trading and Investing
    in Stocks. (Effort versus result; absorption at range extremes.)
Welch, B. L. (1947). "The generalization of Student's problem when several
    different population variances are involved." Biometrika 34.
Hirschman, A. O. (1945). National Power and the Structure of Foreign Trade.
    (The concentration index, applied here to daily volume shares.)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

# One year of sessions, matching `ranking.RANK_WINDOW`. The same-window rule
# applies for the same reason it applies there: two names with identical recent
# tape must not read differently because one of them listed earlier.
WINDOW = 252

# Below this there is no test worth running. Under about 160 sessions the heavy
# split is a dozen observations and a Welch statistic computed on it is theatre.
MIN_BARS = 160

# What counts as a heavy session: relative volume at or above this quantile of
# the name's own year. The top fifth leaves roughly fifty heavy sessions against
# two hundred ordinary ones, which is the split the significance rates in
# `tape_calibration.json` were measured at. Tightening it to the top decile
# halves the sample and the test stops resolving anything.
HEAVY_QUANTILE = 0.80

# Relative volume is measured against a rolling MEDIAN, not a mean. One 20x
# print — a crossing, an index rebalance — drags a mean far enough to reclassify
# the surrounding fortnight as ordinary, which is exactly backwards.
RVOL_WINDOW = 63

# The significance bar. Two-sided, conventional, and quoted alongside the
# t-statistic so a reader can disagree with it. NOT corrected for multiple
# testing here, because this is one name's reading; the scanner counts how many
# of its names cleared the bar against how many chance predicts, which is where
# a correction belongs and where `eventstudy.py` already puts one.
ALPHA = 0.05

# How far a significant reading and the secondary wick term may each move the
# score from neutral. The wick allowance is deliberately small: it carries no
# significance test, and letting an untested observation move a score as far as
# a tested one would misrepresent which of the two is evidence.
LIFT_SWING = 38.0
WICK_SWING = 6.0

# Both saturations are in standard deviations of the scanned market's own
# cross-section — see failure 2 in the module docstring. Two sigma is where a
# reading stops being "high" and starts being "extreme", and past it the
# estimator's own error is wide enough that 2.5 and 3.5 are not distinguishable
# claims about the world.
LIFT_SATURATION_SIGMA = 2.0
WICK_SATURATION_SIGMA = 2.0

# Fallbacks for a market with no calibration row. Testing against a zero
# baseline is the WRONG null — it is failure 1 above — so an uncalibrated market
# still gets a reading but never a direction, and says why.
UNCALIBRATED_LIFT_SD = 0.12
UNCALIBRATED_WICK_SD = 0.06

_CALIBRATION_PATH = Path(__file__).with_name("tape_calibration.json")
_CALIBRATION_CACHE: Optional[dict] = None
_LOAD_FROM_DISK = object()


def load_calibration() -> dict:
    """The stamped cross-sectional baselines, or an empty dict.

    Read from disk once. A checkout that has never run
    `scripts/calibrate_tape.py` degrades to reporting the raw statistics with no
    direction, rather than to a crash or — far worse — to a confident direction
    computed against the wrong null.
    """
    global _CALIBRATION_CACHE
    if _CALIBRATION_CACHE is None:
        try:
            _CALIBRATION_CACHE = json.loads(_CALIBRATION_PATH.read_text())
        except (OSError, ValueError):
            _CALIBRATION_CACHE = {}
    return _CALIBRATION_CACHE


def calibration_for(market_code: Optional[str],
                    calibration=_LOAD_FROM_DISK) -> Optional[dict]:
    """One market's row, or None. Never another market's — see the docstring's
    third failure: the IDX and US cross-sections differ by a factor of three on
    every scale in this file, so borrowing a row would be worse than having none.
    """
    if calibration is _LOAD_FROM_DISK:
        calibration = load_calibration()
    markets = (calibration or {}).get("markets") or {}
    return markets.get((market_code or "").strip().upper())


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _saturate(value: float, scale: Optional[float]) -> float:
    if not scale or scale <= 0:
        return 0.0
    return float(min(1.0, abs(value) / scale))


def close_location(frame: pd.DataFrame) -> pd.Series:
    """Where each session closed inside its own range: -1 at the low, +1 at the high.

    NaN on a zero-range bar rather than zero. A limit-up print with no range is
    not a session that closed in the middle — it is a session carrying no
    information about who won it, and averaging a fabricated zero into the
    heavy-day mean is how a locked stock comes to read as balanced.
    """
    high = frame["High"].astype("float64")
    low = frame["Low"].astype("float64")
    close = frame["Close"].astype("float64")
    span = (high - low).where(lambda s: s > 0)
    return ((close - low) - (high - close)) / span


def wick_asymmetry(frame: pd.DataFrame) -> pd.Series:
    """Lower shadow minus upper shadow, as a share of the session's range.

    Positive means it was pushed down and bought back — bids underneath.
    Negative means rallies were sold into.
    """
    high = frame["High"].astype("float64")
    low = frame["Low"].astype("float64")
    span = (high - low).where(lambda s: s > 0)
    body_low = frame[["Open", "Close"]].astype("float64").min(axis=1)
    body_high = frame[["Open", "Close"]].astype("float64").max(axis=1)
    return ((body_low - low) - (high - body_high)) / span


def concentration(volume: pd.Series) -> dict:
    """How much of the window's volume happened on how few sessions.

    Two views of one fact, because neither is legible alone. `topFiveShare` is
    concrete and quotable; `effectiveDays` — the reciprocal of the Herfindahl
    index over daily volume shares — says how many sessions of EVEN trading the
    window is worth, which is what makes a 0.25 top-five share readable as "this
    year was really fifty days".

    No band is assigned here. Where the line falls is a property of the market
    being scanned, not of this function, so `read` applies the calibrated
    percentiles and this returns the raw quantities.
    """
    total = float(volume.sum())
    if not np.isfinite(total) or total <= 0 or len(volume) < 5:
        return {"available": False, "topFiveShare": None, "effectiveDays": None,
                "sessions": len(volume)}

    shares = (volume / total).astype("float64")
    herfindahl = float((shares ** 2).sum())
    return {
        "available": True,
        "topFiveShare": float(volume.nlargest(5).sum() / total),
        "effectiveDays": _finite(1.0 / herfindahl) if herfindahl > 0 else None,
        "sessions": len(volume),
    }


# ============================================================================ #
# Raw statistics — no calibration, no score, no direction
#
# Split out so `scripts/calibrate_tape.py` can measure the cross-section with
# the same code the reading uses. A calibration computed by a second
# implementation would drift from the thing it calibrates, which is the failure
# `explain.for_synthesis` avoids by reading the assembled payload rather than
# recomputing it.
# ============================================================================ #
def statistics(frame: Optional[pd.DataFrame], window: int = WINDOW) -> dict:
    """Every raw tape quantity for one name, or a stated refusal."""
    if frame is None or len(frame) < MIN_BARS:
        have = 0 if frame is None else len(frame)
        return {"available": False,
                "reason": (f"needs {MIN_BARS} sessions to compare heavy against "
                           f"ordinary ones; this has {have}")}

    recent = frame.tail(window)
    volume = recent["Volume"].astype("float64")
    if float(volume.sum()) <= 0:
        return {"available": False, "reason": "no volume was reported in this window"}

    baseline = volume.rolling(RVOL_WINDOW, min_periods=20).median()
    rvol = volume / baseline.replace(0, np.nan)
    usable = rvol.notna()
    if int(usable.sum()) < MIN_BARS // 2:
        return {"available": False,
                "reason": "too few sessions with a comparable volume baseline"}

    cutoff = float(rvol[usable].quantile(HEAVY_QUANTILE))
    heavy = usable & (rvol >= cutoff)

    location = close_location(recent)
    heavy_values = location[heavy].dropna().to_numpy(dtype="float64")
    ordinary_values = location[usable & ~heavy].dropna().to_numpy(dtype="float64")
    if len(heavy_values) < 15 or len(ordinary_values) < 30:
        return {"available": False,
                "reason": ("too few sessions with a measurable range to compare — "
                           "usually a listing that spends days locked or untraded")}

    # Volume-weighted, because a long wick on a day nobody traded is not a
    # defended bid. Weights normalise inside the window so one enormous session
    # cannot become the whole average.
    wicks = wick_asymmetry(recent)
    wick_ok = wicks.notna() & volume.notna()
    wick_weight = float(volume[wick_ok].sum())
    wick = (float((wicks[wick_ok] * volume[wick_ok]).sum() / wick_weight)
            if wick_weight > 0 else None)

    # Heavy-session range against ordinary-session range. Above 1 nearly always —
    # size moves price — so it is read relatively: a name where trebled volume
    # barely widens the range is having that volume absorbed by a resting order.
    span = (recent["High"] - recent["Low"]) / recent["Close"].replace(0, np.nan)
    heavy_span = _finite(span[heavy].median())
    ordinary_span = _finite(span[usable & ~heavy].median())

    return {
        "available": True,
        "lift": float(heavy_values.mean() - ordinary_values.mean()),
        "heavyMeanLocation": float(heavy_values.mean()),
        "ordinaryMeanLocation": float(ordinary_values.mean()),
        "heavyValues": heavy_values,
        "ordinaryValues": ordinary_values,
        "heavySessions": len(heavy_values),
        "ordinarySessions": len(ordinary_values),
        "rvolCutoff": _finite(cutoff),
        "wick": wick,
        "spanRatio": (heavy_span / ordinary_span
                      if heavy_span is not None and ordinary_span else None),
        "concentration": concentration(volume),
        "sessions": len(recent),
    }


# ============================================================================ #
# The calibrated reading
# ============================================================================ #
def read(frame: Optional[pd.DataFrame], market_code: Optional[str] = None,
         calibration=_LOAD_FROM_DISK, window: int = WINDOW) -> dict:
    """The tape reading for one name, tested against its own market's baseline.

    `direction` is one of "accumulation", "distribution" or "unreadable", and
    UNREADABLE IS THE COMMON OUTCOME BY DESIGN. Against a calibrated null the
    test fires on about one IDX listing in six and one US listing in twenty-five.
    Reporting a direction for the rest would be manufacturing findings out of a
    cross-section that has none.
    """
    raw = statistics(frame, window=window)
    if not raw["available"]:
        return raw

    row = calibration_for(market_code, calibration)
    lift_baseline = _finite((row or {}).get("liftMedian")) or 0.0
    lift_sd = _finite((row or {}).get("liftSd")) or UNCALIBRATED_LIFT_SD
    wick_sd = _finite((row or {}).get("wickSd")) or UNCALIBRATED_WICK_SD

    # THE NULL IS THE MARKET'S OWN MEDIAN, NOT ZERO. Shifting the heavy sample
    # by the baseline turns the two-sample test into a test of "is this lift
    # bigger than the typical lift here", which is the only version of the
    # question that is not answered "yes" for half the market.
    t_stat, p_value = stats.ttest_ind(
        raw["heavyValues"] - lift_baseline, raw["ordinaryValues"], equal_var=False)
    t_stat, p_value = _finite(t_stat), _finite(p_value)

    excess = raw["lift"] - lift_baseline
    calibrated = row is not None
    significant = bool(calibrated and p_value is not None
                       and p_value < ALPHA and excess != 0.0)

    score = 50.0
    if significant:
        score += (1.0 if excess > 0 else -1.0) * LIFT_SWING * (
            0.5 + 0.5 * _saturate(excess, lift_sd * LIFT_SATURATION_SIGMA))
    if raw["wick"] is not None and calibrated:
        score += (1.0 if raw["wick"] > 0 else -1.0) * WICK_SWING * _saturate(
            raw["wick"], wick_sd * WICK_SATURATION_SIGMA)
    score = float(max(0.0, min(100.0, score)))

    direction = ("accumulation" if significant and excess > 0
                 else "distribution" if significant and excess < 0
                 else "unreadable")

    bands = (row or {}).get("concentration") or {}
    conc = dict(raw["concentration"])
    conc["band"] = _concentration_band(conc.get("topFiveShare"), bands)
    conc["caution"] = _finite(bands.get("caution"))
    conc["severe"] = _finite(bands.get("severe"))
    conc["calibrated"] = bool(bands)

    return {
        "available": True,
        "direction": direction,
        "score": score,
        "lift": raw["lift"],
        "liftBaseline": lift_baseline,
        "excessLift": excess,
        "heavyMeanLocation": raw["heavyMeanLocation"],
        "ordinaryMeanLocation": raw["ordinaryMeanLocation"],
        "tStat": t_stat,
        "pValue": p_value,
        "significant": significant,
        "alpha": ALPHA,
        "calibrated": calibrated,
        "market": (market_code or "").upper() or None,
        "measuredOn": (calibration_for(market_code, calibration) or {}).get("measuredOn"),
        "heavySessions": raw["heavySessions"],
        "ordinarySessions": raw["ordinarySessions"],
        "rvolCutoff": raw["rvolCutoff"],
        "wick": raw["wick"],
        "spanRatio": _finite(raw["spanRatio"]),
        "concentration": conc,
        "sessions": raw["sessions"],
        "reading": _reading(direction, excess, lift_baseline, t_stat, p_value,
                            raw, calibrated, row),
        "missing": (
            "Not a broker summary. This cannot say who bought, and cannot separate "
            "foreign from domestic money or a pre-arranged cross from open trading — "
            "the three things the exchange's own daily file would settle."),
    }


def _concentration_band(top_five: Optional[float], bands: dict) -> Optional[str]:
    """Which measured percentile of its market this name's concentration clears."""
    value = _finite(top_five)
    severe, caution = _finite(bands.get("severe")), _finite(bands.get("caution"))
    if value is None or severe is None or caution is None:
        return None
    return ("severe" if value >= severe
            else "caution" if value >= caution else "ordinary")


def _reading(direction: str, excess: float, baseline: float,
             t_stat: Optional[float], p_value: Optional[float], raw: dict,
             calibrated: bool, row: Optional[dict]) -> str:
    """One sentence quoting the test, never summarising past it."""
    heavy, ordinary = raw["heavySessions"], raw["ordinarySessions"]
    stat = (f"t = {t_stat:+.1f}, p = {p_value:.3f}"
            if t_stat is not None and p_value is not None else "no test statistic")

    if not calibrated:
        return (f"Its {heavy} heaviest sessions closed {abs(raw['lift']):.2f} "
                f"{'higher' if raw['lift'] > 0 else 'lower'} in their own range than the "
                f"other {ordinary}. NO DIRECTION IS REPORTED: this market has no measured "
                f"baseline, and heavy sessions close higher than ordinary ones almost "
                f"everywhere, so testing against zero would call the median stock an "
                f"accumulation candidate. Run scripts/calibrate_tape.py.")

    where = (f"against a {baseline:+.2f} median for this market"
             if abs(baseline) >= 0.005 else "against a market median of about zero")

    if direction == "unreadable":
        rate = _finite((row or {}).get("significantShare"))
        common = (f" About {rate * 100:.0f}% of this market reads a direction at all."
                  if rate is not None else "")
        return (f"No readable difference: its {heavy} heaviest sessions closed "
                f"{abs(raw['lift']):.2f} {'higher' if raw['lift'] > 0 else 'lower'} in "
                f"their own range than the other {ordinary}, which is {abs(excess):.2f} "
                f"{'above' if excess > 0 else 'below'} normal {where} and not separable "
                f"from it ({stat}).{common}")

    word = "buying" if direction == "accumulation" else "selling"
    side = "toward the high" if excess > 0 else "toward the low"
    text = (f"On its {heavy} heaviest sessions it closed {abs(raw['lift']):.2f} "
            f"{'nearer the high' if raw['lift'] > 0 else 'nearer the low'} of the day's "
            f"range than on the other {ordinary} — {abs(excess):.2f} further {side} than "
            f"normal {where} ({stat}). Size arrives to do the {word}.")

    wick = raw.get("wick")
    if wick is not None and abs(wick) > 0.04:
        text += (" Volume-weighted, sessions leave a longer "
                 + ("lower shadow: pushed down and bought back."
                    if wick > 0 else "upper shadow: rallies sold into."))
    return text
