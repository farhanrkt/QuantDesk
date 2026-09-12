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

It also reads two things the published view does not: the heavy-session tape
(`tape.py`) and the share register (`ownership.py`). Both are new bodies of
evidence rather than new presentations of old ones, and both arrive with their
own refusals — the tape is not a broker summary and says so on every surface
that renders it, and the register's independence from the filings is measured
rather than claimed.
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
1. EIGHT COMPONENTS, each 0-100, each read from something that has already run.
   Nothing here recomputes anything — same contract as `explain.for_synthesis`
   and for the same reason: the score must quote the figures the panels render,
   and a parallel computation would eventually drift from them.

2. THREE FAMILY SCORES, not eight component scores averaged. Eight measurements
   over three bodies of data are not eight opinions — `explain._family_votes`
   has said so since it shipped.

     price and volume   the cross-sectional rank, the long-horizon trend, order
                        flow, and the heavy-session tape reading
     the filings        the valuation model and the accounting screens
     the share register free float and the share-count trend

   Averaging all eight would give the price record four votes to the filings'
   two purely because price signals are cheaper to compute.

   THE THIRD FAMILY'S INDEPENDENCE CLAIM IS DELIBERATELY NARROWER THAN THE
   OTHERS'. The share count is printed in the filings; what is actually true is
   that no filings lens reads it. So it is measured rather than asserted —
   `family_overlap` reports the realised rank correlation across a scan, and on
   a real IDX sweep the three read +0.07 to +0.10 against each other.

3. ONE RAW SCORE: the families, one vote each, scaled only by how much of its
   own evidence each family actually brought. Each body of data gets one vote;
   a family reporting on half its evidence makes half a claim. That is the app's
   central claim expressed as arithmetic.

4. SHRINKAGE TOWARD 50, by how much independent evidence there actually is.
   Families that disagree, a family that never read, components that were
   missing — each pulls the score toward neutral rather than being silently
   dropped. A 78 computed from two agreeing families and a 78 computed from one
   family with three gaps are not the same claim, and the second must not print
   as though it were.

   A SILENT FAMILY IS NOT A DISSENTING ONE, and conflating those two was a real
   mistake in the two-to-three-family change. The share register reads neutral
   for the median listing by construction, so requiring all three families to
   take a direction dropped high conviction to zero names out of twenty-nine on
   a real IDX30 sweep — and the compression was invisible: every score simply
   moved toward 50 and nothing said why. The bar is TWO INDEPENDENT SOURCES
   ACTIVELY AGREEING, with abstentions named rather than counted.

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

import json
from pathlib import Path
from typing import Optional

from . import explain as E
from . import ownership

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
        "key": "tape",
        "label": "Who wins the heavy days",
        "family": "price",
        "evidence": "weak",
        "weight": 0.4,
        "detail": ("Whether this name's heaviest sessions close nearer the high of their "
                   "range than its ordinary ones, tested against its own market's median. "
                   "The readable shadow of what bandarmology looks for — it cannot say WHO "
                   "bought, because that needs the exchange's broker summary and no "
                   "provider here carries it. Graded weak because it is measured: the test "
                   "fires on 13% of Indonesian listings against 5% expected by chance, and "
                   "on 4% of US large caps, which IS chance."),
    },
    {
        "key": "patterns",
        "label": "Chart formations",
        "family": "price",
        "evidence": "weak",
        "weight": 0.4,
        "detail": ("Head-and-shoulders, broadening, triangle, rectangle and double "
                   "formations, defined by Lo, Mamaysky and Wang's kernel-regression "
                   "method so two implementations agree. Scored ONLY where a formation's "
                   "forward return survived a correction across every pattern and horizon "
                   "tested — and scored by the measured sign, not the textbook one. On "
                   "both markets measured, the survivors all predicted UNDERperformance "
                   "whichever way the chart books read them."),
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
    {
        "key": "float",
        "label": "Free float and control",
        "family": "register",
        "evidence": "weak",
        "weight": 0.4,
        "detail": ("How much of the company is not held by insiders, and how much of that "
                   "turns over in a session. The structural precondition for a stock that "
                   "one holder can walk. Graded weak deliberately: a thin float is a "
                   "strong statement about whether a position can be exited and a weak one "
                   "about what the price does next."),
    },
    {
        "key": "issuance",
        "label": "Share count trend",
        "family": "register",
        "evidence": "moderate",
        "weight": 0.7,
        "detail": ("Whether the number of shares is growing or being retired, annualised "
                   "over three years, with the largest single step named. Net share "
                   "issuance is among the better replicated cross-sectional effects, and "
                   "on IDX it is not subtle — a rights issue dilutes a holder who does not "
                   "subscribe, and no other lens here would notice."),
    },
]

COMPONENT_BY_KEY = {c["key"]: c for c in COMPONENTS}

# THE THIRD FAMILY, AND THE HONEST LIMIT OF THE CLAIM MADE FOR IT.
#
# The app's central claim has always been that the price record and the filings
# share no inputs, so agreement between them is not one fact counted twice. The
# register is a genuine third thing — nothing in `ranking.py` sees a float, and
# none of Piotroski, Altman, Beneish or the discounted cash flow reads a share
# count trend — but the claim must be narrower than the one made for the first
# two, because the share count is PRINTED IN THE FILINGS. What is true is that
# no lens here reads it, not that it is independent by construction.
#
# So the assumption is not asserted, it is measured: `family_overlap` computes
# the realised rank correlation between family scores across a scan, and the
# scanner prints it. If the register turns out to move with the filings, that
# measurement is where it will show up.
FAMILY_LABEL = {"price": "price and volume", "filings": "the filings",
                "register": "the share register"}
FAMILIES = ("price", "filings", "register")

# The total evidence each family can bring when everything reads. Used only to
# compute a family's own coverage — see `_family_score` — never to weight one
# family against another.
FAMILY_BASE_WEIGHT = {
    family: sum(c["weight"] for c in COMPONENTS if c["family"] == family)
    for family in FAMILIES
}

# A family reporting on half its evidence does not get a whole vote. The floor
# stops a family with one thin component from vanishing entirely, because half a
# body of data still says something the other two cannot.
#
# THIS IS NOT "THE COUNT DECIDES". The count of components in a family is
# deliberately not consulted anywhere; what is consulted is how much of the
# evidence that family was SUPPOSED to bring actually arrived, which is the same
# coverage rule applied globally in `score` and per-signal in `ranking.py`.
MIN_FAMILY_VOTE = 0.5

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

# How far the presence of ANY chart formation moves the score inside
# `scripts/backtest_verdict.py`, which cannot use the live path.
#
# The live component scores only formations whose forward returns survived a
# correction — and those survivors were chosen using the whole sample, so
# feeding them back into a backtest of that same sample would be circular. The
# backtest therefore scores presence alone with a fixed sign and a fixed size.
# Eight points is roughly what a -3% measured effect earns through
# `PATTERN_POINTS_PER_PCT`, so the two paths are the same order of magnitude
# without the second one selecting on its own answer.
PATTERN_BACKTEST_POINTS = 8.0

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


def read_tape(tape_result: Optional[dict]) -> dict:
    """The heavy-session reading, which is usually that there is nothing to read.

    `tape.read` returns "unreadable" for most names by design — against a
    calibrated null the test fires on about one Indonesian listing in seven and
    one US listing in twenty-five. An unreadable tape is NOT unavailable: the
    test ran, it produced a number, and the number was ordinary. It scores near
    neutral and says so, which is different from having no reading at all.
    """
    if not isinstance(tape_result, dict):
        return _unavailable("the tape was not read for this name")
    if not tape_result.get("available"):
        return _unavailable(tape_result.get("reason") or "the tape could not be read")
    if not tape_result.get("calibrated"):
        # A direction computed against the wrong null is worse than no
        # direction. `tape.py` already refuses to report one; this refuses to
        # score it, so an uncalibrated market cannot contribute a component at
        # all rather than contributing a confident 50.
        return _unavailable(
            "this market has no measured tape baseline, so no direction can be read "
            "from it — run scripts/calibrate_tape.py")

    score = _finite(tape_result.get("score"))
    if score is None:
        return _unavailable("the tape produced no usable score")
    return {"score": score, "available": True, "reason": None, "refused": False,
            "weightScale": 1.0, "detail": tape_result.get("reading")}


def read_patterns(pattern_result: Optional[dict]) -> dict:
    """Chart formations, which contribute nothing until they have been measured.

    `patterns.read` sets `usable` only when at least one detected formation has
    a forward return that survived a false-discovery correction across every
    pattern and horizon tested. Anything else — no formation, no calibration, or
    formations whose measurement came out null — is UNAVAILABLE rather than
    neutral, because "we looked and found nothing that predicts" and "we found a
    shape that predicts nothing" are the same contribution and it is zero.
    """
    # EVERY ABSENCE HERE IS A REFUSAL, NOT A GAP, AND THE DISTINCTION IS LOAD
    # BEARING. `scan_market` warns when a component is MISSING on many names,
    # because a failed fetch removes weight from the blend and lifts the names
    # that lens would have marked down. It flagged `patterns` on a US sweep and
    # was wrong: all 1,553 absences were "no formation completed in the window"
    # or "formations found, none that survived correction" — the module working
    # exactly as designed, on a market where most names are simply not chopping.
    #
    # None of these states would change if the scan ran slower, which is the
    # test that separates the two. A false alarm on a healthy component is how
    # the real alarm — `quality` at 56%, genuinely rate-limited — gets ignored.
    if not isinstance(pattern_result, dict):
        return _unavailable("chart formations were not read for this name",
                            refused=True)
    if not pattern_result.get("available"):
        return _unavailable(pattern_result.get("reason")
                            or "not enough history to read formations", refused=True)
    if not pattern_result.get("calibrated"):
        return _unavailable(
            "this market has no measured pattern study, so a formation cannot be "
            "scored — run scripts/calibrate_patterns.py", refused=True)
    if not pattern_result.get("usable"):
        found = len(pattern_result.get("detections") or [])
        return _unavailable(
            f"{found} formation{'' if found == 1 else 's'} found, none with a forward "
            f"return that survived correction on this market"
            if found else "no formation completed in the scanned window",
            refused=True)

    score = _finite(pattern_result.get("score"))
    if score is None:
        return _unavailable("the formations produced no usable score")
    return {"score": score, "available": True, "reason": None, "refused": False,
            "weightScale": 1.0, "detail": pattern_result.get("reading")}


def read_float(register_result: Optional[dict]) -> dict:
    """How much of the company is actually for sale."""
    if not isinstance(register_result, dict) or not register_result.get("available"):
        reason = (register_result or {}).get("reason")
        return _unavailable(reason or "the share register was not read")
    floats = register_result.get("float") or {}
    if not floats.get("available"):
        return _unavailable(floats.get("reason") or "no float figure came back")
    score = _finite(floats.get("score"))
    if score is None:
        return _unavailable("the float could not be scored")

    detail = floats.get("reading") or ""
    turnover = _finite(register_result.get("floatTurnover"))
    if turnover is not None and turnover > 0:
        share = f"{turnover * 100:.3f}%" if turnover < 1e-4 else f"{turnover * 100:.2f}%"
        detail += f" A session turns over {share} of that float."
    return {"score": score, "available": True, "reason": None, "refused": False,
            "weightScale": 1.0, "detail": detail.strip()}


def read_issuance(register_result: Optional[dict]) -> dict:
    """Whether the share count is growing, and by how much a year."""
    if not isinstance(register_result, dict) or not register_result.get("available"):
        reason = (register_result or {}).get("reason")
        return _unavailable(reason or "the share register was not read")
    issued = register_result.get("issuance") or {}
    if not issued.get("available"):
        return _unavailable(issued.get("reason") or "no share-count history came back")
    score = _finite(issued.get("score"))
    if score is None:
        return _unavailable("the share count could not be scored")

    # A three-year trend read from four filing dates is a weaker version of the
    # same statement than one read from twenty. The WEIGHT bends rather than the
    # score, for the reason `read_price_rank` bends it: renormalising the score
    # would move a thinly reported name toward the middle and call it a finding.
    observations = issued.get("observations") or 0
    scale = 0.6 if observations < 8 else 1.0
    return {"score": score, "available": True, "reason": None, "refused": False,
            "weightScale": scale, "detail": issued.get("reading")}


READERS = {
    "priceRank": lambda ctx: read_price_rank(ctx.get("rank_row")),
    "trend": lambda ctx: read_trend(ctx.get("legs") or {}),
    "flow": lambda ctx: read_flow(ctx.get("legs") or {}),
    "tape": lambda ctx: read_tape(ctx.get("tape")),
    "patterns": lambda ctx: read_patterns(ctx.get("patterns")),
    "value": lambda ctx: read_value(ctx.get("legs") or {}),
    "quality": lambda ctx: read_quality(ctx.get("legs") or {}),
    "float": lambda ctx: read_float(ctx.get("register")),
    "issuance": lambda ctx: read_issuance(ctx.get("register")),
}


# ============================================================================ #
# Families, agreement, shrinkage
# ============================================================================ #
def _family_score(components: list[dict], family: str) -> Optional[dict]:
    """One weighted mean per BODY OF DATA, over the components that read.

    `vote` is how much of a whole vote this family gets when the families are
    combined. It is its own COVERAGE — how much of the evidence it was supposed
    to bring actually arrived — floored so a half-read family still speaks. See
    `MIN_FAMILY_VOTE` for why this is not the component count in disguise.
    """
    members = [c for c in components if c["family"] == family and c["available"]]
    if not members:
        return None
    total_weight = sum(c["effectiveWeight"] for c in members)
    if total_weight <= 0:
        return None

    score = sum(c["score"] * c["effectiveWeight"] for c in members) / total_weight
    side = 1 if score > NEUTRAL_HIGH else -1 if score < NEUTRAL_LOW else 0
    base = FAMILY_BASE_WEIGHT.get(family) or 0.0
    read_base = sum(c["baseWeight"] for c in members)
    coverage = (read_base / base) if base > 0 else 0.0
    return {"family": family, "label": FAMILY_LABEL[family], "score": score,
            "side": side, "members": [c["key"] for c in members],
            "weight": total_weight, "coverage": round(coverage, 3),
            "vote": round(max(MIN_FAMILY_VOTE, min(1.0, coverage)), 3)}


def _agreement(families: dict) -> dict:
    """What the bodies of data add up to, and how much of it to believe.

    THE BRANCHES ARE THE SAME FOUR `explain._agreement` PRINTS, generalised from
    two families to three. That correspondence is deliberate and load-bearing:
    the private scanner and the published rail must not be able to reach opposite
    readings of the same evidence, so the states are the same states and only the
    arithmetic behind "they agree" had to change.

    With three families "they agree" now means every family that took a
    direction took the SAME direction, and one family pointing the other way is
    a disagreement even when the other two concur. That is the conservative
    reading and it is the right one here: the whole argument for combining
    independent sources is that a dissent from one of them is information, not
    an outvoted minority.
    """
    present = [f for f in families.values() if f is not None]
    if not present:
        return {"state": "none", "shrink": 0.0, "conviction": "none",
                "text": "No lens returned a usable reading, so there is nothing to score."}

    if len(present) == 1:
        only = present[0]
        return {"state": "single", "shrink": SHRINK_SINGLE_FAMILY, "conviction": "low",
                "text": (f"Only {only['label']} could be read here, so there is no "
                         f"cross-check. Everything rests on one body of data, which is "
                         f"exactly the situation this app exists to avoid.")}

    directional = [f for f in present if f["side"] != 0]
    neutral = [f for f in present if f["side"] == 0]
    names = ", ".join(f["label"] for f in present)

    if not directional:
        return {"state": "allNeutral", "shrink": SHRINK_ONE_NEUTRAL, "conviction": "medium",
                "text": (f"All {len(present)} bodies of data read as unremarkable "
                         f"({names}). Nothing here argues either way, which is a finding "
                         f"rather than a gap.")}

    sides = {f["side"] for f in directional}
    if len(sides) > 1:
        up = ", ".join(f["label"] for f in directional if f["side"] > 0)
        down = ", ".join(f["label"] for f in directional if f["side"] < 0)
        return {"state": "disagree", "shrink": SHRINK_DISAGREE, "conviction": "low",
                "text": (f"They disagree: {up} read constructively while {down} do not. "
                         f"The disagreement is the finding, nothing here can settle which "
                         f"side is right, and that is why the score is pulled hard toward "
                         f"neutral.")}

    direction = "constructive" if directional[0]["side"] > 0 else "negative"
    quiet = ", ".join(f["label"] for f in neutral)
    active = ", ".join(f["label"] for f in directional)

    # A SILENT SOURCE IS NOT A DISSENTING ONE, and conflating the two was a real
    # mistake in the two-to-three-family change. With two families, "one of them
    # is neutral" meant half the evidence had no opinion. With three it stopped
    # meaning that: the share register reads NEUTRAL for the median listing by
    # construction — an ordinary float and a flat share count is what most
    # companies have — so requiring all three to take a direction made high
    # conviction almost unreachable. On a real IDX30 sweep it fell to zero names
    # out of twenty-nine, and the compression was invisible in the output; every
    # score simply moved toward 50 and nothing said why.
    #
    # The bar is now TWO INDEPENDENT SOURCES ACTIVELY AGREEING, which is the
    # claim the cross-check was always about. A third source with nothing to say
    # neither adds to that nor takes from it, and is named in the sentence so the
    # reader can see it abstained rather than concurred.
    if len(directional) >= 2:
        # Singular where one family abstained, plural where several did. The
        # labels are noun phrases ("the share register"), so the verb has to
        # follow the count of them rather than being written once either way.
        plural = len(neutral) > 1
        aside = (f" {quiet.capitalize()} "
                 f"{'read' if plural else 'reads'} as unremarkable and "
                 f"{'neither support nor contradict' if plural else 'neither supports nor contradicts'} "
                 f"them." if neutral else "")
        return {"state": "agree", "shrink": SHRINK_AGREE, "conviction": "high",
                "text": (f"{len(directional)} independent bodies of data point the same "
                         f"{direction} way ({active}).{aside} That is the strongest thing "
                         f"this app can say, because those sources are not reading the "
                         f"same numbers.")}

    return {"state": "oneNeutral", "shrink": SHRINK_ONE_NEUTRAL, "conviction": "medium",
            "text": (f"{active.capitalize()} lean {direction} while {quiet} read as "
                     f"unremarkable. One body of data is carrying this, and the others "
                     f"are silent rather than opposed.")}


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
           turnover_floor: Optional[float] = None,
           register_result: Optional[dict] = None,
           tape_result: Optional[dict] = None,
           structure_result: Optional[dict] = None) -> list[dict]:
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

    # --- the register gates ------------------------------------------------
    # THESE ARE TRADEABILITY AND STRUCTURE, NOT OPINION, which is why they sit
    # with the turnover floor rather than costing points. A 6% free float is not
    # a company with poor prospects; it is a company whose quoted price is a
    # handful of holders' opinion and whose exit is not guaranteed to exist.
    register = register_result if isinstance(register_result, dict) else {}
    floats = (register.get("float") or {}) if register.get("available") else {}
    if floats.get("available"):
        value = _finite(floats.get("freeFloat"))
        if value is not None and value < ownership.FLOAT_CRITICAL:
            gates.append({
                "id": "microFloat", "action": "HOLD",
                "label": "Almost nothing is free to trade",
                # ONE DECIMAL, because whole percentages put this sentence at war
                # with itself. HMSP.JK's 7.5% float rendered as "Only 8% ... under
                # the 8% line", which reads as an arithmetic error rather than as
                # rounding, in the one sentence explaining why a good score was
                # capped.
                "detail": (f"Only {value * 100:.1f}% of the shares sit outside insider "
                           f"hands, under the {ownership.FLOAT_CRITICAL * 100:.0f}% line. "
                           f"The quoted price is what a handful of holders agree it is, "
                           f"one seller moves it, and a position that has to be exited "
                           f"may not find the other side. Capped at hold rather than "
                           f"refused: this describes the instrument, not the business."),
            })

    issued = (register.get("issuance") or {}) if register.get("available") else {}
    if issued.get("available"):
        annual = _finite(issued.get("annualised"))
        if annual is not None and annual >= ownership.ISSUANCE_SEVERE:
            step = ""
            if issued.get("largestStep") and issued["largestStep"] > 0.1:
                step = (f" The largest single step was +{issued['largestStep'] * 100:.0f}%"
                        + (f" around {issued['largestStepAt']}."
                           if issued.get("largestStepAt") else "."))
            gates.append({
                "id": "heavyIssuance", "action": "HOLD",
                "label": "The share count is growing fast",
                "detail": (f"Shares outstanding have grown {annual * 100:.0f}% a year over "
                           f"{issued.get('years', 0):.1f} years.{step} A holder who does "
                           f"not subscribe to each issue owns a shrinking share of the "
                           f"same company, and every per-share figure elsewhere is "
                           f"measured against a moving denominator."),
            })

    # --- volume concentration ----------------------------------------------
    tape_payload = tape_result if isinstance(tape_result, dict) else {}
    conc = (tape_payload.get("concentration") or {}) if tape_payload.get("available") else {}
    if conc.get("band") == "severe" and conc.get("calibrated"):
        top = _finite(conc.get("topFiveShare"))
        effective = _finite(conc.get("effectiveDays"))
        gates.append({
            "id": "episodicVolume", "action": "HOLD",
            "label": "The year happened in a handful of sessions",
            "detail": (f"{(top or 0) * 100:.0f}% of the year's volume traded on its five "
                       f"biggest days"
                       + (f", making the window worth about {effective:.0f} sessions of "
                          f"even trading" if effective else "")
                       + f" — past the {(conc.get('severe') or 0) * 100:.0f}% line that "
                         f"only one name in twenty of this market clears. A position "
                         f"cannot be sized against liquidity that only shows up on the "
                         f"days everyone else also wants to trade."),
        })

    # --- the entry, as distinct from the asset -----------------------------
    # THE ONLY GATE HERE THAT IS ABOUT THE PRICE ON THE SCREEN RATHER THAN THE
    # COMPANY, and it is worded to say so. Everything else in this function is a
    # fact about the security or the register; this one says the company may be
    # perfectly sound and that buying it at today's price is still a poor trade,
    # because the nearest ceiling is three times closer than the floor whose
    # failure would mean the reason for the trade was wrong.
    #
    # `riskTooWide` GATES TOO, AND LEAVING IT OUT WAS A REAL BUG. `structure._band`
    # returns the FIRST state that matches and tests the risk distance BEFORE the
    # ratio, so `riskTooWide` and `bad` are mutually exclusive labels rather than
    # a scale — which meant a name whose nearest floor was 35% below took the
    # more severe diagnosis and escaped the gate entirely, while a name with a
    # merely lopsided ratio was stopped.
    #
    # It was found on the highest-scoring name in a full IDX sweep: SRSN read
    # STRONG_BUY at 74.6 with its only defended floor 35.2% underneath, and
    # nothing fired. `MAX_USEFUL_RISK` exists precisely because past that
    # distance "the risk being measured is the whole thesis rather than a level",
    # which is not a milder problem than a poor ratio — it is the same problem
    # with no number left to describe it.
    entry = structure_result if isinstance(structure_result, dict) else {}
    if entry.get("available") and entry.get("band") in ("bad", "riskTooWide"):
        ratio = _finite(entry.get("rewardRisk"))
        risk = (_finite(entry.get("riskToSupport")) or 0) * 100
        reward = (_finite(entry.get("rewardToResistance")) or 0) * 100
        if entry.get("band") == "riskTooWide":
            detail = (f"The nearest defended floor is {risk:.1f}% below, which is too far "
                      f"to be a stop — past that distance what is being risked is the "
                      f"whole reason for the trade rather than a level, and there is no "
                      f"sensible size for the position")
        else:
            detail = (f"The nearest resistance is {reward:.1f}% overhead while the "
                      f"nearest support sits {risk:.1f}% below"
                      + (f" — about {ratio:.2f} to 1 against" if ratio is not None
                         else ""))
        gates.append({
            "id": "poorEntry", "action": "HOLD",
            "label": "Poor entry at this price",
            "detail": detail + ". This is a statement about the price, not the "
                               "company: the score above is unchanged and a different "
                               "price would clear this.",
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
          turnover_floor: Optional[float] = None,
          tape_result: Optional[dict] = None,
          register_result: Optional[dict] = None,
          pattern_result: Optional[dict] = None,
          structure_result: Optional[dict] = None) -> dict:
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
    # ONE CONTEXT OBJECT RATHER THAN A GROWING POSITIONAL SIGNATURE. Each reader
    # takes what it needs and ignores the rest, so adding a component is adding a
    # key here and a row in `COMPONENTS` — not editing every reader's arguments,
    # which is how the fifth one would silently get handed the fourth one's data.
    context = {"legs": legs, "rank_row": rank_row, "tape": tape_result,
               "register": register_result, "patterns": pattern_result}

    components: list[dict] = []
    for spec in COMPONENTS:
        reading = READERS[spec["key"]](context)
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

    scored_families = {family: _family_score(components, family) for family in FAMILIES}
    agreement = _agreement(scored_families)

    # EACH BODY OF DATA GETS ONE VOTE, not one vote per component. Four price
    # components, two filings ones and two register ones are still three bodies
    # of data, and letting the count decide would give the price record most of
    # the say purely because price signals are cheaper to compute.
    #
    # The one thing that scales a vote is that family's OWN coverage — a family
    # reporting on half its evidence is making half a claim. That is the same
    # rule applied globally below and per-signal in `ranking.py`, and it is not
    # the component count wearing a disguise: a family with one component that
    # read fully votes in full.
    present = [f for f in scored_families.values() if f is not None]
    vote_total = sum(f["vote"] for f in present)
    raw = (sum(f["score"] * f["vote"] for f in present) / vote_total
           if vote_total > 0 else None)

    coverage_shrink = SHRINK_COVERAGE_FLOOR + (1.0 - SHRINK_COVERAGE_FLOOR) * coverage
    shrink = agreement["shrink"] * coverage_shrink
    shrunk = 50.0 + (raw - 50.0) * shrink if raw is not None else None

    penalties = _penalties(pretrade_result)
    penalty_total = min(MAX_TOTAL_PENALTY, sum(p["points"] for p in penalties))
    final = _clamp(shrunk - penalty_total) if shrunk is not None else None

    gates = _gates(liquidity, latest_close, market, legs, len(available),
                   turnover_floor=turnover_floor, register_result=register_result,
                   tape_result=tape_result, structure_result=structure_result)

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
        # Two or more of the three bodies of data returned something. It stays a
        # two-family test rather than becoming a three-family one: the claim
        # "nothing cross-checked this" is about whether ANY second source spoke,
        # and requiring all three would mark a perfectly cross-checked name as
        # unchecked whenever one register field was missing.
        "crossChecked": len(present) >= 2,
        "familiesRead": len(present),
        "coverage": round(coverage, 3),
        "componentsRead": len(available),
        "componentsTotal": len(COMPONENTS),
        "components": components,
        "families": scored_families,
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
        # WHERE THE TRADE IS WRONG, beside the verdict rather than a tab away.
        # It is deliberately NOT a component: the score answers "is this worth
        # owning" and this answers "is now a sensible moment", and blending them
        # would let a tidy entry make a poor company look better.
        "structure": structure_result,
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
# Is the third family actually a third source? — measured, not asserted
# ============================================================================ #
def family_overlap(rows: list[dict]) -> dict:
    """Rank correlation between the family scores, across a whole scan.

    THE HONEST COUNTERWEIGHT TO GIVING EACH FAMILY A VOTE. This module weights
    the price record, the filings and the share register equally on the argument
    that they read different data. `ranking.signal_correlation` makes exactly
    this move for its seven price signals — it reports the measured overlap
    rather than asserting independence — and the argument applies harder here,
    because the register's independence claim is the weakest of the three: the
    share count is printed in the filings, and what is actually true is only
    that no filings lens reads it.

    So this measures it. If the register turns out to track the filings across a
    real universe, this is where it shows, and the equal weighting above becomes
    a thing to fix rather than a thing to believe.

    Spearman rather than Pearson, because the scores are bounded, capped and
    saturating in several places — a linear correlation over a saturated scale
    measures the saturation.
    """
    import numpy as _np
    import pandas as _pd

    frame = _pd.DataFrame([
        {family: ((row.get("families") or {}).get(family) or {}).get("score")
         for family in FAMILIES}
        for row in rows
    ], columns=list(FAMILIES))

    usable = [f for f in FAMILIES if frame[f].notna().sum() >= 10]
    if len(usable) < 2:
        return {"available": False,
                "reason": ("Fewer than two families read on enough names to measure "
                           "whether they overlap.")}

    matrix = frame[usable].corr(method="spearman")
    pairs = []
    for index, first in enumerate(usable):
        for second in usable[index + 1:]:
            both = int((frame[first].notna() & frame[second].notna()).sum())
            value = matrix.loc[first, second]
            if _np.isfinite(value):
                pairs.append({"a": first, "b": second, "aLabel": FAMILY_LABEL[first],
                              "bLabel": FAMILY_LABEL[second],
                              "correlation": float(value), "names": both})
    pairs.sort(key=lambda entry: -abs(entry["correlation"]))
    if not pairs:
        return {"available": False,
                "reason": "No pair of families could be compared on this scan."}

    strongest = pairs[0]
    return {
        "available": True,
        "families": usable,
        "pairs": pairs,
        "counts": {family: int(frame[family].notna().sum()) for family in usable},
        "reading": _overlap_reading(strongest, pairs),
    }


def _overlap_reading(strongest: dict, pairs: list[dict]) -> str:
    text = (f"Across this scan the most overlapping pair is {strongest['aLabel']} and "
            f"{strongest['bLabel']}, correlated at {strongest['correlation']:+.2f} over "
            f"{strongest['names']} names. ")
    if abs(strongest["correlation"]) > 0.6:
        text += ("They are close to measuring the same thing, so weighting them as "
                 "separate votes is over-counting one fact — treat that pair as one "
                 "source until it is fixed. ")
    elif abs(strongest["correlation"]) > 0.3:
        text += ("That is a real but partial overlap: they share some information and "
                 "each still carries something the other does not. ")
    else:
        text += ("Nothing here is duplicating another family, which is what the equal "
                 "weighting assumes and this measurement is here to check. ")
    register = [p for p in pairs if "register" in (p["a"], p["b"])]
    if register:
        worst = max(register, key=lambda p: abs(p["correlation"]))
        text += (f"The share register — the family with the weakest independence claim, "
                 f"because the share count is printed in the filings — reads at most "
                 f"{worst['correlation']:+.2f} against the others.")
    return text


# ============================================================================ #
# Provenance — the measurement that says what this ordering is worth
# ============================================================================ #
_BLEND_BACKTEST_PATH = Path(__file__).with_name("verdict_backtest.json")
_BLEND_CACHE: Optional[dict] = None


def blend_validation(market: Optional[str] = None) -> dict:
    """What the walk-forward found about the BLEND, not just the price rank.

    `provenance()` quotes `backtest_results.json`, which measures the seven-signal
    price composite — one component of nine. This reads the second artifact,
    which measures the four components that can be reconstructed without reading
    the future, and carries its own scope so the coverage is never mistaken for
    the whole score.

    Returns `available: False` on a checkout that has never run
    `scripts/backtest_verdict.py`, which reads as unmeasured rather than as
    passed.
    """
    global _BLEND_CACHE
    if _BLEND_CACHE is None:
        try:
            _BLEND_CACHE = json.loads(_BLEND_BACKTEST_PATH.read_text())
        except (OSError, ValueError):
            _BLEND_CACHE = {}
    if not _BLEND_CACHE.get("markets"):
        return {"available": False,
                "reason": ("The blend has never been backtested on this checkout. "
                           "Run scripts/backtest_verdict.py.")}

    row = _BLEND_CACHE["markets"].get((market or "").strip().upper())
    if row is None:
        return {"available": False,
                "reason": (f"The blend has been backtested, but not on "
                           f"{(market or '?').upper()}. A result measured on another "
                           f"market is not evidence about this one.")}
    return {
        "available": True,
        "measuredOn": row.get("measuredOn"),
        "scope": _BLEND_CACHE.get("scope"),
        "headline": row.get("headline"),
        "components": row.get("components"),
        "coverage": row.get("coverage"),
        "excluded": row.get("excluded"),
        "observations": row.get("observations"),
        "dates": row.get("dates"),
        "survived": row.get("survived"),
        "contradicted": row.get("contradicted"),
        "tests": row.get("tests"),
    }


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
        # THE COUNT IS DERIVED, NOT WRITTEN. It read "one of five components" for
        # a while after the component list grew to eight — a small wrongness in
        # the one paragraph whose whole job is to be exact about what has and has
        # not been measured.
        # THE COUNT IS DERIVED, NOT WRITTEN, and so is the claim about the
        # blend. This sentence read "the blend of them has never been
        # backtested at all" until `backtest_verdict.py` existed; now it says
        # what that measured and what it could not reach.
        "appliesTo": (f"the price-and-volume composite, which is one of "
                      f"{len(COMPONENTS)} components below. The blend itself is "
                      f"measured separately and partially — see `blendBacktest` — "
                      f"because five of the nine components cannot be reconstructed on "
                      f"a past date without reading filings published years later."),
    }
