"""Where the price sits, and what buying it HERE risks.

WHAT THESE TESTS PROTECT, IN ORDER OF HOW BADLY IT WOULD HURT TO LOSE IT

1. IT IS NOT A SCORING COMPONENT. The score answers "is this worth owning";
   this answers "is now a sensible moment". Blending them would let a tidy
   entry make a poor company look better, which is the confusion a composite is
   most prone to. It feeds a gate and the prose, and nothing else.

2. NO CEILING IS NOT A BAD ENTRY. A name at a 52-week high has nothing
   overhead, which is the ABSENCE of the measurement rather than a failure of
   it. It reads unbounded and the gate stays silent.

3. NO FLOOR IS NOT A CLEAN ENTRY EITHER. Without a support there is no level
   whose failure says the trade was wrong, so there is nothing to measure risk
   against — and that is a gap, treated as unmeasured rather than as fine.

4. THE LEVELS ARE READ, NOT RECOMPUTED. `swing.support_resistance` already ran
   inside the trend lens. A second implementation would eventually disagree
   with the levels the chart draws.

5. THE REGIME SCORES NOTHING. Whether the index is above its own average is
   context. Turning it into points would be a market-timing claim nobody here
   has measured.

The wording is free to change. Those five are not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import structure as S


def levels(price=1000.0, supports=(960.0, 900.0), resistances=(1100.0, 1200.0),
           atr=25.0, usable=True):
    return {
        "usable": usable, "price": price, "atr": atr,
        "supports": [{"price": p, "touches": 3} for p in supports],
        "resistances": [{"price": p, "touches": 3} for p in resistances],
        "confirmationLag": 3,
    }


def technical(short=None, mid=None):
    payload = {}
    if short is not None:
        payload["shortTerm"] = {"levels": short}
    if mid is not None:
        payload["midTerm"] = {"levels": mid}
    return payload


# ============================================================================ #
# 1. Reward to risk, measured to structure
# ============================================================================ #
def test_the_ratio_is_the_two_nearest_levels_either_side():
    result = S.read(levels=levels(price=1000.0, supports=(960.0, 900.0),
                                  resistances=(1100.0, 1200.0)))
    assert result["available"] is True
    assert result["support"] == 960.0, "the NEAREST support below, not the deepest"
    assert result["resistance"] == 1100.0, "the NEAREST resistance above"
    assert result["riskToSupport"] == pytest.approx(0.04)
    assert result["rewardToResistance"] == pytest.approx(0.10)
    assert result["rewardRisk"] == pytest.approx(2.5)
    assert result["band"] == "fine"


def test_levels_on_the_wrong_side_of_the_price_are_ignored():
    """A 'support' above the price is a resistance that has not been relabelled,
    and using it would invert the whole reading."""
    result = S.read(levels=levels(price=1000.0, supports=(960.0, 1050.0),
                                  resistances=(1100.0, 980.0)))
    assert result["support"] == 960.0
    assert result["resistance"] == 1100.0


@pytest.mark.parametrize("resistance,band", [
    (1100.0, "fine"),     # 2.5 : 1
    (1030.0, "poor"),     # 0.75 : 1
    (1010.0, "bad"),      # 0.25 : 1
])
def test_the_bands_run_in_the_stated_order(resistance, band):
    result = S.read(levels=levels(price=1000.0, supports=(960.0,),
                                  resistances=(resistance,)))
    assert result["band"] == band


def test_a_stop_further_than_a_third_away_is_not_a_stop():
    """Past that distance the 'risk' being measured is the whole thesis rather
    than a level, and the ratio stops describing anything a position could be
    sized on."""
    result = S.read(levels=levels(price=1000.0, supports=(600.0,),
                                  resistances=(1400.0,)))
    assert result["band"] == "riskTooWide"
    assert "different investment" in result["reading"]


def test_a_stop_inside_the_daily_noise_withholds_the_ratio():
    """A reward-to-risk figure is only as real as its denominator.

    Found on a full IDX sweep: the two best-looking ratios in the whole buy list
    were 15:1 and 11:1, and both were built on stops 0.18 and 0.27 of an average
    daily range below the price. The arithmetic is correct and the number is
    meaningless — it grows as the stop becomes MORE fragile, which is exactly
    backwards from what a reader takes it to mean.
    """
    result = S.read(levels=levels(price=1000.0, supports=(995.0,),
                                  resistances=(1100.0,), atr=25.0))
    assert result["band"] == "riskInsideNoise"
    assert result["rewardRisk"] is None, "the ratio was quoted anyway"
    assert result["atSupport"] is True


def test_the_withheld_arithmetic_still_travels_under_a_name_nobody_renders():
    result = S.read(levels=levels(price=1000.0, supports=(995.0,),
                                  resistances=(1100.0,), atr=25.0))
    assert result["ratioWithheld"] is True
    assert result["rewardRiskRaw"] == pytest.approx(20.0)


def test_the_prose_does_not_quote_the_number_the_payload_withheld():
    """Suppressing the field and printing it in the sentence would be theatre —
    and prose is the half of the payload people actually read."""
    result = S.read(levels=levels(price=1000.0, supports=(995.0,),
                                  resistances=(1100.0,), atr=25.0))
    assert "to 1" not in result["reading"]
    assert "20.0" not in result["reading"]
    assert "dividing by" in result["reading"]


def test_a_floor_just_outside_the_noise_still_gets_its_ratio():
    """The threshold has to be a threshold, not a mood."""
    inside = S.read(levels=levels(price=1000.0, supports=(988.0,),
                                  resistances=(1100.0,), atr=25.0))
    outside = S.read(levels=levels(price=1000.0, supports=(987.0,),
                                   resistances=(1100.0,), atr=25.0))
    assert inside["band"] == "riskInsideNoise" and inside["rewardRisk"] is None
    assert outside["band"] == "fine" and outside["rewardRisk"] is not None


def test_both_levels_inside_the_noise_is_unmeasurable_rather_than_bad():
    """A price pinned between two levels a single session reaches is not a poor
    trade with a small ratio — it is a ratio of two noise-sized numbers, and
    calling it `bad` would be a judgement the data cannot support."""
    result = S.read(levels=levels(price=1000.0, supports=(995.0,),
                                  resistances=(1002.0,), atr=25.0))
    assert result["band"] == "riskInsideNoise"
    assert result["rewardRisk"] is None


def test_the_real_case_that_prompted_this():
    """GGRM on 11 September 2026, at the numbers the scan actually produced."""
    result = S.read(levels=levels(price=19375.0, supports=(19275.0,),
                                  resistances=(20875.0,), atr=542.0))
    assert result["band"] == "riskInsideNoise"
    assert result["rewardRiskRaw"] == pytest.approx(15.0, abs=0.1)
    assert result["rewardRisk"] is None


def test_a_wide_stop_still_outranks_a_noisy_one_in_the_band_order():
    """`riskTooWide` is checked first because it is the state that gates, and
    the two cannot co-occur outside a listing that moves 70% in a session."""
    assert S._band(ratio=0.7, risk=0.40, unbounded=False, has_support=True,
                   at_support=True) == "riskTooWide"


# ============================================================================ #
# 2. No ceiling is not a bad entry
# ============================================================================ #
def test_nothing_overhead_reads_unbounded_and_does_not_condemn_the_entry():
    result = S.read(levels=levels(price=1000.0, supports=(960.0,), resistances=()))
    assert result["unboundedUpside"] is True
    assert result["band"] == "unbounded"
    assert result["rewardRisk"] is None
    assert "Unbounded is not the same as large" in result["reading"]


# ============================================================================ #
# 3. No floor is not a clean entry either
# ============================================================================ #
def test_nothing_below_is_a_gap_not_a_pass():
    result = S.read(levels=levels(price=1000.0, supports=(), resistances=(1100.0,)))
    assert result["noSupport"] is True
    assert result["band"] == "noSupport"
    assert "gap, not a clean entry" in result["reading"]


def test_unusable_levels_decline_rather_than_defaulting_to_fine():
    assert S.read(levels=levels(usable=False))["available"] is False
    assert S.read(levels=None, technical=None)["available"] is False
    assert S.read(technical={"shortTerm": {}})["available"] is False


# ============================================================================ #
# 4. The levels are read, not recomputed
# ============================================================================ #
def test_the_short_horizon_is_preferred_and_the_mid_stands_in():
    both = S.read(technical=technical(short=levels(price=1000.0),
                                      mid=levels(price=2000.0)))
    assert both["horizon"] == "shortTerm"
    assert both["price"] == 1000.0

    only_mid = S.read(technical=technical(short=levels(usable=False),
                                          mid=levels(price=2000.0)))
    assert only_mid["horizon"] == "midTerm"
    assert only_mid["price"] == 2000.0


def test_at_a_level_is_measured_in_the_names_own_daily_range():
    """A fixed percentage would call a placid utility and a small-cap 'at' a
    level at completely different real distances."""
    at_it = S.read(levels=levels(price=1000.0, supports=(990.0,),
                                 resistances=(1200.0,), atr=25.0))
    away = S.read(levels=levels(price=1000.0, supports=(990.0,),
                                resistances=(1200.0,), atr=2.0))
    assert at_it["atSupport"] is True
    assert away["atSupport"] is False


# ============================================================================ #
# 5. The regime scores nothing
# ============================================================================ #
def index_frame(n=400, drift=0.0005, seed=5):
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(drift, 0.008, n)))
    return pd.DataFrame(
        {"Open": close, "High": close * 1.005, "Low": close * 0.995,
         "Close": close, "Volume": np.full(n, 1e6)},
        index=pd.bdate_range("2024-01-01", periods=n))


def test_the_regime_reports_a_state_and_never_a_score():
    result = S.regime(index_frame(drift=0.0012), symbol="^TEST")
    assert result["available"] is True
    assert result["scores"] is False
    assert "score" not in result
    assert result["state"] in {"advancing", "recovering", "pulling back", "declining"}


def test_a_rising_index_and_a_falling_one_read_differently():
    up = S.regime(index_frame(drift=0.0015, seed=11))
    down = S.regime(index_frame(drift=-0.0015, seed=11))
    assert up["aboveSlow"] is True
    assert down["aboveSlow"] is False
    assert up["state"] != down["state"]


def test_the_regime_says_out_loud_that_it_decides_nothing():
    result = S.regime(index_frame())
    assert "scores nothing" in result["reading"]
    assert "cross-sectional" in result["reading"]


def test_too_little_index_history_declines():
    result = S.regime(index_frame(n=100))
    assert result["available"] is False
    assert str(S.REGIME_SLOW + 21) in result["reason"]


# ============================================================================ #
# The boundary that must not move
# ============================================================================ #
def test_nothing_here_emits_a_score():
    """It is a gate and a sentence. A `score` key would be the first step to it
    becoming a component, which is the thing the module docstring refuses."""
    payloads = [
        S.read(levels=levels()),
        S.read(levels=levels(resistances=())),
        S.read(levels=levels(supports=())),
        S.regime(index_frame()),
    ]
    for payload in payloads:
        assert "score" not in payload
        assert "weight" not in payload
