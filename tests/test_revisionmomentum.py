"""The revision-momentum measurement, against planted associations.

WHAT THESE TESTS PROTECT

1. The bridge gates the grade. A forward result measured on a proxy that cannot
   be shown to track the voting quantity says nothing about the vote, and the
   grade has to fall to `weak` however clean the forward number looks. That is
   the whole reason the bridge is measured at all.

2. All four reading branches ship. A module that could only phrase the result it
   hoped for would have decided the answer before the run — the same requirement
   `explain._warrant` is built to satisfy.

3. Demeaning happens WITHIN market. A window where one index rose and the other
   fell would otherwise hand every name in one market a positive outcome and
   every name in the other a negative one, and a signal that merely differed in
   average level between the two would score a correlation from that alone.

4. Nothing here becomes a weight. `evidence` is read by the explanation that
   reports it and by nothing else.
"""

from __future__ import annotations

import numpy as np
import pytest

from _lib import revisionmomentum as RM


def usable(rho=0.4, n=100, excludes=True):
    return {"label": "planted", "n": n, "rho": rho,
            "low": 0.2 if excludes else -0.2, "high": 0.6,
            "excludesZero": excludes, "usable": n >= RM.MIN_SAMPLE}


# --------------------------------------------------------------------------- #
# Demeaning
# --------------------------------------------------------------------------- #
def test_demeaning_is_within_group_not_global():
    """The market is removed per market. Planted so the two differ sharply.

    US names average +10%, ID names average -10%. After demeaning within market
    every name sits at zero; a global demean would leave the US names at +10
    and the ID names at -10, which is the artefact this exists to remove.
    """
    values = [0.10, 0.10, -0.10, -0.10]
    groups = ["US", "US", "ID", "ID"]
    out = RM.demean_within(values, groups)
    assert all(abs(v) < 1e-12 for v in out)


def test_demeaning_preserves_within_group_ordering():
    out = RM.demean_within([0.20, 0.10, 0.00], ["US", "US", "US"])
    assert out[0] > out[1] > out[2]


def test_a_missing_value_stays_missing():
    out = RM.demean_within([0.2, None, 0.4], ["US", "US", "US"])
    assert out[1] is None
    assert out[0] is not None and out[2] is not None


def test_a_group_with_no_usable_members_does_not_raise():
    assert RM.demean_within([None, None], ["ID", "ID"]) == [None, None]


# --------------------------------------------------------------------------- #
# The estimators
# --------------------------------------------------------------------------- #
def test_spearman_is_one_on_a_monotone_but_non_linear_relationship():
    """A rank correlation must not care about the shape, only the ordering.

    This is why the module uses it: estimate revisions are zero-inflated with
    tails set by names whose earnings are near zero, and a Pearson correlation
    would largely be a statement about those.
    """
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [1.0, 4.0, 9.0, 16.0, 2500.0]
    assert RM.spearman(x, y)["rho"] == pytest.approx(1.0)


def test_spearman_returns_none_when_either_side_never_varies():
    assert RM.spearman([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None


def test_pairing_drops_names_missing_either_quantity():
    """Tested on `_paired` directly: two surviving names is below the floor
    `spearman` needs, so going through it would conflate the pairing rule with
    the sample-size refusal."""
    a, b = RM._paired([1.0, None, 3.0, 4.0], [1.0, 2.0, None, 4.0])
    assert list(a) == [1.0, 4.0]
    assert list(b) == [1.0, 4.0]


def test_a_non_finite_value_is_dropped_like_a_missing_one():
    a, _ = RM._paired([1.0, float("nan"), 3.0], [1.0, 2.0, 3.0])
    assert a.size == 2


def test_spearman_refuses_fewer_than_three_paired_names():
    assert RM.spearman([1.0, None, 3.0, 4.0], [1.0, 2.0, None, 4.0]) is None


def test_misaligned_series_raise_rather_than_silently_truncating():
    """Two lengths mean the caller misaligned its names. Truncating would pair
    one company's signal with another company's return."""
    with pytest.raises(ValueError):
        RM.spearman([1.0, 2.0, 3.0], [1.0, 2.0])


def test_the_bootstrap_interval_brackets_the_point_estimate():
    rng = np.random.default_rng(11)
    x = rng.normal(size=120)
    y = x + rng.normal(scale=0.5, size=120)
    point = RM.spearman(x, y)["rho"]
    interval = RM.bootstrap_spearman(x, y, draws=400)
    assert interval["low"] < point < interval["high"]


def test_a_planted_null_produces_an_interval_that_straddles_zero():
    rng = np.random.default_rng(5)
    x, y = rng.normal(size=200), rng.normal(size=200)
    out = RM.association("planted null", x, y)
    assert out["excludesZero"] is False


def test_association_marks_a_small_sample_unusable():
    rng = np.random.default_rng(7)
    n = RM.MIN_SAMPLE - 1
    out = RM.association("small", rng.normal(size=n), rng.normal(size=n))
    assert out["usable"] is False


# --------------------------------------------------------------------------- #
# The dispersion frame
# --------------------------------------------------------------------------- #
def test_the_frame_reports_quartiles_not_a_mean():
    """The quantity is a ratio bounded below by zero with a long right tail.

    Planted with one enormous outlier: the median must not move to it.
    """
    spreads = [0.5] * 40 + [40.0]
    frame = RM.dispersion_frame(spreads)
    assert frame["median"] == pytest.approx(0.5)
    assert frame["n"] == 41


def test_too_few_names_gives_no_frame():
    """No frame means the explanation says there is none, rather than guessing."""
    assert RM.dispersion_frame([0.5] * (RM.MIN_SAMPLE - 1)) is None


def test_non_finite_spreads_are_excluded_from_the_frame():
    assert RM.dispersion_frame([0.5] * 40 + [np.nan, None])["n"] == 40


# --------------------------------------------------------------------------- #
# The grade — the bridge is what gates it
# --------------------------------------------------------------------------- #
def test_a_clean_forward_result_on_a_broken_bridge_is_only_weak():
    """The core rule of this module.

    The forward test measures the estimate LEVEL; the lens votes on the
    revision COUNT. If the two cannot be shown to move together, a forward
    result says nothing about the vote — and it must not be allowed to read as
    though it does.
    """
    assert RM._grade(usable(rho=0.5), usable(excludes=False)) == "weak"
    assert RM._grade(usable(rho=0.5), None) == "weak"


def test_a_clean_forward_result_on_a_sound_bridge_is_moderate():
    assert RM._grade(usable(rho=0.5), usable()) == "moderate"


def test_a_null_forward_result_is_weak_even_with_a_sound_bridge():
    assert RM._grade(usable(excludes=False), usable()) == "weak"


def test_no_forward_measurement_is_graded_none():
    assert RM._grade(None, usable()) == "none"
    assert RM._grade(usable(n=5), usable()) == "none"


def test_the_grade_is_never_strong():
    """One window is not a body of evidence, whatever it happens to contain."""
    for forward in (usable(rho=0.9), usable(rho=-0.9), usable(rho=0.0)):
        assert RM._grade(forward, usable()) != "strong"


# --------------------------------------------------------------------------- #
# The reading — all four branches ship
# --------------------------------------------------------------------------- #
def test_the_null_branch_says_no_detectable_relationship():
    text = RM._reading(usable(rho=0.01, excludes=False), usable(), "the Dow")
    assert "no detectable relationship" in text


def test_the_positive_branch_reports_outperformance():
    text = RM._reading(usable(rho=0.4), usable(), "the Dow")
    assert "outperform" in text and "UNDER" not in text


def test_the_negative_branch_is_reported_as_it_came_out():
    """A result opposite to the documented effect is a finding, not a bug."""
    text = RM._reading({**usable(rho=-0.4), "low": -0.6, "high": -0.2},
                       usable(), "the Dow")
    assert "UNDERperform" in text
    assert "opposite of the documented effect" in text


def test_an_unmeasured_forward_test_says_so():
    assert "has not been measured" in RM._reading(None, usable(), "the Dow")


def test_a_broken_bridge_is_disclosed_in_the_reading_itself():
    """Not only in the grade. A reader seeing the sentence has to be told."""
    text = RM._reading(usable(rho=0.4), usable(excludes=False), "the Dow")
    assert "could not be shown to track" in text


def test_a_null_prints_as_zero_rather_than_negative_zero():
    """`{:+.2f}` renders -0.004 as "-0.00", which reads as a tiny negative
    effect rather than as nothing."""
    assert RM._rho(-0.004) == "0.00"
    assert RM._rho(0.004) == "0.00"
    assert RM._rho(-0.42) == "-0.42"


# --------------------------------------------------------------------------- #
# The panel payload
# --------------------------------------------------------------------------- #
def measurement(**over) -> dict:
    population = {"label": "the Dow", "forward": usable(rho=0.01, excludes=False),
                  "bridge": usable(), "dispersion": {"n": 100, "median": 0.54,
                                                     "p25": 0.4, "p75": 0.75}}
    population.update(over)
    return {"measuredOn": "2026-09-01", "populations": {"ALL": population,
                                                        "US": population}}


def test_for_panel_prefers_the_market_specific_population():
    other = {"label": "IDX30", "forward": usable(rho=0.3), "bridge": usable(),
             "dispersion": None}
    payload = measurement()
    payload["populations"]["ID"] = other
    assert RM.for_panel("ID", measurement=payload)["scope"] == "IDX30"
    assert RM.for_panel("US", measurement=payload)["scope"] == "the Dow"


def test_for_panel_returns_none_when_never_measured():
    """Withheld rather than guessed — the same rule `pretrade` applies."""
    assert RM.for_panel("US", measurement=None) is None


def test_the_panel_payload_always_carries_the_limit():
    """A single-window cross-section reported without it reads as a backtest."""
    out = RM.for_panel("US", measurement=measurement())
    assert "One window, not a backtest" in out["limit"]
    assert str(RM.OUTCOME_DAYS) in out["limit"]


def test_the_panel_payload_carries_no_weight_or_multiplier():
    """`evidence` is a word for the explanation to print, never a number to
    multiply by. Asserted on the key set for the reason `test_pretrade` asserts
    on its own."""
    out = RM.for_panel("US", measurement=measurement())
    assert set(out) == {"measuredOn", "scope", "forward", "bridge", "dispersion",
                        "evidence", "reading", "window", "limit"}
    assert isinstance(out["evidence"], str)
