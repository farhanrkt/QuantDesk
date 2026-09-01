"""
revisionmomentum.py
===================
Whether the expectations lens's signal has any relationship to what the price
did next — measured, and published whichever way it comes out.

WHY THIS EXISTS BEFORE THE PANEL DOES
--------------------------------------
`expectations.py` votes. A vote reaches `explain._family_votes`, and from there
the confluence rail's headline, where agreement between families is presented as
corroborating evidence. That is a claim that the direction of estimate revisions
carries information about a company, and this repo's second rule is that such a
claim is measured offline and published including nulls, or it does not ship.

The four lenses that came before all carry one of these. `backtest_results.json`
reports that the ranking composite has no detectable edge. `check_calibration.
json` demoted a pre-trade flag to a base condition. `exposure_stability.json`
refused one of the four factors it tested. This is the fifth, and it was built
expecting a null.

THE PROBLEM: THE VOTING QUANTITY HAS NO HISTORY
------------------------------------------------
The lens votes on revision BREADTH — how many analysts moved up against how
many moved down, from `eps_revisions`. Yahoo serves that table as a snapshot.
There is no history of it, anywhere in the source, so the quantity that actually
votes cannot be back-tested at all.

What DOES have history is the estimate LEVEL. `eps_trend` carries the consensus
as it stands now and as it stood 7, 30, 60 and 90 days ago, which is a 90-day
window available on every name, today, without any stored panel.

So the measurement is built in two halves, and the second half is what makes the
first half admissible:

  1. THE FORWARD TEST. Signal = how far the consensus level moved between 90 and
     60 days ago. Outcome = the market-adjusted return over the 60 days SINCE.
     The signal is formed entirely before the outcome window opens, so there is
     no look-ahead.

  2. THE BRIDGE. The measured signal is the level drift; the voting signal is
     the revision count. If the two do not point the same way, the forward test
     says nothing about the vote. So their contemporaneous rank correlation
     across the same universe is measured and published beside it, and the
     panel's evidence grade is set from BOTH — a forward result on a proxy that
     does not track the vote is worth nothing, and the artifact has to be able
     to say so.

WHAT THIS IS NOT, AND THE LIMIT IS SEVERE
------------------------------------------
IT IS ONE WINDOW. One signal date, one outcome window, every name measured over
the same sixty days. That is not a backtest and it is not called one anywhere in
this repo. A real study of revision momentum samples many non-overlapping
windows over many years; this samples one, because one is what a source with no
history can supply.

The consequence is specific and it is the reason the interval below is not a
p-value: with every name sharing an outcome window, the returns are correlated
through whatever the market did over those sixty days, so the 168 names are far
fewer than 168 independent observations. Two defences, and neither is complete:
returns are CROSS-SECTIONALLY DEMEANED WITHIN MARKET before anything is
computed, which removes the single common factor that does most of that damage
(the same move, and the same reason, as `exposure.py` removing the market
first); and the statistic is a RANK correlation, which cannot be dragged by a
handful of extreme returns in a window that happened to contain one.

What survives is a precision statement about this window, and that is how it is
reported: whether the interval straddles zero on this sample, never whether an
effect exists.

WHY SPEARMAN AND NOT A REGRESSION SLOPE
-----------------------------------------
A slope would be denominated in "return per unit of revision", which invites
reading it as an expected return — the exact number this app refuses to print.
A rank correlation answers the question that was actually asked, which is
whether the ordering carries any information, and it has no units to misread.

It is also robust to the shape of the signal, which matters here: estimate
revisions are heavily zero-inflated and their tails are set by a handful of
names whose earnings are near zero, where a small absolute change is an enormous
relative one. `MDKA.JK` moved 38% on a level of 0.0068 in testing. A Pearson
correlation would be largely a statement about that one name.

WHAT COMES OUT
--------------
`api/_lib/revision_momentum.json`, stamped, holding per population: the forward
rank correlation with its bootstrap interval, the breadth-drift bridge, and the
distribution of target dispersion that gives `explain._dispersion` its frame.

RE-RUN IT whenever `expectations.revision_breadth` or `revision_drift` changes
what it computes. A stale result attached to a changed signal is worse than
none, because the panel prints it with a date that makes it look checked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

MEASUREMENT_PATH = Path(__file__).with_name("revision_momentum.json")

# Below this many names a rank correlation is not a measurement. Same floor and
# same reasoning as `lensagreement.MIN_PAIR_SAMPLE`, kept separate rather than
# imported for the reason that module gives for keeping its own: the two
# describe different quantities and should be free to move apart.
MIN_SAMPLE = 30

# Resamples per interval. Matches `lensagreement.BOOTSTRAP_DRAWS` so the two
# artifacts' intervals are comparable in precision.
BOOTSTRAP_DRAWS = 2000

# Fixed so the stamped artifact is reproducible from the same inputs. A research
# number that moved when nobody changed anything would be indistinguishable from
# one that moved because something did.
BOOTSTRAP_SEED = 20260901

# The window the forward test uses, in calendar days. 90-to-60 forms the signal
# and 60-to-now is the outcome, because those are the columns the source
# actually serves — not because sixty days is the right holding period for
# anything. Stated in the artifact so nobody later reads it as a recommended
# horizon.
SIGNAL_FROM_DAYS = 90
SIGNAL_TO_DAYS = 60
OUTCOME_DAYS = 60

_LOAD_FROM_DISK = object()


# --------------------------------------------------------------------------- #
# The estimators
# --------------------------------------------------------------------------- #
def _paired(first: Sequence, second: Sequence) -> tuple[np.ndarray, np.ndarray]:
    """The names where both quantities exist, as two aligned float arrays.

    `strict` on the zip for the reason `lensagreement._paired` uses it: two
    series of different lengths mean the caller has misaligned its names, and
    truncating to the shorter one would pair one company's signal with another
    company's return and return a plausible correlation for a table nobody
    assembled.
    """
    a, b = [], []
    for left, right in zip(first, second, strict=True):
        if left is None or right is None:
            continue
        left, right = float(left), float(right)
        if not (np.isfinite(left) and np.isfinite(right)):
            continue
        a.append(left)
        b.append(right)
    return np.asarray(a, dtype="float64"), np.asarray(b, dtype="float64")


def demean_within(values: Sequence, groups: Sequence) -> list[Optional[float]]:
    """Subtract each group's own mean from its members.

    THE MARKET IS REMOVED FIRST, and it is removed per market rather than
    globally. A sixty-day window in which the Jakarta Composite fell and the
    Nasdaq rose would otherwise leave every Indonesian name with a negative
    outcome and every US one positive, and a signal that merely differed in
    average level between the two markets would score a correlation from that
    alone.

    Same move as `exposure.py` §16 makes for the same reason: what is left after
    the common factor is the part a cross-sectional statistic can honestly speak
    about.
    """
    out: list[Optional[float]] = [None] * len(values)
    for group in sorted({g for g in groups if g is not None}):
        members = [i for i, g in enumerate(groups)
                   if g == group and values[i] is not None
                   and np.isfinite(float(values[i]))]
        if not members:
            continue
        mean = float(np.mean([float(values[i]) for i in members]))
        for i in members:
            out[i] = float(values[i]) - mean
    return out


def spearman(first: Sequence, second: Sequence) -> Optional[dict]:
    """Rank correlation between two series, with the tie correction scipy applies.

    None when there is nothing to correlate or when either side never varies —
    a constant has no ranks to correlate and scipy returns nan there rather than
    a number.
    """
    from scipy.stats import spearmanr

    a, b = _paired(first, second)
    if a.size < 3 or np.unique(a).size < 2 or np.unique(b).size < 2:
        return None
    rho = float(spearmanr(a, b).statistic)
    if not np.isfinite(rho):
        return None
    return {"n": int(a.size), "rho": rho}


def bootstrap_spearman(first: Sequence, second: Sequence, *,
                       draws: int = BOOTSTRAP_DRAWS,
                       seed: int = BOOTSTRAP_SEED) -> Optional[dict]:
    """A percentile interval for the rank correlation, resampling NAMES.

    Names rather than observations, for the reason `lensagreement.
    bootstrap_kappa` resamples names: the unit sampled from the world is the
    company, and resampling the two columns independently would destroy the
    pairing the statistic is entirely about.

    Degenerate draws — a resample in which one side came out constant — are
    dropped rather than counted as zero, and the surviving count is returned so
    a reader can see when the interval rests on fewer draws than were asked for.
    """
    from scipy.stats import spearmanr

    a, b = _paired(first, second)
    if a.size < 3:
        return None

    rng = np.random.default_rng(seed)
    index = rng.integers(0, a.size, size=(draws, a.size))
    values = []
    for row in index:
        sa, sb = a[row], b[row]
        if np.unique(sa).size < 2 or np.unique(sb).size < 2:
            continue
        rho = spearmanr(sa, sb).statistic
        if np.isfinite(rho):
            values.append(float(rho))
    if not values:
        return None
    return {"low": float(np.percentile(values, 2.5)),
            "high": float(np.percentile(values, 97.5)),
            "draws": len(values)}


def association(label: str, first: Sequence, second: Sequence) -> Optional[dict]:
    """Everything measurable about one pair of series.

    `excludesZero` is a PRECISION statement and never a p-value — the same
    distinction `lensagreement.pair_agreement` draws. It says whether this
    sample pins the number away from zero, which is the whole of what a
    bootstrap percentile interval supports.
    """
    result = spearman(first, second)
    if result is None:
        return None
    interval = bootstrap_spearman(first, second) or {}
    low, high = interval.get("low"), interval.get("high")
    return {
        "label": label,
        **result,
        "low": low, "high": high,
        "excludesZero": bool(low is not None and high is not None
                             and (low > 0.0 or high < 0.0)),
        "usable": result["n"] >= MIN_SAMPLE,
    }


def dispersion_frame(spreads: Sequence) -> Optional[dict]:
    """The distribution of target dispersion across a universe.

    This is the FRAME, and it exists because `expectations.target_dispersion`
    deliberately carries no threshold. "The published targets span 57% of their
    own mean" is unreadable on its own; "against a median of 48% across the
    Nasdaq-100" is the sentence that makes it mean something.

    Quartiles rather than a mean and a standard deviation, because the quantity
    is a ratio bounded below by zero with a long right tail, and neither of
    those two summaries describes it.
    """
    values = np.asarray([float(v) for v in spreads
                         if v is not None and np.isfinite(float(v))],
                        dtype="float64")
    if values.size < MIN_SAMPLE:
        return None
    return {"n": int(values.size),
            "median": float(np.median(values)),
            "p25": float(np.percentile(values, 25)),
            "p75": float(np.percentile(values, 75))}


# --------------------------------------------------------------------------- #
# The stamped artifact
# --------------------------------------------------------------------------- #
def load_measurement(path: Path = MEASUREMENT_PATH) -> Optional[dict]:
    """The stamped measurement, or None when it has never been run.

    Served from a file for the reason every other measured artifact in this
    directory is: it costs a universe-wide run against an endpoint with no SLA,
    it is a research finding about the app rather than a per-user computation,
    and a figure that decays slowly should carry the date it was taken.
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

    Market-specific wins wherever one exists, for the reason `pretrade._rate_for`
    and `lensagreement._population` both prefer one: analyst coverage differs
    sharply between the two markets, so the signal is measured on a different
    population in each and a blend describes neither.
    """
    populations = measurement.get("populations") or {}
    entry = populations.get((market or "").upper())
    if isinstance(entry, dict):
        return entry
    entry = populations.get("ALL")
    return entry if isinstance(entry, dict) else None


def _grade(forward: Optional[dict], bridge: Optional[dict]) -> str:
    """How much weight the panel may put on the revision reading.

    BOTH HALVES DECIDE IT, and that is the point of measuring the bridge at all.
    A forward result on a proxy that does not track the voting quantity is worth
    nothing, however clean the forward result looks — so a broken bridge caps
    the grade regardless of what the first half found.

    Returns one of `explain.EVIDENCE`. Deliberately never "strong": one window
    is not a body of evidence, whatever it happens to contain.
    """
    if not forward or not forward.get("usable"):
        return "none"
    if not bridge or not bridge.get("usable") or not bridge.get("excludesZero"):
        # The measured proxy cannot be shown to move with the quantity that
        # votes, so the forward test does not speak to the vote.
        return "weak"
    return "moderate" if forward.get("excludesZero") else "weak"


def _rho(value: float) -> str:
    """A rank correlation, formatted so a null does not print as "-0.00".

    Two decimals is the right precision for a statistic this noisy, and it puts
    every genuine null inside the last place — where `{:+.2f}` renders a signed
    zero. "rho = -0.00" reads as a tiny negative effect rather than as nothing,
    which is the opposite of what the number says.
    """
    if abs(value) < 0.005:
        return "0.00"
    return f"{value:+.2f}"


def _reading(forward: Optional[dict], bridge: Optional[dict], scope: str) -> str:
    """One sentence, reporting whichever way it came out.

    All four branches ship. A module that could only phrase the result it hoped
    for would have decided the answer before the run — the same requirement
    `explain._warrant` is built to satisfy.
    """
    if not forward or not forward.get("usable"):
        return ("Whether these revisions have led the price has not been measured "
                "on a sample large enough to say.")

    rho, n = forward["rho"], forward["n"]
    # CAPITALISED, because this clause opens the sentence the panel renders as
    # a standalone paragraph. It read "across 119 names in the Dow..." on screen.
    window = f"Across {n} names in {scope}, over one {OUTCOME_DAYS}-day window"

    if not forward.get("excludesZero"):
        body = (f"{window}, the direction of estimate revisions had no detectable "
                f"relationship with what the price did next (rho = {_rho(rho)})")
    elif rho > 0:
        body = (f"{window}, names whose estimates were being raised did go on to "
                f"outperform their own market (rho = {_rho(rho)})")
    else:
        body = (f"{window}, names whose estimates were being raised went on to "
                f"UNDERperform their own market (rho = {_rho(rho)}), which is the "
                f"opposite of the documented effect and is reported as it came out")

    if not bridge or not bridge.get("usable") or not bridge.get("excludesZero"):
        return (body + ". That test used the estimate level, which is the only part "
                       "of this record with any history; it could not be shown to "
                       "track the count of analysts that actually decides the "
                       "verdict, so it says little about the reading above.")
    return body + "."


def for_panel(market: Optional[str] = None,
              measurement=_LOAD_FROM_DISK) -> Optional[dict]:
    """What the expectations panel prints about its own signal.

    None when the measurement has never been run — withheld rather than guessed,
    the same rule `pretrade` applies to an uncalibrated check and
    `lensagreement.for_synthesis` to an unmeasured agreement.
    """
    if measurement is _LOAD_FROM_DISK:
        measurement = load_measurement()
    if not isinstance(measurement, dict):
        return None

    population = _population(measurement, market)
    if population is None:
        return None

    forward = population.get("forward")
    bridge = population.get("bridge")
    scope = population.get("label") or "the calibration universes"
    return {
        "measuredOn": measurement.get("measuredOn"),
        "scope": scope,
        "forward": forward,
        "bridge": bridge,
        "dispersion": population.get("dispersion"),
        "evidence": _grade(forward, bridge),
        "reading": _reading(forward, bridge, scope),
        "window": {"signalFrom": SIGNAL_FROM_DAYS, "signalTo": SIGNAL_TO_DAYS,
                   "outcome": OUTCOME_DAYS},
        # THE LIMIT, IN THE PAYLOAD. It is not a footnote the panel may choose to
        # drop: a single-window cross-section reported without it reads as a
        # backtest, and this app does not have one for this signal.
        "limit": (f"One window, not a backtest. Every name was measured over the "
                  f"same {OUTCOME_DAYS} days, so the returns share whatever the "
                  f"market did over them and the sample is worth far fewer than "
                  f"its name count. Returns are demeaned within each market before "
                  f"anything is computed, which removes the largest part of that "
                  f"but not all of it."),
    }
