"""What a round trip costs, and the refusal that keeps it honest.

WHAT THESE TESTS PROTECT

1. AN UNRESOLVED SPREAD IS UNMEASURED, NOT CHEAP. `microstructure` knows when
   its own estimate sits at the estimator's noise floor. Reporting that as a
   small cost would be the most flattering possible error, on the number that
   decides whether any measured effect is actionable.

2. A ROUND TRIP CROSSES THE SPREAD TWICE. Once buying, once selling. Quoting
   the one-way spread as the cost of a trade halves it.

3. IT NEVER SCORES. The cost is a fact about the order book. Docking a company
   for its own bid-ask would put a market-microstructure quantity into a
   judgement about a business.
"""

from __future__ import annotations

import pytest

from _lib import structure as S


def test_a_resolved_spread_is_crossed_twice():
    result = S.round_trip_cost({"spread": 0.011, "spreadResolved": True})
    assert result["available"] is True
    assert result["roundTrip"] == pytest.approx(0.022)
    assert "twice" in result["reading"]


def test_an_unresolved_spread_is_unmeasured_rather_than_small():
    result = S.round_trip_cost({"spread": 0.0008, "spreadResolved": False})
    assert result["available"] is False
    assert result["resolved"] is False
    assert "not\nthe same as it being small" in result["reason"].replace(" ", " ") \
        or "not the same as it being small" in " ".join(result["reason"].split())
    # The raw estimate is still carried so a reader can see what was rejected.
    assert result["spread"] == pytest.approx(0.0008)


@pytest.mark.parametrize("profile", [
    None, {}, {"spread": None}, {"spread": 0.0, "spreadResolved": True},
    {"spread": -0.01, "spreadResolved": True}, {"spread": "wide"},
])
def test_a_missing_or_nonsense_spread_declines(profile):
    assert S.round_trip_cost(profile)["available"] is False


def test_the_cost_never_carries_a_score():
    for profile in ({"spread": 0.01, "spreadResolved": True},
                    {"spread": 0.01, "spreadResolved": False}, None):
        payload = S.round_trip_cost(profile)
        assert "score" not in payload
        assert "action" not in payload


def test_a_wider_spread_costs_more():
    tight = S.round_trip_cost({"spread": 0.002, "spreadResolved": True})
    wide = S.round_trip_cost({"spread": 0.02, "spreadResolved": True})
    assert wide["roundTrip"] > tight["roundTrip"]
