"""
posterior.py
============
What a screen's flag is actually worth, given how rare the thing it screens for is.

THE PROBLEM WITH A FLAG
-----------------------
"The M-Score flags" is not the decision-relevant number, and the app has been
saying so in prose since the quality lens shipped: Beneish catches roughly
three-quarters of manipulators, and on a population where manipulation is rare
that also means most flags are false alarms. Prose is where that sentence has
been sitting. It can be a number.

The number is the positive predictive value — the probability that a flagged
company is a real manipulator — and it needs three inputs, all of which exist:

    P(manipulator | flag) = sens . p / (sens . p + fpr . (1 - p))

Sensitivity and the false-positive rate are published. The prevalence `p` is
not a property of the model at all; it is a claim about the population the
reader is drawing from, which is exactly why it has to be explicit and movable
rather than baked into a single headline figure.

WHY THE PRIOR IS THE WHOLE FEATURE
----------------------------------
Across the range the literature supports, the posterior moves from about 3% to
about 41%. Both ends are informative and they are informative in the SAME
direction, which is the finding worth putting on screen:

    prior 0.69%  (Beneish's own population estimate)      -> 2.9% true
    prior 2.84%  (the sample his coefficients were fitted on) -> 11.3% true
    prior 10%    (all securities fraud, Dyck et al.)      -> 32.5% true
    prior 14%    (the top of their 95% interval)          -> 41.4% true

At every prior anybody has published, a Beneish flag is MORE LIKELY TO BE A
FALSE ALARM THAN NOT. That is a much stronger statement than "most flags are
false alarms" and it survives disagreement about the prior, which is the only
input a reader could reasonably argue with.

WHICH PROBIT, AND WHY IT MATTERS
--------------------------------
Beneish reports two estimations. The WESML (weighted) probit assumes a
population manipulation rate of 0.69%; the unweighted probit assumes 2.844%, the
rate in its own sample. THE COEFFICIENTS EVERY IMPLEMENTATION USES — the -4.84
constant and the eight weights in `quality.beneish_m_score` — are the unweighted
ones. So the classifier in this app carries an implicit prior of 2.844%, and
that is the default here: it is the one prior under which the published error
rates and the shipped coefficients describe the same model.

THE CLEAN CASE IS SHOWN TOO, AND FRAMED AS A MOVE RATHER THAN A VERDICT
------------------------------------------------------------------------
The mirror-image number — P(manipulator | no flag) — is 0.84% at the default
prior. Rendered on its own beside a clean score it would read as a clean bill of
health, which is the misreading this codebase works hardest against.

So both branches are reported as a SHIFT FROM THE PRIOR rather than as a level:
the test takes 2.8% to 11.3% when it fires and to 0.8% when it does not. That
framing is what makes the clean case honest — it says the probability was
already small and the test made it somewhat smaller, rather than announcing that
nothing is wrong.

WHAT THIS DOES NOT CLAIM
------------------------
Nothing here is fitted, measured or predicted by this app. It is Bayes' theorem
applied to two published constants, and it inherits every limit of the study
they came from — see `_lib/screendomain.py`, which states the sample those
constants were measured on and how far this use sits from it.

The arithmetic also assumes the error rates transfer to the population the prior
describes. They were measured against manipulators identified by SEC enforcement
action; the wider priors below refer to broader definitions of fraud, and are
carried to bracket the range rather than because the rates are known to hold
there. Each anchor says which it is.

References
----------
Beneish, M. D. (1999). "The Detection of Earnings Manipulation." Financial
    Analysts Journal 55(5), 24-36. At the -1.78 cutoff the model classifies
    about 76% of manipulators correctly and misclassifies about 17.5% of
    non-manipulators, a trade-off chosen for a 30:1 relative cost of missing a
    manipulator against a false alarm. The WESML probit assumes a prior of
    0.0069; the unweighted probit, whose coefficients are the ones in common
    use, assumes 0.02844.
Dyck, A., Morse, A., & Zingales, L. (2024). "How pervasive is corporate fraud?"
    Review of Accounting Studies. Samples of DETECTED financial fraud average
    2-3% of firms a year; allowing for undetected fraud they estimate about 10%
    of large public firms commit securities fraud in a given year, 95% interval
    7-14%; accounting restatements run near 13% a year.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

# --------------------------------------------------------------------------- #
# The published operating characteristics
# --------------------------------------------------------------------------- #
# Two constants and a cutoff, all from Beneish (1999). They are reference data,
# not tuning parameters: changing one without a citation would turn a published
# finding into an opinion with a decimal point on it.
BENEISH_CUTOFF = -1.78
BENEISH_SENSITIVITY = 0.76        # manipulators correctly classified
BENEISH_FALSE_POSITIVE = 0.175    # non-manipulators wrongly flagged

# The prior the app's own coefficients were estimated under. Default for the
# same reason: it is the only prior at which the published error rates and the
# shipped coefficients describe one model rather than two.
BENEISH_MODEL_PRIOR = 0.02844

BENEISH_CITATION = "Beneish (1999), Financial Analysts Journal 55(5), 24-36"

# WHAT COUNTS AS "MANIPULATION" CHANGES WITH THE PRIOR, and the anchors have to
# say so. Beneish's manipulators were companies subject to SEC enforcement
# action. A prior drawn from a broader definition — all securities fraud
# including the undetected, or every restatement — is answering a different
# question, and the sensitivity was never measured against those events. Those
# anchors are carried to bracket the range, flagged `extrapolated`, because the
# conclusion holds across all of them and that is worth showing.
PRIOR_ANCHORS: list[dict] = [
    {"prior": 0.0069, "label": "Beneish's own population estimate",
     "source": "the prior his weighted (WESML) probit assumes",
     "event": "manipulation as his enforcement sample defined it",
     "extrapolated": False},
    {"prior": 0.02, "label": "detected financial fraud, low end",
     "source": "Dyck, Morse & Zingales (2024)",
     "event": "fraud that was actually caught",
     "extrapolated": False},
    {"prior": BENEISH_MODEL_PRIOR, "label": "the sample these coefficients were fitted on",
     "source": "the prior Beneish's unweighted probit assumes",
     "event": "manipulation as his enforcement sample defined it",
     "extrapolated": False},
    {"prior": 0.03, "label": "detected financial fraud, high end",
     "source": "Dyck, Morse & Zingales (2024)",
     "event": "fraud that was actually caught",
     "extrapolated": False},
    {"prior": 0.07, "label": "all securities fraud, bottom of the interval",
     "source": "Dyck, Morse & Zingales (2024), 95% interval",
     "event": "securities fraud including the undetected",
     "extrapolated": True},
    {"prior": 0.10, "label": "all securities fraud, central estimate",
     "source": "Dyck, Morse & Zingales (2024)",
     "event": "securities fraud including the undetected",
     "extrapolated": True},
    {"prior": 0.13, "label": "accounting restatements",
     "source": "Dyck, Morse & Zingales (2024)",
     "event": "any failure to apply accounting rules",
     "extrapolated": True},
    {"prior": 0.14, "label": "all securities fraud, top of the interval",
     "source": "Dyck, Morse & Zingales (2024), 95% interval",
     "event": "securities fraud including the undetected",
     "extrapolated": True},
]

# The stops a reader can move the prior to. Every one is a round number someone
# could defend rather than a point on a dense grid, so the control cannot land
# somewhere meaningless. The range deliberately extends past the literature at
# both ends: seeing the posterior at 30% is what shows how hard you would have
# to push the prior before a flag became more likely true than not.
PRIOR_STOPS: tuple[float, ...] = (
    0.005, 0.0069, 0.0075, 0.01, 0.015, 0.02, 0.025, BENEISH_MODEL_PRIOR, 0.03,
    0.04, 0.05, 0.07, 0.10, 0.13, 0.14, 0.20, 0.25, 0.30,
)


def _pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def posterior_given_flag(prior: float, sensitivity: float = BENEISH_SENSITIVITY,
                         false_positive: float = BENEISH_FALSE_POSITIVE) -> float:
    """P(the company really is a manipulator | the screen flagged it)."""
    true_positive = sensitivity * prior
    false_alarm = false_positive * (1.0 - prior)
    total = true_positive + false_alarm
    return float(true_positive / total) if total > 0 else float("nan")


def posterior_given_clean(prior: float, sensitivity: float = BENEISH_SENSITIVITY,
                          false_positive: float = BENEISH_FALSE_POSITIVE) -> float:
    """P(the company is a manipulator anyway | the screen did NOT flag it).

    Reported alongside its flagged twin rather than on its own. A single small
    number beside a clean score reads as a clean bill of health; the pair reads
    as how far the test moved the estimate, which is what it actually did.
    """
    specificity = 1.0 - false_positive
    missed = (1.0 - sensitivity) * prior
    correct_pass = specificity * (1.0 - prior)
    total = missed + correct_pass
    return float(missed / total) if total > 0 else float("nan")


def _nearest_stop(prior: Optional[float]) -> float:
    if prior is None or not np.isfinite(prior):
        return BENEISH_MODEL_PRIOR
    return min(PRIOR_STOPS, key=lambda stop: abs(stop - float(prior)))


def curve() -> list[dict]:
    """The posterior at every stop, with the sentence for each.

    THE WHOLE CURVE IS SERVED, not just the selected point, and that is an
    architectural choice rather than a payload decision. The reader can move the
    prior; if the panel computed the posterior as they moved it, the arithmetic
    and its interpretation would live in TypeScript, where this codebase
    deliberately keeps neither. Every stop arrives already computed and already
    worded, so the control selects rather than calculates.
    """
    out = []
    anchors = {round(a["prior"], 6): a for a in PRIOR_ANCHORS}
    for stop in PRIOR_STOPS:
        anchor = anchors.get(round(stop, 6))
        flagged = posterior_given_flag(stop)
        clean = posterior_given_clean(stop)
        out.append({
            "prior": float(stop),
            "priorText": _pct(stop, 2 if stop < 0.01 else 1),
            "label": (anchor or {}).get("label"),
            "source": (anchor or {}).get("source"),
            "event": (anchor or {}).get("event"),
            "extrapolated": bool((anchor or {}).get("extrapolated")),
            "isDefault": abs(stop - BENEISH_MODEL_PRIOR) < 1e-9,
            "givenFlag": flagged,
            "givenFlagText": _pct(flagged, 0),
            "falseAlarmText": _pct(1.0 - flagged, 0),
            "givenClean": clean,
            "givenCleanText": _pct(clean, 2),
        })
    return out


def for_beneish(band: Optional[str], prior: Optional[float] = None,
                indices_available: Optional[int] = None,
                indices_total: int = 8) -> Optional[dict]:
    """What this company's M-Score reading is worth, at a stated prior.

    `band` is `quality.beneish_m_score`'s own verdict, so the branch shown here
    can never disagree with the score printed beside it. Returns None when no
    score was computed — there is nothing to condition on.
    """
    if band not in ("flagged", "borderline", "clean"):
        return None

    selected = _nearest_stop(prior)
    flagged = band == "flagged"
    given_flag = posterior_given_flag(selected)
    given_clean = posterior_given_clean(selected)
    posterior = given_flag if flagged else given_clean

    points = curve()
    flags = [p["givenFlag"] for p in points
             if not p["extrapolated"] and p["prior"] <= 0.14]
    partial = (indices_available is not None
               and indices_available < (indices_total or 8))

    return {
        "screen": "beneish",
        "flagged": flagged,
        "band": band,
        "prior": float(selected),
        "priorText": _pct(selected, 2 if selected < 0.01 else 1),
        "posterior": float(posterior),
        "posteriorText": _pct(posterior, 0 if flagged else 2),
        "givenFlag": float(given_flag),
        "givenClean": float(given_clean),
        # How far the test moved the estimate, which is the honest framing for
        # both branches — see the module docstring.
        "shift": {"from": float(selected), "fromText": _pct(selected, 2),
                  "to": float(posterior),
                  "toText": _pct(posterior, 0 if flagged else 2)},
        "characteristics": {
            "cutoff": BENEISH_CUTOFF,
            "sensitivity": BENEISH_SENSITIVITY,
            "falsePositiveRate": BENEISH_FALSE_POSITIVE,
            "specificity": 1.0 - BENEISH_FALSE_POSITIVE,
            "citation": BENEISH_CITATION,
            "note": (
                f"At the {BENEISH_CUTOFF} cutoff the model catches about "
                f"{_pct(BENEISH_SENSITIVITY, 0)} of manipulators and misclassifies about "
                f"{_pct(BENEISH_FALSE_POSITIVE, 1)} of everyone else — a trade-off chosen "
                f"at a 30-to-1 cost of missing a manipulator, on the paper's own data."),
        },
        "curve": points,
        "anchors": PRIOR_ANCHORS,
        # The strongest thing the arithmetic supports, and it is strong BECAUSE
        # it survives every prior anyone has published rather than resting on one.
        "robustRange": {
            "lowText": _pct(min(flags), 0), "highText": _pct(max(flags), 0),
            "sentence": (
                f"Across every prevalence the literature supports — from "
                f"{_pct(min(a['prior'] for a in PRIOR_ANCHORS), 2)} to "
                f"{_pct(max(a['prior'] for a in PRIOR_ANCHORS), 0)} — a flag comes out "
                f"between {_pct(posterior_given_flag(min(a['prior'] for a in PRIOR_ANCHORS)), 0)} "
                f"and {_pct(posterior_given_flag(max(a['prior'] for a in PRIOR_ANCHORS)), 0)} "
                f"likely to be a real manipulator. It never reaches even odds, so the "
                f"conclusion does not depend on agreeing about the prior."),
        },
        "partialScore": partial,
        "partialNote": (
            f"This score was assembled from {indices_available} of {indices_total} "
            f"indices. The error rates above were measured on the complete eight-index "
            f"model, so they describe a classifier slightly different from the one that "
            f"produced the number beside them." if partial else None),
        "caveat": (
            "Bayes' theorem on two published constants — nothing here is fitted or "
            "measured by this app. The error rates come from companies caught by SEC "
            "enforcement between 1982 and 1988; how far that sits from the company on "
            "screen is set out under 'where these numbers come from'."),
    }
