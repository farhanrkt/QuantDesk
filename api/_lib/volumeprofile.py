"""
volumeprofile.py
================
Where the shares actually changed hands, as distinct from where the price turned.

WHY A SECOND KIND OF LEVEL
---------------------------
Every level in this app comes from one mechanism. `swing.support_resistance`
finds prices the market TURNED at — local extrema of high and low, clustered
within an average daily range — and counts how often each was tested. That is a
good mechanism and it is the only one here, which is the problem.

A full sweep of 251 tradeable Indonesian listings made the cost of that concrete:
six names had no defended floor below the price at all, and forty more had one so
close that `structure.read` now refuses to quote a reward-to-risk ratio against
it. Eighteen percent of a tradeable market, with no measurable answer to "where
is this trade wrong" — not because the information is missing, but because one
estimator was being asked for all of it.

Volume at price is a different question with a different answer. A turning point
is where somebody stopped selling; a volume shelf is where a large number of
positions were actually opened. Those are not the same prices and they do not
fail at the same time. A shelf can sit in the middle of a trend that never turned
there, which is exactly the region a swing-point finder is blind to.

WHAT THIS CAN AND CANNOT SEE, WHICH DECIDES THE WHOLE DESIGN
-------------------------------------------------------------
A real volume profile is built from ticks: every print at the price it happened
at. This app has daily OHLCV and nothing else, so the session's volume has to be
DISTRIBUTED across the session's range by assumption. The assumption here is
uniform — each bar's volume spread evenly from its low to its high — and it is
wrong in a knowable direction: real intraday volume concentrates near the open,
the close and the VWAP rather than spreading flat.

That is stated rather than hidden because it bounds what the output may be used
for. A shelf found this way is a claim that "a lot of trade happened in this
band over the last year", which survives the approximation: spreading a bar's
volume uniformly still puts it in the right band, it just smears it within the
band. What does NOT survive is any claim about a precise price — a point of
control quoted to the rupiah would be false precision, so every level here is
reported as a BAND whose width is the bin width, never as a point.

Triangular and close-weighted distributions were both tried and neither is more
defensible without intraday data to check them against; uniform is the one that
adds no parameter nobody measured.

THE BIN WIDTH IS IN AVERAGE TRUE RANGES, NOT PERCENT OR COUNT
--------------------------------------------------------------
A fixed bin count makes "a shelf" mean something different on every name: fifty
bins across a quiet utility's 15% year are 0.3% wide, and fifty across a
small-cap's 300% year are 6% wide. A fixed percentage has the same problem in
reverse. Bins are `BIN_ATR` of the name's own average true range, the same
scaling `swing.support_resistance` uses for its clustering tolerance and for the
same reason — so that "nearby" and "a lot of volume at one price" mean the same
thing on a utility and on a miner.

WHAT THE MEASUREMENT FOUND: A NULL, AND THE FEATURE IS SCOPED TO IT
--------------------------------------------------------------------
`scripts/calibrate_volume_profile.py` asked the only question that would license
using a shelf as support — does price arriving at a high-volume band hold more
often than price arriving at an ordinary band the same distance away? Across 250
Indonesian listings, six years and 64,969 touches, paired within calendar month:

    0.5-2 ATR below   shelves 69.4%   ordinary 68.0%   +1.5 pts   q = 0.30
    2-5 ATR below     shelves 71.8%   ordinary 69.7%   +2.1 pts   q = 0.30
    5-10 ATR below    shelves 74.3%   ordinary 66.9%   +5.2 pts   q = 0.19

Every bucket leans the same way and NOT ONE survives a false-discovery
correction across the three. The consistent sign is worth very little on its own:
the buckets are drawn from the same names in the same months, so they are closer
to one test repeated than to three.

Two details are worth keeping because they say how fragile this is. The hold rate
rises with distance in BOTH arms — 68% to 67% to 66.9% for the controls is flat,
but the shelf arm climbs — which is the distance confound the bucketing exists to
contain, and it is clearly real. And the nearest bucket, the only one where a
level could function as a stop, came back NEGATIVE at a 60-name sample and
positive at 250. An effect whose sign depends on sample size is not one to build
a stop on.

So the profile is DESCRIPTION. It draws, it reports where the year's trade sat,
and `structure.py` goes on finding its levels exactly as before. The original
motivation for this module — that a sweep found 46 of 251 names with no usable
floor, and volume might supply one — is not supported: measured properly, a
volume shelf is not reliably a floor. (It would have filled 13 of those 46
geometrically, which is a fact about where the bands sit, not about whether they
hold.)

NOTHING HERE SCORES, AND THAT IS A RULE ABOUT EVIDENCE
--------------------------------------------------------
`PRODUCT.md` constraint 2 requires that anything implying a return prediction be
measured offline first. `scripts/calibrate_volume_profile.py` measures what this
module is actually claiming — that price approaching a volume shelf behaves
differently from price approaching an ordinary stretch the same distance away —
and publishes the answer including a null.

Even a positive result licenses using a shelf as a LEVEL, which is what
`structure.py` does with it. It would not license a scoring component, because
"price respects this band" is not the same claim as "this name outperforms", and
this module never makes the second one.

References
----------
Steidlmayer, J. P. & Hawkins, S. (2003). *Steidlmayer on Markets: Trading with
    Market Profile.* The original construct, built from half-hourly brackets
    rather than daily bars; the value-area rule below is theirs.
Easley, D., López de Prado, M., & O'Hara, M. (2012). "Flow Toxicity and
    Liquidity in a High-Frequency World." Review of Financial Studies 25(5).
    (Why a daily bar's volume is not uniformly distributed over its range.)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# The trailing window, in sessions. One year, matching `tape.WINDOW` and
# `ranking.RANK_WINDOW`: two names with identical recent trade must not profile
# differently because one of them listed earlier.
WINDOW = 252

# Below this there is not enough trade to find a shelf in. A quarter of sessions
# is the floor at which a bin holding "a lot of volume" is holding more than a
# handful of days.
MIN_BARS = 120

# Bin width, in average true ranges. A quarter of a day's range: fine enough that
# two shelves a day's move apart stay separate, coarse enough that a bin holds
# several sessions' trade rather than one.
BIN_ATR = 0.25

# Guard rails on the bin count, for the pathological inputs a whole-market sweep
# finds. A name whose range is 200 ATRs wide would otherwise get 800 bins, each
# holding almost nothing; one pinned at its tick floor would get three.
MIN_BINS, MAX_BINS = 20, 200

# The share of the window's volume inside the value area. Steidlmayer's 70%,
# unchanged — it is a convention rather than a measurement, and moving it to a
# rounder number would not make it more true.
VALUE_AREA_SHARE = 0.70

# What makes a bin a shelf: its volume as a multiple of the AVERAGE bin's. Two
# means "twice the trade of an ordinary band at this name's own scale". This is
# the one threshold in the file picked by judgement rather than derived, so
# `calibrate_volume_profile.py` sweeps it and publishes the sensitivity.
SHELF_MULTIPLE = 2.0

# Adjacent qualifying bins are one shelf, not several. Without this a broad
# high-volume region reports as four levels a quarter-ATR apart, which would
# flood `structure.py` with the same fact repeated.
MERGE_ADJACENT = True


_CALIBRATION_PATH = Path(__file__).with_name("volume_profile_calibration.json")
_CALIBRATION_CACHE: Optional[dict] = None
_LOAD_FROM_DISK = object()


def load_calibration() -> dict:
    global _CALIBRATION_CACHE
    if _CALIBRATION_CACHE is None:
        try:
            _CALIBRATION_CACHE = json.loads(_CALIBRATION_PATH.read_text())
        except (OSError, ValueError):
            _CALIBRATION_CACHE = {}
    return _CALIBRATION_CACHE


def calibration_for(market_code: Optional[str],
                    calibration=_LOAD_FROM_DISK) -> Optional[dict]:
    """One market's measurement, or None. Never another market's.

    The same rule `tape` and `patterns` follow: whether a volume shelf behaves
    like a level is a property of the population it was measured on, and IDX and
    the US differ enough elsewhere in this codebase that borrowing would be worse
    than having nothing.
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


def _atr(frame: pd.DataFrame, length: int = 14) -> Optional[float]:
    """Average true range, the same estimator `indicators.atr` uses."""
    high = frame["High"].astype("float64")
    low = frame["Low"].astype("float64")
    close = frame["Close"].astype("float64")
    previous = close.shift(1)
    span = pd.concat([high - low, (high - previous).abs(),
                      (low - previous).abs()], axis=1).max(axis=1)
    return _finite(span.ewm(alpha=1.0 / length, adjust=False).mean().iloc[-1])


def distribute(frame: pd.DataFrame, edges: np.ndarray) -> np.ndarray:
    """Spread each session's volume across the bins its range covers.

    UNIFORM, AND THE ASSUMPTION IS THE MODULE'S MAIN LIMITATION — see the
    docstring. A bar spanning four bins puts a quarter of its volume in each.

    The overlap arithmetic is deliberately exact rather than "assign the bar to
    the bin holding its midpoint": a name that trends through a year in wide
    daily ranges would otherwise concentrate its whole profile onto the handful
    of midpoints, inventing shelves out of the binning.
    """
    lows = frame["Low"].to_numpy(dtype="float64")
    highs = frame["High"].to_numpy(dtype="float64")
    volumes = frame["Volume"].to_numpy(dtype="float64")

    totals = np.zeros(len(edges) - 1, dtype="float64")
    for low, high, volume in zip(lows, highs, volumes, strict=True):
        if not np.isfinite(volume) or volume <= 0:
            continue
        if not (np.isfinite(low) and np.isfinite(high)) or high < low:
            continue
        if high == low:
            # A locked session — limit up, or a halt that printed once. All of
            # it belongs to the single bin containing that price.
            index = int(np.clip(np.searchsorted(edges, low, side="right") - 1,
                                0, len(totals) - 1))
            totals[index] += volume
            continue
        # Overlap of [low, high] with each bin, as a share of the bar's range.
        left = np.clip(edges[:-1], low, high)
        right = np.clip(edges[1:], low, high)
        overlap = np.maximum(right - left, 0.0)
        span = overlap.sum()
        if span > 0:
            totals += volume * overlap / span
    return totals


def build(frame: Optional[pd.DataFrame], window: int = WINDOW,
          bin_atr: float = BIN_ATR,
          shelf_multiple: float = SHELF_MULTIPLE,
          market_code: Optional[str] = None,
          calibration=_LOAD_FROM_DISK) -> dict:
    """The volume profile of the trailing window, as bands rather than prices.

    `usable` says whether this market's measurement licensed reading a shelf as
    a level. It is read by anything that would treat one as support, and it is
    false until `scripts/calibrate_volume_profile.py` has said otherwise.
    """
    if frame is None or len(frame) < MIN_BARS:
        have = 0 if frame is None else len(frame)
        return {"available": False,
                "reason": (f"needs {MIN_BARS} sessions to profile a year of trade; "
                           f"this has {have}")}

    recent = frame.tail(window)
    volume = recent["Volume"].astype("float64")
    if not np.isfinite(float(volume.sum())) or float(volume.sum()) <= 0:
        return {"available": False, "reason": "no volume was reported in this window"}

    low = _finite(recent["Low"].min())
    high = _finite(recent["High"].max())
    price = _finite(recent["Close"].iloc[-1])
    atr = _atr(recent)
    if None in (low, high, price) or high <= low or price <= 0:
        return {"available": False,
                "reason": "the price range in this window is flat or unusable"}
    if not atr or atr <= 0:
        return {"available": False, "reason": "no usable average true range"}

    width = max(atr * bin_atr, (high - low) / MAX_BINS)
    count = int(np.clip(round((high - low) / width), MIN_BINS, MAX_BINS))
    edges = np.linspace(low, high, count + 1)
    width = float(edges[1] - edges[0])

    row = calibration_for(market_code, calibration)
    totals = distribute(recent, edges)
    grand = float(totals.sum())
    if grand <= 0:
        return {"available": False, "reason": "no volume fell inside the price range"}

    centres = (edges[:-1] + edges[1:]) / 2.0
    shares = totals / grand
    poc = int(np.argmax(totals))

    # VALUE AREA, Steidlmayer's rule: start at the point of control and take
    # whichever neighbour holds more volume until 70% is enclosed. Expanding
    # symmetrically instead would centre the area on the POC by construction and
    # hide a profile that is genuinely lopsided, which is the common case in a
    # trending name.
    lower, upper = poc, poc
    enclosed = shares[poc]
    while enclosed < VALUE_AREA_SHARE and (lower > 0 or upper < len(totals) - 1):
        below = shares[lower - 1] if lower > 0 else -1.0
        above = shares[upper + 1] if upper < len(totals) - 1 else -1.0
        if above >= below:
            upper += 1
            enclosed += shares[upper]
        else:
            lower -= 1
            enclosed += shares[lower]

    shelves = _shelves(totals, shares, edges, centres, shelf_multiple, price, atr)

    return {
        "available": True,
        "sessions": len(recent),
        "price": price,
        "atr": atr,
        "binWidth": width,
        "binWidthAtr": width / atr,
        "bins": count,
        # THE HISTOGRAM ITSELF, so the chart can draw what the levels were read
        # off rather than only the conclusions.
        "profile": [{"low": float(edges[i]), "high": float(edges[i + 1]),
                     "mid": float(centres[i]), "share": float(shares[i])}
                    for i in range(count)],
        # EVERY LEVEL IS A BAND. A point of control quoted to the rupiah would be
        # false precision on a profile built by spreading daily bars — see the
        # docstring's note on what the approximation does and does not survive.
        "pointOfControl": {"low": float(edges[poc]), "high": float(edges[poc + 1]),
                           "mid": float(centres[poc]), "share": float(shares[poc])},
        "valueArea": {"low": float(edges[lower]), "high": float(edges[upper + 1]),
                      "share": float(enclosed)},
        "insideValueArea": bool(edges[lower] <= price <= edges[upper + 1]),
        "shelves": shelves,
        "shelfMultiple": shelf_multiple,
        # WHAT THE MEASUREMENT SAID, travelling with every profile so no caller
        # can read a shelf as support without having been handed the verdict on
        # whether it is one.
        "market": (market_code or "").upper() or None,
        "calibrated": bool(row),
        "measuredOn": (row or {}).get("measuredOn"),
        "usable": bool((row or {}).get("usable")),
        "calibrationReading": (row or {}).get("reading"),
        "reading": _reading(price, shelves, edges, poc, centres, enclosed,
                            bool(edges[lower] <= price <= edges[upper + 1]), row),
    }


def _shelves(totals: np.ndarray, shares: np.ndarray, edges: np.ndarray,
             centres: np.ndarray, multiple: float, price: float,
             atr: float) -> list[dict]:
    """Contiguous runs of bins holding more than `multiple` of average trade.

    MERGED, because a broad high-volume region is one fact. Reporting each
    quarter-ATR slice of it separately would hand `structure.py` four levels a
    hair apart and let the same shelf be counted four times.
    """
    average = float(totals.mean())
    if average <= 0:
        return []
    qualifying = totals >= multiple * average

    out: list[dict] = []
    index = 0
    while index < len(qualifying):
        if not qualifying[index]:
            index += 1
            continue
        start = index
        while index + 1 < len(qualifying) and (MERGE_ADJACENT and qualifying[index + 1]):
            index += 1
        end = index
        low_edge, high_edge = float(edges[start]), float(edges[end + 1])
        mid = (low_edge + high_edge) / 2.0
        out.append({
            "low": low_edge, "high": high_edge, "mid": mid,
            "share": float(shares[start:end + 1].sum()),
            "bins": end - start + 1,
            "peakMultiple": float(totals[start:end + 1].max() / average),
            # Which side of today's price it sits on, and how far, in this
            # name's own daily ranges — the unit every distance in the entry
            # logic is already expressed in.
            "side": ("below" if high_edge < price
                     else "above" if low_edge > price else "here"),
            "distanceAtr": (0.0 if low_edge <= price <= high_edge
                            else float((mid - price) / atr)),
            "distancePct": float(mid / price - 1.0),
        })
        index += 1
    return sorted(out, key=lambda shelf: shelf["mid"])


def _reading(price: float, shelves: list[dict], edges: np.ndarray, poc: int,
             centres: np.ndarray, enclosed: float, inside: bool,
             row: Optional[dict] = None) -> str:
    control = (f"Most of the last year's trade happened between "
               f"{edges[poc]:,.0f} and {edges[poc + 1]:,.0f}. ")
    where = ("The price is inside the band that holds 70% of it. " if inside
             else "The price is outside the band that holds 70% of it. ")

    # THE STATUS OF THE CLAIM TRAVELS WITH THE CLAIM, ON EVERY PATH. This was
    # built as a tail appended to the shelf sentence, so the early return for a
    # profile with NO shelves skipped it — and those are exactly the names where
    # a reader is most likely to go looking at the bands themselves instead.
    # Naming a shelf without saying whether shelves were shown to hold is how a
    # description becomes a recommendation between one reader and the next.
    if row is None:
        status = (" Whether a shelf holds better than an ordinary band has not been "
                  "measured on this market, so nothing here is read as support.")
    elif row.get("usable"):
        status = (" Measured on this market, a shelf does hold more often than an "
                  "ordinary band at the same distance.")
    else:
        status = (" Measured on this market, a shelf does NOT hold reliably better than "
                  "an ordinary band at the same distance, so none of this is read as "
                  "support — it is a description of where trade happened.")

    below = [s for s in shelves if s["side"] == "below"]
    above = [s for s in shelves if s["side"] == "above"]
    parts = []
    if below:
        nearest = below[-1]
        parts.append(f"the nearest shelf beneath is {nearest['low']:,.0f}-"
                     f"{nearest['high']:,.0f}, holding {nearest['share'] * 100:.0f}% "
                     f"of the year's volume")
    if above:
        nearest = above[0]
        parts.append(f"the nearest above is {nearest['low']:,.0f}-"
                     f"{nearest['high']:,.0f} at {nearest['share'] * 100:.0f}%")
    if not parts:
        return (control + where + "No band stands out as carrying unusual trade, which "
                "is a profile with no shelves rather than a profile nobody looked at."
                + status)


    return (control + where + "Of the bands carrying unusual trade, " + " and ".join(parts)
            + ". These are where positions were opened, not where the price turned — a "
              "different question from the swing levels, and they fail at different "
              "times." + status)
