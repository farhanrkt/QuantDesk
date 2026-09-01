"""
expectations.py
===============
Engine 5 — the estimate record. What the analysts covering this listing
currently predict, and which way they have been moving.

WHY A FIFTH LENS, AND WHY IT IS A THIRD FAMILY
----------------------------------------------
The four lenses that came before all read one of two records. Flow and Trend
read the price and volume series; Value and Quality read the filings. Between
them they answer what the market did, what the company reported, what the
filings are worth and whether they can be believed.

None of them reads what is already EXPECTED. That gap is not academic — it is
the difference between the two companies that look identical to the other four
lenses:

    Cheap on a DCF, sound on the accounting screens, consensus rising.
    Cheap on a DCF, sound on the accounting screens, consensus cut for a year.

The four lenses print the same four verdicts for both, because a discounted
cash flow reads last year's statements and a Piotroski score reads the year
before that. The second company is the shape of a value trap, and the record
that distinguishes it is one no existing lens fetches.

So this reads a third body of data: the estimate record. It is neither the
price series nor the filings, and its failure modes are its own — it is an
opinion rather than a measurement, it is revised, and the revisions are dated.

THE FAMILY GROUPING IS A DECLARED ASSUMPTION, AND THIS ONE IS THE WEAKEST
-------------------------------------------------------------------------
`explain.SYNTHESIS_FAMILY` puts this lens in a family of its own, and that is a
STATED assumption exactly as the other two are — nothing measures which data a
lens reads and nothing could. But it deserves more suspicion than the first two,
and saying so here is cheaper than being caught by it later.

Analysts read the filings. An estimate record is downstream of the same
statements the Value and Quality lenses read, so if any pair of families in this
app turns out to be redundant, this is the pair. The confluence rail's whole
claim is that agreement across families is not one fact counted twice, and that
claim is only worth what the measurement behind it says.

Which is why the measurement came FIRST. `scripts/measure_lens_agreement.py`
now runs with three families and publishes all three pairwise kappas, and
`explain._warrant` has always had a branch that TAKES THE CLAIM AWAY when a
kappa excludes zero on the high side. See RESEARCH_ROADMAP.md §18.

WHAT VOTES, AND WHAT DELIBERATELY DOES NOT
-------------------------------------------
One vote, from ONE quantity: the breadth of estimate revisions. Everything else
here is supporting detail with no direction attached, and that is a design
decision rather than an omission.

  revision breadth    VOTES. How many of the analysts covering this name moved
                      their number up against how many moved it down.
  revision drift      no vote. The SIZE of the move, which shares a direction
                      with breadth and would be the same fact counted twice.
  surprise record     no vote. See below — its direction is not the company's.
  target dispersion   no vote. Disagreement is not bullish or bearish, in the
                      same way `exposure.py`'s betas are not: a negative beta
                      is not a bad beta and a wide spread of opinion is not a
                      bad spread of opinion.

THE SURPRISE RECORD DOES NOT VOTE, AND THE REASON IS NOT CAUTION
------------------------------------------------------------------
A beat is a fact about the relationship between two numbers, and its sign is
not the company's direction. A firm that has beaten four quarters running while
its consensus was cut all year is a deteriorating business that manages
expectations well, and the beats are the mechanism of the management rather
than evidence against the deterioration. Voting on the surprise would let that
company outvote its own estimate record.

So the surprise record is reported as what it is — a description of how this
company's results have landed against what was asked of them — and the panel
says the sentence above in words.

WHY THE ANNUAL PERIODS AND NOT THE QUARTERS
--------------------------------------------
yfinance serves four periods: the current quarter, the next quarter, the current
fiscal year and the next one. The vote pools the two ANNUAL periods and ignores
both quarters.

Two reasons. A quarterly estimate moves for reasons that are not about the
business — one extra shipping week, a seasonal split between Q3 and Q4 — and
those revisions net out across the year rather than accumulating. And the app's
other filings-side lens is annual: `valuation.py` forecasts five fiscal years,
so an expectations reading on a quarterly clock would be answering a question no
other panel on the page asks.

The quarters are still fetched and still reported, labelled as quarters. They
just do not decide the verdict.

BREADTH SURVIVES A FISCAL-YEAR ROLL AND MAGNITUDE DOES NOT
-----------------------------------------------------------
This is the hazard that decided which quantity carries the vote.

`eps_trend` is a LEVEL: the estimate for a period as it stands now, and as it
stood 7, 30, 60 and 90 days ago. The period is labelled relatively (`0y` is
"the current fiscal year"), so at some point in every year the label rolls onto
a different year and the level jumps for a reason that has nothing to do with a
revision. Nothing in the payload marks where that happened, and this module
cannot detect it — a 12% jump is what both a roll and a genuine re-rating look
like.

`eps_revisions` is a COUNT: how many analysts moved up and how many moved down
in the last 7 and 30 days. A count carries no level, so it cannot be corrupted
by a relabelling. It is also the quantity the literature actually uses.

So the count votes, the level is reported as supporting magnitude with the
hazard stated on the panel, and a sign change between two levels is reported as
a sign change rather than as a percentage — a swing from profit to loss is real
information, and dividing by a number that crossed zero is not.

WHAT IT REFUSES
---------------
  * A listing nobody covers gets `applicable: false` with the analyst count,
    not a zero. The two are opposite findings and must not render alike, which
    is the same refusal `quality.py` makes for a bank.
  * A quiet estimate record — analysts covering it, none of them moving — is
    reported as QUIET and never as balanced. An absent revision is not a
    neutral revision, which is this app's oldest rule arriving in a new place.
  * The mean price target is fetched and deliberately not published as a
    forecast. See `target_dispersion`.

References
----------
Chan, L. K. C., Jegadeesh, N., & Lakonishok, J. (1996). "Momentum Strategies."
    Journal of Finance 51(5), 1681-1713.
Bernard, V. L., & Thomas, J. K. (1989). "Post-Earnings-Announcement Drift:
    Delayed Price Response or Risk Premium?" Journal of Accounting Research 27,
    1-36.
Womack, K. L. (1996). "Do Brokerage Analysts' Recommendations Have Investment
    Value?" Journal of Finance 51(1), 137-167.
Diether, K. B., Malloy, C. J., & Scherbina, A. (2002). "Differences of Opinion
    and the Cross Section of Stock Returns." Journal of Finance 57(5),
    2113-2141.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Thresholds, each with the reason it sits where it does
# --------------------------------------------------------------------------- #
# yfinance's period labels. The two annual ones carry the vote; the quarterly
# ones are reported and ignored — see the module docstring.
ANNUAL_PERIODS = ("0y", "+1y")
QUARTERLY_PERIODS = ("0q", "+1q")
PERIOD_LABEL = {
    "0q": "the current quarter",
    "+1q": "the next quarter",
    "0y": "this fiscal year",
    "+1y": "next fiscal year",
}

# Below this many analysts, there is no consensus to read and the lens refuses.
# Three is the floor at which "the analysts disagree" can mean anything at all:
# with two, every split is 1-1 or 2-0 and the diffusion index below can only
# return -1, 0 or +1, which is a coin landing rather than a measurement of a
# consensus.
MIN_ANALYSTS = 3

# Below this many MOVES in the window, the sign of the diffusion index is one
# analyst's opinion rather than a property of the consensus. Distinct from
# MIN_ANALYSTS above: a well-covered name where two people moved is exactly as
# thin, on this quantity, as a thinly covered one.
MIN_REVISIONS = 3

# Where the diffusion index stops being "essentially even". The band has to be
# CLEARED, not met: a 5-to-3 split is exactly 0.25 and is reported as mixed, and
# it takes 6-to-3 to read as a direction. Mixed is a real state rather than a
# failure to decide, so the boundary belongs on that side. Deliberately not tuned against returns — that would
# be fitting a threshold to the outcome it is later used to predict, which is
# the mistake `backtest.py` exists to keep this app honest about.
DIFFUSION_BAND = 0.25

# How far a level has to move before it is worth a sentence. Estimate levels
# carry rounding and currency noise at the third decimal; a tenth of a percent
# over ninety days is not a revision, it is a different rounding.
DRIFT_FLOOR = 0.005

# Quarters of realised results needed before the beat/miss record is a record
# rather than an anecdote. Four is what Yahoo serves and what a year contains.
MIN_SURPRISE_QUARTERS = 2

# THERE IS DELIBERATELY NO "WIDE DISPERSION" THRESHOLD HERE.
#
# The first draft carried one, at 0.60, and it was wrong in the way this repo
# has a rule against: on the four names it was tried against, a 57% spread came
# out "narrow" and an 88% spread "wide", and nothing anywhere justified the line
# between them. `pretrade.py` already refuses to render a check whose base rate
# nobody has measured, and a band is that same claim in a single word.
#
# So the spread is reported as a number with no band, and the FRAME comes from
# the measurement instead: `revision_momentum.json` records the median spread
# across each market's universe, and `explain._dispersion` quotes this listing
# against it. That is the same move `ranking.py` argues for — a percentile is a
# claim about a named universe on a named date, and a score out of a hundred
# implies an absolute scale that was never calibrated.


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _safe_float(value, default=np.nan) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if np.isfinite(out) else default


def _nullable(value) -> Optional[float]:
    out = _safe_float(value)
    return float(out) if np.isfinite(out) else None


def _cell(frame, period: str, column: str) -> float:
    """One cell of a yfinance analyst table, as a float or NaN.

    Every access here is defensive on purpose. These frames are scrapes: the
    index labels have changed spelling upstream before, a column can be absent
    on one listing and present on the next, and a missing cell must degrade to
    "no reading" rather than raise inside a lens that four other panels are
    waiting on.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return np.nan
    if period not in frame.index or column not in frame.columns:
        return np.nan
    try:
        return _safe_float(frame.loc[period, column])
    except (KeyError, TypeError, ValueError):
        return np.nan


# yfinance's revision columns, whose capitalisation is inconsistent upstream —
# `upLast7days` against `downLast7Days` in the same table. Both spellings are
# tried rather than assumed, because a silently missing column would read as
# "nobody revised" and that is the one answer this module must never invent.
_UP_30 = ("upLast30days", "upLast30Days")
_DOWN_30 = ("downLast30days", "downLast30Days")
_UP_7 = ("upLast7days", "upLast7Days")
_DOWN_7 = ("downLast7days", "downLast7Days")


def _count(frame, period: str, names: tuple[str, ...]) -> float:
    for name in names:
        value = _cell(frame, period, name)
        if np.isfinite(value):
            return value
    return np.nan


# --------------------------------------------------------------------------- #
# Revision breadth — the quantity that votes
# --------------------------------------------------------------------------- #
def revision_breadth(revisions, periods: tuple[str, ...] = ANNUAL_PERIODS,
                     window: str = "30d") -> dict:
    """How many analysts moved up against how many moved down.

        diffusion = (up - down) / (up + down)

    Bounded in [-1, +1], and it is a share rather than a count on purpose: six
    upgrades on a name followed by forty analysts is a different fact from six
    on a name followed by seven, and the raw count cannot tell them apart.

    POOLED ACROSS THE TWO ANNUAL PERIODS, summing the counts rather than
    averaging the two diffusions. Averaging would give a period with two moves
    the same weight as one with twenty, which is the same mistake as averaging
    two percentages over different denominators.

    `up + down == 0` is QUIET, and it is returned as its own state with a null
    diffusion. Nobody moving is not the same as movement in both directions
    cancelling, and 0.0 would render identically for both.
    """
    columns = (_UP_30, _DOWN_30) if window == "30d" else (_UP_7, _DOWN_7)
    up = sum(v for v in (_count(revisions, p, columns[0]) for p in periods)
             if np.isfinite(v))
    down = sum(v for v in (_count(revisions, p, columns[1]) for p in periods)
               if np.isfinite(v))

    # `any finite cell at all` separates "the table came back empty" from "the
    # table came back and every count in it was zero". The first is missing
    # data; the second is a real, quiet estimate record.
    present = any(np.isfinite(_count(revisions, p, col))
                  for p in periods for col in columns)
    if not present:
        return {"available": False, "reason": "no revision table for these periods",
                "window": window, "up": None, "down": None,
                "moves": None, "diffusion": None, "state": None}

    up, down = int(up), int(down)
    moves = up + down
    if moves == 0:
        return {"available": True, "window": window, "up": 0, "down": 0,
                "moves": 0, "diffusion": None, "state": "quiet",
                "thin": False}

    diffusion = (up - down) / moves
    if moves < MIN_REVISIONS:
        state = "thin"
    elif diffusion > DIFFUSION_BAND:
        state = "rising"
    elif diffusion < -DIFFUSION_BAND:
        state = "falling"
    else:
        state = "mixed"

    return {"available": True, "window": window, "up": up, "down": down,
            "moves": moves, "diffusion": float(diffusion), "state": state,
            # Carried so the panel can say "two analysts moved" rather than
            # printing a diffusion index nobody can weigh.
            "thin": moves < MIN_REVISIONS}


# --------------------------------------------------------------------------- #
# Revision drift — the magnitude, which does not vote
# --------------------------------------------------------------------------- #
def revision_drift(trend, period: str = "0y", days: int = 90) -> dict:
    """How far the estimate for one period has moved, as a share of where it was.

    Reported, never voted on: it shares its direction with `revision_breadth`,
    and two readings of one direction presented as two findings is the inflation
    the confluence rail's family grouping exists to prevent, arriving inside a
    single lens.

    THREE OUTCOMES, AND THE THIRD IS THE INTERESTING ONE:

      moved       both levels finite, same sign, gap above the noise floor.
                  A percentage is meaningful and is returned.
      flat        both levels finite, gap inside the noise floor.
      swung       the sign changed between the two levels. A percentage here
                  would divide by a number that crossed zero, so none is
                  returned — but the swing itself is the most informative thing
                  in this function and is reported in words. A consensus moving
                  from a profit to a loss is not a 140% revision, it is a
                  different forecast about the business.

    THE FISCAL-YEAR HAZARD IS NOT DETECTABLE HERE and is not papered over. The
    period label is relative, so `0y` means a different fiscal year before and
    after the roll, and a level compared across that boundary is comparing two
    different years. Nothing in the payload marks it. The panel carries the
    caveat; the vote does not depend on this function precisely because of it.
    """
    column = {7: "7daysAgo", 30: "30daysAgo", 60: "60daysAgo", 90: "90daysAgo"}.get(days)
    if column is None:
        return {"available": False, "reason": f"no {days}-day column", "days": days}

    current = _cell(trend, period, "current")
    before = _cell(trend, period, column)
    if not np.isfinite(current) or not np.isfinite(before):
        return {"available": False, "reason": "the estimate level is missing",
                "days": days, "period": period}

    if before == 0:
        return {"available": False, "reason": "the earlier estimate was zero",
                "days": days, "period": period}

    if (current > 0) != (before > 0):
        return {"available": True, "days": days, "period": period,
                "state": "swung", "change": None,
                "current": float(current), "before": float(before),
                "direction": "up" if current > before else "down"}

    change = (current - before) / abs(before)
    return {"available": True, "days": days, "period": period,
            "state": "flat" if abs(change) < DRIFT_FLOOR else "moved",
            "change": float(change),
            "current": float(current), "before": float(before),
            "direction": "up" if change > 0 else "down"}


# --------------------------------------------------------------------------- #
# The surprise record — descriptive, never a vote
# --------------------------------------------------------------------------- #
def surprise_record(history) -> dict:
    """How this company's results have landed against what was asked of them.

    ROWS WITH NO REPORTED FIGURE ARE DROPPED, not counted as misses. Yahoo
    carries the upcoming quarter in this table with an estimate and a null
    actual, and counting that as a miss would put a company one row behind its
    own record on the day before it reports.

    The median rather than the mean, because one restatement-sized surprise
    moves a four-observation mean to wherever it likes.
    """
    if not isinstance(history, pd.DataFrame) or history.empty:
        return {"available": False, "reason": "no reported quarters came back"}

    frame = history.copy()
    for column in ("epsActual", "epsEstimate", "surprisePercent"):
        if column not in frame.columns:
            return {"available": False, "reason": "the surprise table is missing a column"}
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=["epsActual", "surprisePercent"])
    if len(frame) < MIN_SURPRISE_QUARTERS:
        return {"available": False,
                "reason": f"only {len(frame)} reported "
                          f"quarter{'' if len(frame) == 1 else 's'} came back"}

    frame = frame.sort_index()
    surprises = frame["surprisePercent"].astype(float)
    beats = int((surprises > 0).sum())
    misses = int((surprises < 0).sum())

    quarters = []
    for label, row in frame.iterrows():
        quarters.append({
            "quarter": str(label)[:10],
            "actual": _nullable(row["epsActual"]),
            "estimate": _nullable(row["epsEstimate"]),
            "surprise": _nullable(row["surprisePercent"]),
        })

    return {"available": True, "quarters": quarters,
            "reported": len(frame), "beats": beats, "misses": misses,
            "inline": len(frame) - beats - misses,
            "medianSurprise": float(np.median(surprises)),
            # The most recent quarter on its own, because "beat three of four"
            # and "missed the last one badly" are both true of the same record
            # and a reader wants the second as well as the first.
            "latest": quarters[-1]}


# --------------------------------------------------------------------------- #
# Consensus growth — the external benchmark the reverse DCF never had
# --------------------------------------------------------------------------- #
def consensus_growth(growth) -> dict:
    """What the analysts expect earnings to do over the next fiscal year.

    Its whole purpose is comparison. `valuation.py` computes an implied growth
    rate — what the CURRENT PRICE would need the business to do — and until now
    the only thing that figure could be held against was the app's own default
    assumption, which came from the same module. Both sides of that comparison
    were this app talking to itself.

    This is somebody else's number, and it is the first genuinely external
    check on the valuation lens that this app has ever carried. The comparison
    is drawn in `explain._tensions`, where both legs are visible.

    LTG IS NOT USED. Yahoo carries a long-term growth row and it is null on
    every listing tested, US and Indonesian alike. A five-year consensus would
    be the right horizon to hold a five-year DCF against; a one-year consensus
    is what exists, so the comparison is drawn at one year and labelled as one
    year rather than quietly stretched to five.
    """
    if not isinstance(growth, pd.DataFrame) or growth.empty:
        return {"available": False, "reason": "no growth estimates came back"}
    if "stockTrend" not in growth.columns:
        return {"available": False, "reason": "the growth table has no company column"}

    value = _cell(growth, "+1y", "stockTrend")
    if not np.isfinite(value):
        return {"available": False, "reason": "no next-year growth estimate"}

    return {"available": True, "nextYear": float(value), "horizon": "one fiscal year",
            "thisYear": _nullable(_cell(growth, "0y", "stockTrend"))}


# --------------------------------------------------------------------------- #
# Target dispersion — disagreement, and the number this module will not print
# --------------------------------------------------------------------------- #
def target_dispersion(targets: dict) -> dict:
    """How far apart the published price targets are, as a share of their mean.

    THE MEAN TARGET IS FETCHED AND IS DELIBERATELY NOT PUBLISHED AS A FORECAST,
    and this is the one refusal in this module that is about a number rather
    than about missing data.

    A price target is the only figure in this whole app that is simultaneously
    a point forecast of a price, unattached to any stated method, and produced
    by people with a commercial relationship to the company being forecast.
    Rendering "mean target 3,700" beside a price of 3,380 states a 9% expected
    return that nothing on this page — and nothing in the source — supports.
    The app has spent four other lenses refusing to print a forecast it cannot
    defend,
    and this would be one arriving as a quotation.

    The SPREAD is a different quantity and survives the objection. It does not
    require believing any single target, only that the people publishing them
    disagree, and disagreement is measurable from the numbers themselves.
    Diether, Malloy & Scherbina (2002) is the reason it is worth a line.

    IT IS NEVER COLOURED. Wide disagreement is not bad news and narrow agreement
    is not good news — the same rule §8 applies to provenance and §16 to the
    exposure betas. `explain` gives it the `context` band and nothing else.

    AND IT CARRIES NO BAND. See the note where `WIDE_DISPERSION` used to be: the
    frame for "is this a lot?" is the measured median across a named universe,
    not a constant somebody picked.
    """
    if not isinstance(targets, dict) or not targets:
        return {"available": False, "reason": "no published targets came back"}

    high = _safe_float(targets.get("high"))
    low = _safe_float(targets.get("low"))
    mean = _safe_float(targets.get("mean"))
    if not (np.isfinite(high) and np.isfinite(low) and np.isfinite(mean)) or mean == 0:
        return {"available": False, "reason": "the target table is incomplete"}
    if high < low:
        return {"available": False, "reason": "the target range came back inverted"}

    spread = (high - low) / abs(mean)
    return {"available": True, "spread": float(spread),
            # The HIGH and LOW are published because they are what the spread is
            # computed from and a reader should be able to check the arithmetic.
            # The MEAN and MEDIAN are not — see the docstring.
            "high": float(high), "low": float(low)}


# --------------------------------------------------------------------------- #
# The lens
# --------------------------------------------------------------------------- #
def _verdict(breadth: dict) -> tuple[str, str]:
    """The verdict enum and the tone word, from breadth and nothing else.

    Returned together so no caller ever re-derives one from the other. This is
    the same rule `explain.make` enforces for metric colour: direction is
    decided once, in Python, and everything downstream reads the word.
    """
    if not breadth.get("available"):
        return "UNREADABLE", "none"
    state = breadth.get("state")
    if state == "rising":
        return "RISING", "good"
    if state == "falling":
        return "FALLING", "bad"
    if state == "quiet":
        return "QUIET", "neutral"
    if state == "thin":
        return "THIN", "neutral"
    return "MIXED", "neutral"


HEADLINES = {
    "RISING": "The analysts covering it have been raising their numbers.",
    "FALLING": "The analysts covering it have been cutting their numbers.",
    "MIXED": "Revisions have gone both ways in roughly equal measure.",
    "QUIET": "Analysts cover this company, and none of them has moved a number "
             "in the last month.",
    "THIN": "Too few analysts moved for the direction to mean anything.",
    "UNREADABLE": "No revision record came back for this listing.",
}


def analyze(record: dict, *, symbol: Optional[str] = None) -> dict:
    """The whole expectations reading for one listing.

    `record` is `market_data.estimates(symbol)`.

    A LISTING NOBODY COVERS IS A REFUSAL, NOT A NEUTRAL READING, and it is the
    same distinction `quality.py` draws for a bank: `applicable: false` says the
    lens declined, and it must never render as "no concerns found". The whole
    of this app's honesty rests on an absent reading and a clean reading looking
    different, and this lens has more uncovered listings ahead of it than any
    other — smaller Indonesian names are exactly where analyst coverage stops.
    """
    analysts = _safe_float(record.get("analysts"))
    coverage = int(analysts) if np.isfinite(analysts) else None

    if coverage is None or coverage < MIN_ANALYSTS:
        return {
            "applicable": False,
            "analysts": coverage,
            "minAnalysts": MIN_ANALYSTS,
            "verdict": "NOT_COVERED",
            "tone": "none",
            "headline": (
                f"Only {coverage} analyst{'' if coverage == 1 else 's'} publishes "
                f"estimates for this listing, so there is no consensus to read."
                if coverage else
                "No analyst publishes estimates for this listing, so there is no "
                "consensus to read."),
            # SAID IN WORDS, EVERY TIME. An empty expectations panel is the
            # easiest one in this app to misread as reassurance — "no cuts" and
            # "nobody watching" render as the same blank space.
            "refusal": (
                "That is a gap in coverage, not a clean bill of health. Nothing here "
                "says the estimates are steady; it says there are no estimates. This "
                "is the most common outcome for smaller listings, and it is the one "
                "place where this lens is systematically absent rather than quiet."),
        }

    breadth = revision_breadth(record.get("eps_revisions"))
    breadth_7d = revision_breadth(record.get("eps_revisions"), window="7d")
    verdict, tone = _verdict(breadth)

    trend = record.get("eps_trend")
    drift = {
        "annual90": revision_drift(trend, "0y", 90),
        "annual30": revision_drift(trend, "0y", 30),
        "forward90": revision_drift(trend, "+1y", 90),
    }

    return {
        "applicable": True,
        "analysts": coverage,
        "minAnalysts": MIN_ANALYSTS,
        "verdict": verdict,
        "tone": tone,
        "headline": HEADLINES.get(verdict, HEADLINES["MIXED"]),
        "breadth": breadth,
        "breadth7d": breadth_7d,
        "drift": drift,
        "surprise": surprise_record(record.get("earnings_history")),
        "consensusGrowth": consensus_growth(record.get("growth_estimates")),
        "dispersion": target_dispersion(record.get("targets")),
        "periods": {
            "voting": [PERIOD_LABEL[p] for p in ANNUAL_PERIODS],
            "reported": [PERIOD_LABEL[p] for p in QUARTERLY_PERIODS],
        },
        # The two hazards a reader needs in order to weigh anything above, kept
        # in the payload rather than the component so they cannot be dropped by
        # a redesign. Both are stated as limits of the SOURCE, not of the app.
        "limits": [
            "An estimate is an opinion, not a measurement. This lens reads what "
            "the analysts covering this company currently predict — it does not "
            "check whether they have been right before.",
            "Estimate levels are labelled by a relative period, so a comparison "
            "across a fiscal-year boundary can compare two different years. The "
            "verdict is taken from the count of analysts who moved, which carries "
            "no level and cannot be corrupted that way.",
        ],
    }
