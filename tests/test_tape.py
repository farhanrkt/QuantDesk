"""The heavy-session reading — the OHLCV shadow of bandarmology.

WHAT THESE TESTS PROTECT, IN ORDER OF HOW BADLY IT WOULD HURT TO LOSE IT

1. THE NULL IS THE MARKET'S OWN MEDIAN, NOT ZERO. Heavy sessions close higher
   in their range than ordinary ones almost everywhere — the median Indonesian
   listing reads +0.07 — so a test against zero calls the MEDIAN STOCK an
   accumulation candidate. That bug shipped once, produced a confident and
   universally wrong reading, and is the reason `tape_calibration.json` exists.

2. NO CALIBRATION MEANS NO DIRECTION. An uncalibrated market gets the raw
   statistic and an explicit refusal, never a direction computed against the
   wrong null. Degrading to a plausible answer is worse than degrading to none.

3. AN UNREADABLE TAPE IS A READING. Most stocks have nothing to say and the
   honest output is to say so in words, near neutral — not to convert a noisy
   point estimate into a confident direction.

4. CONCENTRATION NEVER SCORES. It is not directional. A year that happened in
   five sessions is not thereby good or bad, it is unsizeable.

5. THE SCALES ARE PER MARKET. The IDX cross-section's wick standard deviation
   is three times the Nasdaq's. A fixed scale saturated for a quarter of one
   market and never moved at all in the other.

The wording is free to change. Those five are not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import tape as T


# --------------------------------------------------------------------------- #
# Planted ground truth
# --------------------------------------------------------------------------- #
def synthetic(n: int = 300, heavy_close_at: float = 0.5,
              ordinary_close_at: float = 0.5, heavy_every: int = 5,
              seed: int = 7) -> pd.DataFrame:
    """Bars where the close location on heavy days is PLANTED, not emergent.

    `heavy_close_at` and `ordinary_close_at` are positions inside each bar's
    range, 0 at the low and 1 at the high, so a caller states the effect it
    expects the module to recover rather than hoping a random walk produces one.
    """
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2024-01-01", periods=n)

    base = 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n)))
    span = base * 0.03
    high = base + span / 2
    low = base - span / 2

    is_heavy = np.zeros(n, dtype=bool)
    is_heavy[::heavy_every] = True
    # A rolling median needs a warm-up before anything counts as heavy, and the
    # first `RVOL_WINDOW` bars are dropped by the module anyway.
    volume = np.where(is_heavy, 5_000_000.0, 1_000_000.0)
    volume = volume * rng.lognormal(0.0, 0.05, n)

    position = np.where(is_heavy, heavy_close_at, ordinary_close_at)
    position = np.clip(position + rng.normal(0.0, 0.05, n), 0.02, 0.98)
    close = low + position * (high - low)

    return pd.DataFrame(
        {"Open": low + 0.5 * (high - low), "High": high, "Low": low,
         "Close": close, "Volume": volume},
        index=index)


def calibration(lift_median: float = 0.0, lift_sd: float = 0.14,
                wick_sd: float = 0.10, market: str = "ID") -> dict:
    return {
        "measuredOn": "2026-09-08", "alpha": T.ALPHA,
        "markets": {market: {
            "names": 188, "population": "the Indonesian listed market",
            "measuredOn": "2026-09-08", "liftMedian": lift_median,
            "liftSd": lift_sd, "wickSd": wick_sd, "significantShare": 0.133,
            "significantCount": 25, "tested": 188,
            "concentration": {"caution": 0.21, "severe": 0.36, "median": 0.13},
        }},
    }


# ============================================================================ #
# 1. The null is the market's median, not zero
# ============================================================================ #
def test_it_recovers_a_planted_accumulation_pattern():
    frame = synthetic(heavy_close_at=0.90, ordinary_close_at=0.50)
    result = T.read(frame, market_code="ID", calibration=calibration())

    assert result["available"] is True
    assert result["direction"] == "accumulation"
    assert result["lift"] > 0.4
    assert result["score"] > 70


def test_it_recovers_a_planted_distribution_pattern():
    frame = synthetic(heavy_close_at=0.10, ordinary_close_at=0.50)
    result = T.read(frame, market_code="ID", calibration=calibration())

    assert result["direction"] == "distribution"
    assert result["lift"] < -0.4
    assert result["score"] < 30


def test_a_market_typical_lift_reads_as_unremarkable_not_as_accumulation():
    """THE BUG THIS EXISTS FOR. A stock whose heavy days close exactly as much
    higher as the market's typical stock is not accumulating — it is ordinary.
    Against a zero null it reads as a confident buy signal."""
    frame = synthetic(heavy_close_at=0.66, ordinary_close_at=0.50)
    typical = T.read(frame, market_code="ID", calibration=calibration())["lift"]

    against_market = T.read(frame, market_code="ID",
                            calibration=calibration(lift_median=typical))
    against_zero = T.read(frame, market_code="ID",
                          calibration=calibration(lift_median=0.0))

    assert against_market["direction"] == "unreadable"
    assert against_zero["direction"] == "accumulation", (
        "the fixture must be strong enough that the wrong null would fire on it")


def test_the_baseline_is_carried_in_the_payload_and_named_in_the_prose():
    frame = synthetic(heavy_close_at=0.90)
    result = T.read(frame, market_code="ID", calibration=calibration(lift_median=0.07))
    assert result["liftBaseline"] == pytest.approx(0.07)
    assert result["excessLift"] == pytest.approx(result["lift"] - 0.07, abs=1e-9)
    assert "median for this market" in result["reading"]


# ============================================================================ #
# 2. No calibration means no direction
# ============================================================================ #
def test_an_uncalibrated_market_reports_the_statistic_and_refuses_a_direction():
    frame = synthetic(heavy_close_at=0.95, ordinary_close_at=0.30)
    result = T.read(frame, market_code="XX", calibration=calibration())

    assert result["available"] is True
    assert result["calibrated"] is False
    assert result["direction"] == "unreadable"
    assert result["score"] == 50.0, "an uncalibrated reading must not move the score"
    assert result["lift"] > 0.4, "the raw statistic is still reported"
    assert "NO DIRECTION IS REPORTED" in result["reading"]
    assert "calibrate_tape" in result["reading"]


def test_one_market_never_borrows_another_markets_row():
    """The IDX and US cross-sections differ by a factor of three on every scale
    in the module. Borrowing would be worse than having none."""
    assert T.calibration_for("US", calibration(market="ID")) is None
    assert T.calibration_for("ID", calibration(market="ID")) is not None


# ============================================================================ #
# 3. An unreadable tape is a reading
# ============================================================================ #
def test_no_planted_effect_reads_as_unreadable_near_neutral():
    frame = synthetic(heavy_close_at=0.50, ordinary_close_at=0.50)
    result = T.read(frame, market_code="ID", calibration=calibration())

    assert result["direction"] == "unreadable"
    assert result["significant"] is False
    assert 40.0 < result["score"] < 60.0
    assert "not separable from it" in result["reading"]


def test_too_little_history_is_unavailable_rather_than_neutral():
    result = T.read(synthetic(n=80), market_code="ID", calibration=calibration())
    assert result["available"] is False
    assert str(T.MIN_BARS) in result["reason"]


def test_a_frame_with_no_volume_declines():
    frame = synthetic()
    frame["Volume"] = 0.0
    result = T.read(frame, market_code="ID", calibration=calibration())
    assert result["available"] is False
    assert "volume" in result["reason"]


def test_a_locked_bar_contributes_no_close_location_rather_than_a_middle_one():
    """A limit-up print with no range is not a session that closed in the
    middle. It is a session carrying no information about who won it, and
    averaging a fabricated zero into the heavy-day mean is how a locked stock
    comes to read as balanced."""
    frame = synthetic()
    frame.loc[frame.index[10], ["High", "Low", "Close", "Open"]] = 100.0
    values = T.close_location(frame)
    assert pd.isna(values.iloc[10])


# ============================================================================ #
# 4. Concentration never scores
# ============================================================================ #
def test_concentration_is_computed_but_is_not_in_the_score():
    even = synthetic()
    spiky = synthetic()
    # One session carrying a fifth of the year, with the same close locations.
    spiky.loc[spiky.index[100], "Volume"] = float(spiky["Volume"].sum())

    even_result = T.read(even, market_code="ID", calibration=calibration())
    spiky_result = T.read(spiky, market_code="ID", calibration=calibration())

    assert (spiky_result["concentration"]["topFiveShare"]
            > even_result["concentration"]["topFiveShare"])
    assert spiky_result["concentration"]["band"] == "severe"
    assert even_result["concentration"]["band"] == "ordinary"


def test_the_concentration_band_comes_from_the_calibration_not_a_literal():
    frame = synthetic()
    frame.loc[frame.index[100], "Volume"] = float(frame["Volume"].sum()) * 0.5

    strict = T.read(frame, market_code="ID",
                    calibration=_with_bands(calibration(), caution=0.05, severe=0.10))
    loose = T.read(frame, market_code="ID",
                   calibration=_with_bands(calibration(), caution=0.90, severe=0.95))

    assert strict["concentration"]["band"] == "severe"
    assert loose["concentration"]["band"] == "ordinary"


def test_an_uncalibrated_market_assigns_no_concentration_band():
    result = T.read(synthetic(), market_code="XX", calibration=calibration())
    assert result["concentration"]["band"] is None
    assert result["concentration"]["calibrated"] is False


def _with_bands(payload: dict, caution: float, severe: float) -> dict:
    payload["markets"]["ID"]["concentration"] = {
        "caution": caution, "severe": severe, "median": 0.13}
    return payload


# ============================================================================ #
# 5. The scales are per market
# ============================================================================ #
def test_the_wick_term_is_scaled_in_that_markets_standard_deviations():
    """A fixed scale saturated for a quarter of IDX names and never moved at all
    for US ones. The same wick must count for more in a market where wicks vary
    less."""
    frame = synthetic(heavy_close_at=0.50, ordinary_close_at=0.50)

    wide = T.read(frame, market_code="ID", calibration=calibration(wick_sd=0.30))
    narrow = T.read(frame, market_code="ID", calibration=calibration(wick_sd=0.01))

    assert abs(narrow["score"] - 50.0) >= abs(wide["score"] - 50.0)


def test_the_wick_term_cannot_outweigh_the_tested_statistic():
    """It carries no significance test. Letting an untested observation move a
    score as far as a tested one would misrepresent which is evidence."""
    assert T.WICK_SWING < T.LIFT_SWING / 4


# ============================================================================ #
# The refusal that has to survive every rewording
# ============================================================================ #
def test_every_available_reading_carries_what_a_broker_summary_would_settle():
    result = T.read(synthetic(heavy_close_at=0.9), market_code="ID",
                    calibration=calibration())
    assert "broker summary" in result["missing"]
    for phrase in ("who bought", "foreign", "cross"):
        assert phrase in result["missing"]


def test_no_rendered_string_claims_to_be_bandarmology():
    """The method is defined by the broker summary, which this does not have.

    ASSERTED ON THE OUTPUT, NOT THE SOURCE. An earlier version of this test
    grepped the module text and failed on a sentence that was itself a
    qualification — the docstring is written for whoever maintains this, and the
    payload is what reaches somebody deciding what to buy. It is the payload
    that must never carry the claim.
    """
    readings = []
    for direction in (0.95, 0.05, 0.50):
        result = T.read(synthetic(heavy_close_at=direction), market_code="ID",
                        calibration=calibration())
        readings.extend(str(v) for v in result.values() if isinstance(v, str))
    readings.append(T.read(synthetic(), market_code="XX",
                           calibration=calibration())["reading"])

    for text in readings:
        assert "bandarmology" not in text.lower(), (
            f"a rendered string names the method: {text!r}")


def test_the_module_states_the_refusal_where_a_maintainer_will_meet_it():
    """The docstring is the other half. Somebody extending this file has to hit
    the boundary before they hit the code."""
    doc = (T.__doc__ or "").lower()
    assert "not bandarmology" in doc
    assert "broker summary" in doc
