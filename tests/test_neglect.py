"""The screen for what the blended score is structurally unable to recommend.

WHY THIS EXISTS, MEASURED BEFORE IT WAS BUILT

`verdict.score` shrinks toward 50 when its families disagree, which is right in
general and wrong for one specific case. Five of the seven price signals reward
a stock for having already risen, so a solid business that has FALLEN scores
badly on the price family by construction — and falling is what makes it cheap.
On a 775-name Indonesian sweep, 82 names had strong filings and a weak price
family and not one was a buy: 29 HOLD, 53 gated, mean score 51.2.

WHAT THESE TESTS PROTECT

1. ALL THREE CONDITIONS HOLD TOGETHER. Cheap without solid is a value trap;
   solid without unattended is already priced. Any one alone is a known way to
   lose money.
2. NO MOMENTUM FILTER. Adding "and it has stopped falling" would reintroduce
   exactly the bias the screen exists to escape. The drawdown is context.
3. A GAP IS A REFUSAL, NOT A PASS. A name whose value or quality did not read is
   declined, never selected on whichever components happened to arrive.
4. BOTH REGISTER SHAPES ARE READ. The raw Yahoo payload is flat; the scanner
   stores `ownership.read`'s nested one. Reading only the first selected ZERO
   names out of 775 and said nothing about it.
"""

from __future__ import annotations

import pytest

from _lib import neglect as N


def verdict_row(value=80.0, quality=80.0, **extra):
    components = [
        {"key": "value", "available": value is not None, "score": value,
         "refused": False},
        {"key": "quality", "available": quality is not None, "score": quality,
         "refused": False},
    ]
    return {"ticker": "T.JK", "components": components, **extra}


def flat_register(held=0.0, count=0, insiders=0.4, analysts=None):
    """The shape `market_data.share_register` returns."""
    out = {"ok": True, "institutionsPercentHeld": held, "institutionsCount": count,
           "insidersPercentHeld": insiders}
    if analysts is not None:
        out["recommendations"] = {"numberOfAnalystOpinions": analysts}
    return out


def nested_register(held=0.0, count=0, free=0.6):
    """The shape `ownership.read` returns, which is what the scanner stores."""
    return {"available": True,
            "float": {"available": True, "freeFloat": free},
            "institutions": {"percentHeld": held, "count": count, "note": "context"}}


# ============================================================================ #
# 1. All three conditions, together
# ============================================================================ #
def test_cheap_and_solid_and_unattended_is_selected():
    out = N.screen(verdict_row(), flat_register())
    assert out["available"] and out["selected"]
    assert out["cheap"] and out["solid"] and out["attention"]["unattended"]


def test_cheap_but_not_solid_is_a_value_trap_and_is_refused():
    out = N.screen(verdict_row(value=95.0, quality=30.0), flat_register())
    assert out["selected"] is False
    assert "not solid" in out["reading"]


def test_solid_but_not_cheap_is_already_priced():
    out = N.screen(verdict_row(value=20.0, quality=95.0), flat_register())
    assert out["selected"] is False
    assert "not cheap" in out["reading"]


def test_cheap_and_solid_but_widely_held_is_not_underrated():
    """A company fifty analysts cover and everyone hates is priced. The screen
    is about names that may not have been READ, not names that are disliked."""
    out = N.screen(verdict_row(), flat_register(held=0.42, count=180))
    assert out["selected"] is False
    assert "already covered" in out["reading"]


def test_analyst_coverage_alone_disqualifies_it():
    out = N.screen(verdict_row(), flat_register(held=0.0, analysts=14))
    assert out["attention"]["unattended"] is False
    assert out["selected"] is False


@pytest.mark.parametrize("value,quality,expected", [
    (N.CHEAP_AT, N.SOLID_AT, True),
    (N.CHEAP_AT - 0.1, N.SOLID_AT, False),
    (N.CHEAP_AT, N.SOLID_AT - 0.1, False),
])
def test_the_thresholds_are_thresholds(value, quality, expected):
    out = N.screen(verdict_row(value=value, quality=quality), flat_register())
    assert out["selected"] is expected


# ============================================================================ #
# 2. No momentum filter
# ============================================================================ #
def test_a_name_deep_in_drawdown_is_still_selected():
    """Filtering on the fall would reintroduce the bias the screen escapes.
    The drawdown is reported so a reader can judge; it is not a criterion.

    THIS TEST USED TO PLANT `current` AND PASS, while the app read `current` too
    and `longterm.py` had always written `currentDrawdown`. Both sides agreed
    with each other and neither agreed with the data, so the drawdown was always
    None in production and the sentence below never rendered once. A fixture
    that encodes the same assumption as the code under test measures the
    assumption, not the behaviour — which is why this repo's standard is to
    plant ground truth from the producing module's own field names.
    """
    technical = {"longTerm": {"drawdown": {"currentDrawdown": -0.55}}}
    out = N.screen(verdict_row(), flat_register(), technical=technical)
    assert out["selected"] is True
    assert out["drawdown"] == pytest.approx(-0.55)
    assert "below its own high" in out["reading"]
    assert "not evidence the fall is over" in out["reading"]


def test_an_unavailable_drawdown_does_not_block_selection():
    out = N.screen(verdict_row(), flat_register(), technical=None)
    assert out["selected"] is True
    assert out["drawdown"] is None


# ============================================================================ #
# 3. A gap is a refusal
# ============================================================================ #
@pytest.mark.parametrize("value,quality", [(None, 80.0), (80.0, None), (None, None)])
def test_a_missing_component_declines_rather_than_selecting(value, quality):
    out = N.screen(verdict_row(value=value, quality=quality), flat_register())
    assert out["available"] is False
    assert out["selected"] is False
    assert "did not read" in out["reason"]


def test_an_unreadable_register_is_not_treated_as_unattended():
    """Silence about who holds a stock is not evidence that nobody does."""
    out = N.screen(verdict_row(), {})
    assert out["attention"]["known"] is False
    assert out["attention"]["unattended"] is False
    assert out["selected"] is False
    assert "unmeasured rather than low" in out["attention"]["reading"]


def test_a_stock_nobody_can_buy_is_not_underrated():
    out = N.screen(verdict_row(), flat_register(insiders=0.96))
    assert out["tradeableFloat"] is False
    assert out["selected"] is False


# ============================================================================ #
# 4. Both register shapes
# ============================================================================ #
def test_the_nested_scanner_shape_is_read():
    """Reading only the flat shape found no institutional holding on ANY name in
    a 775-name sweep, so every name looked unattended, and the screen selected
    zero. A silent nothing, from a key that was somewhere else."""
    out = N.screen(verdict_row(), nested_register(held=0.0, count=0))
    assert out["selected"] is True
    assert out["attention"]["known"] is True


def test_the_nested_shape_also_disqualifies_a_held_name():
    out = N.screen(verdict_row(), nested_register(held=0.55, count=200))
    assert out["attention"]["institutionsHeld"] == pytest.approx(0.55)
    assert out["selected"] is False


def test_free_float_is_read_from_either_shape():
    assert N.screen(verdict_row(), nested_register(free=0.04))["tradeableFloat"] is False
    assert N.screen(verdict_row(), flat_register(insiders=0.30))["tradeableFloat"] is True


# ============================================================================ #
# It never touches the score
# ============================================================================ #
def test_the_screen_returns_a_reading_and_changes_nothing():
    row = verdict_row()
    before = dict(row)
    N.screen(row, flat_register())
    assert row == before, "the screen mutated the verdict it was reading"


# --------------------------------------------------------------------------- #
# The drawdown context, which was silently absent from the day this was written
#
# This module deliberately has NO momentum filter — adding "and it has stopped
# falling" would reintroduce the exact bias it exists to escape — and its
# docstring says the drawdown is reported as CONTEXT instead, so a reader can
# apply their own judgement. It read `drawdown.current`; `longterm.py` has
# always called the field `currentDrawdown`. The value was therefore always
# None, the sentence quoting it never rendered, and the compensation the design
# promised for not filtering was never actually delivered.
# --------------------------------------------------------------------------- #
def technical_with_drawdown(current):
    return {"longTerm": {"drawdown": {"usable": True, "currentDrawdown": current,
                                      "maxDrawdown": -0.74}}}


def test_the_drawdown_is_read_from_the_key_that_exists():
    out = N.screen(verdict_row(), register_result=None,
                   technical=technical_with_drawdown(-0.3277))
    assert out["drawdown"] == pytest.approx(-0.3277)


def test_a_selected_name_well_below_its_high_says_so():
    """The sentence that had never rendered."""
    register = {"institutions": {"percentHeld": 0.0},
                "float": {"freeFloat": 0.8}}
    out = N.screen(verdict_row(value=80.0, quality=80.0), register,
                   technical=technical_with_drawdown(-0.33))
    assert out["selected"] is True
    assert "33% below its own high" in out["reading"]
    assert "not evidence the fall is over" in out["reading"]


def test_it_stays_context_and_never_becomes_a_criterion():
    """Two names identical but for the drawdown must both select."""
    register = {"institutions": {"percentHeld": 0.0},
                "float": {"freeFloat": 0.8}}
    fallen = N.screen(verdict_row(), register,
                      technical=technical_with_drawdown(-0.70))
    risen = N.screen(verdict_row(), register,
                     technical=technical_with_drawdown(0.0))
    assert fallen["selected"] is True and risen["selected"] is True


def test_an_absent_drawdown_is_none_rather_than_zero():
    out = N.screen(verdict_row(), register_result=None, technical={})
    assert out["drawdown"] is None
