"""The estimate record, checked against hand arithmetic and planted tables.

The yfinance analyst frames are built by hand here so every input is known.
That matters more on this lens than on the others: the source's column
capitalisation is inconsistent (`upLast7days` beside `downLast7Days` in one
table), several cells are legitimately absent on real listings, and the
difference between "nobody moved" and "no table came back" is a difference
between a reading and a refusal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import expectations as X

PERIODS = ["0q", "+1q", "0y", "+1y"]


def revisions(up30=(0, 0, 0, 0), down30=(0, 0, 0, 0),
              up7=(0, 0, 0, 0), down7=(0, 0, 0, 0)) -> pd.DataFrame:
    """An `eps_revisions` table, in the source's own mixed capitalisation."""
    return pd.DataFrame(
        {"upLast7days": list(up7), "upLast30days": list(up30),
         "downLast30days": list(down30), "downLast7Days": list(down7)},
        index=PERIODS)


def trend(current=(1.0, 1.0, 4.0, 4.4), ago90=(1.0, 1.0, 4.0, 4.4)) -> pd.DataFrame:
    return pd.DataFrame(
        {"current": list(current), "7daysAgo": list(current),
         "30daysAgo": list(current), "60daysAgo": list(ago90),
         "90daysAgo": list(ago90)},
        index=PERIODS)


def record(**over) -> dict:
    base = {
        "analysts": 20.0,
        "eps_trend": trend(),
        "eps_revisions": revisions(),
        "earnings_history": pd.DataFrame(),
        "growth_estimates": pd.DataFrame(),
        "targets": {},
        "currency": "USD",
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# Revision breadth — the quantity that votes
# --------------------------------------------------------------------------- #
def test_breadth_pools_the_two_annual_periods_and_ignores_the_quarters():
    """The quarters are fetched and must not reach the vote.

    Planted so the quarters point hard the OTHER way: if they leaked in, the
    diffusion would be negative instead of +1.
    """
    frame = revisions(up30=(0, 0, 6, 4), down30=(9, 9, 0, 0))
    out = X.revision_breadth(frame)
    assert (out["up"], out["down"]) == (10, 0)
    assert out["diffusion"] == pytest.approx(1.0)
    assert out["state"] == "rising"


def test_breadth_sums_counts_rather_than_averaging_the_two_diffusions():
    """A period with twenty moves must outweigh one with two.

    0y is 1 up / 1 down (diffusion 0) and +1y is 18 up / 0 down (diffusion +1).
    Averaging the two gives +0.5; summing the counts gives 19/20 = +0.9. The
    second is right for the same reason averaging two percentages over
    different denominators is wrong.
    """
    frame = revisions(up30=(0, 0, 1, 18), down30=(0, 0, 1, 0))
    assert X.revision_breadth(frame)["diffusion"] == pytest.approx(0.9)


def test_quiet_is_not_mixed_and_carries_a_null_diffusion():
    """Nobody moving and movement cancelling must not render alike."""
    out = X.revision_breadth(revisions())
    assert out["available"] is True
    assert out["state"] == "quiet"
    assert out["diffusion"] is None
    assert out["moves"] == 0


def test_an_absent_table_is_unavailable_rather_than_quiet():
    out = X.revision_breadth(pd.DataFrame())
    assert out["available"] is False
    assert out["state"] is None


def test_too_few_moves_is_thin_however_lopsided():
    """One analyst moving is one opinion, not a consensus shifting."""
    out = X.revision_breadth(revisions(up30=(0, 0, 2, 0)))
    assert out["diffusion"] == pytest.approx(1.0)
    assert out["state"] == "thin"
    assert out["thin"] is True


def test_the_diffusion_band_is_symmetric():
    up = X.revision_breadth(revisions(up30=(0, 0, 6, 0), down30=(0, 0, 3, 0)))
    down = X.revision_breadth(revisions(up30=(0, 0, 3, 0), down30=(0, 0, 6, 0)))
    assert up["state"] == "rising"
    assert down["state"] == "falling"
    assert up["diffusion"] == pytest.approx(-down["diffusion"])


def test_the_band_must_be_cleared_not_met():
    """A 5-to-3 split is exactly 0.25 and reads as mixed.

    The boundary belongs on the mixed side: 'not clearly either' is a real
    finding and a direction called from a split this even is not.
    """
    exact = X.revision_breadth(revisions(up30=(0, 0, 5, 0), down30=(0, 0, 3, 0)))
    assert exact["diffusion"] == pytest.approx(X.DIFFUSION_BAND)
    assert exact["state"] == "mixed"


def test_a_five_to_four_split_is_mixed():
    """Inside the band is a real state, not a failure to decide."""
    assert X.revision_breadth(
        revisions(up30=(0, 0, 5, 0), down30=(0, 0, 4, 0)))["state"] == "mixed"


def test_the_seven_day_window_reads_its_own_columns():
    """Both capitalisations of the 7-day columns are handled."""
    frame = revisions(up7=(0, 0, 4, 0), down7=(0, 0, 0, 0),
                      up30=(0, 0, 0, 0), down30=(0, 0, 9, 0))
    week = X.revision_breadth(frame, window="7d")
    month = X.revision_breadth(frame, window="30d")
    assert week["state"] == "rising"
    assert month["state"] == "falling"


# --------------------------------------------------------------------------- #
# Revision drift — the magnitude, which does not vote
# --------------------------------------------------------------------------- #
def test_drift_is_a_share_of_where_the_estimate_started():
    out = X.revision_drift(trend(current=(1, 1, 5.0, 1), ago90=(1, 1, 4.0, 1)), "0y", 90)
    assert out["change"] == pytest.approx(0.25)
    assert out["direction"] == "up"
    assert out["state"] == "moved"


def test_a_sign_change_returns_no_percentage_and_says_so():
    """A consensus crossing zero is a change of forecast, not a 300% revision."""
    out = X.revision_drift(trend(current=(1, 1, 2.0, 1), ago90=(1, 1, -1.0, 1)), "0y", 90)
    assert out["state"] == "swung"
    assert out["change"] is None
    assert out["direction"] == "up"


def test_a_zero_earlier_estimate_is_refused_rather_than_divided_by():
    out = X.revision_drift(trend(current=(1, 1, 2.0, 1), ago90=(1, 1, 0.0, 1)), "0y", 90)
    assert out["available"] is False


def test_a_move_inside_the_noise_floor_is_flat():
    out = X.revision_drift(trend(current=(1, 1, 4.001, 1), ago90=(1, 1, 4.0, 1)), "0y", 90)
    assert out["state"] == "flat"


def test_a_missing_level_is_unavailable():
    frame = trend()
    frame.loc["0y", "90daysAgo"] = np.nan
    assert X.revision_drift(frame, "0y", 90)["available"] is False


# --------------------------------------------------------------------------- #
# The surprise record
# --------------------------------------------------------------------------- #
def surprises(rows) -> pd.DataFrame:
    return pd.DataFrame(
        {"epsActual": [r[0] for r in rows],
         "epsEstimate": [r[1] for r in rows],
         "epsDifference": [None] * len(rows),
         "surprisePercent": [r[2] for r in rows]},
        # Real quarter-ends, in order. A generated "2024-04-31" is not a date
        # and pandas is right to refuse it.
        index=pd.to_datetime(["2025-03-31", "2025-06-30", "2025-09-30",
                              "2025-12-31", "2026-03-31"][:len(rows)]))


def test_an_unreported_quarter_is_dropped_not_counted_as_a_miss():
    """Yahoo carries the upcoming quarter with an estimate and a null actual.

    Counting it would put a company one row behind its own record on the day
    before it reports.
    """
    out = X.surprise_record(surprises([
        (1.0, 0.9, 0.11), (1.1, 1.0, 0.10), (1.2, 1.1, 0.09), (np.nan, 1.3, np.nan),
    ]))
    assert out["reported"] == 3
    assert out["beats"] == 3
    assert out["misses"] == 0


def test_the_surprise_summary_is_a_median_not_a_mean():
    """One restatement-sized surprise must not move the summary."""
    out = X.surprise_record(surprises([
        (1.0, 1.0, 0.01), (1.0, 1.0, 0.02), (1.0, 1.0, 0.03), (1.0, 1.0, 4.00),
    ]))
    assert out["medianSurprise"] == pytest.approx(0.025)


def test_too_few_reported_quarters_is_unavailable():
    assert X.surprise_record(surprises([(1.0, 0.9, 0.11)]))["available"] is False


def test_a_missing_column_is_refused_rather_than_guessed():
    frame = surprises([(1.0, 0.9, 0.11), (1.1, 1.0, 0.1)]).drop(columns=["surprisePercent"])
    assert X.surprise_record(frame)["available"] is False


# --------------------------------------------------------------------------- #
# Target dispersion — and the number this module will not print
# --------------------------------------------------------------------------- #
def test_dispersion_is_the_spread_over_the_mean():
    out = X.target_dispersion({"high": 150.0, "low": 50.0, "mean": 100.0,
                               "median": 100.0, "current": 90.0})
    assert out["spread"] == pytest.approx(1.0)


def test_the_mean_target_is_never_served():
    """The level is a point price forecast with no stated method. Refused.

    Guarded by name rather than by inspection, because the failure mode is a
    later change helpfully passing the whole dict through.
    """
    out = X.target_dispersion({"high": 150.0, "low": 50.0, "mean": 100.0,
                               "median": 110.0, "current": 90.0})
    assert set(out) == {"available", "spread", "high", "low"}
    assert "mean" not in out and "median" not in out and "current" not in out


def test_dispersion_carries_no_band():
    """No threshold without a measured frame — see the note in the module."""
    out = X.target_dispersion({"high": 400.0, "low": 215.0, "mean": 324.0})
    assert "band" not in out


def test_an_inverted_range_is_refused():
    assert X.target_dispersion({"high": 50.0, "low": 150.0,
                                "mean": 100.0})["available"] is False


# --------------------------------------------------------------------------- #
# Applicability — the refusal, which must never read as a clean reading
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("analysts", [None, np.nan, 0.0, 1.0, 2.0])
def test_thin_or_absent_coverage_is_a_refusal(analysts):
    out = X.analyze(record(analysts=analysts))
    assert out["applicable"] is False
    assert out["verdict"] == "NOT_COVERED"
    assert out["tone"] == "none"
    # SAID IN WORDS. An empty expectations panel is the easiest state in this
    # app to misread as reassurance.
    assert "not a clean bill of health" in out["refusal"]


def test_the_refusal_carries_no_reading_fields():
    """A refusal must not ship a breadth or a drift for a panel to render."""
    out = X.analyze(record(analysts=1.0))
    for key in ("breadth", "drift", "surprise", "dispersion", "consensusGrowth"):
        assert key not in out


def test_exactly_the_minimum_analysts_is_applicable():
    """The floor is inclusive; three analysts is a consensus."""
    assert X.analyze(record(analysts=float(X.MIN_ANALYSTS)))["applicable"] is True


# --------------------------------------------------------------------------- #
# The lens verdict
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("up", "down", "verdict", "tone"), [
    ((0, 0, 8, 2), (0, 0, 1, 1), "RISING", "good"),
    ((0, 0, 1, 1), (0, 0, 8, 2), "FALLING", "bad"),
    ((0, 0, 5, 0), (0, 0, 4, 0), "MIXED", "neutral"),
    ((0, 0, 0, 0), (0, 0, 0, 0), "QUIET", "neutral"),
    ((0, 0, 2, 0), (0, 0, 0, 0), "THIN", "neutral"),
])
def test_verdict_and_tone_move_together(up, down, verdict, tone):
    out = X.analyze(record(eps_revisions=revisions(up30=up, down30=down)))
    assert (out["verdict"], out["tone"]) == (verdict, tone)


def test_only_a_clear_direction_gets_a_directional_tone():
    """Quiet, thin and mixed are readings — none of them is a direction."""
    for up, down in [((0, 0, 0, 0), (0, 0, 0, 0)),
                     ((0, 0, 2, 0), (0, 0, 0, 0)),
                     ((0, 0, 5, 0), (0, 0, 4, 0))]:
        out = X.analyze(record(eps_revisions=revisions(up30=up, down30=down)))
        assert out["tone"] == "neutral"


def test_an_unreadable_revision_table_does_not_vote():
    out = X.analyze(record(eps_revisions=pd.DataFrame()))
    assert out["verdict"] == "UNREADABLE"
    assert out["tone"] == "none"


def test_the_payload_carries_its_two_hazards():
    """The limits live in the payload so a redesign cannot drop them."""
    out = X.analyze(record())
    assert len(out["limits"]) == 2
    assert any("opinion, not a measurement" in line for line in out["limits"])
    assert any("fiscal-year boundary" in line for line in out["limits"])


def test_no_aggregate_score_anywhere_in_the_payload():
    """This lens must not acquire the composite the app refuses to have.

    Asserted on the key set for the reason `test_pretrade` asserts on its own:
    a `score` or `strength` field is exactly what a later change adds without
    noticing.
    """
    out = X.analyze(record(eps_revisions=revisions(up30=(0, 0, 8, 0))))
    assert set(out) == {
        "applicable", "analysts", "minAnalysts", "verdict", "tone", "headline",
        "breadth", "breadth7d", "drift", "surprise", "consensusGrowth",
        "dispersion", "periods", "limits",
    }


# --------------------------------------------------------------------------- #
# Consensus growth
# --------------------------------------------------------------------------- #
def test_consensus_growth_reads_the_next_fiscal_year():
    frame = pd.DataFrame({"stockTrend": [0.07, 0.01, 0.18, 0.08],
                          "indexTrend": [0.49, 0.24, 0.31, 0.15]}, index=PERIODS)
    out = X.consensus_growth(frame)
    assert out["nextYear"] == pytest.approx(0.08)
    assert out["thisYear"] == pytest.approx(0.18)
    assert out["horizon"] == "one fiscal year"


def test_a_null_long_term_growth_row_does_not_break_the_read():
    """LTG is null on every listing tested and must never be reached for."""
    frame = pd.DataFrame({"stockTrend": [0.07, 0.01, 0.18, 0.08, np.nan]},
                         index=[*PERIODS, "LTG"])
    assert X.consensus_growth(frame)["nextYear"] == pytest.approx(0.08)


def test_a_missing_company_column_is_refused():
    frame = pd.DataFrame({"indexTrend": [0.1] * 4}, index=PERIODS)
    assert X.consensus_growth(frame)["available"] is False
