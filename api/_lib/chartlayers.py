"""
chartlayers.py
==============
The analysis, on the chart, where it can be checked.

WHY THIS MODULE EXISTS
-----------------------
Everything the private scanner knows about a name's tape was, until this file,
available only as prose. `structure.py` finds the level a stop belongs under and
reports it as a number in a sentence. `patterns.py` fits a kernel regression,
takes its turning points and announces that an inverse head-and-shoulders
completed on a date. `tape.py` runs a Welch test on the heaviest fifth of a
year's sessions and says they closed high in their range.

Every one of those is a claim about a SHAPE, and a shape is the one kind of
claim a reader can falsify at a glance and cannot evaluate at all from a
sentence. "Its fifty heaviest sessions closed 0.31 higher in their range than
ordinary ones" is a fact about a distribution; whether that fact is one
index-rebalance print and forty-nine nothings is visible on a chart and
invisible in a mean. A panel that reports the mean and withholds the sessions is
asking to be believed rather than read.

So this module turns readings that already exist into geometry. It computes no
new analysis and makes no new judgement: every level, every pattern, every heavy
session here was decided by the module that owns it, and `build` only says where
to draw it.

THE THREE WAYS AN ANNOTATED CHART LIES, AND WHAT IS DONE ABOUT EACH
--------------------------------------------------------------------
1. **IT DRAWS A CURVE NOBODY COULD HAVE SEEN.** The obvious implementation
   smooths the whole price series once and plots it. That curve is fitted with a
   two-sided kernel, so its shape at any past date is built partly out of prices
   from after that date — and a pattern traced on it was partly drawn by the
   returns it is about to be credited with predicting. `patterns.geometry`
   refits each detection on the same trailing window at the same bandwidth
   ending on the same bar, so the drawn curve is the one the detector had.

2. **IT PROJECTS A TARGET.** Every chart-pattern convention ends with a measured
   move: take the height of the head, project it from the neckline, draw an
   arrow. It is the most satisfying thing on the chart and this module refuses
   to draw it, because `scripts/calibrate_patterns.py` measured these formations
   on this market and found that the textbook direction carries no information —
   a head-and-shoulders and its bullish mirror image predicted the same thing,
   and both predicted underperformance. A target arrow would put a claim on the
   chart that the app's own measurement declined to support. What is attached
   instead is the measured excess return, labelled as measured, with the
   textbook bias carried beside it and labelled as textbook.

3. **IT MAKES EVERY LINE LOOK EQUALLY REAL.** A 200-day average, a support level
   touched three times, and a pattern that survived a false-discovery correction
   are three completely different grades of evidence drawn in the same ink. So
   every layer ships with its own one-line note saying what it is and what it is
   not, and `legend` is part of the payload rather than a frontend decoration —
   a client cannot render the drawing without having been handed the caveats.

WHAT IS DRAWN THAT IS NOT OTHERWISE VISIBLE ANYWHERE IN THIS APP
-----------------------------------------------------------------
  * The five extrema of each detected formation, at the CLOSES the inequalities
    were evaluated on, not at the smoothed values they turned on.
  * Which sessions the tape test counted as heavy, and where each one closed in
    its own range.
  * The stop, the entry and the first ceiling as one shape, so the reward-risk
    ratio in `structure.read` is a picture rather than a quotient.
  * Level touch counts. A level defended four times and a level defended twice
    are drawn the same way everywhere else in this app.

PRIVATE SURFACE ONLY
---------------------
`PRODUCT.md` constraint 5 scopes multi-bar patterns to the scanner and states
that the published single-company view is unchanged. This module is reachable
from `GET /api/verdict` and nowhere else; the technical panel's chart is
untouched.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from . import indicators as ind
from . import patterns, structure, tape

# How many sessions the annotated chart covers. Nine months, and the number is
# not free: a pattern reported inside `patterns.read`'s 63-session lookback can
# begin `WINDOW` bars earlier still, so anything under about 100 sessions would
# clip the left-hand half of a detection that the panel below it describes in
# full. Past roughly 200 the candles are narrower than the level lines and the
# drawing stops being readable at the width a browser gives it.
PLOT_SESSIONS = 180

# Averages drawn over the price. Deliberately the same three the technical panel
# already uses — a reader who has both open must not find the 50-day in one
# place disagreeing with the 50-day in the other.
FAST_MA, MID_MA, SLOW_MA = 20, 50, 200

# The trailing window the high and low water marks are taken over. A year,
# matching `tape.WINDOW` and `ranking.RANK_WINDOW`.
EXTREME_WINDOW = 252


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _series(frame: pd.DataFrame) -> dict:
    """Every overlay, computed on the FULL history and trimmed afterwards.

    THE ORDER MATTERS AND IT IS THE ONE BUG THIS FUNCTION EXISTS TO PREVENT. A
    200-day average computed on a 180-bar plot window is empty for its first 200
    bars, which is to say all of them, and the line silently disappears. Every
    average here is computed against everything available and only then cut to
    the window, so a nine-month chart still carries a 200-day line drawn from
    the eighteen months behind it.
    """
    close = frame["Close"].astype("float64")
    # LOWER, MIDDLE, UPPER — and getting this backwards is invisible. An
    # earlier version unpacked it the other way round and produced a chart whose
    # "upper" band ran below the price and whose "lower" band ran above it. The
    # shaded region still bracketed the price, still narrowed in quiet stretches
    # and still flared around the selloff, so it looked entirely correct; it was
    # only caught by printing one bar and noticing bbUpper 2571 under bbLower
    # 2650. `swing.py` unpacks it correctly and is the reference.
    lower, middle, upper = ind.bollinger_bands(close)
    return {
        "sma20": ind.sma(close, FAST_MA),
        "sma50": ind.sma(close, MID_MA),
        "sma200": ind.sma(close, SLOW_MA),
        "bbUpper": upper,
        "bbMid": middle,
        "bbLower": lower,
    }


def _levels(resolved: Optional[dict], site: Optional[dict]) -> list[dict]:
    """Defended levels, nearest-first within each side, each carrying its touches.

    `nearest` marks the two levels `structure.read` actually measured the trade
    against. Without it a chart with eight lines on it invites the reader to
    pick their own stop and then compare it against a reward-risk ratio computed
    from a different one.
    """
    if not isinstance(resolved, dict) or not resolved.get("usable"):
        return []

    support = (site or {}).get("support")
    resistance = (site or {}).get("resistance")
    out = []
    for key, side in (("supports", "support"), ("resistances", "resistance")):
        for level in resolved.get(key) or []:
            price = _finite(level.get("price"))
            if price is None:
                continue
            anchor = support if side == "support" else resistance
            out.append({
                "price": price,
                "side": side,
                "touches": int(level.get("touches") or 0),
                "distancePct": _finite(level.get("distancePct")),
                "nearest": anchor is not None and abs(price - float(anchor)) < 1e-9,
            })
    return sorted(out, key=lambda row: row["price"])


def _trade(site: Optional[dict]) -> Optional[dict]:
    """The entry, the stop and the first ceiling as one drawable shape.

    Returns None rather than a partial shape when `structure.read` refused. A
    reward-risk band drawn with a missing side is a picture of a trade nobody
    measured.
    """
    if not isinstance(site, dict) or not site.get("available"):
        return None
    price = _finite(site.get("price"))
    if price is None:
        return None
    return {
        "entry": price,
        "stop": _finite(site.get("support")),
        "target": _finite(site.get("resistance")),
        "riskPct": _finite(site.get("riskToSupport")),
        "rewardPct": _finite(site.get("rewardToResistance")),
        "rewardRisk": _finite(site.get("rewardRisk")),
        "ratioWithheld": bool(site.get("ratioWithheld")),
        "band": site.get("band"),
        "unboundedUpside": bool(site.get("unboundedUpside")),
        "noSupport": bool(site.get("noSupport")),
        "atr": _finite(site.get("atr")),
        # How close counts as "at" a level, in price. `structure.AT_LEVEL_ATR`
        # decides the flags; drawing the same tolerance is what makes "it is at
        # resistance" checkable rather than assertable.
        "levelTolerance": (structure.AT_LEVEL_ATR * _finite(site.get("atr"))
                           if _finite(site.get("atr")) else None),
        "horizon": site.get("horizon"),
    }


def _patterns(frame: pd.DataFrame, found: Optional[dict],
              first_index: int) -> list[dict]:
    """Each detection as a curve, five points and its construction lines.

    `first_index` is where the plot window starts in the full frame. A detection
    whose window begins before it is dropped rather than clipped: half a
    head-and-shoulders is not a head-and-shoulders, and drawing one would invite
    the reader to disagree with a classification they cannot see.
    """
    if not isinstance(found, dict) or not found.get("available"):
        return []

    prices = frame["Close"].astype("float64").to_numpy(dtype="float64")
    index = frame.index
    bandwidth = _finite(found.get("bandwidth"))
    if bandwidth is None or bandwidth <= 0:
        return []

    def stamp(position: int) -> Optional[str]:
        if 0 <= position < len(index):
            return index[position].strftime("%Y-%m-%d")
        return None

    out = []
    for detection in found.get("detections") or []:
        shape = patterns.geometry(prices, detection, bandwidth,
                                  window=int(found.get("window") or patterns.WINDOW))
        if shape is None or shape["startIndex"] < first_index:
            continue

        points = [{**point, "date": stamp(point["index"])}
                  for point in shape["points"]]
        lines = []
        for guide in patterns.guides(shape["points"], detection.get("pattern")):
            lines.append({
                **guide,
                "from": {**guide["from"], "date": stamp(guide["from"]["index"])},
                "to": {**guide["to"], "date": stamp(guide["to"]["index"])},
            })

        forward = detection.get("forward") or {}
        out.append({
            "pattern": detection.get("pattern"),
            "label": detection.get("label"),
            "completedAt": detection.get("completedAt"),
            "detectedAt": detection.get("detectedAt"),
            "fromDate": stamp(shape["startIndex"]),
            "toDate": stamp(shape["endIndex"]),
            "path": [{"date": stamp(node["index"]), "price": node["price"]}
                     for node in shape["path"]],
            "points": points,
            "guides": lines,
            # THE TWO DIRECTIONS, NEVER MERGED. `textbookBias` is what the chart
            # books say the shape means and it is the claim the measurement
            # declined; `measuredExcess` is what this formation actually did on
            # this market, over the horizon it was measured at. A reader must be
            # able to see that they disagree.
            "textbookBias": detection.get("bias"),
            "significant": bool(detection.get("significant")),
            "measuredExcess": _finite(forward.get("meanExcess")),
            "measuredHorizon": forward.get("horizonDays"),
            # TWO COUNTS, AND THE SMALLER ONE IS THE HONEST ONE. `observations`
            # is every detection the study saw; `months` is how many calendar
            # months those fell into, and the event study collapses to months
            # precisely because bottom patterns fire together — one market-wide
            # selloff supplies hundreds of "independent" detections that are all
            # the same event. Quoting 1,475 detections where the effective
            # sample is 69 months overstates the evidence by twenty times.
            #
            # An earlier version read `observations` off `forward`, where it
            # does not live, and the panel rendered "across  detections" with a
            # hole in the sentence. That is the cheap version of this bug; the
            # expensive version is quoting the larger number confidently.
            "measuredObservations": detection.get("observations"),
            "measuredMonths": forward.get("months"),
            "firingRate": _finite(detection.get("firingRate")),
        })
    return out


def _profile(volume_profile: Optional[dict]) -> Optional[dict]:
    """The volume profile reduced to the bands a price chart can draw exactly.

    THE FULL HISTOGRAM IS NOT DRAWN ON THE PRICE PANE, and that is a decision
    rather than an omission. A volume-at-price histogram is a horizontal chart
    sharing the price axis, and the only ways to put one inside a recharts
    time-series are to overlay it on the candles — obscuring the thing it is
    meant to annotate — or to render it as a second element whose y-scale is
    matched to the first by hand, which stays aligned until the first margin
    changes and then silently does not.

    The bands below are y-ranges, so they draw exactly and cannot drift. The
    full `profile` array still travels in the verdict payload for anyone who
    wants the histogram itself.
    """
    if not isinstance(volume_profile, dict) or not volume_profile.get("available"):
        return None
    control = volume_profile.get("pointOfControl") or {}
    area = volume_profile.get("valueArea") or {}
    return {
        "pointOfControl": {"low": _finite(control.get("low")),
                           "high": _finite(control.get("high")),
                           "share": _finite(control.get("share"))},
        "valueArea": {"low": _finite(area.get("low")), "high": _finite(area.get("high")),
                      "share": _finite(area.get("share"))},
        "insideValueArea": bool(volume_profile.get("insideValueArea")),
        "shelves": [{"low": _finite(shelf.get("low")), "high": _finite(shelf.get("high")),
                     "share": _finite(shelf.get("share")),
                     "side": shelf.get("side"),
                     "distanceAtr": _finite(shelf.get("distanceAtr"))}
                    for shelf in (volume_profile.get("shelves") or [])],
        "binWidth": _finite(volume_profile.get("binWidth")),
        "sessions": volume_profile.get("sessions"),
        "reading": volume_profile.get("reading"),
    }


def _heavy_note(marks: dict) -> str:
    if not marks.get("available"):
        return marks.get("reason") or "the heavy-session split could not be read"
    return (f"Sessions whose volume cleared {marks['rvolCutoff']:.1f}x this name's own "
            f"rolling median — its heaviest {(1 - marks['heavyQuantile']) * 100:.0f}% "
            f"of the last {marks['window']} — shaded by where each one closed in its "
            f"range.")


def build(frame: Optional[pd.DataFrame], *,
          technical: Optional[dict] = None,
          structure_result: Optional[dict] = None,
          pattern_result: Optional[dict] = None,
          tape_result: Optional[dict] = None,
          volume_profile: Optional[dict] = None,
          ticker: Optional[str] = None,
          currency: Optional[str] = None,
          plot_sessions: int = PLOT_SESSIONS) -> dict:
    """Everything the scanner measured about this tape, positioned for drawing."""
    if frame is None or len(frame) < 30:
        have = 0 if frame is None else len(frame)
        return {"available": False,
                "reason": f"needs 30 sessions to draw anything; this has {have}"}

    overlays = _series(frame)
    marks = tape.sessions(frame)
    by_date: dict[str, dict] = {}
    if marks.get("available"):
        by_date = {row["date"]: row for row in marks["sessions"]}

    first_index = max(0, len(frame) - int(plot_sessions))
    window = frame.iloc[first_index:]

    bars = []
    for stamp, row in window.iterrows():
        date = stamp.strftime("%Y-%m-%d")
        mark = by_date.get(date) or {}
        bars.append({
            "date": date,
            "open": _finite(row["Open"]), "high": _finite(row["High"]),
            "low": _finite(row["Low"]), "close": _finite(row["Close"]),
            "volume": _finite(row["Volume"]),
            "sma20": _finite(overlays["sma20"].get(stamp)),
            "sma50": _finite(overlays["sma50"].get(stamp)),
            "sma200": _finite(overlays["sma200"].get(stamp)),
            "bbUpper": _finite(overlays["bbUpper"].get(stamp)),
            "bbLower": _finite(overlays["bbLower"].get(stamp)),
            "relativeVolume": mark.get("relativeVolume"),
            "heavy": bool(mark.get("heavy")),
            "closeLocation": mark.get("closeLocation"),
        })

    resolved = structure.levels_from(technical)
    site = structure_result if isinstance(structure_result, dict) else None

    # Crossovers are READ off the trend lens rather than recomputed from the
    # averages above. They would agree today and drift the first time either
    # side changed a smoothing length, and a chart that disagrees with the table
    # under it is worse than a chart with one fewer marker.
    crossovers = []
    for signal in ((technical or {}).get("signals") or []):
        if signal.get("date") and signal["date"] >= bars[0]["date"]:
            crossovers.append({"date": signal["date"], "type": signal.get("type"),
                               "price": _finite(signal.get("price")),
                               "description": signal.get("description")})

    recent = frame.tail(EXTREME_WINDOW)
    high_at = recent["High"].astype("float64").idxmax()
    low_at = recent["Low"].astype("float64").idxmin()
    extremes = {
        "window": len(recent),
        "high": {"date": high_at.strftime("%Y-%m-%d"),
                 "price": _finite(recent["High"].max()),
                 "inWindow": high_at.strftime("%Y-%m-%d") >= bars[0]["date"]},
        "low": {"date": low_at.strftime("%Y-%m-%d"),
                "price": _finite(recent["Low"].min()),
                "inWindow": low_at.strftime("%Y-%m-%d") >= bars[0]["date"]},
    }

    shapes = _patterns(frame, pattern_result, first_index)
    levels = _levels(resolved, site)
    trade = _trade(site)
    profile = _profile(volume_profile)

    return {
        "available": True,
        "ticker": ticker,
        "currency": currency,
        "sessions": len(bars),
        "from": bars[0]["date"],
        "to": bars[-1]["date"],
        "bars": bars,
        "levels": levels,
        "trade": trade,
        "patterns": shapes,
        # WHERE THE TRADE HAPPENED, as distinct from where the price turned.
        # Bands on the price axis only — every figure here is a y-range, so it
        # draws exactly rather than being aligned by eye against a second chart.
        "volumeProfile": profile,
        "crossovers": crossovers,
        "extremes": extremes,
        "tape": {
            "available": bool(marks.get("available")),
            "reason": marks.get("reason"),
            "rvolCutoff": marks.get("rvolCutoff"),
            "heavyQuantile": marks.get("heavyQuantile"),
            "drawn": sum(1 for bar in bars if bar["heavy"]),
            # THE TWO MEANS THE WELCH TEST COMPARED, so the test itself can be
            # drawn rather than quoted. A reader looking at fifty dots scattered
            # around a line can see at once whether the gap between those two
            # numbers is a tendency or one enormous session, which is the thing
            # a t-statistic is least able to communicate.
            #
            # Read off `tape.read`'s payload, never recomputed: these are the
            # figures the panel underneath quotes, and a chart that derived its
            # own would eventually disagree with the sentence beside it.
            "heavyMeanLocation": _finite((tape_result or {}).get("heavyMeanLocation")),
            "ordinaryMeanLocation": _finite(
                (tape_result or {}).get("ordinaryMeanLocation")),
            "significant": bool((tape_result or {}).get("significant")),
        },
        "legend": _legend(levels, trade, shapes, marks, profile, volume_profile),
        "caption": _caption(shapes, levels, trade),
    }


def _legend(levels: list[dict], trade: Optional[dict], shapes: list[dict],
            marks: dict, profile: Optional[dict] = None,
            volume_profile: Optional[dict] = None) -> list[dict]:
    """One line per layer: what it is, and what it is not.

    Part of the payload rather than a frontend constant, so a client cannot
    render the drawing without the caveats — the same rule `verdict.provenance`
    follows for the score.
    """
    out = [
        {"key": "candles", "label": "Daily bars",
         "note": "Open, high, low and close. Unadjusted for splits inside the window."},
        {"key": "averages", "label": f"{FAST_MA}, {MID_MA} and {SLOW_MA}-day averages",
         "note": ("Computed on the full history behind this window, not on the window, "
                  "so the slow line is a real 200-day average.")},
        {"key": "bands", "label": "Bollinger band",
         "note": "Two standard deviations of the last 20 closes. A width, not a signal."},
    ]
    if levels:
        defended = max((level["touches"] for level in levels), default=0)
        out.append({
            "key": "levels", "label": f"{len(levels)} defended levels",
            "note": (f"Swing highs and lows clustered within one average daily range, "
                     f"the best-defended touched {defended} times. These work only "
                     f"while enough participants watch them, which is also why they "
                     f"are drawn and not scored."),
        })
    if trade:
        out.append({
            "key": "trade", "label": "Stop, entry and first ceiling",
            "note": ("The same three prices `structure.read` computed the reward-risk "
                     "ratio from. The shaded band is where the trade is wrong."),
        })
    if shapes:
        survivors = sum(1 for shape in shapes if shape["significant"])
        out.append({
            "key": "patterns",
            "label": f"{len(shapes)} formations, {survivors} measured as significant",
            "note": ("The curve is refitted on the window that was available when the "
                     "shape completed — never smoothed with hindsight. No target is "
                     "projected: the textbook direction did not survive measurement."),
        })
    if profile:
        # THE STATUS OF THE CLAIM IS THE NOTE. A shaded band labelled "most
        # traded" reads as a support level to anyone who has seen one before,
        # and the measurement is the only thing standing between a description
        # and a recommendation.
        measured = (volume_profile or {})
        if not measured.get("calibrated"):
            verdict_text = ("Whether price holds at one of these better than at an "
                            "ordinary band has not been measured on this market, so "
                            "none of it is read as support.")
        elif measured.get("usable"):
            verdict_text = ("Measured on this market, price does hold at these more "
                            "often than at an ordinary band the same distance away.")
        else:
            verdict_text = ("Measured on this market, price does NOT hold at these "
                            "reliably better than at an ordinary band the same distance "
                            "away — so they are drawn as description and nothing here "
                            "treats them as support.")
        out.append({
            "key": "volumeProfile",
            "label": (f"Volume at price · {len(profile.get('shelves') or [])} "
                      f"shelf{'' if len(profile.get('shelves') or []) == 1 else 'ves'}"),
            "note": ("Where the last year's shares actually changed hands, as opposed to "
                     "where the price turned. Built by spreading each daily bar's volume "
                     "evenly across its own range, which is the best this data supports "
                     "and is why every band is a band rather than a price. "
                     + verdict_text),
        })
    out.append({"key": "heavy", "label": "Heavy sessions", "note": _heavy_note(marks)})
    return out


def _caption(shapes: list[dict], levels: list[dict],
             trade: Optional[dict]) -> str:
    """What the drawing adds up to, in the voice the rest of the app uses."""
    parts = []
    if trade and trade.get("rewardRisk") is not None:
        parts.append(
            f"The shaded band is the trade: {trade['rewardRisk']:.1f} to one from here, "
            f"measured to the nearest floor and the first ceiling above")
    elif trade and trade.get("ratioWithheld"):
        # THE BAND IS STILL DRAWN AND THE RATIO IS STILL REFUSED. The picture is
        # the honest part here: a reader can see for themselves that the red
        # sliver under the price is thinner than a single candle, which is
        # precisely what makes the quotient meaningless.
        parts.append("The red band under the price is the whole of the measured risk, and "
                     "it is thinner than one ordinary session — no reward-to-risk figure "
                     "is quoted, because dividing by it would return a large number for "
                     "the wrong reason")
    elif trade and trade.get("unboundedUpside"):
        parts.append("Nothing overhead in this window — the upside is unbounded rather "
                     "than large, which is the absence of a measurement")
    elif trade and trade.get("noSupport"):
        parts.append("No defended floor below the price, so there is no level to put a "
                     "stop under and no ratio to quote")

    if levels:
        parts.append(f"{len(levels)} level{'' if len(levels) == 1 else 's'} "
                     f"{'is' if len(levels) == 1 else 'are'} drawn, each with the "
                     f"number of times it was defended")

    if shapes:
        survivors = [shape for shape in shapes if shape["significant"]]
        if survivors:
            effects = [shape["measuredExcess"] for shape in survivors
                       if shape["measuredExcess"] is not None]
            strongest = max(effects, key=abs) if effects else None
            detail = (f", and the strongest measured {strongest * 100:+.1f}% against the "
                      f"market over its horizon" if strongest is not None else "")
            parts.append(f"{len(survivors)} of {len(shapes)} formation"
                         f"{'' if len(shapes) == 1 else 's'} survived a "
                         f"false-discovery correction{detail}")
        else:
            parts.append(f"{len(shapes)} formation{'' if len(shapes) == 1 else 's'} "
                         f"{'is' if len(shapes) == 1 else 'are'} marked and none "
                         f"survived correction, so none moved the score")

    text = ". ".join(parts)
    if text:
        text += ". "
    return text + (
        "Every line here was decided by the module that owns it; nothing on this chart "
        "is a forecast, and no price target is drawn because the measured direction of "
        "these formations contradicted the textbook one."
    )
