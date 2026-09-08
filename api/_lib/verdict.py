"""
verdict.py
==========
One score and one action per name, from every lens this app can run.

READ THIS BEFORE READING THE CODE
---------------------------------
`PRODUCT.md` constraint 1 refuses a composite buy/hold/sell for the published
single-company view, and that refusal is not being weakened: nothing in this
module is imported by `explain.for_synthesis`, by `pretrade.assess`, or by any
route those two feed. `tests/test_synthesis.py` and `tests/test_pretrade.py`
still guard those payloads against exactly the aggregate this file produces, and
they still pass.

This is a SEPARATE, PRIVATE SURFACE with a different job. The published view
answers "what is and is not known about this company" for a reader who should
form their own view. This answers "of 837 Indonesian listings, which forty are
worth my attention this week, and in what order" — a question that is not
answerable without ranking, and where refusing to rank means refusing to answer.
The honest response to that is not to pretend the two questions are the same. It
is to build the second one where it cannot leak into the first, and to attach to
every number it prints the measurement that says how much the ordering is worth.

WHICH BRINGS US TO THE MEASUREMENT
----------------------------------
`backtest_results.json` reports that this app's own price composite showed no
relationship to subsequent returns that survives correcting for the number of
tests run — across four universes, three holding periods, six years. The most
sensitive test could only have detected a mean information coefficient of about
0.08, and a useful one in this field is nearer 0.03. That is "no edge large
enough for this sample to see", not "no edge", and the difference matters. But
the direction of the finding is unambiguous and it is about the largest single
input to the score below.

So `provenance()` returns that statement, every report prints it at the top, and
no caller may render a score without it. That is the standard `PRODUCT.md`
constraint 2 sets — measured, published including nulls — met the only way it
can be met by a feature the measurement did not vindicate.

HOW THE SCORE IS BUILT, AND WHY IN THAT ORDER
---------------------------------------------
1. FIVE COMPONENTS, each 0-100, each read from a lens that has already run.
   Nothing here recomputes anything — same contract as `explain.for_synthesis`
   and for the same reason: the score must quote the figures the panels render,
   and a parallel computation would eventually drift from them.

2. TWO FAMILY SCORES, not five component scores averaged. Four lenses over two
   bodies of data are not four opinions — `explain._family_votes` has said so
   since it shipped. Price, trend and flow are one weighted mean; value and
   quality are another. Averaging all five would give the price record three
   votes to the filings' two purely because it is cheaper to compute.

3. ONE RAW SCORE: the two families, weighted equally. Each body of data gets one
   vote. That is the app's central claim expressed as arithmetic.

4. SHRINKAGE TOWARD 50, by how much independent evidence there actually is.
   Families that disagree, a family that never read, components that were
   missing — each pulls the score toward neutral rather than being silently
   dropped. A 78 computed from two agreeing families and a 78 computed from one
   family with three gaps are not the same claim, and the second must not print
   as though it were.

5. PENALTIES from the pre-trade checks that fired, each scaled by how rare it
   is. `pretrade.py` already establishes why: a condition firing on a third of a
   universe describes the market, not the company. A flag that fires on 3% of
   names costs nearly the full penalty; one that fires on 30% costs almost
   nothing. Base conditions cost nothing at all, by that module's own logic.

6. GATES, which are not opinions and are not scored. Whether a name trades
   enough for a real order to fill is a fact about the order book, and no
   quantity of good signal makes an untradeable name tradeable. A gated name
   returns NO ACTION with the gate named, whatever its score.

WHY THE ILLIQUIDITY GATE IS THE MOST IMPORTANT LINE IN THIS FILE
-----------------------------------------------------------------
On the Indonesian market it removes most of the universe. Of ~840 listings, a
large minority trade a few tens of millions of rupiah a day — a single retail
order moves them, the spread is a multiple of any edge, and `microstructure.py`
already computes the number that says so. A whole-market scan without this gate
returns a top ten made almost entirely of names that cannot be bought, because
thin names have the most extreme percentiles on every price signal. The gate is
what makes a full-market scan mean anything at all.
"""

from __future__ import annotations

from typing import Optional

from . import explain as E

# --------------------------------------------------------------------------- #
# Components — what reads what, and how much each is trusted
# --------------------------------------------------------------------------- #
# `weight` uses the same evidence-to-weight mapping `ranking.SIGNALS` does
# (strong 1.0 / moderate 0.7 / weak 0.4), so the two tiers of this app do not
# hold two different opinions about what a moderately supported effect is worth.
# The grades are judgements, they are stated in the payload, and equal weighting
# would be a judgement too — there is no neutral choice here, only a declared one.
COMPONENTS: list[dict] = [
    {
        "key": "priceRank",
        "label": "Price and volume rank",
        "family": "price",
        "evidence": "moderate",
        "weight": 0.7,
        "detail": ("Where this name sits in the scanned universe on seven price-derived "
                   "signals — momentum, trend slope, nearness to its high, steadiness, "
                   "drawdown, strength against the index, money flow. A percentile within "
                   "THIS scan on THIS date, not a score on an absolute scale."),
    },
    {
        "key": "trend",
        "label": "Long-horizon trend",
        "family": "price",
        "evidence": "moderate",
        "weight": 0.7,
        "detail": ("The share of the long-horizon checklist that points upward: the "
                   "200-day average, the Faber rule, 12-1 momentum, trend strength, "
                   "persistence, drawdown recovery and risk-adjusted return."),
    },
    {
        "key": "flow",
        "label": "Order flow",
        "family": "price",
        "evidence": "weak",
        "weight": 0.4,
        "detail": ("Which way statistically unusual trading days have leaned recently, and "
                   "whether a sustained accumulation or distribution regime is running "
                   "underneath. Graded weak: this app's own event study found no "
                   "predictive edge in the anomaly flag."),
    },
    {
        "key": "value",
        "label": "Value against the model",
        "family": "filings",
        "evidence": "moderate",
        "weight": 0.7,
        "detail": ("The share of simulated valuation runs that came out cheap at today's "
                   "price. A probability from the model's own uncertainty, not a target."),
    },
    {
        "key": "quality",
        "label": "Accounting quality",
        "family": "filings",
        "evidence": "strong",
        "weight": 1.0,
        "detail": ("Piotroski's nine health checks, bounded by Altman's distress band and "
                   "discounted where Beneish flags the accrual pattern. Graded strong: the "
                   "F-score is among the better replicated accounting anomalies."),
    },
]

COMPONENT_BY_KEY = {c["key"]: c for c in COMPONENTS}
FAMILY_LABEL = {"price": "price and volume", "filings": "the filings"}

# --------------------------------------------------------------------------- #
# Constants, each with the reason it sits where it does
# --------------------------------------------------------------------------- #
# A DCF whose terminal value is most of the answer is mostly a statement about
# the perpetuity assumption. The response is to trust it LESS, not to score it
# worse — a model that is mostly assumption is uninformative in both directions,
# and marking it down would turn "we cannot tell" into "this is expensive".
TERMINAL_SHARE_WARN = E.TERMINAL_SHARE_WARN
TERMINAL_SHARE_WEIGHT = 0.6

# Above this share of the calibration universe a pre-trade condition is a
# description of the market rather than a finding about one company, so it costs
# nothing. Same constant `pretrade.py` uses to demote a flag, and imported from
# there rather than restated so the two cannot drift apart.
BASE_RATE_MAX = 0.33

# The most one fired flag can cost, and the most all of them together can. Eight
# points moves a name across at most one action band, which is the right size: a
# flag is a reason to look harder, not a verdict. The total cap exists because
# flags are correlated — a distressed balance sheet trips several at once — and
# an uncapped sum would count one underlying fact five times.
MAX_FLAG_PENALTY = 8.0
MAX_TOTAL_PENALTY = 20.0
CAUTION_PENALTY_SCALE = 0.5

# Below this a family score is negative, above it positive. The band is
# deliberately wide, and it was widened once already after reading real output:
# at 45/55 a filings score of 56 — one point past the line, assembled from a
# single lens — triggered the "both bodies of data point the same way" branch,
# which is the strongest sentence this app owns. Earning that sentence with a 56
# devalues it everywhere it is true. The middle of a distribution is the most
# common place to be, and every component here is centred on 50 by construction.
NEUTRAL_LOW, NEUTRAL_HIGH = 42.0, 58.0

# How far the score is pulled toward 50 by each deficiency in the evidence.
# These are not tuned to produce a distribution anybody liked the look of; each
# is the answer to "how much less does this claim support than the full one".
SHRINK_AGREE = 1.00          # both families read, both on the same side
SHRINK_ONE_NEUTRAL = 0.85    # both read, one sits in the neutral band
SHRINK_DISAGREE = 0.60       # both read, opposite sides — the disagreement IS the finding
SHRINK_SINGLE_FAMILY = 0.70  # one body of data, which is what this app exists to avoid
# Coverage maps [0,1] onto [SHRINK_COVERAGE_FLOOR, 1]. It never reaches zero:
# a name with one component still says something, just much less.
SHRINK_COVERAGE_FLOOR = 0.60

# Action bands, on the score AFTER shrinkage and penalties.
BANDS = [
    (72.0, "STRONG_BUY", "Strong buy", "good"),
    (60.0, "BUY", "Buy", "good"),
    (45.0, "HOLD", "Hold", "neutral"),
    (33.0, "REDUCE", "Reduce", "warn"),
    (0.0, "AVOID", "Avoid", "bad"),
]
# STRONG BUY requires high conviction as well as the score. A 74 assembled from
# one family with two gaps is not a strong anything, and the shrinkage alone
# does not always drag it below the band.
STRONG_BUY_REQUIRES = "high"

ACTION_ORDER = ["AVOID", "REDUCE", "HOLD", "BUY", "STRONG_BUY"]

# --------------------------------------------------------------------------- #
# Tradeability gates, per market
# --------------------------------------------------------------------------- #
# Median daily turnover, in the listing's own currency, below which a personal
# order is a meaningful share of the day's volume. IDR 2bn is roughly USD 120k:
# a 1% participation rate on that is a 20m rupiah order, which is a real
# position for one person and invisible to the book. The US floor is USD 2m for
# the same reasoning at that market's scale.
#
# These are the single most consequential numbers in this file — on IDX they
# decide most of the universe — so they are a named, overridable parameter
# rather than a literal buried in a comparison.
TURNOVER_FLOOR = {"ID": 2.0e9, "US": 2.0e6}

# The exchange's minimum tick. A name resting on it is not being priced, it is
# being pinned, and every percentile computed from its price series is an
# artifact of the floor rather than a measurement. IDX's lowest tier is Rp 50.
TICK_FLOOR = {"ID": 50.0, "US": 1.0}

# Fewer components than this and there is no cross-check worth the name. Two is
# the minimum at which a score is a blend rather than a relabelled single lens.
MIN_COMPONENTS = 2


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _leg(legs: dict, name: str) -> Optional[dict]:
    """One confluence leg's data, or None if it failed or is absent.

    Same accessor shape `explain._leg` uses, restated locally rather than
    imported: `explain` is a presentation module and this one must not acquire a
    dependency on its private helpers, which are free to change.
    """
    entry = (legs or {}).get(name)
    if not isinstance(entry, dict) or not entry.get("ok"):
        return None
    data = entry.get("data")
    return data if isinstance(data, dict) else None


# ============================================================================ #
# The five component readings
#
# Each returns {score, available, reason, detail, weightScale} where `score` is
# 0-100 on that lens's own resolution. A lens that can only distinguish three
# states returns three values and says so — inventing intermediate precision to
# make the columns look alike would be a lie about resolution, and the WEIGHT is
# where a lens's trustworthiness is expressed, not the range of its output.
# ============================================================================ #
def _unavailable(reason: str, refused: bool = False) -> dict:
    return {"score": None, "available": False, "reason": reason,
            "refused": refused, "weightScale": 1.0}


def read_price_rank(rank_row: Optional[dict]) -> dict:
    """The breadth tier's composite percentile, carried through unchanged."""
    if not isinstance(rank_row, dict):
        return _unavailable("this name was not in the ranked scan")
    composite = _finite(rank_row.get("composite"))
    if composite is None:
        return _unavailable("no price signal computed — usually too little history")

    coverage = _finite(rank_row.get("coverage"))
    detail = (f"{composite:.0f}th percentile of the scanned universe on "
              f"{rank_row.get('signalsAvailable', '?')} of "
              f"{rank_row.get('signalsTotal', '?')} price signals.")
    # A row whose composite rests on half its signals is a weaker reading of the
    # same thing, so the WEIGHT bends rather than the score. Renormalising the
    # score instead would move a name toward the middle of the pack for the
    # crime of being newly listed — the failure `ranking.py` names explicitly.
    scale = 1.0 if coverage is None else _clamp(0.5 + 0.5 * coverage, 0.5, 1.0)
    return {"score": composite, "available": True, "reason": None,
            "refused": False, "detail": detail, "weightScale": scale}


def read_trend(legs: dict) -> dict:
    """The long-horizon checklist as a share of its own checks that passed."""
    data = _leg(legs, "technical")
    if data is None:
        return _unavailable("the trend lens did not return")

    view = (data.get("longTerm") or {}).get("view") or {}
    scored = view.get("scored")
    passed = view.get("passed")
    if data.get("hasLongTerm") and scored and passed is not None:
        score = 100.0 * float(passed) / float(scored)
        return {"score": _clamp(score), "available": True, "reason": None,
                "refused": False, "weightScale": 1.0,
                "detail": (f"{passed} of {scored} long-horizon checks point upward "
                           f"({view.get('verdict', '?').lower()}).")}

    # FALLBACK, AT A REDUCED WEIGHT. The 50/200-day label describes the last few
    # months wearing the same word the long-horizon verdict uses, and a reader
    # asking what a name adds up to is asking the longer question. It is worth
    # something, and it is worth less.
    summary = data.get("summary") or {}
    tone = summary.get("trend_tone")
    if tone not in {"bull", "bear", "neutral"}:
        return _unavailable("not enough history for a trend reading")
    score = {"bull": 68.0, "bear": 32.0, "neutral": 50.0}[tone]
    return {"score": score, "available": True, "reason": None, "refused": False,
            "weightScale": 0.6,
            "detail": (f"Short-run trend reads {summary.get('trend', tone)}. Not enough "
                       f"history for the long-horizon checklist, so this counts for less.")}


def read_flow(legs: dict) -> dict:
    """Which way unusual trading has leaned, at this lens's real resolution.

    Five states, because that is how many this lens can actually distinguish:
    both readings up, one up, quiet or mixed, one down, both down. Interpolating
    a continuous score out of an anomaly count would be inventing precision the
    detector does not have.
    """
    data = _leg(legs, "anomaly")
    if data is None:
        return _unavailable("the flow lens did not return")

    stats = data.get("stats") or {}
    recent = stats.get("recentCount")
    days = stats.get("recentDays")
    if recent is None or days is None:
        return _unavailable("no recent window to read flow over")

    bias = str(stats.get("recentFlowBias") or "neutral").strip().lower()
    episode = (data.get("accumulation") or {}).get("current") or {}
    regime = str((episode or {}).get("direction") or "").strip().lower()

    votes = 0
    parts = []
    if recent:
        if bias == "accumulation":
            votes += 1
            parts.append(f"{recent} unusual day{'' if recent == 1 else 's'} in the last "
                         f"{days}, leaning buying")
        elif bias == "distribution":
            votes -= 1
            parts.append(f"{recent} unusual day{'' if recent == 1 else 's'} in the last "
                         f"{days}, leaning selling")
        else:
            parts.append(f"{recent} unusual day{'' if recent == 1 else 's'} in the last "
                         f"{days}, mixed")
    else:
        parts.append(f"nothing unusual in the last {days} days")

    if regime == "accumulation":
        votes += 1
        parts.append("a sustained accumulation regime is running underneath")
    elif regime == "distribution":
        votes -= 1
        parts.append("a sustained distribution regime is running underneath")

    score = {2: 85.0, 1: 65.0, 0: 50.0, -1: 35.0, -2: 15.0}[max(-2, min(2, votes))]
    return {"score": score, "available": True, "reason": None, "refused": False,
            "weightScale": 1.0,
            "detail": ("; ".join(parts).capitalize()
                       + ". Unusual means statistically unlike this stock's other days — "
                         "it does not mean an institution was behind it.")}


def read_value(legs: dict) -> dict:
    """The share of simulated valuation runs that came out cheap at this price."""
    data = _leg(legs, "valuation")
    if data is None:
        return _unavailable("the value lens did not return — usually a filing gap")

    monte = data.get("monteCarlo") or {}
    prob = _finite(monte.get("probUndervalued"))
    weight_scale = 1.0
    notes = []

    terminal = _finite(data.get("terminalShare"))
    if terminal is None:
        terminal = _finite((data.get("baseCase") or {}).get("terminalShare"))
    if terminal is not None and terminal > TERMINAL_SHARE_WARN:
        weight_scale = TERMINAL_SHARE_WEIGHT
        notes.append(f"{terminal * 100:.0f}% of the model's value is the terminal "
                     f"assumption, so this counts for less")

    if prob is not None:
        score = _clamp(prob * 100.0)
        detail = (f"{score:.0f}% of simulated runs came out cheap at "
                  f"{data.get('priceLabel', 'today\'s price')}"
                  f"{'; ' + '; '.join(notes) if notes else ''}.")
        return {"score": score, "available": True, "reason": None, "refused": False,
                "weightScale": weight_scale, "detail": detail}

    # No simulation, but a verdict. Three states at three-state resolution.
    verdict = data.get("verdict")
    mapped = {"UNDERVALUED": 72.0, "FAIRLY VALUED": 50.0, "OVERVALUED": 28.0}.get(verdict)
    if mapped is None:
        return _unavailable("no usable valuation came back")
    return {"score": mapped, "available": True, "reason": None, "refused": False,
            "weightScale": weight_scale * 0.7,
            "detail": (f"The model reads {verdict.lower()}, but its simulation did not run, "
                       f"so there is no probability behind it.")}


def read_quality(legs: dict) -> dict:
    """Piotroski, bounded by Altman's band and discounted by Beneish's flag.

    THE BOUNDS ARE CAPS, NOT SUBTRACTIONS, and that is the whole design. Solvency
    is not a gradient a good trading record can offset: a firm inside the
    distress zone with eight of nine health checks passing is a firm inside the
    distress zone. A subtraction would let the F-score buy its way back out.
    """
    data = _leg(legs, "quality")
    if data is None:
        return _unavailable("the quality lens did not return")

    if not data.get("applicable"):
        # THE LENS HAS TWO WAYS OF SAYING "NO SCORE" AND THEY ARE NOT THE SAME
        # THING. `quality.analyze` distinguishes them with `cause` precisely so a
        # caller need not sniff the prose, and collapsing them here produced a
        # wrong answer of the worst kind on the first real IDX scan: seven
        # small-cap names — a tape manufacturer, a hotel operator, a chocolate
        # maker — were reported as "refused: the models do not transfer to a bank
        # or insurer" when what actually happened is that Yahoo returned no
        # statements for them at all. One of those is a designed refusal that
        # says something true about the models; the other is a coverage gap that
        # says something true about the data source, and on IDX small caps it is
        # the common one.
        if data.get("cause") == "financial":
            return _unavailable(
                "Piotroski, Altman and Beneish were built on non-financial firms and "
                "none of them transfers to a bank or insurer, so no score is reported. "
                "On IDX this removes a large share of the index by weight",
                refused=True)
        return _unavailable(
            data.get("reason")
            or "no financial statements came back for this listing")

    piotroski = data.get("piotroski") or {}
    score_raw = _finite(piotroski.get("score"))
    max_score = _finite(piotroski.get("maxScore")) or 9.0
    if score_raw is None or max_score <= 0:
        return _unavailable("the health checks could not be scored from these filings")

    score = _clamp(100.0 * score_raw / max_score)
    parts = [f"{score_raw:.0f} of {max_score:.0f} health checks passed"]

    altman_band = (data.get("altman") or {}).get("band")
    if altman_band == "distress":
        score = min(score, 25.0)
        parts.append("the balance sheet is inside the distress zone, which caps this "
                     "reading regardless of the health checks")
    elif altman_band == "grey":
        score = min(score, 60.0)
        parts.append("the balance sheet sits in the grey zone")
    elif altman_band == "safe":
        parts.append("clear of the distress zone")

    beneish_band = (data.get("beneish") or {}).get("band")
    if beneish_band == "flagged":
        score *= 0.6
        parts.append("the accrual pattern is flagged for a closer look")
    elif beneish_band == "borderline":
        score *= 0.85
        parts.append("accruals sit close to the manipulation threshold")

    return {"score": _clamp(score), "available": True, "reason": None, "refused": False,
            "weightScale": 1.0, "detail": (", ".join(parts) + ".").capitalize()}


READERS = {
    "priceRank": lambda legs, rank_row: read_price_rank(rank_row),
    "trend": lambda legs, rank_row: read_trend(legs),
    "flow": lambda legs, rank_row: read_flow(legs),
    "value": lambda legs, rank_row: read_value(legs),
    "quality": lambda legs, rank_row: read_quality(legs),
}


# ============================================================================ #
# Families, agreement, shrinkage
# ============================================================================ #
def _family_score(components: list[dict], family: str) -> Optional[dict]:
    """One weighted mean per BODY OF DATA, over the components that read."""
    members = [c for c in components if c["family"] == family and c["available"]]
    if not members:
        return None
    total_weight = sum(c["effectiveWeight"] for c in members)
    if total_weight <= 0:
        return None
    score = sum(c["score"] * c["effectiveWeight"] for c in members) / total_weight
    side = 1 if score > NEUTRAL_HIGH else -1 if score < NEUTRAL_LOW else 0
    return {"family": family, "label": FAMILY_LABEL[family], "score": score,
            "side": side, "members": [c["key"] for c in members],
            "weight": total_weight}


def _agreement(price: Optional[dict], filings: Optional[dict]) -> dict:
    """What the two bodies of data add up to, and how much to trust it.

    The four branches are the same four `explain._agreement` prints in sentences,
    with a shrinkage factor attached to each. That is deliberate: the private
    scanner and the published rail must not be able to reach opposite readings of
    the same two families.
    """
    if price is None and filings is None:
        return {"state": "none", "shrink": 0.0, "conviction": "none",
                "text": "No lens returned a usable reading, so there is nothing to score."}

    if price is None or filings is None:
        only = price or filings
        return {"state": "single", "shrink": SHRINK_SINGLE_FAMILY, "conviction": "low",
                "text": (f"Only {only['label']} could be read here, so there is no "
                         f"cross-check. Everything rests on one body of data, which is "
                         f"exactly the situation this app exists to avoid.")}

    if price["side"] and price["side"] == filings["side"]:
        direction = "constructive" if price["side"] > 0 else "negative"
        return {"state": "agree", "shrink": SHRINK_AGREE, "conviction": "high",
                "text": (f"Both bodies of data point the same {direction} way. That is the "
                         f"strongest thing this app can say, because the price record and "
                         f"the filings read different data.")}

    if price["side"] and filings["side"]:
        up = "price and volume" if price["side"] > 0 else "the filings"
        down = "the filings" if price["side"] > 0 else "price and volume"
        return {"state": "disagree", "shrink": SHRINK_DISAGREE, "conviction": "low",
                "text": (f"They disagree: {up} read constructively while {down} do not. "
                         f"The disagreement is the finding, and nothing here can settle "
                         f"which side is right — which is why the score is pulled hard "
                         f"toward neutral.")}

    active = price if price["side"] else filings
    quiet = filings if price["side"] else price
    return {"state": "oneNeutral", "shrink": SHRINK_ONE_NEUTRAL, "conviction": "medium",
            "text": (f"{active['label'].capitalize()} lean one way while {quiet['label']} "
                     f"read as unremarkable. One body of data is carrying this.")}


def _penalties(pretrade_result: Optional[dict]) -> list[dict]:
    """Points off for each pre-trade flag, scaled by how rarely it fires.

    Reads `flags` only. `baseConditions` cost nothing, by `pretrade.py`'s own
    argument: a condition firing on a third of a universe is a description of the
    equity market and charging a company for it manufactures a finding out of a
    base rate.
    """
    out = []
    for flag in (pretrade_result or {}).get("flags") or []:
        explanation = flag.get("explain") or {}
        rate = _finite(flag.get("firingRate"))
        # An uncalibrated flag never reaches here — `pretrade.assess` drops it
        # rather than rendering it — but a caller could hand us a hand-built
        # payload, and an unmeasured condition must not be able to cost points.
        if rate is None:
            continue
        # `classification` is the authority on whether this is a flag or a base
        # condition; `assess` already sorted them into separate lists, and
        # re-deriving it from the rate here would let the two disagree.
        if flag.get("classification") == "base":
            continue
        rarity = _clamp(1.0 - rate / BASE_RATE_MAX, 0.0, 1.0)
        band = explanation.get("band") or flag.get("band")
        scale = CAUTION_PENALTY_SCALE if band == "caution" else 1.0
        points = MAX_FLAG_PENALTY * rarity * scale
        if points <= 0.05:
            continue
        scope = flag.get("universeLabel") or "the calibration universe"
        rarity_words = ("a genuinely uncommon condition" if rate < 0.10
                        else "not especially rare, so it costs little")
        out.append({
            "id": flag.get("id"),
            "label": explanation.get("label") or flag.get("id"),
            "band": band,
            "where": flag.get("where"),
            "firingRate": rate,
            "points": round(points, 2),
            "reading": explanation.get("reading"),
            "why": f"Fires on {rate * 100:.0f}% of {scope} — {rarity_words}.",
        })
    out.sort(key=lambda entry: -entry["points"])
    return out


# ============================================================================ #
# Gates — facts about tradeability, which no amount of signal overrides
# ============================================================================ #
def _gates(liquidity: Optional[dict], price: Optional[float], market: str,
           legs: dict, available: int,
           turnover_floor: Optional[float] = None) -> list[dict]:
    market = (market or "US").upper()
    floor = turnover_floor if turnover_floor is not None else TURNOVER_FLOOR.get(market, 0.0)
    gates: list[dict] = []

    turnover = _finite((liquidity or {}).get("medianDollarVolume"))
    if turnover is None:
        gates.append({
            "id": "turnoverUnknown", "action": "NO_ACTION",
            "label": "Turnover could not be measured",
            "detail": ("No usable volume history, so there is no way to tell whether an "
                       "order would fill. That is not the same as illiquid — it is "
                       "unmeasured, and unmeasured is not tradeable either."),
        })
    elif turnover < floor:
        gates.append({
            "id": "illiquid", "action": "NO_ACTION",
            "label": "Below the turnover floor",
            "detail": (f"Median daily turnover is about {turnover:,.0f} against a floor of "
                       f"{floor:,.0f}. A personal order would be a visible share of the "
                       f"day's volume and the spread would cost more than any signal here "
                       f"is worth."),
        })

    tick = TICK_FLOOR.get(market)
    if tick is not None and price is not None and price <= tick:
        gates.append({
            "id": "tickFloor", "action": "NO_ACTION",
            "label": "Resting on the minimum tick",
            "detail": (f"The price is at or below the exchange's minimum tick ({tick:,.0f}). "
                       f"It is being pinned rather than priced, and every percentile "
                       f"computed from that series is an artifact of the floor."),
        })

    if available < MIN_COMPONENTS:
        gates.append({
            "id": "insufficientEvidence", "action": "NO_ACTION",
            "label": "Too few lenses returned",
            "detail": (f"{available} of {len(COMPONENTS)} components read. Below "
                       f"{MIN_COMPONENTS} there is no blend, only a single lens wearing a "
                       f"composite's name."),
        })

    quality = _leg(legs, "quality") or {}
    altman = (quality.get("altman") or {}).get("band")
    beneish = (quality.get("beneish") or {}).get("band")
    if altman == "distress" and beneish == "flagged":
        gates.append({
            "id": "distressAndAccruals", "action": "AVOID",
            "label": "Distress zone and flagged accruals together",
            "detail": ("Altman puts the balance sheet in the distress zone and Beneish "
                       "flags the accrual pattern. Either alone is a caution; together "
                       "they are the combination that most often precedes a restatement, "
                       "and no price signal offsets it."),
        })
    elif altman == "distress":
        gates.append({
            "id": "distress", "action": "HOLD",
            "label": "Inside the distress zone",
            "detail": ("Altman puts the balance sheet inside the distress zone. The score "
                       "is capped at hold: on an emerging market this screen has a real "
                       "false-positive rate, so it blocks a buy rather than forcing a sale."),
        })
    return gates


def _cap_action(action: str, ceiling: str) -> str:
    return ACTION_ORDER[min(ACTION_ORDER.index(action), ACTION_ORDER.index(ceiling))]


# ============================================================================ #
# Position sizing — arithmetic, and only arithmetic
# ============================================================================ #
def _sizing(action: str, annual_vol: Optional[float], risk_budget: float,
            max_weight: float) -> dict:
    """Inverse-volatility weight for a name the scan put in the buy bands.

    THIS IS NOT A RECOMMENDATION AND IT IS NOT CALIBRATED TO ANYTHING. It is one
    line of arithmetic — risk budget divided by annualised volatility, capped —
    which answers "what size makes this position contribute the same risk as the
    others" and answers nothing else. It does not know the holder's other
    positions, their tax position, their horizon or their income. Reported
    because a scanner that ranks names and says nothing about size implicitly
    suggests equal weighting, and equal weighting across names whose volatility
    differs threefold is itself a strong and unstated bet.
    """
    if action not in {"BUY", "STRONG_BUY"}:
        return {"applicable": False,
                "reason": "Sizing is only computed for names in the buy bands."}
    vol = _finite(annual_vol)
    if vol is None or vol <= 0:
        return {"applicable": False,
                "reason": "Volatility could not be measured, so no size can be computed."}
    raw = risk_budget / vol
    return {
        "applicable": True,
        "annualVolatility": vol,
        "riskBudget": risk_budget,
        "uncappedWeight": raw,
        "weight": min(raw, max_weight),
        "capped": raw > max_weight,
        "basis": (f"Inverse volatility: a {risk_budget * 100:.1f}% annualised risk budget "
                  f"divided by {vol * 100:.0f}% volatility, capped at "
                  f"{max_weight * 100:.0f}% of the sleeve. Arithmetic, not advice."),
    }


# ============================================================================ #
# The whole thing
# ============================================================================ #
def score(ticker: str,
          legs: Optional[dict] = None,
          rank_row: Optional[dict] = None,
          pretrade_result: Optional[dict] = None,
          liquidity: Optional[dict] = None,
          market: str = "US",
          name: Optional[str] = None,
          annual_volatility: Optional[float] = None,
          latest_close: Optional[float] = None,
          risk_budget: float = 0.02,
          max_weight: float = 0.10,
          turnover_floor: Optional[float] = None) -> dict:
    """One name's score, action and the arithmetic that produced both.

    `legs` is the `/api/confluence` shape — each leg carrying its own `ok` flag —
    so a failed lens becomes a stated gap rather than an exception, and every
    figure quoted here is one a panel would render.

    Nothing is imputed. A component that could not be read is absent from the
    blend, its weight is renormalised away, and the coverage that results shrinks
    the final score toward neutral. Filling a gap with 50 would move a name
    toward the middle of the pack and call it a measurement.
    """
    legs = legs or {}

    components: list[dict] = []
    for spec in COMPONENTS:
        reading = READERS[spec["key"]](legs, rank_row)
        effective = spec["weight"] * reading.get("weightScale", 1.0)
        components.append({
            **{k: spec[k] for k in ("key", "label", "family", "evidence", "detail")},
            "baseWeight": spec["weight"],
            "effectiveWeight": effective if reading["available"] else 0.0,
            "score": reading["score"],
            "available": reading["available"],
            "refused": reading.get("refused", False),
            "reason": reading.get("reason"),
            "reading": reading.get("detail"),
        })

    available = [c for c in components if c["available"]]
    intended_weight = sum(c["baseWeight"] for c in components)
    coverage = (sum(c["baseWeight"] for c in available) / intended_weight
                if intended_weight else 0.0)

    price_family = _family_score(components, "price")
    filings_family = _family_score(components, "filings")
    agreement = _agreement(price_family, filings_family)

    # THE TWO FAMILIES ARE WEIGHTED EQUALLY, not by how many components each
    # happened to contribute. Three price components and two filings ones are
    # still two bodies of data, and letting the count decide would give the price
    # record more say purely because it is cheaper to compute.
    families = [f for f in (price_family, filings_family) if f is not None]
    raw = sum(f["score"] for f in families) / len(families) if families else None

    coverage_shrink = SHRINK_COVERAGE_FLOOR + (1.0 - SHRINK_COVERAGE_FLOOR) * coverage
    shrink = agreement["shrink"] * coverage_shrink
    shrunk = 50.0 + (raw - 50.0) * shrink if raw is not None else None

    penalties = _penalties(pretrade_result)
    penalty_total = min(MAX_TOTAL_PENALTY, sum(p["points"] for p in penalties))
    final = _clamp(shrunk - penalty_total) if shrunk is not None else None

    gates = _gates(liquidity, latest_close, market, legs, len(available),
                   turnover_floor=turnover_floor)

    if final is None:
        action, action_label, tone = "NO_ACTION", "No action", "none"
    else:
        action, action_label, tone = next(
            (a, label, t) for threshold, a, label, t in BANDS if final >= threshold)
        if action == "STRONG_BUY" and agreement["conviction"] != STRONG_BUY_REQUIRES:
            action, action_label, tone = "BUY", "Buy", "good"

    gate_reasons = []
    for gate in gates:
        if gate["action"] == "NO_ACTION":
            action, action_label, tone = "NO_ACTION", "No action", "none"
        elif action != "NO_ACTION":
            action = _cap_action(action, gate["action"])
            action_label, tone = next(
                (label, t) for _, a, label, t in BANDS if a == action)
        gate_reasons.append(gate["label"])

    return {
        "ticker": ticker,
        "name": name or ticker,
        "market": (market or "US").upper(),
        "action": action,
        "actionLabel": action_label,
        "tone": tone,
        "score": None if final is None else round(final, 1),
        "rawScore": None if raw is None else round(raw, 1),
        "shrunkScore": None if shrunk is None else round(shrunk, 1),
        "conviction": agreement["conviction"],
        # WHETHER THIS SCORE RESTS ON A CROSS-CHECK AT ALL, as one boolean a
        # table can show in a column. `conviction` already carries it, but
        # `conviction: low` has three causes and only one of them is "no second
        # body of data agreed or disagreed, because there was no second body of
        # data". That distinction is the app's central claim, so it gets its own
        # field rather than being inferred from a word that also means other
        # things. On IDX small caps it is the common failure: Yahoo publishes no
        # statements, both filings lenses go quiet, and a name reaches the buy
        # bands on price history alone.
        "crossChecked": price_family is not None and filings_family is not None,
        "familiesRead": len(families),
        "coverage": round(coverage, 3),
        "componentsRead": len(available),
        "componentsTotal": len(COMPONENTS),
        "components": components,
        "families": {"price": price_family, "filings": filings_family},
        "agreement": agreement,
        "shrink": {
            "agreement": agreement["shrink"],
            "coverage": round(coverage_shrink, 3),
            "combined": round(shrink, 3),
            "text": _shrink_text(agreement, coverage, shrink, raw, shrunk),
        },
        "penalties": penalties,
        "penaltyTotal": round(penalty_total, 2),
        "penaltyCapped": sum(p["points"] for p in penalties) > MAX_TOTAL_PENALTY,
        "gates": gates,
        "gatedBy": gate_reasons,
        "latestClose": _finite(latest_close),
        "turnover": _finite((liquidity or {}).get("medianDollarVolume")),
        "sizing": _sizing(action, annual_volatility, risk_budget, max_weight),
        "reasons": _reasons(components, agreement, penalties, gates, action),
        "caveat": (
            "A ranking of the evidence available, not a forecast and not investment "
            "advice. This app measured whether its own price ranking predicts returns "
            "and could not detect that it does — see the provenance note that ships "
            "with every scan. Nothing here knows anything about this company that is "
            "not in its price history or its last filing."),
    }


def _shrink_text(agreement: dict, coverage: float, shrink: float,
                 raw: Optional[float], shrunk: Optional[float]) -> str:
    if raw is None or shrunk is None:
        return "Nothing was scored, so there was nothing to shrink."
    if shrink >= 0.995:
        return (f"The blended {raw:.0f} stands as it is: both bodies of data read, both "
                f"point the same way, and every component was available.")
    return (f"The blended {raw:.0f} was pulled to {shrunk:.0f} — {agreement['state']} "
            f"agreement and {coverage * 100:.0f}% component coverage together carry "
            f"{shrink:.2f} of the weight a complete, agreeing reading would.")


def _reasons(components: list[dict], agreement: dict, penalties: list[dict],
             gates: list[dict], action: str) -> list[str]:
    """Why this name landed where it did, strongest first.

    A score with no decomposition cannot be argued with, which is the property
    `technical.long_term_view` refuses a score for. This is the decomposition.
    """
    out: list[str] = []
    for gate in gates:
        out.append(f"{gate['label']}. {gate['detail']}")

    out.append(agreement["text"])

    scored = sorted((c for c in components if c["available"]),
                    key=lambda c: -abs(c["score"] - 50.0) * c["effectiveWeight"])
    for component in scored[:3]:
        direction = ("supports" if component["score"] > NEUTRAL_HIGH
                     else "argues against" if component["score"] < NEUTRAL_LOW
                     else "is neutral on")
        out.append(f"{component['label']} {direction} it at {component['score']:.0f}/100 — "
                   f"{component['reading']}")

    missing = [c for c in components if not c["available"]]
    for component in missing:
        prefix = "Refused" if component["refused"] else "Not read"
        out.append(f"{prefix}: {component['label']} — {component['reason']}. "
                   f"Its weight was removed from the blend rather than filled in.")

    for penalty in penalties[:3]:
        out.append(f"-{penalty['points']:.1f} for \"{penalty['label']}\". {penalty['why']}")

    if action == "NO_ACTION" and not gates:
        out.append("Nothing scored, so there is no action to take.")
    return out


# ============================================================================ #
# Provenance — the measurement that says what this ordering is worth
# ============================================================================ #
def provenance() -> dict:
    """The published null result, for a caller that must print it.

    A score that orders a universe implies, without ever saying so, that the
    order means something. This app measured that claim and could not confirm
    it. Every surface rendering a score is required to carry this — it is not a
    footnote, it is the calibration of everything above.

    Read from `ranking.validation` rather than restated, so it cannot drift from
    the artifact the published panel prints.
    """
    from . import ranking

    measured = ranking.validation()
    if not measured.get("available"):
        return {
            "available": False,
            "headline": ("This ranking's predictive power has NOT been measured on this "
                         "checkout — `backtest_results.json` is missing. Treat every "
                         "score below as an ordering of evidence with no established "
                         "relationship to returns whatsoever."),
        }
    return {
        "available": True,
        "measuredOn": measured.get("measuredOn"),
        "years": measured.get("years"),
        "tests": measured.get("tests"),
        "significant": measured.get("significant"),
        "headline": measured.get("headline"),
        "appliesTo": ("the price-and-volume composite, which is one of five components "
                      "below and the only one whose predictive power this app has "
                      "measured at all. The four lens components have not been "
                      "backtested as a combined score, and this scan does not claim "
                      "they have."),
    }
