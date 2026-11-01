"""
ownership.py
============
The share register: who holds it, how little of it trades, and whether the
number of shares keeps going up.

WHY THIS IS A THIRD BODY OF DATA AND NOT A FIFTH LENS
------------------------------------------------------
Every lens this app had reads one of two things. Flow and Trend read the price
record; Value and Quality read the filings. The whole cross-check rests on those
two sharing no inputs.

The register is neither. Who owns the shares, how concentrated that ownership
is, and how the count of shares has moved are facts about the CAPITAL
STRUCTURE — and no existing lens reads any of them. Not one price signal sees
the float. Piotroski, Altman, Beneish and the discounted cash flow all read
statements in which the share count appears and none of them uses its trend.

That last sentence is the honest boundary and it is worth stating precisely: the
share count IS printed in the filings, so this family is not independent of them
in the way the price record is. What is true is narrower — no lens here reads
it — and `verdict.py` measures the realised correlation across a scan rather
than asserting independence. If the register turns out to move with the filings
family, the measurement will say so.

THE TWO THINGS IT ANSWERS
-------------------------
1. HOW MUCH OF THIS COMPANY IS ACTUALLY FOR SALE, and can a personal position
   get out of it. On IDX the median listing is 68% insider-held; the tail runs
   past 90%. A 9% free float is a different instrument from a 60% one — the
   quoted price is whatever a handful of holders agree it is, a single seller
   moves it, and `microstructure.py`'s turnover floor does not catch it because
   a thin float can still print respectable rupiah volume on a few excited days.

   This is the ONE structural precondition the Indonesian practice of
   bandarmology actually looks for that is obtainable here. See `tape.py` for
   what is not obtainable and why nothing in this codebase may claim to be
   reading a broker summary.

2. IS THE COUNT OF SHARES GOING UP. Net share issuance is among the better
   replicated cross-sectional effects — firms that issue underperform, firms
   that retire outperform — and on IDX it is not a subtlety: rights issues are
   routine and a retail holder who does not subscribe is diluted on a schedule.
   Nothing else in this app would notice a company that doubled its share count
   over three years. Every per-share figure the valuation engine prints would
   quietly absorb it.

WHAT IS DELIBERATELY NOT SCORED
-------------------------------
Institutional ownership is reported and does not vote. "Somebody professional
owns this" is an argument from authority, the institutions in question are
mostly index funds with no view at all, and the coverage is worst exactly where
it would matter most. It renders as context.

References
----------
Pontiff, J., & Woodgate, A. (2008). "Share Issuance and Cross-Sectional
    Returns." Journal of Finance 63(2).
Daniel, K., & Titman, S. (2006). "Market Reactions to Tangible and Intangible
    Information." Journal of Finance 61(4).
McLean, R. D., Pontiff, J., & Watanabe, A. (2009). "Share issuance and
    cross-sectional returns: International evidence." Journal of Financial
    Economics 94(1). (The effect outside the United States.)
Amihud, Y., Mendelson, H., & Uno, J. (1999). "Number of Shareholders and Stock
    Prices." Journal of Finance 54(3). (Float, breadth of ownership and value.)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Free float bands
#
# JUDGEMENT, AND SAID TO BE. Unlike the tape's bands these are not percentiles
# of a measured cross-section, because the question they answer is not "is this
# unusual for its market" but "can one person get out of this position". On IDX
# a low float is entirely ordinary — the median listing is around two-thirds
# insider-held — so a percentile band would call the typical Indonesian company
# unremarkable, which is true and useless. The line is about tradeability.
#
# 8% is where a personal holding starts being a visible share of everything
# available; 20% is where the float stops being the binding constraint and the
# turnover floor takes over.
# --------------------------------------------------------------------------- #
FLOAT_CRITICAL = 0.08
FLOAT_TIGHT = 0.20
FLOAT_COMFORTABLE = 0.40

# Annualised change in share count. Above the first, dilution is material enough
# to name; above the second it is the dominant fact about the holding. A rights
# issue at one-for-four is +25% in a single event, which is why the severe line
# sits where it does rather than at some rounder number.
ISSUANCE_MATERIAL = 0.05
ISSUANCE_SEVERE = 0.25

# Below this many share-count observations there is no trend, only two numbers.
MIN_SHARE_POINTS = 4

# The share-count trend is measured over this many days. Long enough to cover
# more than one reporting cycle, short enough that a rights issue four years ago
# does not describe the company today.
ISSUANCE_WINDOW_DAYS = 1095

# How far each half may move ITS OWN component score from neutral. These are not
# relative weights between the two — `verdict.py` decides that, from evidence
# grades, in the one place that decides it for every component. These say how
# emphatic each half is allowed to be about its own question: issuance can reach
# a near-extreme reading because a company doubling its share count is an
# unambiguous fact, while a float reading saturates earlier because "9% free
# float" is a strong statement about tradeability and a weak one about return.
ISSUANCE_SWING = 32.0
FLOAT_SWING = 18.0


def _share_series(records) -> Optional[pd.Series]:
    """A date-indexed share count from the boundary's dated records.

    Accepts a bare `pd.Series` too, because a caller holding one in-process
    should not have to round-trip it through JSON to be understood. Everything
    that crosses a cache or the wire arrives as records — see
    `market_data._register_uncached` for why the boundary hands them over in
    that shape.
    """
    if isinstance(records, pd.Series):
        series = pd.to_numeric(records, errors="coerce").dropna()
        return series[series > 0].sort_index() if len(series) else None
    if not isinstance(records, list) or not records:
        return None

    dates, counts = [], []
    for entry in records:
        if not isinstance(entry, dict):
            continue
        try:
            stamp = pd.Timestamp(entry.get("date"))
            count = float(entry.get("count"))
        except (TypeError, ValueError):
            continue
        if pd.isna(stamp) or not np.isfinite(count) or count <= 0:
            continue
        dates.append(stamp)
        counts.append(count)
    if not counts:
        return None
    return pd.Series(counts, index=pd.DatetimeIndex(dates)).sort_index()


# Inside this many sessions, a scheduled report is close enough that buying now
# is partly a bet on it. Ten trading days is a fortnight — long enough to be
# worth naming, short enough that it is not true of every name all the time.
EARNINGS_SOON_DAYS = 14


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def earnings_proximity(register: Optional[dict],
                       today: Optional[dt.date] = None) -> dict:
    """How long until the next scheduled report, and whether that is soon.

    CONTEXT, NOT A SCORE AND NOT A GATE. Buying a week before a result is a
    different bet from buying a month after one — the position is partly a wager
    on an announcement nothing in this app has read. But whether that is good or
    bad is not something anybody here has measured, and turning "reports on
    Tuesday" into points would be inventing a direction for a fact that has
    none.

    A provider's scheduled date is also an estimate that moves. `estimated` is
    not distinguishable from `confirmed` in this feed, so the reading says
    "scheduled" and never "will".
    """
    when = (register or {}).get("nextEarnings")
    if not when:
        return {"available": False,
                "reason": "no scheduled reporting date came back for this listing"}
    try:
        date = dt.date.fromisoformat(str(when))
    except (TypeError, ValueError):
        return {"available": False, "reason": f"unreadable reporting date {when!r}"}

    days = (date - (today or dt.date.today())).days
    soon = 0 <= days <= EARNINGS_SOON_DAYS
    return {
        "available": True,
        "date": date.isoformat(),
        "calendarDays": days,
        "soon": soon,
        "scores": False,
        "reading": (
            f"Scheduled to report on {date.isoformat()}, {days} day"
            f"{'' if days == 1 else 's'} away. Buying inside a fortnight of a result "
            f"makes the position partly a bet on that announcement, which nothing here "
            f"has read. Reported as context: whether it is a reason to wait is not "
            f"something this app has measured."
            if soon else
            f"Next scheduled report {date.isoformat()}, {days} days away — far enough "
            f"that today's price is not mostly a wager on it."),
    }


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# ============================================================================ #
# Free float
# ============================================================================ #
def free_float(register: Optional[dict]) -> dict:
    """How much of the company is not held by insiders.

    `insidersPercentHeld` is the provider's figure and it is a blunt one: it
    lumps founders, the state, a parent company and cross-holdings together, and
    it does not know about lock-ups. It is also available for essentially every
    IDX listing, which no better measure is, and the direction of its error is
    consistent — it understates control if anything, because a friendly
    institutional holder counts as float here.
    """
    insiders = _finite((register or {}).get("insidersPercentHeld"))
    if insiders is None or not (0.0 <= insiders < 1.0):
        return {"available": False,
                "reason": "no insider-held share came back for this listing"}

    value = 1.0 - insiders
    band = ("critical" if value < FLOAT_CRITICAL
            else "tight" if value < FLOAT_TIGHT
            else "moderate" if value < FLOAT_COMFORTABLE else "comfortable")

    # PIECEWISE AND SATURATING, NOT LINEAR. The interesting range is entirely
    # below 40%: the difference between a 45% float and a 70% one does not matter
    # to anybody's exit, while the difference between 6% and 18% is the whole
    # question.
    if value >= FLOAT_COMFORTABLE:
        contribution = 1.0
    elif value >= FLOAT_TIGHT:
        contribution = (value - FLOAT_TIGHT) / (FLOAT_COMFORTABLE - FLOAT_TIGHT)
    elif value >= FLOAT_CRITICAL:
        contribution = -1.0 + (value - FLOAT_CRITICAL) / (FLOAT_TIGHT - FLOAT_CRITICAL)
    else:
        contribution = -1.0

    return {
        "available": True,
        "freeFloat": value,
        "insidersHeld": insiders,
        "band": band,
        "score": _clamp(50.0 + contribution * FLOAT_SWING),
        "reading": (
            f"{value * 100:.0f}% of the shares are outside insider hands"
            + {"critical": " — a personal position is a visible share of everything "
                           "for sale, and getting out is not a given",
               "tight": " — thin enough that one seller sets the price",
               "moderate": ", which is an ordinary float",
               "comfortable": ", which is a wide float"}[band] + "."),
        "institutionsHeld": _finite((register or {}).get("institutionsPercentHeld")),
        "institutionsCount": _finite((register or {}).get("institutionsCount")),
    }


def float_turnover(float_shares: Optional[float],
                   median_volume: Optional[float]) -> Optional[float]:
    """What share of the tradeable float changes hands on a typical session.

    The number that separates "large company, thin float" from "large company,
    liquid". Rupiah turnover alone cannot: a name where the same 2% of the
    register trades back and forth every day looks liquid by turnover and is a
    closed loop.
    """
    shares = _finite(float_shares)
    volume = _finite(median_volume)
    if shares is None or volume is None or shares <= 0:
        return None
    return volume / shares


# ============================================================================ #
# Share count
# ============================================================================ #
def issuance(register: Optional[dict],
             window_days: int = ISSUANCE_WINDOW_DAYS) -> dict:
    """The annualised change in shares outstanding, and the biggest single step.

    TWO NUMBERS, BECAUSE ONE HIDES THE THING WORTH SEEING. A company that issued
    30% once and then sat still for two years annualises to about 9%, which
    reads as mild drift; the 30% event is the fact. So the largest single
    period-on-period step is reported alongside the trend, and the caller may
    act on either.

    The series arrives irregularly — filing dates, not a calendar — so the
    annualisation divides by the actual elapsed time rather than assuming
    evenly spaced points.
    """
    clean = _share_series((register or {}).get("shares"))
    if clean is None or len(clean) < MIN_SHARE_POINTS:
        have = 0 if clean is None else len(clean)
        return {"available": False,
                "reason": (f"needs {MIN_SHARE_POINTS} share-count observations to read a "
                           f"trend; this has {have}")}

    try:
        cutoff = clean.index.max() - pd.Timedelta(days=window_days)
        windowed = clean[clean.index >= cutoff]
    except (TypeError, ValueError):
        windowed = clean
    if len(windowed) < MIN_SHARE_POINTS:
        windowed = clean.tail(MIN_SHARE_POINTS)

    first, last = float(windowed.iloc[0]), float(windowed.iloc[-1])
    try:
        years = (windowed.index[-1] - windowed.index[0]).days / 365.25
    except (TypeError, AttributeError):
        years = None
    if not years or years <= 0.25:
        return {"available": False,
                "reason": "the share-count observations do not span enough time"}

    total = last / first - 1.0
    annualised = (last / first) ** (1.0 / years) - 1.0

    # The largest single step, and when. Computed on the windowed series so a
    # rights issue outside the window cannot be reported as current.
    steps = windowed.pct_change().dropna()
    largest = _finite(steps.max()) if len(steps) else None
    largest_at = None
    if largest is not None and largest > 0:
        try:
            largest_at = str(pd.Timestamp(steps.idxmax()).date())
        except (TypeError, ValueError):
            largest_at = None

    band = ("severe" if annualised >= ISSUANCE_SEVERE
            else "material" if annualised >= ISSUANCE_MATERIAL
            else "retiring" if annualised <= -ISSUANCE_MATERIAL
            else "flat")

    # Negative issuance — a buyback — is the good direction, so the sign flips.
    # Saturates at the severe line both ways: a company retiring 25% a year and
    # one retiring 60% are not a distinction this data supports making.
    contribution = -_clamp(annualised / ISSUANCE_SEVERE, -1.0, 1.0)

    if band == "retiring":
        reading = (f"The share count has fallen {abs(annualised) * 100:.0f}% a year over "
                   f"{years:.1f} years.")
    elif band == "flat":
        reading = f"The share count is broadly flat over {years:.1f} years."
    else:
        step = ""
        if largest and largest > 0.05:
            step = (f", the largest single step being +{largest * 100:.0f}%"
                    + (f" around {largest_at}" if largest_at else ""))
        reading = (f"The share count has grown {annualised * 100:.0f}% a year over "
                   f"{years:.1f} years{step} — every per-share figure elsewhere is "
                   f"measured against a moving denominator.")

    return {
        "score": _clamp(50.0 + contribution * ISSUANCE_SWING),
        "reading": reading,
        "available": True,
        "annualised": _finite(annualised),
        "total": _finite(total),
        "years": round(float(years), 2),
        "observations": len(windowed),
        "firstCount": first,
        "latestCount": last,
        "largestStep": largest,
        "largestStepAt": largest_at,
        "band": band,
    }


# ============================================================================ #
# The register reading
# ============================================================================ #
def read(register: Optional[dict], median_volume: Optional[float] = None,
         shares_outstanding: Optional[float] = None) -> dict:
    """Everything the register says about one name, assembled but never blended.

    Returns two independently scored halves — `float` and `issuance` — plus the
    derived quantities that need both, and prose. It deliberately returns NO
    combined score: `verdict.py` weights the two by evidence grade alongside
    every other component, and a blend computed here would either duplicate that
    weighting or quietly contradict it.

    `available: False` only when NEITHER half read. One half is enough, and the
    missing one becomes coverage rather than an imputed 50 — the same
    renormalise-over-what-is-present rule `ranking.py` applies across signals.
    Filling a gap would move a thinly covered name toward the middle of the pack
    and call it a measurement.
    """
    floats = free_float(register)
    issued = issuance(register)

    if not floats["available"] and not issued["available"]:
        return {"available": False,
                "reason": (f"{floats.get('reason', 'no float')}; "
                           f"{issued.get('reason', 'no share count')}")}

    # EACH HALF SCORES ITSELF; NOTHING IS BLENDED HERE. They are separate
    # components in `verdict.py` with different evidence grades — issuance has
    # replicated cross-sectional evidence behind it, float has a liquidity
    # argument — so a blend computed in this module would either duplicate that
    # weighting or quietly contradict it. One place decides how much each is
    # worth, and it is the place that decides it for every other component too.
    notes = [reading for reading in
             (floats.get("reading") if floats["available"] else None,
              issued.get("reading") if issued["available"] else None)
             if reading]

    # THE SHARE COUNT COMES FROM THE REGISTER'S OWN SERIES WHEN THE CALLER DID
    # NOT SUPPLY ONE. The last observation in the share-count history IS shares
    # outstanding, from the same fetch that produced everything else here, so
    # asking `market_data.company` for it again would be a second call for a
    # number already in hand — and in a whole-market scan that second call is
    # per name, past the boundary's cache eviction, and lands as hundreds of
    # extra requests.
    count = _finite(shares_outstanding)
    count_source = "caller"
    if count is None and issued["available"]:
        count = _finite(issued.get("latestCount"))
        count_source = "the share-count history"

    float_shares = None
    if floats["available"] and count:
        float_shares = count * floats["freeFloat"]
    turnover = float_turnover(float_shares, median_volume)

    return {
        "available": True,
        "float": floats,
        "issuance": issued,
        "floatShares": float_shares,
        "sharesOutstanding": count,
        "sharesOutstandingFrom": count_source if count else None,
        "floatTurnover": turnover,
        "daysToTradeFloat": (1.0 / turnover) if turnover and turnover > 0 else None,
        "reading": _reading(notes, floats, issued, turnover),
        # Context that rides along with the register because it came from the
        # same fetch. It scores nothing — see `earnings_proximity`.
        "earnings": earnings_proximity(register),
        # Reported, never scored. See the module docstring for why.
        "institutions": {
            "percentHeld": floats.get("institutionsHeld") if floats["available"] else None,
            "count": floats.get("institutionsCount") if floats["available"] else None,
            "note": ("Reported as context and deliberately not scored: most institutional "
                     "holders of a listed company are index funds with no view on it, and "
                     "'somebody professional owns this' is an argument from authority "
                     "rather than a measurement."),
        },
    }


def _reading(notes: list[str], floats: dict, issued: dict,
             turnover: Optional[float]) -> str:
    if not notes:
        return "Nothing in the share register could be read for this listing."
    text = " ".join(notes)

    if turnover is not None and turnover > 0:
        days = 1.0 / turnover
        # Three decimals under a hundredth of a percent. GOTO.JK, pinned at the
        # Rp 50 tick with its volume collapsed, reads 0.0017% — which rounds to
        # "0.00%" at two places and reads as a missing number rather than as the
        # finding it is.
        share = (f"{turnover * 100:.3f}%" if turnover < 1e-4 else f"{turnover * 100:.2f}%")
        text += (f" A typical session turns over {share} of that float, so the whole "
                 f"tradeable register changes hands about once every {days:,.0f} "
                 f"sessions.")

    gaps = []
    if not floats["available"]:
        gaps.append("the float")
    if not issued["available"]:
        gaps.append("the share-count trend")
    if gaps:
        text += (f" {' and '.join(gaps).capitalize()} could not be read, so this rests on "
                 f"the other half alone.")
    return text
