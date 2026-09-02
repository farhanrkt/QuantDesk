"""What a Beneish flag is worth, given how rare manipulation is.

The arithmetic is Bayes' theorem, which is not the interesting part. What these
tests protect is the honesty around it.

1. The constants are the published ones. Sensitivity, the false-positive rate
   and the cutoff are reference data from Beneish (1999), not tuning knobs, and
   an edit that "rounds them off" changes a published finding into an opinion.

2. The posterior is checked against an INDEPENDENT computation, not against a
   second copy of the formula. A test that reimplements the function it tests
   proves only that the author can copy.

3. The finding survives every prior in the literature. That is the claim the
   panel makes, and it is much stronger than "most flags are false alarms" —
   so it is asserted across the whole anchor range rather than at the default.

4. The clean branch is framed as a shift, never as a level. "0.84%" beside a
   clean score reads as a clean bill of health, and this codebase works harder
   against that misreading than against any other.

5. Nothing is coloured. The M-Score already carries the alarm; this number
   qualifies it downward at every prior, and a second warning colour would count
   one fact twice.
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from _lib import explain as E
from _lib import posterior as P


# --------------------------------------------------------------------------- #
# 1. The published constants, as published
# --------------------------------------------------------------------------- #
def test_the_operating_characteristics_are_the_ones_beneish_reports():
    """At the -1.78 cutoff Beneish reports ~76% of manipulators caught and
    ~17.5% of non-manipulators misclassified. These are citations, not
    parameters, and they are asserted so a later tweak has to argue with a
    paper rather than with a default."""
    assert P.BENEISH_CUTOFF == -1.78
    assert P.BENEISH_SENSITIVITY == 0.76
    assert P.BENEISH_FALSE_POSITIVE == 0.175
    assert P.BENEISH_CITATION.startswith("Beneish (1999)")


def test_the_default_prior_is_the_one_the_shipped_coefficients_assume():
    """Beneish reports two probits. The WESML one assumes a 0.69% population
    rate; the UNWEIGHTED one assumes 2.844% — and the unweighted coefficients
    are the ones every implementation uses, including `quality.beneish_m_score`.
    Defaulting to any other prior would pair the published error rates with a
    model they were not measured on."""
    assert P.BENEISH_MODEL_PRIOR == 0.02844
    assert P.for_beneish("flagged")["prior"] == 0.02844
    # And the app really does ship the unweighted constant.
    from _lib import quality as Q
    assert "-4.84" in Q.beneish_m_score.__doc__


def test_beneishs_own_population_estimate_is_among_the_anchors():
    priors = [a["prior"] for a in P.PRIOR_ANCHORS]
    assert 0.0069 in priors, "the WESML prior is the low end of the defensible range"
    assert max(priors) == 0.14, "the top of Dyck, Morse & Zingales's 95% interval"


def test_every_anchor_names_its_source_and_what_event_it_counts():
    """A prevalence is a claim about a population and about an EVENT. 'All
    securities fraud including the undetected' is not what Beneish's sensitivity
    was measured against, and an anchor that did not say so would silently
    change the question."""
    for anchor in P.PRIOR_ANCHORS:
        assert anchor["source"] and anchor["event"] and anchor["label"]
        assert 0.0 < anchor["prior"] < 1.0
        assert isinstance(anchor["extrapolated"], bool)
    broad = [a for a in P.PRIOR_ANCHORS if "undetected" in a["event"]]
    assert broad and all(a["extrapolated"] for a in broad), (
        "priors for a broader event class than the sensitivity was measured on "
        "must be marked as the extrapolation they are")


# --------------------------------------------------------------------------- #
# 2. The arithmetic, against an independent derivation
# --------------------------------------------------------------------------- #
def _by_counting(prior, sensitivity=0.76, false_positive=0.175, population=1_000_000):
    """Bayes the long way round: build the 2x2 table and count.

    Deliberately NOT the module's formula. Counting out a population of a
    million and dividing true positives by all positives is the same answer
    arrived at from the other direction, so agreement is evidence rather than
    tautology.
    """
    manipulators = population * prior
    honest = population - manipulators
    caught = manipulators * sensitivity
    false_alarms = honest * false_positive
    missed = manipulators * (1 - sensitivity)
    passed = honest * (1 - false_positive)
    return caught / (caught + false_alarms), missed / (missed + passed)


@pytest.mark.parametrize("prior", [0.0069, 0.01, 0.02844, 0.05, 0.10, 0.14, 0.30])
def test_the_posterior_matches_counting_out_a_population(prior):
    expected_flag, expected_clean = _by_counting(prior)
    assert P.posterior_given_flag(prior) == pytest.approx(expected_flag, rel=1e-9)
    assert P.posterior_given_clean(prior) == pytest.approx(expected_clean, rel=1e-9)


def test_a_perfect_screen_returns_the_prior_untouched_on_a_flag():
    """Sanity anchor at the boundary: a test that never errs makes a flag
    certain, and one that is pure noise leaves the prior exactly where it was."""
    assert P.posterior_given_flag(0.05, sensitivity=1.0, false_positive=0.0) == 1.0
    useless = P.posterior_given_flag(0.05, sensitivity=0.5, false_positive=0.5)
    assert useless == pytest.approx(0.05), "a coin-flip screen carries no information"


def test_the_posterior_rises_with_the_prior_and_never_leaves_zero_to_one():
    values = [P.posterior_given_flag(p) for p in P.PRIOR_STOPS]
    assert all(a < b for a, b in pairwise(values))
    assert all(0.0 < v < 1.0 for v in values)


# --------------------------------------------------------------------------- #
# 3. The finding survives disagreement about the prior
# --------------------------------------------------------------------------- #
def test_a_flag_is_more_likely_false_than_true_at_every_published_prior():
    """This is the claim the panel makes, and it is the reason the feature is
    worth shipping: it does not depend on winning the argument about the prior."""
    for anchor in P.PRIOR_ANCHORS:
        value = P.posterior_given_flag(anchor["prior"])
        assert value < 0.5, f"{anchor['label']} ({anchor['prior']}) gives {value:.3f}"


def test_the_robust_range_is_left_out_of_a_clean_reading():
    """It is a sentence about what a FLAG is worth. Appended to a clean reading
    it answers a question the company in front of the reader did not raise."""
    robust = P.for_beneish("clean")["robustRange"]["sentence"]
    clean = E.explain("manipulationPosterior", 0.0084, flagged=False,
                      prior_text="2.8%", robust=robust)["reading"]
    flagged = E.explain("manipulationPosterior", 0.113, flagged=True,
                        prior_text="2.8%", robust=robust)["reading"]
    assert "even odds" not in clean
    assert "even odds" in flagged


def test_the_robust_range_sentence_quotes_both_ends():
    sentence = P.for_beneish("flagged")["robustRange"]["sentence"]
    assert "0.69%" in sentence and "14%" in sentence
    assert "3%" in sentence and "41%" in sentence
    assert "never reaches even odds" in sentence


def test_the_curve_reaches_past_the_literature_at_both_ends():
    """Showing where the posterior WOULD cross a half is what makes the range
    meaningful — a reader can see how far the prior has to be pushed."""
    stops = P.PRIOR_STOPS
    assert min(stops) < min(a["prior"] for a in P.PRIOR_ANCHORS)
    assert max(stops) > max(a["prior"] for a in P.PRIOR_ANCHORS)
    assert P.posterior_given_flag(max(stops)) > 0.5


def test_every_curve_point_arrives_already_worded():
    """The control selects a point; it must never compute one. Arithmetic in
    TypeScript is arithmetic no pytest can reach."""
    for point in P.for_beneish("flagged")["curve"]:
        assert point["priorText"].endswith("%")
        assert point["givenFlagText"].endswith("%")
        assert point["falseAlarmText"].endswith("%")
        assert point["givenCleanText"].endswith("%")
        assert 0.0 < point["givenFlag"] < 1.0


def test_exactly_one_curve_point_is_the_default():
    defaults = [p for p in P.for_beneish("clean")["curve"] if p["isDefault"]]
    assert len(defaults) == 1
    assert defaults[0]["prior"] == P.BENEISH_MODEL_PRIOR


# --------------------------------------------------------------------------- #
# 4. The clean branch is a shift, never a level
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("band", ["clean", "borderline"])
def test_a_clean_reading_reports_the_move_rather_than_the_level(band):
    result = P.for_beneish(band)
    assert result["flagged"] is False
    assert result["shift"]["from"] == P.BENEISH_MODEL_PRIOR
    assert result["shift"]["to"] < result["shift"]["from"], "a clean test lowers it"
    reading = E.explain("manipulationPosterior", result["posterior"],
                        flagged=False, prior_text=result["priorText"])["reading"]
    assert "down from" in reading, "the level alone reads as a clean bill of health"
    assert result["priorText"] in reading


def test_a_clean_reading_says_what_the_screen_does_not_test():
    action = E.explain("manipulationPosterior", 0.008, flagged=False,
                       prior_text="2.8%")["action"]
    assert "not a clean bill of health" in action


def test_borderline_takes_the_clean_branch_because_it_did_not_cross_the_cutoff():
    assert P.for_beneish("borderline")["flagged"] is False
    assert P.for_beneish("flagged")["flagged"] is True


# --------------------------------------------------------------------------- #
# 5. Never a second warning colour
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("flagged", [True, False])
def test_the_posterior_is_never_coloured(flagged):
    """The M-Score already carries the alarm and this number qualifies it
    DOWNWARD at every prior. A warning colour here would count one fact twice
    and make the deflating number look like a second flag."""
    value = 0.113 if flagged else 0.0084
    result = E.explain("manipulationPosterior", value, flagged=flagged,
                       prior_text="2.8%")
    assert result["band"] == "context"
    assert result["tone"] == "neutral"


def test_the_flagged_reading_states_the_false_alarm_share_explicitly():
    reading = E.explain("manipulationPosterior", 0.113, flagged=True,
                        prior_text="2.8%")["reading"]
    assert "11%" in reading and "89%" in reading
    assert "false alarms" in reading


# --------------------------------------------------------------------------- #
# Degradation and plumbing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("band", [None, "unknown", "", "nonsense"])
def test_no_score_means_no_posterior_rather_than_a_guess(band):
    assert P.for_beneish(band) is None


def test_a_partial_score_says_the_error_rates_describe_a_different_classifier():
    partial = P.for_beneish("flagged", indices_available=6, indices_total=8)
    assert partial["partialScore"] is True
    assert "six" in partial["partialNote"] or "6 of 8" in partial["partialNote"]
    reading = E.explain("manipulationPosterior", partial["posterior"], flagged=True,
                        prior_text=partial["priorText"], partial=True)["reading"]
    assert "fewer than the eight indices" in reading
    assert P.for_beneish("flagged", indices_available=8)["partialScore"] is False


def test_an_arbitrary_prior_snaps_to_a_stop_rather_than_being_taken_literally():
    """Every stop is a number somebody could defend. Accepting 0.0417 would put
    a made-up prevalence on screen with two decimal places of false authority."""
    assert P.for_beneish("flagged", prior=0.0417)["prior"] in P.PRIOR_STOPS
    assert P.for_beneish("flagged", prior=0.099)["prior"] == 0.10
    assert P.for_beneish("flagged", prior=None)["prior"] == P.BENEISH_MODEL_PRIOR
    assert P.for_beneish("flagged", prior=float("nan"))["prior"] == P.BENEISH_MODEL_PRIOR


def test_the_branch_shown_can_never_disagree_with_the_score_beside_it():
    """`band` comes straight from `quality.beneish_m_score`, so the posterior
    cannot report a flag's odds next to a clean score."""
    from _lib import quality as Q
    assert Q.posterior_lib is P
    for band in ("flagged", "borderline", "clean"):
        assert P.for_beneish(band)["band"] == band


def test_the_caveat_disclaims_having_measured_anything():
    caveat = P.for_beneish("flagged")["caveat"]
    assert "nothing here is fitted or measured by this app" in caveat.lower()
    assert "1982" in caveat


def test_the_characteristics_note_states_both_error_rates_and_the_cost_ratio():
    note = P.for_beneish("clean")["characteristics"]["note"]
    assert "76%" in note and "17.5%" in note
    assert "30-to-1" in note
    assert math.isclose(P.for_beneish("clean")["characteristics"]["specificity"], 0.825)
