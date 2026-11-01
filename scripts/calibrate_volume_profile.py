#!/usr/bin/env python3
"""
calibrate_volume_profile.py
===========================
Does a volume shelf behave like a level, or does any price behave like a level?

    python scripts/calibrate_volume_profile.py
    python scripts/calibrate_volume_profile.py --market ID --sample 250 --years 6

DELIBERATELY OUTSIDE CI, like the other network scripts here, and stamped with
the date it ran.

WHAT THIS DECIDES
-----------------
Whether `structure.py` is allowed to read a volume shelf as support at all.
`volumeprofile.py` will happily report shelves on any name with a year of
history; the question this script exists to settle is whether price arriving at
one of those bands does anything different from price arriving at an ordinary
stretch of chart the same distance away.

THE NULL IS THE HARD PART AND IT IS THE WHOLE SCRIPT
-----------------------------------------------------
This codebase has now been caught three separate times testing a signal against
a baseline that was not the right one — the tape lift against zero when the
market's own median was +0.08, the chart formations against zero when the
unconditional 63-day excess was +13.4%, and nearly the concentration claim. Each
time the wrong null produced a large, confident, wrong result.

The wrong null here is obvious and tempting: measure how often price holds at a
volume shelf, find it is 60-something percent, and report that shelves work.
They would come back 60-something percent because PRICES MOSTLY DO NOT CRASH
THROUGH WHATEVER THEY TOUCH — the base rate of "held" over any short horizon is
high at every price, shelf or not.

So the comparison is against LOW-volume bands on the SAME names, approached from
the same side, matched into distance buckets. A bin holding less than half the
average band's volume is the control; a bin holding at least `SHELF_MULTIPLE` of
it is the treatment. If shelves are levels, the treatment holds more often than
the control WITHIN a distance bucket. If they are not, the two rates sit on top
of each other and this module goes no further than drawing a histogram.

WHY THE BUCKETS ARE NECESSARY RATHER THAN FUSSY
------------------------------------------------
Distance is confounded with volume by construction. A band close to the current
price is close to where trade has recently happened, so it tends to hold more
volume; it is also more likely to be touched and — over a fixed horizon — more
likely to be held simply because price has not travelled far. Pooling across
distances would let that confound masquerade as the effect. Everything below is
reported per bucket and pooled only with bucket weights.

NO LOOK-AHEAD
-------------
The profile at date t is built from the 252 sessions ENDING at t. The touch is
searched for strictly after t. The outcome is read `HOLD_HORIZON` sessions after
the touch. Nothing at t uses a price from after t.

OBSERVATIONS ARE COLLAPSED BY CALENDAR MONTH, for the reason `calibrate_patterns`
collapses them: bands on correlated names get touched together in a selloff, and
counting each as an independent observation would turn one market episode into
several hundred, shrinking every standard error by a factor nobody earned.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as stats_module

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from _lib import artifacts, eventstudy, listings, market_data, universes, volumeprofile

ARTIFACT = Path(__file__).resolve().parents[1] / "api" / "_lib" / "volume_profile_calibration.json"

# How often a profile is taken. Monthly: a profile rebuilt daily is 95% the same
# object as yesterday's, and the touches it finds would be the same touches.
SAMPLE_EVERY = 21

# How long a band is given to be touched after the profile that found it.
TOUCH_WINDOW = 63

# How long after the touch the outcome is read.
HOLD_HORIZON = 21

# What counts as a break rather than a hold: closing this far below the band's
# LOW edge. Requiring a clean break rather than a single close below the top
# keeps a bar that dips into the band and recovers from counting as a failure.
BREAK_ATR = 0.5

# The control: bins holding at most this multiple of the average band's volume.
# Deliberately well clear of the treatment's 2.0 so the two groups are not
# neighbours on a continuum.
CONTROL_MULTIPLE = 0.5

# Distance buckets, in average true ranges below the price at profile time.
BUCKETS = [(0.5, 2.0), (2.0, 5.0), (5.0, 10.0)]

# Below this many collapsed monthly observations in a bucket, no rate is quoted.
MIN_MONTHS = 24

# The false-discovery bar, across the three distance buckets. Matching
# `calibrate_patterns.ALPHA`, and applied for the same reason: three buckets
# drawn from the same names in the same months are three correlated tests, and
# "the sign came out positive in all three" is close to worthless as evidence
# because the three are nearly the same test.
#
# THIS BAR WAS ADDED AFTER THE FIRST RUN PASSED WITHOUT IT. The original
# `usable` flag asked only that the pooled difference be positive and the sign
# consistent, which it was — while no individual bucket reached p < 0.30, 0.27
# and 0.064 respectively. A criterion that admits a result no test supports is
# not a criterion.
ALPHA = 0.10

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


def bucket_of(distance_atr: float):
    for low, high in BUCKETS:
        if low <= distance_atr < high:
            return f"{low:g}-{high:g}"
    return None


def events_for(frame: pd.DataFrame) -> list[dict]:
    """Every band-touch this name offers, with its volume class and outcome."""
    if frame is None or len(frame) < volumeprofile.WINDOW + TOUCH_WINDOW + HOLD_HORIZON:
        return []

    lows = frame["Low"].to_numpy(dtype="float64")
    closes = frame["Close"].to_numpy(dtype="float64")
    index = frame.index
    out: list[dict] = []

    start = volumeprofile.WINDOW
    for cursor in range(start, len(frame) - TOUCH_WINDOW - HOLD_HORIZON, SAMPLE_EVERY):
        window = frame.iloc[cursor - volumeprofile.WINDOW:cursor]
        profile = volumeprofile.build(window)
        if not profile["available"]:
            continue
        price, atr = profile["price"], profile["atr"]
        if not atr or atr <= 0:
            continue

        totals = np.array([b["share"] for b in profile["profile"]], dtype="float64")
        average = float(totals.mean())
        if average <= 0:
            continue

        for band, share in zip(profile["profile"], totals, strict=True):
            if band["high"] >= price:
                continue
            multiple = share / average
            if multiple >= volumeprofile.SHELF_MULTIPLE:
                group = "shelf"
            elif multiple <= CONTROL_MULTIPLE:
                group = "control"
            else:
                continue

            distance = (price - band["high"]) / atr
            bucket = bucket_of(distance)
            if bucket is None:
                continue

            # THE TOUCH: the first session after the profile whose low enters
            # the band. Searched strictly forward of `cursor`.
            forward_low = lows[cursor:cursor + TOUCH_WINDOW]
            hits = np.nonzero(forward_low <= band["high"])[0]
            if len(hits) == 0:
                continue
            touch = cursor + int(hits[0])
            if touch + HOLD_HORIZON >= len(closes):
                continue

            after = closes[touch + HOLD_HORIZON]
            held = bool(after > band["low"] - BREAK_ATR * atr)
            out.append({
                "month": index[touch].strftime("%Y-%m"),
                "group": group, "bucket": bucket, "held": held,
                "multiple": float(multiple), "distanceAtr": float(distance),
            })
    return out


def collapse(events: list[dict]) -> tuple[dict, dict]:
    """Hold rates per (group, bucket), and the PAIRED monthly differences.

    THE MONTH IS THE UNIT OF OBSERVATION, not the touch. Bands across correlated
    names get touched in the same week, and treating each as independent is how
    a single selloff becomes four hundred data points.

    THE TEST IS PAIRED WITHIN A MONTH, which matters more than it looks. Hold
    rates swing enormously with the market — in a month the index falls 8%,
    everything breaks, shelf and control alike — so an unpaired comparison
    spends most of its variance on market direction that affects both arms
    equally. Differencing inside the month removes it, and what is left is the
    only quantity the study is about.
    """
    monthly: dict = defaultdict(list)
    for event in events:
        monthly[(event["group"], event["bucket"], event["month"])].append(event["held"])

    rates = {key: float(np.mean(held)) for key, held in monthly.items()}
    counts = {key: len(held) for key, held in monthly.items()}

    per_group: dict = defaultdict(list)
    for (group, bucket, _month), rate in rates.items():
        per_group[(group, bucket)].append(rate)

    out: dict = {}
    for (group, bucket), values in per_group.items():
        arr = np.array(values, dtype="float64")
        out[(group, bucket)] = {
            "months": len(arr),
            "holdRate": float(arr.mean()),
            "sd": float(arr.std(ddof=1)) if len(arr) > 1 else None,
        }

    # One difference per month in which BOTH arms were touched at that distance.
    paired: dict = defaultdict(list)
    for (group, bucket, month) in list(rates):
        if group != "shelf":
            continue
        control = rates.get(("control", bucket, month))
        if control is None:
            continue
        # Months where either arm rests on a handful of touches are dropped: a
        # rate of 1.0 from two touches is not a month's evidence.
        if counts[("shelf", bucket, month)] < 5 or counts[("control", bucket, month)] < 5:
            continue
        paired[bucket].append(rates[("shelf", bucket, month)] - control)
    return out, dict(paired)


def measure(market: str, sample: int, years: int, quiet: bool = False) -> dict:
    picked, label = symbols_for(market, sample)
    say = (lambda *a: None) if quiet else (lambda *a: print(*a, flush=True))
    say(f"{market}: {len(picked)} names from {label}")

    end = dt.date.today()
    start = end - dt.timedelta(days=int(365.25 * years) + 400)
    frames = market_data.ohlcv_batch(picked, start, end)
    say(f"  {len(frames)} price histories returned")

    events: list[dict] = []
    for position, (symbol, frame) in enumerate(frames.items(), 1):
        try:
            events.extend(events_for(frame))
        except Exception as exc:
            say(f"  {symbol}: {type(exc).__name__}: {exc}")
        if position % 25 == 0:
            say(f"  [{position}/{len(frames)}] {len(events)} touches so far")

    say(f"  {len(events)} touches total")
    stats, paired = collapse(events)

    buckets = []
    for low, high in BUCKETS:
        key = f"{low:g}-{high:g}"
        shelf = stats.get(("shelf", key))
        control = stats.get(("control", key))
        row = {
            "bucket": key, "lowAtr": low, "highAtr": high,
            "shelf": shelf, "control": control, "difference": None,
            "usable": False,
        }
        differences = np.array(paired.get(key, []), dtype="float64")
        if (shelf and control and shelf["months"] >= MIN_MONTHS
                and control["months"] >= MIN_MONTHS and len(differences) >= MIN_MONTHS):
            row["difference"] = float(differences.mean())
            row["pairedMonths"] = len(differences)
            # A one-sample t on the monthly paired differences. Two-sided: a
            # shelf that holds LESS often than an ordinary band is a result too,
            # and the nearest bucket is where that turned out to matter.
            statistic, p_value = stats_module.ttest_1samp(differences, 0.0)
            row["tStat"] = float(statistic)
            row["pValue"] = float(p_value)
            row["significant"] = bool(p_value < 0.05)
            row["usable"] = True
        buckets.append(row)

    # THE CORRECTION, ACROSS THE THREE BUCKETS AT ONCE.
    tested = [b for b in buckets if b["usable"]]
    if tested:
        correction = eventstudy.benjamini_hochberg(
            [b["pValue"] for b in tested], alpha=ALPHA)
        for row, q, rejected in zip(tested, correction["qValues"],
                                    correction["rejected"], strict=True):
            row["qValue"] = float(q)
            row["survived"] = bool(rejected)

    usable = tested
    # THE POOLED FIGURE IS A WEIGHTED MEAN OF BUCKET DIFFERENCES, never a
    # difference of pooled rates — the latter would let the distance confound
    # back in through the door this design closed.
    pooled = None
    if usable:
        weights = np.array([min(b["shelf"]["months"], b["control"]["months"])
                            for b in usable], dtype="float64")
        diffs = np.array([b["difference"] for b in usable], dtype="float64")
        pooled = float((diffs * weights).sum() / weights.sum())

    return {
        "market": market, "population": label, "names": len(frames),
        "measuredOn": end.isoformat(), "years": years,
        "touches": len(events),
        "sampleEvery": SAMPLE_EVERY, "touchWindow": TOUCH_WINDOW,
        "holdHorizon": HOLD_HORIZON, "breakAtr": BREAK_ATR,
        "shelfMultiple": volumeprofile.SHELF_MULTIPLE,
        "controlMultiple": CONTROL_MULTIPLE,
        "minMonths": MIN_MONTHS,
        "buckets": buckets,
        "pooledDifference": pooled,
        # THE VERDICT THIS SCRIPT EXISTS TO RETURN. `structure.py` reads this and
        # nothing else: a shelf is usable as a level only where the measurement
        # says it behaves differently from an ordinary band.
        "alpha": ALPHA,
        # A SHELF IS A LEVEL ONLY IF SOME BUCKET ACTUALLY SURVIVED. Sign
        # agreement across three correlated buckets is not a test and must not
        # be allowed to act like one.
        "usable": bool(usable and any(b.get("survived") for b in usable)
                       and pooled is not None and pooled > 0),
        "survivors": [b["bucket"] for b in usable if b.get("survived")],
        "reading": _reading(buckets, pooled),
    }


def _reading(buckets: list[dict], pooled: float | None) -> str:
    usable = [b for b in buckets if b["usable"]]
    if not usable:
        return ("No distance bucket cleared the minimum number of separate months, so "
                "nothing is claimed either way. That is a sample too small to test on, "
                "not evidence that shelves do not work.")

    parts = []
    for row in usable:
        parts.append(
            f"{row['bucket']} ATR below: shelves held {row['shelf']['holdRate'] * 100:.0f}% "
            f"against {row['control']['holdRate'] * 100:.0f}% for ordinary bands "
            f"({row['difference'] * 100:+.1f} points paired, p={row['pValue']:.3f}, "
            f"q={row.get('qValue', float('nan')):.3f}, {row['pairedMonths']} months)")

    head = "; ".join(parts) + ". "
    survivors = [b for b in usable if b.get("survived")]
    if survivors and pooled is not None and pooled > 0:
        names = " and ".join(b["bucket"] for b in survivors)
        return (head + f"Weighted across buckets a shelf holds {pooled * 100:+.1f} points "
                f"more often than an ordinary band at the same distance, and the "
                f"{names} ATR bucket survives a false-discovery correction across the "
                f"three. That licenses reading a shelf as a level — and nothing more: "
                f"'price respects this band' is not 'this name outperforms', and no "
                f"score is derived from it.")

    direction = ("and every bucket leans the same way, "
                 if all(b["difference"] > 0 for b in usable) else "")
    return (head + f"Weighted across buckets the difference is "
            f"{pooled * 100:+.1f} points {direction}but no bucket survives a "
            f"false-discovery correction across the three — and the buckets share names "
            f"and months, so a consistent sign across them is close to one result "
            f"repeated rather than three. A shelf is therefore DRAWN but is not read as "
            f"support: the histogram is a description of where trade happened, and "
            f"`structure.py` goes on finding its levels the way it always has.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", action="append", default=None, choices=["ID", "US"])
    parser.add_argument("--sample", type=int, default=250)
    parser.add_argument("--years", type=int, default=6)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    markets = args.market or ["ID"]
    payload = {"measuredOn": dt.date.today().isoformat(), "markets": {}}
    for market in markets:
        payload["markets"][market] = measure(market, args.sample, args.years,
                                             quiet=args.quiet)
        if not args.quiet:
            print("\n" + payload["markets"][market]["reading"] + "\n")

    # MERGED, NOT OVERWRITTEN. Running this for one market used to delete
    # every other market's measurement — see `_lib/artifacts` for the day that
    # happened and what it cost.
    merged = artifacts.write_markets(ARTIFACT, payload)
    print(f"wrote {ARTIFACT} — {artifacts.note(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
