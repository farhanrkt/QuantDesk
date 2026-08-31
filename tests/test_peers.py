"""Peer comparison: where one ticker sits among its own index.

The feature exists to fix CALIBRATION — a reader with no priors cannot tell an
ordinary 33% drawdown from an alarming one, and every figure in the single-ticker
view is absolute. These tests pin the three things that make the restatement
trustworthy: the percentile is direction-adjusted so a high number always means
the favourable end, a weak-evidence signal never earns a strong colour however
well it places, and the peer group is named in every sentence so the denominator
cannot go unnoticed.
"""

from __future__ import annotations

import pytest

from _lib import explain as E
from _lib import ranking, universes


# --------------------------------------------------------------------------- #
# Membership lookup
# --------------------------------------------------------------------------- #
def test_membership_is_ordered_largest_first():
    """A percentile against 29 peers places a stock in thirds. Prefer the bigger
    group, because it is the better-resolved comparison."""
    found = universes.containing("AAPL")
    assert [e["id"] for e in found] == ["nasdaq100", "dow30"]
    assert found[0]["count"] > found[1]["count"]


def test_membership_matches_resolved_idx_symbols():
    """The lists store bare codes; the app works in resolved symbols. Matching
    raw strings would find nothing for every Indonesian ticker."""
    assert [e["id"] for e in universes.containing("BBCA.JK")] == ["lq45", "idx30"]
    assert universes.containing("BBCA") == [], "an unsuffixed code is a US symbol"


@pytest.mark.parametrize("symbol", ["", "   ", "NONSUCH", None])
def test_membership_of_an_unknown_symbol_is_empty(symbol):
    assert universes.containing(symbol) == []


# --------------------------------------------------------------------------- #
# The one curated list, and the three things that make it safe
# --------------------------------------------------------------------------- #
def test_curated_list_did_not_leak_into_the_index_lists():
    """The point of a separate list is that the index lists stay TRUE.

    AALI is not in the LQ45 and writing it there to make it reachable would make
    that list assert something false, undetectably from the output. This is the
    same failure `universes.py` refuses an S&P 500 list to avoid.
    """
    for absent in ("AALI", "LSIP", "DSNG", "TAPG", "BUMI", "NCKL"):
        assert absent not in universes.UNIVERSES["idx30"]["tickers"]
        assert absent not in universes.UNIVERSES["lq45"]["tickers"]
    assert universes.get("idx30")["count"] == 30
    assert universes.get("lq45")["count"] == 45


def test_curated_list_carries_its_own_as_of():
    """`AS_OF` means "when the index was transcribed". A curated list's date means
    "when somebody last judged the composition". One field cannot carry both, so an
    entry may override, and the four index lists must keep the global date."""
    assert universes.get("idxresources")["asOf"] != universes.AS_OF
    for index_list in ("dow30", "nasdaq100", "idx30", "lq45"):
        assert universes.get(index_list)["asOf"] == universes.AS_OF
    catalogue = {c["id"]: c["asOf"] for c in universes.catalogue()}
    assert catalogue["idxresources"] != catalogue["idx30"], "the picker must show both dates"


def test_untr_is_not_in_the_resources_list():
    """THE ONE MEMBERSHIP THAT IS LOAD-BEARING, and it is an absence.

    United Tractors reads a higher R-squared against the coal names than one of
    the coal miners reads against its own peers, which is the strongest evidence
    that measuring exposure beats assuming it. That result only means anything
    while UNTR is OUTSIDE the basket: a factor built from UNTR and then used to
    report UNTR as coal-exposed has discovered nothing. Adding it here would
    silently convert the finding into a tautology, so the absence is pinned.
    """
    assert "UNTR" not in universes.UNIVERSES["idxresources"]["tickers"]
    assert "UNTR.JK" not in universes.get("idxresources")["tickers"]


def test_curated_list_does_not_displace_an_index_peer_group():
    """`containing` is ordered largest-first and the peers route takes the first
    entry, so a new list could quietly change every default peer group. It is
    smaller than both Indonesian indices, so it must sort last for a name in them.
    """
    assert [e["id"] for e in universes.containing("ADRO.JK")] == [
        "lq45", "idx30", "idxresources"]
    # A name in no index gets a peer group where it previously had none.
    assert [e["id"] for e in universes.containing("AALI.JK")] == ["idxresources"]


# --------------------------------------------------------------------------- #
# The restatement
# --------------------------------------------------------------------------- #
UNIVERSE = {"id": "nasdaq100", "name": "Nasdaq-100", "market": "US",
            "asOf": "2026-08-22", "count": 99, "scanned": 97}


def row(**percentiles) -> dict:
    signals = {}
    for signal in ranking.SIGNALS:
        key = signal["key"]
        signals[key] = {"raw": 0.1, "percentile": percentiles.get(key), "weight": 1.0}
    return {"ticker": "AAPL", "rank": 7, "composite": 74.9, "signals": signals}


def peers(**percentiles) -> dict:
    return E.for_peers(row(**percentiles), UNIVERSE, ranking.SIGNALS,
                       {"effectiveSignals": 3.2})


def sentence_for(result: dict, key: str) -> str:
    return next(r["sentence"] for r in result["readings"] if r["key"] == key)


def test_a_high_percentile_reads_as_favourable_for_low_is_good_signals():
    """`lowVolatility` and `shallowDrawdown` rank so that a LOW raw value scores
    well, and the percentile already carries that. The sentence must not
    re-invert it — saying a calm stock 'swings more than 90%' is the exact bug
    the direction discipline exists to prevent."""
    result = peers(lowVolatility=90.0, shallowDrawdown=95.0)
    assert "Calmer day to day than 90% of the Nasdaq-100." == sentence_for(result, "lowVolatility")
    assert "milder than 95%" in sentence_for(result, "shallowDrawdown")


def test_the_peer_group_is_named_in_every_sentence():
    """Change the group and the same company moves. A percentile whose
    denominator is off-screen is a score pretending not to be one."""
    result = peers(**{s["key"]: 60.0 for s in ranking.SIGNALS})
    for reading in result["readings"]:
        assert "Nasdaq-100" in reading["sentence"], reading["key"]
    assert "Nasdaq-100" in result["headline"]
    assert "Nasdaq-100" in result["caveat"]


def test_a_weak_evidence_signal_never_earns_a_strong_colour():
    """Top decile on a measure that does not predict anything is not good news.

    `flow` and `shallowDrawdown` are graded weak in ranking.SIGNALS; however well
    a name places on them the tone stays neutral, while a moderate-evidence
    signal at the same percentile goes green.
    """
    result = peers(flow=99.0, shallowDrawdown=99.0, lowVolatility=99.0)
    tones = {r["key"]: r["tone"] for r in result["readings"]}
    assert tones["flow"] == "neutral"
    assert tones["shallowDrawdown"] == "neutral"
    assert tones["lowVolatility"] == "good", "moderate evidence should still colour"


def test_a_bottom_percentile_on_a_supported_signal_reads_poor():
    result = peers(momentum=5.0)
    reading = next(r for r in result["readings"] if r["key"] == "momentum")
    assert reading["band"] == "poor"
    assert reading["tone"] == "warn"


def test_a_missing_percentile_says_so_rather_than_scoring_zero():
    result = peers(momentum=None)
    reading = next(r for r in result["readings"] if r["key"] == "momentum")
    assert reading["percentile"] is None
    assert reading["tone"] == "none"
    assert "Not enough history" in reading["sentence"]


def test_the_signal_overlap_is_carried_through():
    """The composite places the name 7th; the reader is told those seven columns
    are really about three signals before they weight that placing."""
    result = peers(momentum=80.0)
    assert "3.2 signals' worth" in result["overlap"]


def test_the_caveat_states_what_has_no_peer_comparison():
    """Only the price family is compared. Saying so stops a reader assuming the
    valuation and the accounts were ranked too."""
    caveat = peers(momentum=50.0)["caveat"]
    assert "price and volume alone" in caveat
    assert "Value and Quality" in caveat


FORBIDDEN = ["you should buy", "buy signal", "strong buy", "we recommend",
             "will rise", "will outperform", "price target"]


@pytest.mark.parametrize("percentile", [1.0, 25.0, 50.0, 75.0, 99.0])
def test_no_placing_is_ever_phrased_as_an_instruction(percentile):
    """A high placing is a description of where a name sits in a named group on a
    named date. It is not a reason to do anything, at any percentile."""
    result = peers(**{s["key"]: percentile for s in ranking.SIGNALS})
    blob = " ".join([result["headline"], result["caveat"], result["overlap"] or ""]
                    + [r["sentence"] for r in result["readings"]]).lower()
    for phrase in FORBIDDEN:
        assert phrase not in blob, phrase
