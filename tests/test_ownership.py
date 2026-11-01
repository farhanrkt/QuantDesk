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

6. A SPLIT IS NOT AN ISSUE. The provider's counts are not restated for splits,
   so NVDA's 10-for-1 read as a 900% issue and fired the heavy-issuance gate.
   Counts are restated in today's shares, wherever near the ex-date the
   provider's own step happens to land.

The wording is free to change. Those six are not.
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


# ============================================================================ #
# 6. A split is not an issue
# ============================================================================ #
SPLIT_DAY = dt.date(2024, 6, 10)


def split_records(ratio: float = 10.0, offset_days: int = 0,
                  both_units_on_step_day: bool = False,
                  annual_growth: float = 0.0, start: float = 2.46e9):
    """Three years of share counts across one split, unrestated, as the provider
    sends them: fortnightly, plus daily in the fortnight around the ex-date.

    Counts before the provider's step are in the old units. The step lands
    `offset_days` from the ex-date, because that is what was measured: two days
    before it for NVDA and AVGO, one before for CMG, one after for WMT.
    `both_units_on_step_day` repeats the step day in the old units as well, as
    NVDA's own series does.
    """
    first = dt.date(2023, 9, 1)
    ex = (SPLIT_DAY - first).days
    offsets = sorted(set(range(0, 1096, 14)) | set(range(ex - 7, ex + 8)))
    step = SPLIT_DAY + dt.timedelta(days=offset_days)
    records = []
    for offset in offsets:
        when = first + dt.timedelta(days=offset)
        count = start * (1.0 + annual_growth) ** (offset / 365.25)
        if when == step and both_units_on_step_day:
            records.append({"date": when.isoformat(), "count": count})
        records.append({"date": when.isoformat(),
                        "count": count * ratio if when >= step else count})
    return records


def with_split(records, ratio: float = 10.0) -> dict:
    return {"ok": True, "insidersPercentHeld": 0.04, "shares": records,
            "splits": [{"date": SPLIT_DAY.isoformat(), "ratio": ratio}]}


def test_a_split_alone_reads_as_a_flat_share_count():
    """NVDA's 10-for-1 read as a share count growing 121% a year."""
    result = O.issuance(with_split(split_records()))
    assert result["band"] == "flat"
    assert result["annualised"] == pytest.approx(0.0, abs=1e-9)
    assert result["largestStep"] == pytest.approx(0.0, abs=1e-9)
    assert result["latestCount"] == pytest.approx(24.6e9), "counts are in today's shares"
    assert "10-for-1 split of 2024-06-10" in result["reading"]


def test_unrestated_the_same_counts_read_as_a_nine_hundred_percent_issue():
    """The fault itself, kept in view: without the split, the step is an issue."""
    result = O.issuance({"shares": split_records()})
    assert result["band"] == "severe"
    assert result["largestStep"] == pytest.approx(9.0)


@pytest.mark.parametrize("offset_days", [-2, -1, 0, 1])
def test_the_providers_step_need_not_land_on_the_ex_date(offset_days):
    result = O.issuance(with_split(split_records(offset_days=offset_days)))
    assert result["band"] == "flat"
    assert result["largestStep"] == pytest.approx(0.0, abs=1e-9)


def test_both_units_on_the_step_day_are_each_restated():
    """A date cannot say which unit a count near the split is in; its size can."""
    records = split_records(offset_days=-2, both_units_on_step_day=True)
    result = O.issuance(with_split(records))
    assert result["band"] == "flat"
    assert result["largestStep"] == pytest.approx(0.0, abs=1e-9)


def test_a_consolidation_is_not_a_buyback():
    result = O.issuance(with_split(split_records(ratio=0.1), ratio=0.1))
    assert result["band"] == "flat"
    assert "1-for-10 consolidation" in result["reading"]


def test_real_dilution_survives_the_restatement():
    """Restating the units must not erase an issue that also happened."""
    result = O.issuance(with_split(split_records(annual_growth=0.30)))
    assert result["band"] == "severe"
    assert result["annualised"] == pytest.approx(0.30, abs=0.01)
    assert result["largestStep"] < 0.05


def test_a_series_already_restated_is_left_alone():
    """Multiplying its early counts again would invent the step this removes."""
    already = split_records(offset_days=-5000)
    result = O.issuance(with_split(already))
    assert result["band"] == "flat"
    assert result["splitsRestated"] == []
    assert result["latestCount"] == pytest.approx(24.6e9)


def test_junk_split_records_restate_nothing():
    register = with_split(split_records())
    register["splits"] = [{"date": "nope", "ratio": 10.0}, {"date": "2024-06-10", "ratio": None},
                          {"date": "2024-06-10", "ratio": 1.0}, {"date": "2024-06-10", "ratio": -2},
                          "x"]
    assert O.issuance(register)["splitsRestated"] == []


def test_splits_survive_a_json_round_trip():
    import json

    payload = with_split(split_records(annual_growth=0.08))
    reloaded = json.loads(json.dumps(payload))
    assert O.issuance(reloaded)["annualised"] == pytest.approx(
        O.issuance(payload)["annualised"], abs=1e-12)


def test_shares_outstanding_from_the_history_is_in_todays_shares():
    """The float arithmetic reads the last count; it must be post-split."""
    result = O.read(with_split(split_records()), median_volume=1.0e8)
    assert result["sharesOutstanding"] == pytest.approx(24.6e9)
