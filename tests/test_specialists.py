"""The shortlist the scanner exists to produce, and the base rates beside it.

WHY THESE TESTS EXIST

Three readings — what a company sells, whether it leads or owns its field, and
what its filings say it has done — are each useless alone. The intersection is
the deliverable, and the risk in an intersection is that it LOOKS like three
demanding tests when one of them is not.

Measured on 729 cached Indonesian records: 4.3% lead a field, 3.6% are the only
scanned name in theirs, 10.0% are profitable every year with cash behind it and
growing in the top quartile, and 66.5% are uncovered. That last figure is the
one that has to travel with the list, because two thirds of a small exchange
being uncovered is a fact about the exchange, not a filter.

The three together selected five names, and the top of that list by growth was
KETR.JK — the company the owner described, at 28.6% a year on an 18.5% net
margin, the only listed name carrying its industry label. That is evidence the
screen finds what it was described, and nothing at all about returns.

WHAT THESE TESTS PROTECT

1. ALL THREE CONDITIONS HOLD TOGETHER. Any two without the third selects
   something else entirely.
2. SOLE LISTING COUNTS AS A SPECIALIST. `field.leads` refuses a one-member field
   — being the largest of one is not a position — and that refusal is right,
   but a company with no listed rival is exactly the niche this hunts. KETR
   occupies that state, so a screen that required `leads` would miss it.
3. THE BASE RATES ARE THE SCAN'S OWN, not remembered numbers.
4. GATED NAMES ARE SEPARATED, NEVER DROPPED.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def scan():
    sys.path.insert(0, str(ROOT / "api"))
    spec = importlib.util.spec_from_file_location(
        "scan_market_specialists", ROOT / "scripts" / "scan_market.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verdict(ticker="T.JK", *, peers=1, leads=False, every_year=True, ocf=True,
            growing=True, unattended=True, gates=(), cagr=0.286, available=True,
            industry="Communication Equipment", sole=None, unranked=0):
    # `soleListing` is NOT `peers == 1`. `field.standings` withholds it when
    # another listing carries the same label but returned no usable revenue —
    # that company is still a rival, and a field of one whose other members
    # merely failed to file is a thin measurement rather than a monopoly. The
    # default mirrors the module: alone and nothing unranked.
    if sole is None:
        sole = peers == 1 and not unranked
    return {
        "ticker": ticker, "name": f"PT {ticker}", "score": 55.0, "action": "HOLD",
        "industry": industry, "gates": [{"id": g, "label": g} for g in gates],
        "profile": {"summary": "Sells submarine and terrestrial fibre optic cable."},
        "fieldPosition": {"peers": peers, "leads": leads, "rank": 1,
                          "onlyRanked": peers == 1, "soleListing": sole,
                          "unranked": unranked, "reading": "…"},
        "trackRecord": {"available": available, "everyYearProfitable": every_year,
                        "operatingCashFlowPositive": ocf, "growing": growing,
                        "revenueCagr": cagr, "latestNetMargin": 0.185,
                        "yearsProfitable": 4, "yearsAvailable": 4, "reading": "…"},
        "latestClose": 995.0,
        "neglect": {"attention": {"unattended": unattended, "analysts": 0,
                                  "institutionsHeld": 0.0},
                    "drawdown": -0.33},
    }


def test_the_three_conditions_hold_together(scan):
    assert scan._specialists_summary([verdict()])["selected"] == 1
    # Each one removed in turn removes the name.
    assert scan._specialists_summary([verdict(peers=4, leads=False)])["selected"] == 0
    assert scan._specialists_summary([verdict(growing=False)])["selected"] == 0
    assert scan._specialists_summary([verdict(every_year=False)])["selected"] == 0
    assert scan._specialists_summary([verdict(ocf=False)])["selected"] == 0
    assert scan._specialists_summary([verdict(unattended=False)])["selected"] == 0


def test_the_only_measurable_name_in_its_field_counts_as_a_specialist(scan):
    """KETR's state, and the reason `leads` alone would have missed it.

    `field.standings` refuses to name a leader in a one-member field, correctly.
    But no listed rival is the signature of a niche, not a weaker kind of
    leadership, so this screen takes either.
    """
    sole = scan._specialists_summary([verdict(peers=1, leads=False)])
    assert sole["selected"] == 1
    assert sole["tradeable"][0]["soleListing"] is True
    assert sole["tradeable"][0]["leadsField"] is False

    leader = scan._specialists_summary([verdict(peers=6, leads=True)])
    assert leader["selected"] == 1
    assert leader["tradeable"][0]["soleListing"] is False


def test_a_thin_field_that_names_no_leader_is_not_a_specialist(scan):
    """Two members, no leader named, not the only one either — nothing to claim."""
    assert scan._specialists_summary([verdict(peers=2, leads=False)])["selected"] == 0


def test_an_unread_track_record_is_not_a_pass(scan):
    assert scan._specialists_summary(
        [verdict(available=False, every_year=True)])["selected"] == 0


def test_gated_names_are_separated_rather_than_dropped(scan):
    out = scan._specialists_summary([
        verdict("A.JK"), verdict("B.JK", gates=("illiquid",))])
    assert out["selected"] == 2
    assert [r["ticker"] for r in out["tradeable"]] == ["A.JK"]
    assert [r["ticker"] for r in out["gated"]] == ["B.JK"]


def test_the_list_is_ordered_by_growth(scan):
    out = scan._specialists_summary([
        verdict("SLOW.JK", cagr=0.16), verdict("FAST.JK", cagr=0.40),
        verdict("MID.JK", cagr=0.25)])
    assert [r["ticker"] for r in out["tradeable"]] == ["FAST.JK", "MID.JK", "SLOW.JK"]


def test_the_base_rates_are_this_scans_own(scan):
    rows = [verdict("A.JK"),                       # all three
            verdict("B.JK", growing=False),        # specialist + unattended
            verdict("C.JK", peers=4, leads=False), # compounding + unattended
            verdict("D.JK", unattended=False)]     # specialist + compounding
    base = scan._specialists_summary(rows)["baseRates"]
    assert base["scanned"] == 4
    assert base["specialist"] == pytest.approx(3 / 4)
    assert base["compounding"] == pytest.approx(3 / 4)
    assert base["unattended"] == pytest.approx(3 / 4)


def test_the_note_refuses_the_market_share_reading_and_the_backtest(scan):
    note = scan._specialists_summary([verdict()])["note"]
    assert "is not market share" in note
    assert "cannot be backtested" in note


def test_an_empty_scan_selects_nothing_without_dividing_by_zero(scan):
    out = scan._specialists_summary([])
    assert out["selected"] == 0
    assert out["baseRates"]["scanned"] == 0
    assert out["baseRates"]["specialist"] == 0


def test_an_unmeasured_rival_weakens_the_claim_without_dropping_the_name(scan):
    """KETR's actual state, and the reason the screen and the claim differ.

    Two Indonesian listings share KETR's "Communication Equipment" label and
    returned no usable revenue. Selecting on `soleListing` would have dropped
    the one company this feature was built to find; displaying `onlyRanked` AS
    `soleListing` would have told a reader it has no listed competition. So the
    screen takes the weak flag, the row carries both, and the count of rivals
    nobody could measure travels with it.
    """
    alone = scan._specialists_summary([verdict("K.JK", peers=1)])
    assert alone["selected"] == 1
    assert alone["tradeable"][0]["soleListing"] is True
    assert alone["tradeable"][0]["unrankedRivals"] == 0

    qualified = scan._specialists_summary([verdict("K.JK", peers=1, unranked=2)])
    assert qualified["selected"] == 1            # still found
    assert qualified["tradeable"][0]["soleListing"] is False   # but not claimed
    assert qualified["tradeable"][0]["onlyRanked"] is True
    assert qualified["tradeable"][0]["unrankedRivals"] == 2


def test_the_price_travels_with_the_growth_rate(scan):
    """A growth rate without a price misleads in exactly one direction.

    KETR compounds revenue at 29% a year and trades at 995 against a 52-week
    range of 388 to 1480. A reader shown the first number and not the second
    could reasonably think this screen had found something cheap. It has not
    looked at cheapness at all — that is the screen next door — so the price and
    the distance from its own high are carried as CONTEXT, never as a criterion.
    """
    out = scan._specialists_summary([verdict("K.JK")])
    row = out["tradeable"][0]
    assert row["latestClose"] == 995.0
    assert row["drawdown"] == pytest.approx(-0.33)


def test_the_price_is_context_and_never_a_criterion(scan):
    """Filtering on it would reintroduce the bias these screens exist to escape."""
    near_high = verdict("A.JK")
    near_high["neglect"]["drawdown"] = -0.01
    deep = verdict("B.JK")
    deep["neglect"]["drawdown"] = -0.70
    out = scan._specialists_summary([near_high, deep])
    assert out["selected"] == 2, "neither the fallen nor the risen is filtered out"
