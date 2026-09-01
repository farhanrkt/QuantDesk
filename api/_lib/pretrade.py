"""
pretrade.py
===========
What would stop a careful buyer — and how often that condition fires anyway.

WHY THIS IS NOT A SCORE, AND WHY THAT IS HARDER THAN IT SOUNDS
--------------------------------------------------------------
Every condition below is already computed somewhere in this app. Altman's
distress band is on the Quality tab, the terminal-value share is on Value, the
Hurst verdict is inside the long-horizon section. None of that is new. What is
new is that they are in ONE place, and that each one arrives with the number
that makes it readable: how often it fires across a universe.

That second half is the whole feature. A condition that fires on a third of the
Nasdaq-100 is a description of the equity market, not a finding about this
company, and presenting it as a flag manufactures alarm out of a base rate. It
is the same multiple-testing mistake `eventstudy.screener_significance` exists
to correct on the anomaly screener, arriving in a new place. So a check that
cannot be calibrated does not render at all, and one that fires too often is
demoted to a stated base condition rather than dressed as a flag.

ABSENCE OF A FLAG IS NEVER EVIDENCE OF QUALITY
----------------------------------------------
This is the failure mode the panel is designed against, and it is a design
constraint rather than a caveat. A checklist that renders clean as a row of
green ticks has made the app MORE authoritative, which is the opposite of the
point: the reader learns "nothing was found", concludes "nothing is there", and
the app has quietly asserted something it did not test.

Four things follow, and each is enforced rather than intended:

  * There is no count, no score, no "N of M", no severity ranking. Nothing in
    this payload aggregates. `tests/test_pretrade.py` asserts on the key set,
    because an aggregate field is exactly the thing a later change would add
    without noticing.
  * Nothing here is ever green. A check either fired or it is silent; there is
    no pass state to colour. The only bands this module emits are `caution`,
    `bad` and `context`.
  * `notChecked` is a first-class list, not an omission. A bank's refused
    accounting screens, a failed leg and a missing filing are all reasons a
    condition was never tested, and they must not read as "clear".
  * The empty state says so in words, every time.

WHAT IT READS
-------------
The ASSEMBLED `/api/confluence` payload, exactly as `explain.for_synthesis`
does, and for the same reason: it must quote the figures the panels render
rather than run a parallel computation that will eventually drift from them.
It costs no extra fetch and no extra model fit. Everything here is a restatement
of a number that is already on screen somewhere else, plus the one thing that is
genuinely new — the measured firing rate from `check_calibration.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import explain as E

# --------------------------------------------------------------------------- #
# Thresholds, each with the reason it sits where it does
# --------------------------------------------------------------------------- #
# Above this share of the calibration universe, a condition stops being a flag
# about one company and becomes a description of the market it trades in. One in
# three is deliberately generous: the cost of demoting a real flag is that a
# reader reads it as context, and the cost of promoting a base rate is that they
# read the ordinary as alarming. The second error is the one this panel exists
# to avoid making.
BASE_RATE_MAX = 0.33

# Below this many usable observations a firing rate is not a measurement. A
# check whose calibration covers twenty names is quoting noise, and the brief's
# own rule applies: if it cannot be calibrated it should not appear.
MIN_CALIBRATION_SAMPLE = 30

# A DCF whose terminal value is more than this share of the answer is mostly a
# statement about the perpetuity. Same constant the synthesis already uses.
TERMINAL_SHARE_WARN = E.TERMINAL_SHARE_WARN

# How far above the model's own growth assumption the price-implied rate has to
# sit before it is worth naming. Five points a year, compounded over the five
# forecast years, is roughly a third more cumulative growth — large enough that
# the two are not describing the same future.
IMPLIED_GROWTH_GAP = 0.05

# A fall this deep is where position sizing stops being arithmetic and starts
# being about whether the holder stays. Half the money is the conventional line
# and it is the one `long_term_view` already draws.
DEEP_DRAWDOWN = -0.50

CALIBRATION_PATH = Path(__file__).with_name("check_calibration.json")

# `assess(payload)` loads the stamped rates from disk; `assess(payload, None)`
# says there ARE none. Those are different situations and a single default of
# None could not tell them apart — which matters because the second is a state
# the panel has to render honestly rather than a bug to paper over.
_LOAD_FROM_DISK = object()


# --------------------------------------------------------------------------- #
# Outcomes
# --------------------------------------------------------------------------- #
# A check has THREE outcomes, not two, and keeping the third distinct is the
# point of the whole module. "Did not fire" and "could not be tested" look
# identical on a panel that only renders flags, and they mean opposite things.
def fires(reading: str, band: str = "caution", value_text: Optional[str] = None) -> dict:
    return {"state": "fired", "reading": reading, "band": band, "valueText": value_text}


def quiet() -> dict:
    return {"state": "quiet"}


def cannot(reason: str) -> dict:
    return {"state": "unchecked", "reason": reason}


def _leg(payload: dict, name: str) -> Optional[dict]:
    """One confluence leg's data, or None if it failed or is absent.

    Every read below goes through this, for the same reason `explain._leg` does:
    the panel whose job is to name what could not be checked must not be the one
    that raises when an engine returns an unexpected shape.
    """
    leg = (payload or {}).get(name)
    if not isinstance(leg, dict) or not leg.get("ok"):
        return None
    data = leg.get("data")
    return data if isinstance(data, dict) else None


def _known(value) -> bool:
    if value is None:
        return False
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _sub(data: Optional[dict], key: str) -> dict:
    """A nested block, guaranteed to be a dict so `.get` is always safe."""
    block = (data or {}).get(key)
    return block if isinstance(block, dict) else {}


# --------------------------------------------------------------------------- #
# The checks
# --------------------------------------------------------------------------- #
# WHY EACH REFUSAL IS WORDED PER MODEL RATHER THAN QUOTED FROM THE LENS.
# `quality["reason"]` is one paragraph covering all three screens at once, which
# is right on the Quality tab where it appears once. Echoed here it appears three
# times in a row, identical, and a reader scanning "not checked" learns to skip
# the section — which is the one section on this panel that must not be skipped.
_NOT_ON_A_FINANCIAL = {
    "altman": ("Altman built the Z-score on manufacturers, and working capital and the "
               "current ratio describe nothing for an institution with no operating cycle"),
    "beneish": ("Beneish's indices assume a receivables-and-inventory revenue model, which "
                "a bank or insurer does not have"),
    "piotroski": ("Piotroski explicitly excluded financial firms from the sample the nine "
                  "tests were built on"),
}


def _refusal(quality: dict, model: str) -> str:
    """Why one accounting screen was not run on this company.

    `cause` distinguishes the two ways the lens declines, and they must not read
    alike: a bank is a DESIGNED refusal — the models do not transfer — while a
    listing with no statements is missing data somebody might be able to supply.
    """
    if quality.get("cause") != "financial":
        return ((quality.get("reason") or "the accounting screens could not be run "
                 "on this company").rstrip("."))
    return (f"{_NOT_ON_A_FINANCIAL[model]}, so the app refuses a score rather than "
            f"printing one. That is a designed refusal, not a gap in the data")


def _altman_distress(payload: dict) -> dict:
    quality = _leg(payload, "quality")
    if quality is None:
        return cannot("the Quality lens did not run for this company")
    if not quality.get("applicable"):
        return cannot(_refusal(quality, "altman"))
    altman = _sub(quality, "altman")
    if not _known(altman.get("score")):
        return cannot("the filings did not carry the items Altman's score needs")
    if altman.get("band") != "distress":
        return quiet()
    return fires(
        f"Altman's Z''-score reads {altman['score']:.2f}, inside the distress zone. "
        f"A going-concern question outranks a valuation: a discounted cash flow on a "
        f"company sliding toward insolvency is arithmetic, not a price.",
        band="bad", value_text=f"{altman['score']:.2f}")


def _beneish_flagged(payload: dict) -> dict:
    quality = _leg(payload, "quality")
    if quality is None:
        return cannot("the Quality lens did not run for this company")
    if not quality.get("applicable"):
        return cannot(_refusal(quality, "beneish"))
    beneish = _sub(quality, "beneish")
    if not _known(beneish.get("score")):
        return cannot(beneish.get("reading")
                      or "too few of the eight Beneish indices could be computed")
    if beneish.get("band") != "flagged":
        return quiet()
    # THE POSTERIOR, NOT THE FLAG. "Most flags are false alarms" was the prose
    # this check shipped with; the Quality lens now computes the number, and a
    # pre-trade panel that quoted the vaguer version while the figure sat one
    # tab away would be the weaker statement in the more prominent place.
    worth = _sub(quality, "manipulationPosterior")
    odds = ""
    if _known(worth.get("posterior")) and worth.get("priorText"):
        odds = (f" At a {worth['priorText']} base rate for manipulation, a flag like this "
                f"one is about {worth['posterior'] * 100:.0f}% likely to be real — so most "
                f"of them are false alarms.")
    return fires(
        f"The M-Score is {beneish['score']:.2f}, above the -1.78 threshold, so the "
        f"accrual and growth pattern resembles companies later found to have massaged "
        f"earnings.{odds} It is a reason to read the cash-flow statement against the "
        f"income statement, not a finding.",
        band="caution", value_text=f"{beneish['score']:.2f}")


def _piotroski_weak(payload: dict) -> dict:
    quality = _leg(payload, "quality")
    if quality is None:
        return cannot("the Quality lens did not run for this company")
    if not quality.get("applicable"):
        return cannot(_refusal(quality, "piotroski"))
    piotroski = _sub(quality, "piotroski")
    if piotroski.get("band") in (None, "unknown"):
        return cannot("there is not enough statement history to score the trend")
    if piotroski.get("band") != "weak":
        return quiet()
    return fires(
        f"{piotroski.get('score')} of {piotroski.get('maxScore')} fundamental checks "
        f"passed — deteriorating on most of the axes Piotroski measures: profitability, "
        f"leverage and operating efficiency. The direction of the business is against "
        f"the buyer here, whatever the price.",
        band="caution",
        value_text=f"{piotroski.get('score')}/{piotroski.get('maxScore')}")


def _terminal_dominant(payload: dict) -> dict:
    valuation = _leg(payload, "valuation")
    if valuation is None:
        return cannot("the Value lens did not run for this company")
    share = _sub(valuation, "baseCase").get("terminalShare")
    if not _known(share):
        return cannot("this model produced no terminal value to measure")
    if share < TERMINAL_SHARE_WARN:
        return quiet()
    return fires(
        f"{share * 100:.0f}% of the fair value comes from the perpetuity assumption — "
        f"what the business is worth forever after year five — rather than from the "
        f"forecast years. Whatever gap to fair value the panel reports is mostly a "
        f"statement about that one editable input.",
        band="caution", value_text=f"{share * 100:.0f}%")


def _implied_growth_demanding(payload: dict) -> dict:
    valuation = _leg(payload, "valuation")
    if valuation is None:
        return cannot("the Value lens did not run for this company")
    base = _sub(valuation, "baseCase")
    implied, assumed = base.get("impliedGrowth"), base.get("assumedGrowth")
    if not _known(implied):
        return cannot("today's price cannot be reproduced by this model at any growth "
                      "rate in the solver's range")
    if not _known(assumed):
        return cannot("no growth assumption was recorded to compare against")
    gap = implied - assumed
    if gap < IMPLIED_GROWTH_GAP:
        return quiet()
    return fires(
        f"The price implies {implied * 100:.0f}% growth a year for five years against the "
        f"{assumed * 100:.0f}% this model was run with — {gap * 100:.0f} points a year "
        f"more than assumed. That is the claim about the world to argue with, and the "
        f"assumption is editable on the Value tab.",
        band="caution", value_text=f"{implied * 100:.0f}%")


def _thin_filings(payload: dict) -> dict:
    """Reported figures assembled from less than the full input set.

    Not a judgement on the company — a statement about what the numbers beside it
    are built from. A Beneish score from six of eight indices and one from all
    eight are printed identically everywhere else in the app.
    """
    quality = _leg(payload, "quality")
    valuation = _leg(payload, "valuation")
    if quality is None and valuation is None:
        return cannot("neither filings-based lens ran, so there is nothing to assess")

    gaps: list[str] = []
    if quality is not None and quality.get("applicable"):
        piotroski = _sub(quality, "piotroski")
        available = piotroski.get("signalsAvailable")
        total = piotroski.get("signalsTotal")
        if _known(available) and _known(total) and available < total:
            gaps.append(f"Piotroski scored {int(available)} of its {int(total)} tests")
        beneish = _sub(quality, "beneish")
        b_available = beneish.get("indicesAvailable")
        b_total = beneish.get("indicesTotal")
        if _known(b_available) and _known(b_total) and b_available < b_total:
            gaps.append(f"Beneish used {int(b_available)} of its {int(b_total)} indices")

    if valuation is not None:
        manual = _sub(_sub(valuation, "assumptions"), "manualApplied")
        supplied = sorted(k for k, v in manual.items() if v)
        if supplied:
            gaps.append("the valuation used figures you supplied by hand for "
                        + ", ".join(supplied))

    if not gaps:
        return quiet()
    return fires(
        ("; ".join(gaps)).capitalize()
        + ". A partial score and a complete one are printed identically everywhere else "
          "in this app, and they do not mean the same thing. Weigh the readings above "
          "accordingly.",
        band="caution", value_text="partial")


def _hurst_random_walk(payload: dict) -> dict:
    technical = _leg(payload, "technical")
    if technical is None:
        return cannot("the Trend lens did not run for this company")
    if not technical.get("hasLongTerm"):
        return cannot("there is not enough loaded history for the long-horizon section — "
                      "widen the chart range to 5y or more")
    reading = _sub(_sub(technical, "longTerm"), "hurstReading")
    verdict = reading.get("verdict")
    if verdict in (None, "unavailable"):
        return cannot("the Hurst estimate needs about a hundred bars and this range is "
                      "shorter")
    if verdict != "indistinguishable":
        return quiet()
    low = reading.get("randomWalkLow")
    high = reading.get("randomWalkHigh")
    band_text = (f", inside the {low:.2f}-{high:.2f} a random walk produces here"
                 if _known(low) and _known(high) else "")
    return fires(
        f"Hurst reads {reading['hurst']:.2f}{band_text}, so this price history cannot be "
        f"told apart from a random walk. Discount the Trend tab; the filings lenses are "
        f"unaffected.",
        band="caution", value_text=f"{reading['hurst']:.2f}")


def _move_inside_cost(payload: dict) -> dict:
    anomaly = _leg(payload, "anomaly")
    if anomaly is None:
        return cannot("the Flow lens did not run for this company")
    liquidity = _sub(anomaly, "liquidity")
    if not liquidity.get("spreadResolved"):
        return cannot("the bid-ask spread on this name sits below what daily bars can "
                      "resolve, so the round trip cannot be compared with the move — "
                      "which on a liquid stock means the cost is small, not that it is "
                      "unknown in a worrying way")
    if not liquidity.get("insideSpreadNoise"):
        return quiet()
    ratio = liquidity.get("moveVsSpread")
    ratio_text = f"{ratio:.1f}x" if _known(ratio) else "under twice"
    return fires(
        f"The latest day's move is {ratio_text} the estimated round-trip cost. A single "
        f"buy and sell at these prices gives back most of a move this size before the "
        f"price has done anything, so whatever the models found here is not something a "
        f"trade could have captured.",
        band="bad", value_text=ratio_text)


def _deep_drawdown_history(payload: dict) -> dict:
    technical = _leg(payload, "technical")
    if technical is None:
        return cannot("the Trend lens did not run for this company")
    if not technical.get("hasLongTerm"):
        return cannot("there is not enough loaded history for a drawdown record — widen "
                      "the chart range to 5y or more")
    drawdown = _sub(_sub(technical, "longTerm"), "drawdown")
    if not drawdown.get("usable") or not _known(drawdown.get("maxDrawdown")):
        return cannot("the loaded history is too short to measure a peak-to-trough fall")
    worst = drawdown["maxDrawdown"]
    if worst > DEEP_DRAWDOWN:
        return quiet()
    under_water = drawdown.get("timeUnderWaterDays")
    tail = (f", and spent {int(under_water)} trading days below a previous high at its "
            f"longest" if _known(under_water) else "")
    return fires(
        f"This has fallen {abs(worst) * 100:.0f}% peak to trough inside the loaded "
        f"history{tail}. That is the number position size exists to survive — not a "
        f"forecast, a fact about what holding it has already required.",
        band="bad", value_text=f"{worst * 100:.0f}%")


def _consensus_being_cut(payload: dict) -> dict:
    """The people closest to this company are lowering their forecasts.

    THE ONLY CHECK ON THIS PANEL THAT READS THE ESTIMATE RECORD, and the only
    one whose underlying number is about the future rather than the past. Every
    other condition here is a fact about what has already happened — a balance
    sheet, a drawdown, an accrual pattern. This one is a fact about what the
    people who follow the company think is about to.

    That makes it the most useful condition here and the one most easily
    over-read, so the bar is the lens's own directional verdict rather than
    anything computed fresh. If the Expectations lens declined to call a
    direction — nobody covering, nobody moving, or too few moves to tell — this
    check declines too, and says which of those it was. A cut called from two
    analysts out of twenty is exactly the false alarm the whole panel is built
    against.
    """
    expectations = _leg(payload, "expectations")
    if expectations is None:
        return cannot("the Expectations lens did not run for this company")
    if not expectations.get("applicable"):
        analysts = expectations.get("analysts") or 0
        return cannot(f"only {analysts} analyst" + ("" if analysts == 1 else "s")
                      + " publishes estimates for this listing, so there is no "
                        "consensus to read")

    verdict = expectations.get("verdict")
    breadth = _sub(expectations, "breadth")
    if verdict == "QUIET":
        return cannot("analysts cover this company but none of them has moved a "
                      "number in the last month")
    if verdict == "THIN":
        return cannot(f"only {breadth.get('moves')} analysts moved, which is too few "
                      f"to read a direction from")
    if verdict != "FALLING":
        return quiet()

    up, down = breadth.get("up"), breadth.get("down")
    drift = _sub(_sub(expectations, "drift"), "annual90")
    size = ""
    if drift.get("state") == "moved" and _known(drift.get("change")):
        # THE DIRECTION IS READ OFF THE NUMBER, NOT ASSUMED FROM THE VERDICT.
        # The first draft wrote "down {abs(change)}%" because the check only
        # fires when breadth is FALLING — but breadth counts ANALYSTS and drift
        # measures the LEVEL, and the two can disagree: a majority trimming
        # their numbers while one house raises a large one leaves more cuts than
        # raises and a level that rose. That sentence would then have printed
        # "the forecast itself is down 4%" about a forecast that went up.
        change = drift["change"]
        way = "down" if change < 0 else "up"
        size = (f" The forecast level itself is {way} {abs(change) * 100:.0f}% over "
                f"ninety days.")
    return fires(
        f"{down} of the analysts covering this company cut their estimate in the last "
        f"month against {up} who raised it.{size} Every other condition on this panel "
        f"reads what has already happened; this one reads what the people closest to "
        f"the company now expect, and it is the reading a valuation built on last "
        f"year's filings cannot contain.",
        band="caution",
        value_text=f"{down} cuts / {up} raises")


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #
# `where` names the panel that owns the underlying number, because a condition a
# reader cannot go and inspect is one they have to take on trust — which is the
# posture this whole app is written against.
#
# `family` is the body of data the check reads, mirroring `explain.SYNTHESIS_FAMILY`.
# It is what tells the calibration script whether a check can be measured from a
# batched price download or needs the filings one symbol at a time.
CHECKS: list[dict] = [
    {
        "id": "altmanDistress",
        "label": "Balance sheet inside the distress zone",
        "family": "filings",
        "where": "Quality tab",
        "evidence": "strong",
        "what": ("Altman's Z''-score combines four balance-sheet ratios into one distance "
                 "from bankruptcy, using the emerging-market variant so an IDX listing "
                 "and a US one sit on the same scale."),
        "action": ("Read the debt schedule and the interest cover before anything else on "
                   "this page. A solvency question makes the valuation moot rather than "
                   "cheap."),
        "fn": _altman_distress,
    },
    {
        "id": "beneishFlagged",
        "label": "Accrual pattern flags on the manipulation screen",
        "family": "filings",
        "where": "Quality tab",
        "evidence": "moderate",
        "what": ("The Beneish M-Score compares this year's receivables, margins, asset "
                 "quality and accruals with last year's, and asks whether the pattern "
                 "resembles firms later found to have manipulated earnings."),
        "action": ("Read the cash-flow statement against the income statement. This is a "
                   "screen with a high false-positive rate on a population where "
                   "manipulation is rare, so it directs attention rather than concluding "
                   "anything."),
        "fn": _beneish_flagged,
    },
    {
        "id": "piotroskiWeak",
        "label": "Fundamental trend deteriorating",
        "family": "filings",
        "where": "Quality tab",
        "evidence": "moderate",
        "what": ("Piotroski's nine binary tests ask whether profitability, leverage and "
                 "efficiency improved on last year. A weak reading means most of them "
                 "went the wrong way."),
        "action": ("Check whether the deterioration is one bad year or a trend, on the "
                   "Quality tab's per-signal list. The score does not distinguish them."),
        "fn": _piotroski_weak,
    },
    {
        "id": "terminalDominant",
        "label": "Most of the valuation is a perpetuity guess",
        "family": "filings",
        "where": "Value tab",
        "evidence": "strong",
        "what": ("A discounted cash flow forecasts five years explicitly and then assumes "
                 "the business continues forever at a fixed rate. This is how much of the "
                 "answer comes from that forever assumption."),
        "action": ("Move terminal growth by half a point on the Value tab and watch the "
                   "fair value move further than the gap you are looking at. If it does, "
                   "the gap is an artefact of that input rather than a finding."),
        "fn": _terminal_dominant,
    },
    {
        "id": "impliedGrowthDemanding",
        "label": "The price assumes more growth than the model does",
        "family": "filings",
        "where": "Value tab",
        "evidence": "moderate",
        "what": ("Running the valuation backwards gives the growth rate today's price "
                 "requires. This compares it with the rate the model was actually run "
                 "with."),
        "action": ("Decide whether you believe the implied rate — you know things about "
                   "the business the model does not. That is a far more answerable "
                   "question than whether a fair-value estimate is right."),
        "fn": _implied_growth_demanding,
    },
    {
        "id": "thinFilings",
        "label": "Scores built from incomplete data",
        "family": "filings",
        "where": "Quality and Value tabs",
        "evidence": "strong",
        "what": ("Whether the accounting scores and the valuation on this page were "
                 "assembled from every input they want, or from the subset this listing "
                 "actually reports."),
        "action": ("Treat the affected readings as weaker rather than wrong. Where the "
                   "valuation used a figure you typed, the answer is only as good as that "
                   "figure."),
        "fn": _thin_filings,
    },
    {
        "id": "hurstRandomWalk",
        "label": "Price series indistinguishable from a random walk",
        "family": "price",
        "where": "Trend tab, long-horizon section",
        "evidence": "strong",
        "what": ("The Hurst exponent measures whether a price series trends, reverts, or "
                 "does neither. The band that counts as 'neither' widens when there is "
                 "less history, so a short sample cannot fake confidence."),
        "action": ("Downgrade every price-derived reading on the page rather than acting "
                   "on one. The support levels, the trend verdict and the momentum "
                   "figures all assume a structure this says may not be there."),
        "fn": _hurst_random_walk,
    },
    {
        "id": "moveInsideCost",
        "label": "The latest move is inside the cost of trading it",
        "family": "price",
        "where": "Flow tab, liquidity section",
        "evidence": "strong",
        "what": ("The estimated round-trip bid-ask cost against the size of the most "
                 "recent daily move. Below about twice the spread, a buy and a sell give "
                 "back most of the move on their own."),
        "action": ("Size the expected move against the round trip before trading, or do "
                   "not trade this on a daily signal at all. On a thin stock, 'heavy "
                   "volume moved the price' often just means the order book is shallow."),
        "fn": _move_inside_cost,
    },
    {
        "id": "deepDrawdownHistory",
        "label": "Has already fallen more than half",
        "family": "price",
        "where": "Trend tab, what holding it cost",
        "evidence": "strong",
        "what": ("The worst peak-to-trough fall anywhere in the loaded history, with how "
                 "long it spent below a previous high."),
        "action": ("Size any position so a repeat would not force you out. That is the "
                   "single decision this number exists for; it says nothing about what "
                   "happens next."),
        "fn": _deep_drawdown_history,
    },
    {
        "id": "consensusBeingCut",
        "label": "The published forecasts are being cut",
        "family": "estimates",
        "where": "Expectations tab",
        # MODERATE, AND THE MEASUREMENT IS WHY IT IS NOT STRONGER. Estimate
        # revision momentum is among the better documented effects in the
        # literature, but this app's own study of it — one 60-day window,
        # `revision_momentum.json` — came back indistinguishable from zero. A
        # published effect this repo could not reproduce does not get to be
        # called strong here.
        "evidence": "moderate",
        "what": ("How many of the analysts publishing a forecast for this company cut "
                 "their number in the last month against how many raised it. It is the "
                 "only condition on this panel drawn from the estimate record rather "
                 "than from the price history or the filings."),
        "action": ("Find out what they know. A falling consensus beside a cheap "
                   "valuation is the standard shape of a value trap — the filings the "
                   "valuation reads are older than the forecasts being cut. It is a "
                   "direction of travel, not a verdict, and the panel reports how often "
                   "it fires."),
        "fn": _consensus_being_cut,
    },
]

CHECK_BY_ID = {check["id"]: check for check in CHECKS}


def predicates() -> dict[str, Callable[[dict], dict]]:
    """The check functions by id — what the calibration script measures."""
    return {check["id"]: check["fn"] for check in CHECKS}


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #
def load_calibration(path: Path = CALIBRATION_PATH) -> Optional[dict]:
    """The stamped firing rates, or None when they have never been measured.

    Served from a file for the same reason `backtest_results.json` is: it costs a
    full universe download plus a filings fetch per name, it is a research finding
    about the checks rather than a per-user computation, and a figure that decays
    slowly should be stamped rather than recomputed on every request.
    """
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) and payload.get("checks") else None


def _usable(entry) -> bool:
    """A rate measured on too few names is treated as no rate at all.

    The brief's rule applied literally: if a check cannot be calibrated, it does
    not appear. Quoting a prevalence from twenty companies would be quoting
    noise with a decimal point on it.
    """
    if not isinstance(entry, dict):
        return False
    rate, sample = entry.get("firingRate"), entry.get("sampleSize")
    return (_known(rate) and _known(sample) and sample >= MIN_CALIBRATION_SAMPLE)


def _rate_for(calibration: Optional[dict], check_id: str,
              market: Optional[str] = None) -> Optional[dict]:
    """One check's firing rate, preferring the one measured on THIS market.

    A GLOBAL RATE ACROSS TWO MARKETS IS THE WRONG NUMBER, and the calibration
    run is what showed it. "Scores built from incomplete data" fires on 10% of
    the Dow and 80% of IDX30 — Yahoo's fundamentals coverage for smaller
    Indonesian listings is the single biggest fragility in this project, and it
    is a fact about the data source rather than about any company. Blending the
    two gives roughly 40%, which is simultaneously alarming for a US large cap
    (where it is genuinely unusual) and reassuring for an IDX one (where it is
    the norm). Neither reading is true of the company in front of the reader.

    So the market-specific rate wins where one was measured, and the combined
    rate is the fallback for a market nobody calibrated. Either way `scope`
    names the group the percentage is a percentage OF, and the panel prints it.
    """
    entry = ((calibration or {}).get("checks") or {}).get(check_id)
    if not isinstance(entry, dict):
        return None

    per_market = (entry.get("markets") or {}).get((market or "").upper())
    if _usable(per_market):
        labels = (calibration or {}).get("marketLabels") or {}
        return {**per_market,
                "scope": labels.get((market or "").upper())
                or (calibration or {}).get("universeLabel")}

    if _usable(entry):
        return {**entry, "scope": (calibration or {}).get("universeLabel")}
    return None


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def _entry(check: dict, outcome: dict, rate: dict, classification: str,
           calibration: Optional[dict]) -> dict:
    """One rendered condition, with the firing rate that makes it readable."""
    share = float(rate["firingRate"])
    universe_label = rate.get("scope") or "the calibration universe"
    # A base condition is never coloured. It is a fact about the market this
    # company trades in, and colouring it would restate a base rate as a finding.
    band = "context" if classification == "base" else outcome["band"]
    explanation = E.make(
        label=check["label"],
        what=check["what"],
        reading=outcome["reading"],
        action=check["action"],
        band=band,
        good_direction="none",
        evidence=check["evidence"],
        value_text=outcome.get("valueText"),
    )
    return {
        "id": check["id"],
        "classification": classification,
        "where": check["where"],
        "family": check["family"],
        "firingRate": share,
        "firingRateText": f"{share * 100:.0f}%",
        "sampleSize": int(rate["sampleSize"]),
        "universeLabel": universe_label,
        # "of which" would be wrong: `couldNotRun` sits OUTSIDE the sample, not
        # inside it. The denominator is the names where the check could actually
        # be evaluated, and saying so is what stops a coverage gap reading as a
        # low firing rate.
        "rateSentence": (
            f"Fires on {share * 100:.0f}% of {universe_label}, measured across "
            f"{int(rate['sampleSize'])} companies"
            + (f"; a further {int(rate['couldNotRun'])} could not be tested at all"
               if _known(rate.get("couldNotRun")) and rate["couldNotRun"] else "")
            + "."
        ),
        "explain": explanation,
    }


def assess(payload: dict, calibration=_LOAD_FROM_DISK,
           market: Optional[str] = None) -> dict:
    """Every condition that fired, with what it fires on across a universe.

    `payload` is the `/api/confluence` response with each leg carrying its own
    `ok` flag. Nothing here recomputes; every reading restates a figure the
    panels already render.

    `market` selects which population the firing rates describe — see
    `_rate_for` for why a rate blended across the US and Indonesian universes
    is the wrong number for a company in either of them.

    THERE IS DELIBERATELY NO AGGREGATE IN THE RETURN VALUE. No count, no score,
    no severity order. Three flags on one company and three on another are not
    comparable quantities — that is what the per-check firing rate is for — and a
    summary field would be read as one whether or not it was meant as one.
    """
    if calibration is _LOAD_FROM_DISK:
        calibration = load_calibration()

    flags: list[dict] = []
    base_conditions: list[dict] = []
    not_checked: list[dict] = []
    uncalibrated: list[dict] = []

    for check in CHECKS:
        try:
            outcome = check["fn"](payload)
        except (TypeError, ValueError, KeyError, AttributeError, ZeroDivisionError):
            # A check that raises is a check that could not be run. It must not
            # be able to take down the panel whose job is to name what was not
            # tested — and it must not silently read as "clear" either.
            outcome = cannot("this check could not be evaluated from the data returned")

        rate = _rate_for(calibration, check["id"], market)
        if rate is None:
            # Never rendered, never counted as clear. Recorded so the panel can
            # say which conditions it is not in a position to test at all.
            uncalibrated.append({"id": check["id"], "label": check["label"]})
            continue

        if outcome["state"] == "unchecked":
            not_checked.append({"id": check["id"], "label": check["label"],
                                "reason": outcome["reason"], "where": check["where"]})
            continue
        if outcome["state"] == "quiet":
            continue

        classification = "base" if rate["firingRate"] > BASE_RATE_MAX else "flag"
        entry = _entry(check, outcome, rate, classification, calibration)
        (base_conditions if classification == "base" else flags).append(entry)

    return {
        "flags": flags,
        "baseConditions": base_conditions,
        "notChecked": not_checked,
        "uncalibrated": uncalibrated,
        "calibration": ({"measuredOn": calibration.get("measuredOn"),
                         "universeLabel": calibration.get("universeLabel"),
                         "universes": calibration.get("universes"),
                         "market": (market or "").upper() or None,
                         "baseRateMax": BASE_RATE_MAX}
                        if calibration else None),
        **E.for_pretrade(flags, base_conditions, not_checked, uncalibrated, calibration),
    }
