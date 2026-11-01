"""The share register — the third body of data.

WHAT THESE TESTS PROTECT, IN ORDER OF HOW BADLY IT WOULD HURT TO LOSE IT

1. HALF A REGISTER IS STILL A READING. Float and share count are independently
   optional and coverage on IDX is patchy. One half missing removes its weight;
   it never becomes an imputed 50, and it never discards the other half.

2. A RIGHTS ISSUE IS VISIBLE. The annualised trend hides a single 30% event
   behind two flat years, so the largest single step is reported beside it.
   That step is the fact a holder is diluted by.

3. THE SHARE COUNT ARRIVES AS DATED RECORDS. It crosses a JSON cache and the
   wire, so a pandas Series at that boundary would have to be special-cased in
   two places and would come back as something else in a third.

4. LOW FLOAT IS A TRADEABILITY FACT, NOT A VERDICT. The bands are judgement and
   say so: on IDX the median listing is two-thirds insider-held, so a
   percentile band would call the typical company unremarkable — true, useless.

5. INSTITUTIONAL OWNERSHIP NEVER SCORES. "Somebody professional owns this" is an
   argument from authority and the holders are mostly index funds.

The wording is free to change. Those five are not.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from _lib import ownership as O


# --------------------------------------------------------------------------- #
# Planted registers
# --------------------------------------------------------------------------- #
def share_records(start: float = 1.0e9, annual_growth: float = 0.0,
                  years: float = 3.0, points: int = 13,
                  step_at: int | None = None, step_size: float = 0.0):
    """Dated share counts with a stated growth rate and an optional single step.

    The step is what a rights issue looks like: one period where the count jumps
    and then resumes. `annual_growth` is applied on top so the two can be told
    apart in the output.
    """
    today = dt.date(2026, 9, 1)
    spacing = (years * 365.25) / max(points - 1, 1)
    records = []
    count = start
    for index in range(points):
        when = today - dt.timedelta(days=int(spacing * (points - 1 - index)))
        if step_at is not None and index == step_at:
            count *= (1.0 + step_size)
        records.append({"date": when.isoformat(), "count": count})
        count *= (1.0 + annual_growth) ** (spacing / 365.25)
    return records


def register(insiders: float | None = 0.45, institutions: float | None = 0.12,
             shares=None, **share_kwargs) -> dict:
    return {
        "ok": True,
        "insidersPercentHeld": insiders,
        "institutionsPercentHeld": institutions,
        "institutionsCount": 40.0,
        "shares": share_records(**share_kwargs) if shares is None else shares,
    }


# ============================================================================ #
# 1. Half a register is still a reading
# ============================================================================ #
def test_a_missing_share_count_leaves_the_float_reading_intact():
    result = O.read(register(shares=[]))
    assert result["available"] is True
    assert result["float"]["available"] is True
    assert result["issuance"]["available"] is False
    assert "share-count" in result["reading"] or "share count" in result["reading"]


def test_a_missing_float_leaves_the_share_count_reading_intact():
    result = O.read(register(insiders=None))
    assert result["available"] is True
    assert result["float"]["available"] is False
    assert result["issuance"]["available"] is True


def test_neither_half_reading_is_an_unavailable_register_not_a_neutral_one():
    result = O.read(register(insiders=None, shares=[]))
    assert result["available"] is False
    assert "reason" in result


def test_a_missing_half_is_never_filled_in():
    """Imputing the missing half would move a thinly covered name toward the
    middle of the pack and call it a measurement."""
    result = O.read(register(shares=[]))
    assert result["issuance"].get("score") is None
    assert "score" not in result, (
        "the register must not blend its halves; `verdict.py` weights them by "
        "evidence grade in the one place that weights every component")


# ============================================================================ #
# 2. A rights issue is visible
# ============================================================================ #
def test_a_single_dilution_event_is_reported_beside_the_trend():
    """A 30% issue followed by two flat years annualises to about 9%, which
    reads as mild drift. The event is the fact."""
    result = O.issuance(register(step_at=4, step_size=0.30))
    assert result["available"] is True
    assert result["largestStep"] == pytest.approx(0.30, abs=0.01)
    assert result["largestStepAt"] is not None
    assert result["annualised"] < 0.30, "the trend does dilute the single event"


def test_steady_dilution_scores_worse_than_a_flat_count_which_scores_worse_than_a_buyback():
    diluting = O.read(register(annual_growth=0.20))["issuance"]["score"]
    flat = O.read(register(annual_growth=0.0))["issuance"]["score"]
    retiring = O.read(register(annual_growth=-0.20))["issuance"]["score"]
    assert diluting < flat < retiring


def test_extreme_issuance_saturates_rather_than_running_away():
    """A company retiring 25% a year and one retiring 60% are not a distinction
    this data supports making."""
    heavy = O.read(register(annual_growth=-0.30))["issuance"]["score"]
    absurd = O.read(register(annual_growth=-0.90))["issuance"]["score"]
    assert heavy == pytest.approx(absurd, abs=0.01)
    assert 0.0 <= heavy <= 100.0


def test_the_band_names_what_happened():
    assert O.read(register(annual_growth=0.40))["issuance"]["band"] == "severe"
    assert O.read(register(annual_growth=0.10))["issuance"]["band"] == "material"
    assert O.read(register(annual_growth=0.0))["issuance"]["band"] == "flat"
    assert O.read(register(annual_growth=-0.10))["issuance"]["band"] == "retiring"


def test_too_few_observations_is_not_a_trend():
    result = O.issuance(register(points=2))
    assert result["available"] is False
    assert str(O.MIN_SHARE_POINTS) in result["reason"]


def test_observations_inside_too_short_a_span_are_declined():
    result = O.issuance(register(points=6, years=0.1))
    assert result["available"] is False
    assert "span" in result["reason"]


# ============================================================================ #
# 3. Dated records, not a pandas Series
# ============================================================================ #
def test_records_survive_a_json_round_trip():
    import json

    payload = register(annual_growth=0.15)
    reloaded = json.loads(json.dumps(payload))
    assert O.read(reloaded)["issuance"]["annualised"] == pytest.approx(
        O.read(payload)["issuance"]["annualised"], abs=1e-9)


def test_a_bare_series_is_still_understood_in_process():
    """A caller holding one should not have to round-trip through JSON."""
    records = share_records(annual_growth=0.10)
    series = pd.Series([r["count"] for r in records],
                       index=pd.DatetimeIndex([r["date"] for r in records]))
    from_series = O.issuance({"shares": series})
    from_records = O.issuance({"shares": records})
    assert from_series["annualised"] == pytest.approx(from_records["annualised"])


def test_junk_records_are_dropped_rather_than_crashing():
    noise = [{"date": "not-a-date", "count": 5.0}, {"date": "2026-01-01", "count": None},
             {"date": "2026-02-01", "count": -3.0}, {"nope": 1}]
    assert O.issuance({"shares": noise})["available"] is False


# ============================================================================ #
# 4. Low float is a tradeability fact
# ============================================================================ #
def test_free_float_is_what_insiders_do_not_hold():
    result = O.free_float({"insidersPercentHeld": 0.68})
    assert result["freeFloat"] == pytest.approx(0.32)
    assert result["band"] == "moderate"


@pytest.mark.parametrize("insiders,band", [
    (0.95, "critical"), (0.85, "tight"), (0.68, "moderate"), (0.30, "comfortable"),
])
def test_the_float_bands_run_in_the_stated_order(insiders, band):
    assert O.free_float({"insidersPercentHeld": insiders})["band"] == band


def test_a_thinner_float_never_scores_better_than_a_wider_one():
    scores = [O.free_float({"insidersPercentHeld": 1 - value})["score"]
              for value in (0.03, 0.10, 0.25, 0.45, 0.70)]
    assert scores == sorted(scores)


def test_float_scoring_saturates_above_the_comfortable_line():
    """The difference between a 45% float and a 70% one does not matter to
    anybody's exit; the difference between 6% and 18% is the whole question."""
    wide = O.free_float({"insidersPercentHeld": 0.55})["score"]
    wider = O.free_float({"insidersPercentHeld": 0.10})["score"]
    assert wide == pytest.approx(wider)


def test_a_nonsense_insider_share_is_declined_rather_than_clamped():
    for value in (None, -0.2, 1.0, 4.5, "many"):
        assert O.free_float({"insidersPercentHeld": value})["available"] is False


def test_float_turnover_needs_both_halves():
    assert O.float_turnover(None, 1000.0) is None
    assert O.float_turnover(1000.0, None) is None
    assert O.float_turnover(0.0, 1000.0) is None
    assert O.float_turnover(1_000_000.0, 10_000.0) == pytest.approx(0.01)


def test_the_share_count_falls_back_to_the_registers_own_history():
    """The last observation IS shares outstanding, from the same fetch. Asking
    the company cache again is a second call per name in a whole-market scan,
    past that cache's eviction bound."""
    result = O.read(register(start=2.0e9, annual_growth=0.0), median_volume=1.0e6)
    assert result["sharesOutstanding"] == pytest.approx(2.0e9, rel=0.01)
    assert result["sharesOutstandingFrom"] == "the share-count history"
    assert result["floatTurnover"] is not None


def test_a_supplied_share_count_wins_over_the_history():
    result = O.read(register(), median_volume=1.0e6, shares_outstanding=5.0e9)
    assert result["sharesOutstanding"] == pytest.approx(5.0e9)
    assert result["sharesOutstandingFrom"] == "caller"


# ============================================================================ #
# 5. Institutional ownership never scores
# ============================================================================ #
def test_institutional_ownership_is_context_and_says_so():
    result = O.read(register(institutions=0.31))
    assert result["institutions"]["percentHeld"] == pytest.approx(0.31)
    assert "not scored" in result["institutions"]["note"]


def test_institutional_ownership_does_not_move_any_score():
    none_held = O.read(register(institutions=0.0))
    heavily_held = O.read(register(institutions=0.90))
    assert none_held["float"]["score"] == heavily_held["float"]["score"]
    assert none_held["issuance"]["score"] == heavily_held["issuance"]["score"]
