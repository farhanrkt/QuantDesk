"""Lens agreement, and the chance correction that makes it readable.

WHAT THESE TESTS PROTECT, IN ORDER OF HOW BADLY IT WOULD HURT TO LOSE IT

1. The chance correction itself. Two lenses with skewed habits agree most of
   the time while sharing nothing, and a build that quietly started reporting
   raw agreement would print a number that reads as corroboration and is not.
   The planted case here is exactly the one the module docstring describes:
   independent draws that agree 58% of the time and must come back as κ = 0.

2. A refusal is not a neutral vote. A bank's declined accounting screens must
   drop out of the pair rather than arrive as a zero, because a zero agrees
   with every other lens that happened to be quiet. Asserted by showing the two
   readings DIFFER, so a regression that mapped None to 0 fails rather than
   passing on a coincidence.

3. Every branch of the report exists. A module that could only phrase the
   result it hoped for would have decided the answer before the run. Three
   different measurements are pushed through and each has to produce its own
   sentence.

4. Nothing aggregates and nothing weights. The payload's key set is asserted,
   because a `confidence` or `weight` field is exactly what a later change adds
   without noticing, and a measured agreement scaling a verdict is the
   composite score this app refuses to have, arrived at sideways.

5. Withheld beats guessed. No file, too few names, a degenerate matrix — each
   comes back as an absence with a reason, never as a plausible number.

EVERY NUMBER BELOW IS DERIVED BY HAND in the test that uses it, from a planted
confusion table or a planted eigenvalue spectrum. None of them is produced by a
second implementation of the estimator under test.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from _lib import lensagreement as LA


# --------------------------------------------------------------------------- #
# Builders — planted tables, expanded into the vote series the module reads
# --------------------------------------------------------------------------- #
def from_table(table: dict[tuple[int, int], int]) -> tuple[list[int], list[int]]:
    """Two vote series realising a planted confusion table exactly.

    `{(a, b): count}`. Expanding a table rather than sampling is what makes the
    expected kappa an arithmetic fact rather than something that happens to be
    close on this seed.
    """
    first, second = [], []
    for (a, b), count in table.items():
        first.extend([a] * count)
        second.extend([b] * count)
    return first, second


# --------------------------------------------------------------------------- #
# 1. Cohen's kappa, against tables computed with a pencil
# --------------------------------------------------------------------------- #
def test_kappa_matches_a_hand_computed_two_by_two():
    """The textbook 2x2, worked out in this docstring rather than in code.

        observed:   20 agree on +1, 15 agree on -1, 5 + 10 disagree, n = 50
                    p_o = 35 / 50 = 0.70

        marginals:  A says +1 on 25/50 = 0.50 and -1 on 0.50
                    B says +1 on 30/50 = 0.60 and -1 on 0.40
                    p_e = 0.50 x 0.60 + 0.50 x 0.40 = 0.50

        kappa    =  (0.70 - 0.50) / (1 - 0.50) = 0.40
    """
    a, b = from_table({(1, 1): 20, (1, -1): 5, (-1, 1): 10, (-1, -1): 15})
    result = LA.cohens_kappa(a, b)
    assert result["n"] == 50
    assert result["observed"] == pytest.approx(0.70)
    assert result["chance"] == pytest.approx(0.50)
    assert result["kappa"] == pytest.approx(0.40)


def test_kappa_matches_a_hand_computed_three_by_three():
    """The three-level case, because a vote has three states and not two.

        diagonal 10 + 20 + 40 = 70 of 100, so p_o = 0.70
        both marginals come out 0.20 / 0.30 / 0.50 by construction, so
        p_e = 0.20^2 + 0.30^2 + 0.50^2 = 0.04 + 0.09 + 0.25 = 0.38
        kappa = (0.70 - 0.38) / 0.62 = 0.32 / 0.62 = 0.5161...
    """
    a, b = from_table({
        (-1, -1): 10, (-1, 0): 5, (-1, 1): 5,
        (0, -1): 5, (0, 0): 20, (0, 1): 5,
        (1, -1): 5, (1, 0): 5, (1, 1): 40,
    })
    result = LA.cohens_kappa(a, b)
    assert result["observed"] == pytest.approx(0.70)
    assert result["chance"] == pytest.approx(0.38)
    assert result["kappa"] == pytest.approx(0.32 / 0.62)


def test_two_lenses_that_share_nothing_agree_most_of_the_time():
    """THE REASON THIS MODULE EXISTS, planted as an exact product table.

    Two lenses that each say "+1" on 70% of names and are otherwise unrelated
    produce the independent joint distribution 0.49 / 0.21 / 0.21 / 0.09. They
    land on the same label 58 times in 100 — a number that reads as substantial
    corroboration and is worth nothing, because 58% is also exactly what chance
    supplies. The correction has to return zero here, to the last decimal.
    """
    a, b = from_table({(1, 1): 49, (1, 0): 21, (0, 1): 21, (0, 0): 9})
    result = LA.cohens_kappa(a, b)
    assert result["observed"] == pytest.approx(0.58)
    assert result["chance"] == pytest.approx(0.58)
    assert result["kappa"] == pytest.approx(0.0, abs=1e-12)


def test_kappa_goes_negative_when_two_lenses_agree_less_than_chance():
    """Below-chance agreement is a finding, not an error to clamp at zero.

        observed: only the 10 + 10 off-diagonal... no — the diagonal is
        5 + 5 = 10 of 50, so p_o = 0.20
        A says +1 on 25/50 = 0.50, -1 on 0.50; B the same by symmetry
        p_e = 0.50 x 0.50 + 0.50 x 0.50 = 0.50
        kappa = (0.20 - 0.50) / 0.50 = -0.60
    """
    a, b = from_table({(1, 1): 5, (1, -1): 20, (-1, 1): 20, (-1, -1): 5})
    result = LA.cohens_kappa(a, b)
    assert result["observed"] == pytest.approx(0.20)
    assert result["kappa"] == pytest.approx(-0.60)


def test_two_lenses_that_never_vary_are_undefined_rather_than_perfect():
    """Chance agreement of 1 has no kappa, and 0 would be the wrong answer.

    Two lenses that both said "+1" on every name agree 100% of the time — and
    chance also supplies 100%, so there is no room left for the statistic to
    measure. Reporting 0 would read as "no better than chance"; reporting 1
    would read as perfect corroboration. Neither is supportable, so the module
    says so and the sample is treated as unusable.
    """
    result = LA.cohens_kappa([1] * 40, [1] * 40)
    assert result["observed"] == pytest.approx(1.0)
    assert result["chance"] == pytest.approx(1.0)
    assert result["kappa"] is None
    assert "one level" in result["undefined"]

    pair = LA.pair_agreement("Flow", "Trend", [1] * 40, [1] * 40)
    assert pair["usable"] is False


def test_nothing_to_compare_is_none_rather_than_zero():
    assert LA.cohens_kappa([], []) is None
    assert LA.cohens_kappa([None, None], [1, 0]) is None


# --------------------------------------------------------------------------- #
# 2. A refusal is not a neutral vote
# --------------------------------------------------------------------------- #
def test_a_lens_that_could_not_read_is_dropped_rather_than_counted_neutral():
    """The Quality lens refuses on banks. That refusal must not vote.

    Both series below hold the same eight opinions plus four names where the
    second lens declined. Measured correctly, the kappa is the kappa of those
    eight. Measured by mapping the refusals to a neutral 0 — which is what a
    later change would do without noticing — the second lens gains four
    agreements with the first lens's own zeros and the number moves.

    Asserting only the first would pass even if None became 0 whenever the
    other side happened to be neutral, so the two are asserted to DIFFER.
    """
    first = [1, 1, -1, -1, 0, 0, 1, -1, 0, 0, 0, 0]
    second = [1, -1, -1, 1, 0, 1, 1, -1, None, None, None, None]

    honest = LA.cohens_kappa(first, second)
    assert honest["n"] == 8

    as_neutral = LA.cohens_kappa(first, [0 if v is None else v for v in second])
    assert as_neutral["n"] == 12
    assert honest["kappa"] != pytest.approx(as_neutral["kappa"])


def test_misaligned_series_raise_rather_than_pairing_the_wrong_companies():
    """Truncating to the shorter series would pair one company's flow vote with
    a different company's trend vote and return a perfectly plausible kappa."""
    with pytest.raises(ValueError):
        LA.cohens_kappa([1, 0, -1], [1, 0])


# --------------------------------------------------------------------------- #
# 3. Kendall's tau-b — the ordinal half
# --------------------------------------------------------------------------- #
def test_tau_b_matches_a_hand_counted_table_with_ties_on_both_sides():
    """Counted pair by pair in this docstring; ties are most of the work.

        a = [-1, -1,  0,  1,  1]
        b = [-1,  0,  0,  1,  1]

        of the 10 pairs: (1,2) and (4,5) are tied in a; (2,3) and (4,5) are
        tied in b; the remaining 7 are all concordant and none is discordant.

        n0 = 10, n1 = 2, n2 = 2, C - D = 7
        tau_b = 7 / sqrt((10 - 2)(10 - 2)) = 7 / 8 = 0.875
    """
    tau = LA.kendall_tau_b([-1, -1, 0, 1, 1], [-1, 0, 0, 1, 1])
    assert tau == pytest.approx(0.875)


def test_tau_b_and_kappa_answer_different_questions():
    """A perfectly inverted lens: same labels almost never, opposite always.

    Kappa sees two lenses that rarely land on the same word and reports close
    to nothing. Tau-b sees a perfect inverse ordering and reports -1. Both are
    correct and the pair is the reason this module carries two statistics —
    reporting either alone would describe half of what is there.
    """
    first = [1, 1, 1, 0, 0, -1, -1, -1, 1, 0, -1, 1]
    second = [-value for value in first]

    assert LA.kendall_tau_b(first, second) == pytest.approx(-1.0)
    assert abs(LA.cohens_kappa(first, second)["kappa"]) < 0.3


def test_tau_b_is_withheld_when_a_lens_never_varies():
    assert LA.kendall_tau_b([1, 1, 1, 1], [1, 0, -1, 0]) is None


# --------------------------------------------------------------------------- #
# 4. The bootstrap interval
# --------------------------------------------------------------------------- #
def test_the_interval_brackets_the_point_estimate():
    a, b = from_table({
        (-1, -1): 10, (-1, 0): 5, (-1, 1): 5,
        (0, -1): 5, (0, 0): 20, (0, 1): 5,
        (1, -1): 5, (1, 0): 5, (1, 1): 40,
    })
    point = LA.cohens_kappa(a, b)["kappa"]
    interval = LA.bootstrap_kappa(a, b)
    assert interval["low"] < point < interval["high"]
    assert interval["draws"] > 0


def test_the_interval_narrows_as_the_sample_grows():
    """More names, a tighter interval. The property that makes it a precision
    statement rather than decoration."""
    small = from_table({(1, 1): 20, (1, -1): 5, (-1, 1): 10, (-1, -1): 15})
    large = from_table({(1, 1): 200, (1, -1): 50, (-1, 1): 100, (-1, -1): 150})

    narrow = LA.bootstrap_kappa(*large)
    wide = LA.bootstrap_kappa(*small)
    assert (narrow["high"] - narrow["low"]) < (wide["high"] - wide["low"]) / 2


def test_the_same_votes_always_produce_the_same_interval():
    """Seeded, because a stamped research number that moved when nothing changed
    would be indistinguishable from one that moved because something did."""
    a, b = from_table({(1, 1): 30, (1, 0): 15, (0, 1): 15, (0, 0): 40})
    assert LA.bootstrap_kappa(a, b) == LA.bootstrap_kappa(a, b)


def test_an_independent_pair_does_not_exclude_zero_and_an_identical_one_does():
    independent = from_table({(1, 1): 49, (1, 0): 21, (0, 1): 21, (0, 0): 9})
    assert LA.pair_agreement("Flow", "Trend", *independent)["excludesZero"] is False

    votes = ([1, 0, -1] * 20)
    assert LA.pair_agreement("Flow", "Trend", votes, votes)["excludesZero"] is True


# --------------------------------------------------------------------------- #
# 5. The effective lens count
# --------------------------------------------------------------------------- #
def test_a_duplicated_lens_collapses_the_effective_count_to_a_known_value():
    """Four columns, two of them identical, worked out from the eigenvalues.

    A correlation matrix of {A, A, B, C} where B and C are independent of A and
    of each other is block diagonal. The duplicated block has eigenvalues 2 and
    0; B and C contribute 1 each. So the spectrum is [2, 1, 1, 0] and

        effective N = (2 + 1 + 1 + 0)^2 / (4 + 1 + 1 + 0) = 16 / 6 = 2.667

    Four lenses carrying two and two-thirds lenses' worth of information, which
    is the whole point of reporting a participation ratio instead of a count.
    """
    rng = np.random.default_rng(7)
    n = 240
    first = list(rng.choice([-1, 0, 1], size=n))
    votes = {
        "flow": first,
        "trend": list(first),                       # an exact duplicate
        "value": list(rng.choice([-1, 0, 1], size=n)),
        "quality": list(rng.choice([-1, 0, 1], size=n)),
    }
    result = LA.effective_lenses(votes)
    assert result["available"] is True
    assert result["measuredLenses"] == 4
    assert result["completeCases"] == n
    # The planted value is 16/6; the two "independent" columns are independent
    # only in expectation on a finite sample, so the tolerance is the sampling
    # error in their correlations rather than slack in the estimator.
    assert result["effectiveLenses"] == pytest.approx(16 / 6, abs=0.15)


def test_four_independent_lenses_come_back_as_nearly_four():
    rng = np.random.default_rng(11)
    votes = {lens: list(rng.choice([-1, 0, 1], size=400))
             for lens in ("flow", "trend", "value", "quality")}
    assert LA.effective_lenses(votes)["effectiveLenses"] == pytest.approx(4.0, abs=0.2)


def test_a_lens_with_no_variation_is_dropped_and_named_rather_than_nan():
    """A constant column has no standard deviation, so every correlation with it
    is nan — and one nan cell refuses the whole matrix. Dropping the column
    keeps the measurement the other three lenses can still support."""
    rng = np.random.default_rng(3)
    votes = {
        "flow": list(rng.choice([-1, 0, 1], size=200)),
        "trend": list(rng.choice([-1, 0, 1], size=200)),
        "value": list(rng.choice([-1, 0, 1], size=200)),
        "quality": [1] * 200,
    }
    result = LA.effective_lenses(votes)
    assert result["available"] is True
    assert result["measuredLenses"] == 3
    assert result["droppedForNoVariation"] == ["Quality"]


def test_too_few_complete_cases_is_withheld_with_a_reason():
    votes = {
        "flow": [1, 0, -1] * 4,
        "trend": [0, 1, -1] * 4,
        "value": [1, 1, 0] * 4,
        "quality": [None] * 12,
    }
    result = LA.effective_lenses(votes)
    assert result["available"] is False
    assert "0 names" in result["reason"]


def test_the_complete_case_rule_is_not_quietly_pairwise():
    """The participation ratio must use rows where EVERY lens read.

    Assembling a correlation matrix cell by cell from different subsets is what
    makes its eigenvalues go negative, and a participation ratio computed from
    negative eigenvalues is a plausible number from an unusable matrix. Here 40
    names have all four lenses and 60 more have only three, so a pairwise
    implementation would report a complete-case count above 40.
    """
    rng = np.random.default_rng(5)
    votes = {lens: list(rng.choice([-1, 0, 1], size=100))
             for lens in ("flow", "trend", "value", "quality")}
    votes["quality"] = votes["quality"][:40] + [None] * 60
    assert LA.effective_lenses(votes)["completeCases"] == 40


# --------------------------------------------------------------------------- #
# 6. The reported payload — nothing aggregates, nothing weights
# --------------------------------------------------------------------------- #
def measurement(kappa_table: dict, *, names: int = 120, market: str = "US") -> dict:
    """A stamped-artifact shape holding one planted family agreement."""
    price, filings = from_table(kappa_table)
    rng = np.random.default_rng(2)
    votes = {lens: list(rng.choice([-1, 0, 1], size=len(price)))
             for lens in LA.LENS_ORDER}
    population = {"label": "the test universe", "names": names,
                  **LA.measure(votes, {"price": price, "filings": filings})}
    return {"measuredOn": "2026-08-29", "universeLabel": "the test universe",
            "namesMeasured": names,
            "populations": {"ALL": population, market: population}}


def test_the_payload_carries_no_score_weight_or_rating():
    """The key set, asserted rather than the wording.

    A `confidence`, `weight`, `strength` or `score` field is exactly what a
    later change adds without noticing, and a measured agreement that scaled a
    verdict would be the composite this app refuses to have — arrived at
    sideways, through a statistic that sounds too technical to be a
    recommendation.
    """
    report = LA.for_synthesis("US", measurement(
        {(1, 1): 49, (1, 0): 21, (0, 1): 21, (0, 0): 9}))
    assert set(report) == {"measuredOn", "scope", "families", "pairs",
                           "lenses", "reading"}

    def keys(node):
        if isinstance(node, dict):
            return set(node) | {k for value in node.values() for k in keys(value)}
        if isinstance(node, list):
            return {k for item in node for k in keys(item)}
        return set()

    forbidden = {"score", "weight", "confidence", "rating", "strength",
                 "conviction", "grade", "rank", "verdict", "recommendation",
                 "independentSources", "adjustment", "multiplier"}
    assert not {key for key in keys(report) if key.lower() in forbidden}


def test_the_pair_payload_reports_its_own_arithmetic():
    """Observed and chance are printed beside kappa so a reader can check it."""
    pair = LA.pair_agreement("Flow", "Trend",
                             *from_table({(1, 1): 20, (1, -1): 5,
                                          (-1, 1): 10, (-1, -1): 15}))
    assert pair["observed"] == pytest.approx(0.70)
    assert pair["chance"] == pytest.approx(0.50)
    assert pair["kappa"] == pytest.approx(0.40)


# --------------------------------------------------------------------------- #
# 7. The sentence, and what it may not turn into
#
# The reading was 239 words: chance-corrected agreement, the declared pair, the
# participation ratio, and two paragraphs on what kappa cannot settle. All true,
# all the longest block on the page, and all a defence of the method rather than
# a finding about the company. It moved to RESEARCH_ROADMAP §15, which exists to
# hold exactly that.
#
# What is asserted here is what survived: the number, the scope, a direction
# read from the SIGN rather than from what the run happened to find, and no
# causal claim. That last one is the whole reason a short sentence is safe —
# "they agree no more than chance" is a measurement; "they are independent"
# would be a conclusion the statistic cannot support.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("table, phrase", [
    # Indistinguishable from zero — as the real run came out.
    ({(1, 1): 49, (1, 0): 21, (0, 1): 21, (0, 0): 9},
     "no more often than chance would put them there"),
    # Agreeing well beyond chance: the branch that would take the claim away.
    ({(1, 1): 95, (1, 0): 5, (0, 1): 5, (0, 0): 95},
     "rather more often than chance alone would produce"),
    # Below chance, which is a finding rather than reassurance.
    ({(1, 1): 5, (1, 0): 60, (0, 1): 60, (0, 0): 5},
     "less often than chance alone would produce"),
])
def test_the_reading_reads_its_own_sign(table, phrase):
    """All three branches ship. A module that could only phrase the result it
    hoped for would have decided the answer before the run."""
    report = LA.for_synthesis("US", measurement(table))
    assert phrase in report["reading"]


def test_the_reading_carries_the_number_and_the_denominator():
    """A kappa with no sample size behind it is not a measurement. The scope has
    to travel with it for the same reason the pre-trade panel names the universe
    beside every firing rate."""
    report = LA.for_synthesis("US", measurement(
        {(1, 1): 49, (1, 0): 21, (0, 1): 21, (0, 0): 9}))
    reading = report["reading"]
    assert "κ = +0.00" in reading
    assert "100 names" in reading
    assert "the test universe" in reading


@pytest.mark.parametrize("table", [
    {(1, 1): 49, (1, 0): 21, (0, 1): 21, (0, 0): 9},
    {(1, 1): 95, (1, 0): 5, (0, 1): 5, (0, 0): 95},
    {(1, 1): 5, (1, 0): 60, (0, 1): 60, (0, 0): 5},
])
def test_the_reading_never_makes_a_causal_claim(table):
    """Kappa measures redundancy, not causation: two independent tests of a
    sound company should agree, so a low reading is not evidence of
    independence and a high one is not evidence of shared inputs. The short
    sentence is only safe because it states the MEASUREMENT and stops.

    Shortening prose is exactly where a hedge gets dropped by accident, so the
    words that would constitute the overclaim are named here."""
    reading = LA.for_synthesis("US", measurement(table))["reading"]
    for overclaim in ("independent", "unrelated", "share no inputs", "proves",
                      "because", "therefore"):
        assert overclaim not in reading.lower(), f"reading claims more than κ supports: {overclaim}"


# --------------------------------------------------------------------------- #
# 8. Withheld beats guessed
# --------------------------------------------------------------------------- #
def test_no_measurement_on_disk_renders_nothing():
    assert LA.for_synthesis("US", None) is None
    assert LA.for_synthesis("US", {}) is None
    assert LA.for_synthesis("US", {"populations": {}}) is None


def test_a_pair_measured_on_too_few_names_is_withheld_entirely():
    """The same rule `pretrade` applies to an uncalibrated check. A kappa from
    twenty companies is noise with a decimal point on it, and printing it with
    a measurement date would make it look checked."""
    few = {(1, 1): 8, (1, 0): 4, (0, 1): 4, (0, 0): 8}
    assert LA.for_synthesis("US", measurement(few, names=24)) is None


def test_an_unmeasured_market_falls_back_to_the_combined_population():
    report = LA.for_synthesis("ID", measurement(
        {(1, 1): 49, (1, 0): 21, (0, 1): 21, (0, 0): 9}, market="US"))
    assert report is not None
    assert report["scope"] == "the test universe"


def test_a_corrupt_artifact_is_treated_as_no_artifact(tmp_path):
    broken = tmp_path / "lens_agreement.json"
    broken.write_text("{not json")
    assert LA.load_measurement(broken) is None

    wrong_shape = tmp_path / "other.json"
    wrong_shape.write_text(json.dumps({"measuredOn": "2026-08-29"}))
    assert LA.load_measurement(wrong_shape) is None


def test_the_shipped_artifact_is_readable_and_stamped():
    """If a measurement is committed it has to be loadable and dated. A missing
    file is a legitimate state — the panel withholds — but a present one that
    cannot be parsed is a broken build."""
    if not LA.MEASUREMENT_PATH.exists():
        pytest.skip("no measurement has been run in this checkout")
    payload = LA.load_measurement()
    assert payload is not None
    assert payload["measuredOn"]
    assert payload["populations"]
