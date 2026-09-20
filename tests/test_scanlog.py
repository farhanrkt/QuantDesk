"""What the scanner said, and what happened next.

WHAT THESE TESTS PROTECT, IN ORDER OF HOW BADLY IT WOULD HURT TO LOSE IT

1. NO RATE UNDER THE FLOOR. This log exists to measure the components a
   backtest cannot reach, and it produces nothing for months. The temptation is
   to read the first ten resolved calls and conclude something; the refusal to
   compute a hit rate under `MIN_CLOSED` is the only thing stopping that.

2. AN OPEN CALL IS NOT A MISS. A call younger than the horizon has not
   happened. Counting it as wrong would make every recent scan look bad and
   every stale one look good.

3. THE OUTCOME IS AN EXCESS. A market that fell 20% makes every buy look wrong
   and says nothing about the ordering.

4. RE-RUNNING A SCAN REPLACES THAT DAY, NEVER DOUBLES IT. One opinion revised
   is not two observations.

5. HOLD IS NOT MEASURED. It is what the scanner says when it has nothing to
   say, so scoring it would measure the market.

The wording is free to change. Those five are not.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from _lib import scanlog as S


def verdict(ticker="A.JK", action="BUY", score=70.0, price=1000.0):
    return {"ticker": ticker, "name": f"PT {ticker}", "action": action,
            "score": score, "conviction": "high", "crossChecked": True,
            "rank": 1, "sector": "Energy", "latestClose": price, "gates": []}


def series(start: dt.date, days: int, drift: float = 0.0, level: float = 1000.0):
    index = pd.bdate_range(start, periods=days)
    values = level * np.exp(np.cumsum(np.full(days, drift)))
    return pd.Series(values, index=index)


# ============================================================================ #
# 4. Re-running replaces, never doubles
# ============================================================================ #
def test_a_second_scan_on_the_same_day_replaces_that_days_rows(tmp_path):
    first = S.record(tmp_path, "ID", [verdict(), verdict("B.JK")],
                     scanned_on="2026-01-05")
    assert first["added"] == 2

    again = S.record(tmp_path, "ID", [verdict(score=55.0)], scanned_on="2026-01-05")
    assert again["total"] == 1, "the day was doubled instead of replaced"

    rows = S.read(tmp_path, "ID")
    assert len(rows) == 1
    assert rows[0]["score"] == 55.0


def test_scans_on_different_days_accumulate(tmp_path):
    S.record(tmp_path, "ID", [verdict()], scanned_on="2026-01-05")
    S.record(tmp_path, "ID", [verdict()], scanned_on="2026-02-05")
    assert len(S.read(tmp_path, "ID")) == 2


def test_a_name_with_no_score_is_not_recorded(tmp_path):
    gated = {**verdict(), "score": None}
    result = S.record(tmp_path, "ID", [gated], scanned_on="2026-01-05")
    assert result["added"] == 0


def test_markets_are_kept_apart(tmp_path):
    S.record(tmp_path, "ID", [verdict()], scanned_on="2026-01-05")
    S.record(tmp_path, "US", [verdict("AAPL")], scanned_on="2026-01-05")
    assert len(S.read(tmp_path, "ID")) == 1
    assert len(S.read(tmp_path, "US")) == 1


def test_a_truncated_final_line_loses_one_row_not_the_history(tmp_path):
    S.record(tmp_path, "ID", [verdict(), verdict("B.JK")], scanned_on="2026-01-05")
    target = S.path_for(tmp_path, "ID")
    target.write_text(target.read_text() + '{"ticker": "C.JK", "sco')
    assert len(S.read(tmp_path, "ID")) == 2


def test_reading_a_market_never_scanned_is_empty_not_an_error(tmp_path):
    assert S.read(tmp_path, "ID") == []


# ============================================================================ #
# 2. An open call is not a miss
# ============================================================================ #
def test_a_call_younger_than_the_horizon_stays_open(tmp_path):
    rows = [{"scannedOn": "2026-01-05", "ticker": "A.JK", "action": "BUY",
             "score": 70.0}]
    prices = {"A.JK": series(dt.date(2026, 1, 5), 20)}
    resolved = S.resolve(rows, prices, horizon=63)
    assert resolved[0]["open"] is True
    assert resolved[0]["excess"] is None


def test_a_call_old_enough_resolves(tmp_path):
    rows = [{"scannedOn": "2026-01-05", "ticker": "A.JK", "action": "BUY",
             "score": 70.0}]
    prices = {"A.JK": series(dt.date(2026, 1, 5), 120, drift=0.001)}
    resolved = S.resolve(rows, prices, horizon=63)
    assert resolved[0]["open"] is False
    assert resolved[0]["excess"] > 0
    assert resolved[0]["days"] == 63


def test_a_symbol_with_no_later_price_says_so(tmp_path):
    rows = [{"scannedOn": "2026-01-05", "ticker": "GONE.JK", "action": "BUY",
             "score": 70.0}]
    resolved = S.resolve(rows, {}, horizon=63)
    assert resolved[0]["open"] is True
    assert "no later price" in resolved[0]["reason"]


# ============================================================================ #
# 3. The outcome is an excess
# ============================================================================ #
def test_a_rising_market_does_not_make_every_call_look_right():
    rows = [{"scannedOn": "2026-01-05", "ticker": "A.JK", "action": "BUY",
             "score": 70.0}]
    prices = {"A.JK": series(dt.date(2026, 1, 5), 120, drift=0.001)}
    benchmark = series(dt.date(2026, 1, 5), 120, drift=0.001)

    without = S.resolve(rows, prices, horizon=63)[0]
    against = S.resolve(rows, prices, benchmark=benchmark, horizon=63)[0]

    assert without["excess"] > 0.05
    assert against["excess"] == pytest.approx(0.0, abs=1e-9), (
        "a name that exactly matched its index has no excess")
    assert against["raw"] > 0.05, "the raw return is still reported"


# ============================================================================ #
# 1. No rate under the floor
# ============================================================================ #
def test_a_handful_of_resolved_calls_refuses_to_quote_a_rate():
    resolved = [{"action": "BUY", "open": False, "excess": 0.1} for _ in range(5)]
    summary = S.summarise(resolved)
    assert summary["available"] is False
    assert summary["closed"] == 5
    assert str(S.MIN_CLOSED) in summary["reading"]
    assert "hitRate" not in summary


def test_enough_resolved_calls_produces_a_rate():
    resolved = ([{"action": "BUY", "open": False, "excess": 0.05} for _ in range(25)]
                + [{"action": "BUY", "open": False, "excess": -0.02} for _ in range(10)]
                + [{"action": "AVOID", "open": False, "excess": -0.04} for _ in range(12)])
    summary = S.summarise(resolved)
    assert summary["available"] is True
    assert summary["buys"]["calls"] == 35
    assert summary["buys"]["hitRate"] == pytest.approx(25 / 35)
    assert summary["sells"]["calls"] == 12
    assert summary["spread"] is not None


def test_the_summary_never_claims_significance():
    resolved = [{"action": "BUY", "open": False, "excess": 0.05} for _ in range(40)]
    summary = S.summarise(resolved)
    assert "No significance is claimed" in summary["reading"]
    assert "pValue" not in summary
    assert "significant" not in summary


# ============================================================================ #
# 5. HOLD is not measured
# ============================================================================ #
def test_hold_is_excluded_from_every_rate():
    resolved = ([{"action": "HOLD", "open": False, "excess": 0.5} for _ in range(100)]
                + [{"action": "BUY", "open": False, "excess": 0.01} for _ in range(31)])
    summary = S.summarise(resolved)
    assert summary["closed"] == 31, "HOLD leaked into the measured set"
    assert "HOLD" not in S.DIRECTIONAL


def test_an_avoid_is_right_when_the_excess_is_negative():
    """The sign that counts as correct depends on which way the call pointed."""
    resolved = ([{"action": "AVOID", "open": False, "excess": -0.05}
                 for _ in range(20)]
                + [{"action": "BUY", "open": False, "excess": 0.05} for _ in range(20)])
    summary = S.summarise(resolved)
    assert summary["sells"]["hitRate"] == 1.0
    assert summary["buys"]["hitRate"] == 1.0


# --------------------------------------------------------------------------- #
# What the screens said on the day they said it
#
# `neglect.py` and the specialist shortlist both publish that they cannot be
# backtested — the filings come back restated, and industry labels and the share
# register arrive as a snapshot with no history — and both name THIS FILE as the
# honest alternative. It was not recording any of it. The claim was made in two
# docstrings and met in neither.
# --------------------------------------------------------------------------- #
def screened(ticker="T.JK", *, neglected=False, leads=False, peers=4, sole=None,
             every_year=True, ocf=True, growing=True, industry="Thermal Coal"):
    # `soleListing` is the STRONG claim — nothing else carries the label — and
    # `field.standings` withholds it when a same-label listing returned no
    # usable revenue. The log records the strong flag, because a record that
    # says "no listed rival" has to have meant it.
    if sole is None:
        sole = peers == 1
    return {
        "ticker": ticker, "name": f"PT {ticker}", "action": "HOLD", "score": 55.0,
        "latestClose": 100.0, "sector": "Energy", "industry": industry,
        "neglect": {"selected": neglected},
        "fieldPosition": {"leads": leads, "peers": peers, "soleListing": sole,
                          "onlyRanked": peers == 1},
        "trackRecord": {"everyYearProfitable": every_year,
                        "operatingCashFlowPositive": ocf, "growing": growing,
                        "revenueCagr": 0.286},
    }


def test_the_screens_are_recorded_not_just_the_score(tmp_path):
    S.record(tmp_path, "ID", [screened("A.JK", neglected=True, leads=True)],
             scanned_on="2026-09-20")
    row = S.read(tmp_path, "ID")[0]
    assert row["industry"] == "Thermal Coal"
    assert row["neglected"] is True
    assert row["leadsField"] is True
    assert row["soleListing"] is False
    assert row["compounding"] is True
    assert row["revenueCagr"] == pytest.approx(0.286)


def test_a_sole_listing_is_recorded_as_its_own_state(tmp_path):
    S.record(tmp_path, "ID", [screened("K.JK", peers=1)], scanned_on="2026-09-20")
    row = S.read(tmp_path, "ID")[0]
    assert row["soleListing"] is True
    assert row["leadsField"] is False


def test_the_log_records_the_strong_claim_not_the_screen(tmp_path):
    """A field of one whose rivals did not file is not recorded as rival-free.

    The shortlist SELECTS on the weaker flag — a specialist whose two tiny peers
    returned nothing is still a specialist — but the prospective record is what
    a later reader judges the screen by, and "no listed rival" has to have meant
    it on the day it was written.
    """
    S.record(tmp_path, "ID", [screened("K.JK", peers=1, sole=False)],
             scanned_on="2026-09-20")
    assert S.read(tmp_path, "ID")[0]["soleListing"] is False


def test_compounding_needs_all_three_conditions(tmp_path):
    S.record(tmp_path, "ID", [
        screened("A.JK"), screened("B.JK", growing=False),
        screened("C.JK", ocf=False), screened("D.JK", every_year=False),
    ], scanned_on="2026-09-20")
    by_ticker = {row["ticker"]: row for row in S.read(tmp_path, "ID")}
    assert by_ticker["A.JK"]["compounding"] is True
    assert by_ticker["B.JK"]["compounding"] is False
    assert by_ticker["C.JK"]["compounding"] is False
    assert by_ticker["D.JK"]["compounding"] is False


def test_an_unrecorded_day_is_not_an_empty_one(tmp_path):
    """The distinction that makes a prospective log worth keeping.

    Rows written before the screens were recorded carry none of these keys.
    Reading a missing key as False would report that the screen selected nothing
    in August — a finding about the screen rather than about the log, and one
    that would fill the record's early history with fabricated zeroes.
    """
    old = {"scannedOn": "2026-08-01", "ticker": "OLD.JK", "action": "HOLD",
           "score": 50.0, "price": 100.0}
    S.record(tmp_path, "ID", [screened("NEW.JK", neglected=True)],
             scanned_on="2026-09-20")
    rows = [old, *S.read(tmp_path, "ID")]

    days = S.selected_on(rows, "neglected")
    assert days["2026-08-01"]["recorded"] is False
    assert days["2026-08-01"]["tickers"] == []
    assert days["2026-09-20"]["recorded"] is True
    assert days["2026-09-20"]["tickers"] == ["NEW.JK"]


def test_an_unknown_screen_is_refused_rather_than_answered_empty(tmp_path):
    with pytest.raises(ValueError, match="not a recorded screen"):
        S.selected_on([], "profitable")


# --------------------------------------------------------------------------- #
# Reading the screens back, which is the other half of recording them
# --------------------------------------------------------------------------- #
def resolved_row(ticker="T.JK", *, flag="neglected", picked=True, excess=0.05,
                 open_call=False, carries=True):
    row = {"ticker": ticker, "action": "HOLD", "score": 55.0,
           "open": open_call, "excess": None if open_call else excess}
    if carries:
        row[flag] = picked
    return row


def test_a_screen_under_the_threshold_refuses_and_names_its_own_count():
    rows = [resolved_row(f"T{i}.JK") for i in range(5)]
    block = S.summarise_screens(rows)["neglected"]
    assert block["available"] is False
    assert block["closed"] == 5 and block["needed"] == S.MIN_CLOSED
    assert "not ready" in block["reading"]


def test_each_screen_is_measured_on_its_own_selections_not_pooled():
    """A screen picking a handful a sweep reaches the threshold much later."""
    rows = ([resolved_row(f"N{i}.JK", flag="neglected")
             for i in range(S.MIN_CLOSED)]
            + [resolved_row(f"S{i}.JK", flag="soleListing") for i in range(3)])
    # The soleListing rows do not carry `neglected`, and vice versa.
    for row in rows[S.MIN_CLOSED:]:
        row.pop("neglected", None)
    out = S.summarise_screens(rows)
    assert out["neglected"]["available"] is True
    assert out["soleListing"]["available"] is False
    assert out["soleListing"]["closed"] == 3


def test_a_screen_no_scan_recorded_is_not_a_screen_that_picked_nobody():
    rows = [resolved_row(f"T{i}.JK", flag="neglected") for i in range(40)]
    out = S.summarise_screens(rows)
    assert out["compounding"]["available"] is False
    assert out["compounding"]["selected"] == 0
    assert "predate it" in out["compounding"]["reading"]
    assert "selected nobody" in out["compounding"]["reading"]


def test_a_resolved_screen_reports_what_happened_and_claims_nothing():
    rows = [resolved_row(f"T{i}.JK", excess=0.04) for i in range(S.MIN_CLOSED)]
    block = S.summarise_screens(rows)["neglected"]
    assert block["available"] is True
    assert block["meanExcess"] == pytest.approx(0.04)
    assert block["positive"] == S.MIN_CLOSED
    assert "rather than evidence it will happen again" in block["reading"]


def test_open_calls_are_not_counted_as_resolved():
    rows = ([resolved_row(f"C{i}.JK") for i in range(4)]
            + [resolved_row(f"O{i}.JK", open_call=True) for i in range(9)])
    block = S.summarise_screens(rows)["neglected"]
    assert block["closed"] == 4 and block["open"] == 9
