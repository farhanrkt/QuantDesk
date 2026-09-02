"""
lensagreement.py
================
How much the four lenses actually agree, corrected for how much they would
agree knowing nothing.

THE CLAIM THIS EXISTS TO TEST
------------------------------
The confluence rail makes the single strongest statement in this app, on every
run, in the largest type on the page: that four lenses rest on two independent
bodies of data, and therefore that agreement between those two "is not one fact
counted twice". `explain._agreement` says it in prose — "the price record and
the filings share no inputs" — and `ConfluenceRail.agreementOf` does the
arithmetic that headline speaks in.

Both of them then admit, in smaller type, that none of it was measured: *"The
grouping is a stated assumption about what shares a source, not a measured
correlation; the ranking panel measures its own overlap because a scan gives it
a cross-section to measure from, and a single ticker does not."*

That is a predictive claim about the app's own output — that two of its votes
carry separate information — and this repo's rule is that such a claim gets
measured and published including nulls, or it does not ship. It shipped. This
module is the measurement, and `scripts/measure_lens_agreement.py` is the run
that supplies it.

The cross-section the rail says it does not have is one a script can build. The
lens votes exist already: `explain._read_flow / _read_trend / _read_value /
_read_quality` each return a vote in {-1, 0, +1}, and `calibrate_checks.py`
already proves a whole universe can be pushed through the production engines
offline. Nothing here is a new opinion about a company; it is a measurement of
what this app says about many of them.

WHY CHANCE-CORRECTED AGREEMENT AND NOT RAW AGREEMENT
-----------------------------------------------------
Raw agreement is uninterpretable for exactly the reason a raw screener hit
count is. If the Value lens says "below model range" on 70% of names and the
Quality lens says "sound" on 70%, the two land on the same label 58% of the
time while sharing nothing at all — and 58% reported on its own reads as
substantial corroboration.

This is the same correction `eventstudy.screener_significance` applies to scan
hits and `pretrade` applies to check flags, arriving in a third place. Cohen's
kappa is that correction for agreement between two raters:

    kappa = (observed agreement - chance agreement) / (1 - chance agreement)

where chance agreement is computed from each lens's OWN marginal distribution
of votes. It is 0 when two lenses agree exactly as often as their separate
habits predict, 1 when they never disagree, and negative when they agree LESS
than chance — which is a real finding rather than an error.

WHAT KAPPA IDENTIFIES, AND WHAT IT DOES NOT
--------------------------------------------
Kappa measures REDUNDANCY, not causation, and the distinction decides what may
honestly be said about the result.

A high kappa between the price family and the filings family would NOT prove
they share inputs. Two genuinely independent tests of a genuinely good company
should agree, and that agreement would be informative rather than duplicated.
Equally, a kappa near zero would not prove the two read different data — only
that their conclusions coincide about as often as chance puts them together.

But the claim the rail actually makes is an INFORMATION claim, not a causal
one: that agreement between the families "is not one fact counted twice". That
is precisely what kappa bounds. When kappa is high the second family's vote is
largely predictable from the first, and reading them as two facts overstates
the evidence however the redundancy arose. When kappa is near zero the two
votes are close to independent and the rail's arithmetic is sound. So the
measurement answers the question that was asked, and the causal question stays
explicitly unanswered on the panel.

WHY KENDALL'S TAU-B AS WELL
----------------------------
Kappa asks whether two lenses land on the SAME label. Tau-b asks whether, when
they differ, they differ in a consistent DIRECTION — it treats the vote as the
ordered scale it is (-1 < 0 < +1) rather than as three unrelated categories,
and its tie correction is what makes it usable on a scale this coarse, where
most pairs are tied on at least one side.

The two can disagree informatively. Two lenses that rarely produce an identical
label but almost never point opposite ways have a low kappa and a high tau-b,
and that combination means something a single number would hide: they are
measuring the same thing at different sensitivities.

WHY BOOTSTRAP RATHER THAN THE CLOSED-FORM VARIANCE
----------------------------------------------------
Cohen's asymptotic variance conditions on the observed marginals. Here the
marginals are themselves estimates — how often the Value lens calls a company
cheap is a property of the sample, not a fixed design — so the closed form
understates the uncertainty. Resampling NAMES with replacement propagates both
sources at once, needs no distributional assumption, and costs nothing in a
script that already spent minutes on the network. It is the same preference for
simulation over an assumed standard error that sized the Hurst random-walk band
and found the spread estimator's resolution floor.

The interval is a precision statement, not a hypothesis test. It says how well
this sample pins the number down; whether the interval straddles zero is
reported as exactly that and never as a p-value.

WHY THE PARTICIPATION RATIO IS COMPUTED DIFFERENTLY FROM THE PAIRS
-------------------------------------------------------------------
The two answer different questions and want different samples.

Each PAIR's kappa should use every name where THAT pair could be compared. A
bank whose accounting screens are refused still has a flow vote and a trend
vote, and throwing that name away because Quality could not read it would
shrink the flow-trend sample for no reason.

The EFFECTIVE LENS COUNT is a property of one matrix, and a correlation matrix
assembled from different rows per cell is not guaranteed to be a correlation
matrix at all — its eigenvalues can go negative and the participation ratio
stops meaning anything. So that half uses COMPLETE CASES only, where all four
lenses read, which makes the matrix a Gram matrix of standardised columns and
therefore positive semi-definite by construction. The complete-case count is
reported beside it, because it is materially smaller than the pairwise ones and
a reader should be able to see that.

The estimator itself is `riskmodel.effective_independent` — the same one the
ranking panel uses to say how many opinions a seven-column composite is really
averaging, and the portfolio panel to say how many independent bets a book
really is. A third copy would eventually disagree with the other two about what
redundancy means, in an app whose entire argument is that agreement between
correlated measures is worth less than it looks.

PER MARKET, FOR THE REASON THE CHECK CALIBRATION FOUND
-------------------------------------------------------
`calibrate_checks.py` discovered that a rate blended across two markets is the
wrong number for a company in either: Yahoo's fundamentals coverage for smaller
Indonesian listings makes "scores built from incomplete data" fire on 16% of US
large caps and 85% of Indonesian ones. The same fragility bites harder here,
because a lens that cannot read does not vote — so the filings family is
present on a different share of names in each market, and its agreement with
the price family is measured on a different population. Blending them would
report a redundancy neither market has.

WHAT THIS IS NOT
----------------
It is not a weight, a confidence multiplier or an input to any other number.
Nothing downstream consumes the kappa except the sentence that reports it. The
moment a measured agreement started scaling a verdict, this app would have the
composite score it refuses to have — arrived at sideways, through a statistic
that sounds too technical to be a recommendation. `tests/test_lensagreement.py`
asserts on the payload's key set for the same reason `test_pretrade.py` does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from . import riskmodel

# The three states a lens vote can take. Ordered, because tau-b reads them as a
# scale and because "neutral" genuinely sits between the other two.
VOTE_LEVELS = (-1, 0, 1)

# Below this many names a pair's agreement is not a measurement. Same floor as
# `pretrade.MIN_CALIBRATION_SAMPLE` and for the same reason rather than by
# sharing a constant: the two describe different quantities and should be free
# to move apart, but a kappa from twenty companies is noise with a decimal point
# on it exactly as a firing rate from twenty companies is.
MIN_PAIR_SAMPLE = 30

# Resamples per interval. Enough that the 2.5th and 97.5th percentiles are
# stable to about a hundredth on samples this size, cheap enough that six pairs
# across three populations still runs in under a second.
BOOTSTRAP_DRAWS = 2000

# Fixed so the stamped artifact is reproducible from the same votes. A research
# number that moved when nobody changed anything would be indistinguishable from
# one that moved because something did.
BOOTSTRAP_SEED = 20260829

MEASUREMENT_PATH = Path(__file__).with_name("lens_agreement.json")

# `for_synthesis(...)` loads the stamped measurement from disk; passing None
# says there IS none. Those are different situations and one default could not
# tell them apart — the second is a state the panel has to render honestly
# rather than a bug to paper over. Same device as `pretrade._LOAD_FROM_DISK`.
_LOAD_FROM_DISK = object()

LENS_ORDER = ("flow", "trend", "value", "quality")
LENS_LABEL = {"flow": "Flow", "trend": "Trend", "value": "Value", "quality": "Quality"}

# Which body of data each lens reads. The grouping under test, mirrored from
# `explain.SYNTHESIS_FAMILY` rather than re-decided here — this module measures
# the consequence of that grouping and must not quietly adopt a different one.
FAMILY_LABEL = {"price": "price and volume", "filings": "the filings"}


# --------------------------------------------------------------------------- #
# The estimators
# --------------------------------------------------------------------------- #
def _paired(first: Sequence, second: Sequence) -> tuple[np.ndarray, np.ndarray]:
    """The names where BOTH lenses voted, as two aligned integer arrays.

    A lens that could not read is not a neutral vote and must never be counted
    as one. A bank's refused accounting screens would otherwise arrive as a
    string of zeros and manufacture agreement with whatever else was also
    quiet — the same "absence is not evidence" error the pre-trade panel keeps
    a separate `notChecked` list to avoid.
    """
    a, b = [], []
    # `strict` on purpose. Two series of different lengths mean the caller has
    # misaligned its names, and silently truncating to the shorter one would
    # pair one company's flow vote with a different company's trend vote and
    # return a plausible kappa for a table nobody assembled.
    for left, right in zip(first, second, strict=True):
        if left is None or right is None:
            continue
        a.append(int(left))
        b.append(int(right))
    return np.asarray(a, dtype="int64"), np.asarray(b, dtype="int64")


def _counts(votes: np.ndarray) -> np.ndarray:
    """The marginal distribution over the three levels, as proportions."""
    total = votes.size
    if total == 0:
        return np.zeros(len(VOTE_LEVELS), dtype="float64")
    return np.array([np.count_nonzero(votes == level) for level in VOTE_LEVELS],
                    dtype="float64") / total


def cohens_kappa(first: Sequence, second: Sequence) -> Optional[dict]:
    """Agreement between two vote series, minus the agreement chance supplies.

    Returns the pieces rather than only the ratio, because the numerator and
    the denominator are separately worth printing: "they agree 58% of the time,
    and 55% is what their own habits produce" is a more useful sentence than
    "kappa = 0.07", and a reader can check the arithmetic.

    None when there is nothing to compare, or when chance agreement is exactly
    1 — which happens when both lenses returned the same single level on every
    name. Kappa is genuinely undefined there rather than zero: two raters who
    never vary cannot be shown to agree beyond chance, and reporting 0 would
    read as "no more than chance" when the honest answer is "this sample cannot
    say".
    """
    a, b = _paired(first, second)
    if a.size == 0:
        return None

    observed = float(np.mean(a == b))
    chance = float(np.dot(_counts(a), _counts(b)))
    if chance >= 1.0:
        return {"n": int(a.size), "observed": observed, "chance": chance,
                "kappa": None, "undefined": "both lenses returned one level throughout"}
    return {"n": int(a.size), "observed": observed, "chance": chance,
            "kappa": (observed - chance) / (1.0 - chance)}


def kendall_tau_b(first: Sequence, second: Sequence) -> Optional[float]:
    """Ordinal association between two vote series, with the tie correction.

    Delegated to scipy rather than written out. Tau-b's tie handling is where
    hand implementations go wrong, and on a three-level scale nearly every pair
    is tied on at least one side, so the correction is not a detail here — it
    is most of the statistic. The test suite plants a small table with a
    hand-computed tau-b and checks the number that comes back, which is the
    point of using an independent implementation.

    None when either series never varies: with no discordant pairs available
    there is no association to measure, and scipy returns nan there rather
    than a number.
    """
    from scipy.stats import kendalltau

    a, b = _paired(first, second)
    if a.size < 2 or np.unique(a).size < 2 or np.unique(b).size < 2:
        return None
    tau = float(kendalltau(a, b, variant="b").statistic)
    return tau if np.isfinite(tau) else None


def bootstrap_kappa(first: Sequence, second: Sequence, *,
                    draws: int = BOOTSTRAP_DRAWS,
                    seed: int = BOOTSTRAP_SEED) -> Optional[dict]:
    """A percentile interval for kappa, by resampling NAMES with replacement.

    Names rather than votes: the unit that was sampled from the world is the
    company, and resampling the two vote columns independently would destroy
    the pairing that kappa is entirely about.

    Draws where the resample happens to be degenerate — every name identical,
    so chance agreement is 1 — are dropped rather than counted as zero, and the
    surviving count is returned so a reader can see when the interval rests on
    fewer draws than were asked for.
    """
    a, b = _paired(first, second)
    if a.size < 2:
        return None

    rng = np.random.default_rng(seed)
    index = rng.integers(0, a.size, size=(draws, a.size))
    sampled_a, sampled_b = a[index], b[index]

    observed = np.mean(sampled_a == sampled_b, axis=1)
    chance = np.zeros(draws, dtype="float64")
    for level in VOTE_LEVELS:
        chance += (np.mean(sampled_a == level, axis=1)
                   * np.mean(sampled_b == level, axis=1))

    usable = chance < 1.0
    if not np.any(usable):
        return None
    values = (observed[usable] - chance[usable]) / (1.0 - chance[usable])
    return {"low": float(np.percentile(values, 2.5)),
            "high": float(np.percentile(values, 97.5)),
            "draws": int(values.size)}


def pair_agreement(name_a: str, name_b: str,
                   first: Sequence, second: Sequence) -> Optional[dict]:
    """Everything measurable about one pair of vote series."""
    kappa = cohens_kappa(first, second)
    if kappa is None:
        return None
    interval = bootstrap_kappa(first, second) or {}
    return {
        "a": name_a, "b": name_b,
        **kappa,
        "tauB": kendall_tau_b(first, second),
        "low": interval.get("low"), "high": interval.get("high"),
        # A precision statement, never a p-value. The interval either pins the
        # number away from zero on this sample or it does not, and saying which
        # is the whole of what a bootstrap percentile interval supports.
        "excludesZero": bool(
            interval and interval.get("low") is not None
            and (interval["low"] > 0.0 or interval["high"] < 0.0)),
        "usable": kappa["n"] >= MIN_PAIR_SAMPLE and kappa.get("kappa") is not None,
    }


def effective_lenses(votes: dict[str, Sequence]) -> dict:
    """How many independent lenses the four really amount to, on complete cases.

    See the module docstring for why this half uses complete cases where the
    pairwise kappas do not: the participation ratio is a property of one
    matrix, and a matrix assembled from a different set of names per cell is
    not guaranteed to have non-negative eigenvalues.

    A lens with no variation across the complete cases is DROPPED rather than
    carried, and named in the result. Its correlation with everything else is
    undefined (a zero standard deviation), and numpy would fill the row with
    nan — which `riskmodel.effective_independent` correctly refuses, taking the
    whole measurement down with it rather than the one column responsible.
    """
    order = [lens for lens in LENS_ORDER if lens in votes]
    if len(order) < 2:
        return {"available": False, "reason": "fewer than two lenses were measured"}

    columns = [list(votes[lens]) for lens in order]
    length = len(columns[0])
    if any(len(column) != length for column in columns):
        return {"available": False, "reason": "vote series of differing lengths"}

    complete = [i for i in range(length)
                if all(column[i] is not None for column in columns)]
    if len(complete) < MIN_PAIR_SAMPLE:
        return {"available": False, "completeCases": len(complete),
                "reason": f"only {len(complete)} names had all "
                          f"{len(order)} lenses reading"}

    matrix = np.array([[float(column[i]) for i in complete] for column in columns])
    varying = [i for i in range(len(order)) if np.std(matrix[i]) > 0]
    dropped = [LENS_LABEL[order[i]] for i in range(len(order)) if i not in varying]
    if len(varying) < 2:
        return {"available": False, "completeCases": len(complete),
                "reason": "fewer than two lenses varied across the complete cases"}

    correlation = np.corrcoef(matrix[varying])
    effective = riskmodel.effective_independent(correlation)
    if effective is None:
        return {"available": False, "completeCases": len(complete),
                "reason": "the correlation matrix was not usable"}

    kept = [order[i] for i in varying]
    return {
        "available": True,
        "lenses": [LENS_LABEL[lens] for lens in kept],
        "measuredLenses": len(kept),
        "effectiveLenses": float(effective),
        "completeCases": len(complete),
        "droppedForNoVariation": dropped,
    }


def measure(votes: dict[str, Sequence],
            family_votes: Optional[dict[str, Sequence]] = None) -> dict:
    """The whole measurement for one population.

    `votes` maps lens key to a vote series aligned across names, with None
    where that lens could not read. `family_votes` is the same for the two
    bodies of data, and is what the rail's headline claim is actually about —
    the six lens pairs are the supporting detail that says whether the grouping
    behaves the way it is declared to.
    """
    pairs = []
    for i, first in enumerate(LENS_ORDER):
        for second in LENS_ORDER[i + 1:]:
            if first not in votes or second not in votes:
                continue
            entry = pair_agreement(LENS_LABEL[first], LENS_LABEL[second],
                                   votes[first], votes[second])
            if entry is not None:
                pairs.append(entry)

    families = None
    if family_votes and "price" in family_votes and "filings" in family_votes:
        families = pair_agreement(FAMILY_LABEL["price"], FAMILY_LABEL["filings"],
                                  family_votes["price"], family_votes["filings"])

    return {"pairs": pairs, "families": families, "lenses": effective_lenses(votes)}


# --------------------------------------------------------------------------- #
# The stamped artifact
# --------------------------------------------------------------------------- #
def load_measurement(path: Path = MEASUREMENT_PATH) -> Optional[dict]:
    """The stamped agreement measurement, or None when it was never run.

    Served from a file for the same reason `check_calibration.json` and
    `backtest_results.json` are: it costs a full universe run through every
    production engine, it is a research finding about the app rather than a
    per-user computation, and a figure that decays slowly should be stamped
    with the date it was taken rather than recomputed on every request.
    """
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload if isinstance(payload.get("populations"), dict) else None


def _population(measurement: dict, market: Optional[str]) -> Optional[dict]:
    """The measurement for THIS market, falling back to the combined one.

    The market-specific reading wins wherever one exists, for the reason
    `pretrade._rate_for` prefers a market-specific firing rate: the filings
    lenses read on a very different share of Indonesian names than US ones, so
    the two families' agreement is measured on different populations and a
    blend describes neither.
    """
    populations = measurement.get("populations") or {}
    entry = populations.get((market or "").upper())
    if isinstance(entry, dict) and (entry.get("families") or {}).get("usable"):
        return entry
    entry = populations.get("ALL")
    return entry if isinstance(entry, dict) else None


# The pair the grouping ASSUMES is redundant. Flow and Trend are collapsed into
# one price vote precisely because they read the same OHLCV series, so this is
# the pair where the assumption either shows up in the votes or fails to.
DECLARED_REDUNDANT = ("Flow", "Trend")


def _declared_pair(pairs: Sequence[dict]) -> Optional[dict]:
    for pair in pairs:
        if {pair.get("a"), pair.get("b")} == set(DECLARED_REDUNDANT) and pair.get("usable"):
            return pair
    return None


def _reading(families: dict, lenses: dict, pairs: Sequence[dict], scope: str) -> str:
    """One sentence. The argument lives in RESEARCH_ROADMAP.md §15.

    This was 239 words of statistics — chance-corrected agreement, the declared
    pair, the participation ratio, and two paragraphs on what kappa cannot
    settle. All of it true, all of it the longest block on the page, and all of
    it a defence of the method rather than a finding about the company in front
    of the reader. A research desk that argues with a hypothetical critic beside
    every number is a desk nobody can read.

    So the panel keeps the NUMBER and the CONCLUSION, which is what a reader can
    act on, and the working moved to the document that exists to hold it. The
    figure is still measured, still stamped, still reproducible; it is simply no
    longer explained in place.
    """
    kappa, n = families.get("kappa"), families.get("n")
    if not families.get("excludesZero"):
        verdict = "no more often than chance would put them there"
    elif kappa is not None and kappa > 0:
        verdict = "rather more often than chance alone would produce"
    else:
        verdict = "less often than chance alone would produce"
    return (f"Measured across {n} names in {scope}: the two agree {verdict} "
            f"(κ = {kappa:+.2f}).")


def for_synthesis(market: Optional[str] = None,
                  measurement=_LOAD_FROM_DISK) -> Optional[dict]:
    """What the synthesis panel prints beside its independence claim.

    None when the measurement has never been run, or when the pair it rests on
    was measured on too few names — withheld rather than guessed, the same rule
    `pretrade` applies to an uncalibrated check. A claim the app cannot support
    with a number goes back to being stated as an assumption, which is what it
    was before and is at least honest.
    """
    if measurement is _LOAD_FROM_DISK:
        measurement = load_measurement()
    if not isinstance(measurement, dict):
        return None

    population = _population(measurement, market)
    if population is None:
        return None
    families = population.get("families") or {}
    if not families.get("usable"):
        return None

    lenses = population.get("lenses") or {}
    pairs = population.get("pairs") or []
    scope = population.get("label") or "the calibration universes"
    return {
        "measuredOn": measurement.get("measuredOn"),
        "scope": scope,
        "families": families,
        # The six lens pairs, so a reader can see whether the DECLARED grouping
        # behaves the way it is declared to — flow and trend are supposed to be
        # the redundant pair, and this is where that would show up or fail to.
        "pairs": pairs,
        "lenses": lenses,
        "reading": _reading(families, lenses, pairs, scope),
    }
