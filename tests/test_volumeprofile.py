"""Volume at price, and the null that decides what it may be used for.

WHAT THESE TESTS PROTECT

1. THE DISTRIBUTION IS EXACT, NOT MIDPOINT. Each bar's volume is spread across
   every bin its range overlaps, in proportion to the overlap. Assigning a bar
   to the bin holding its midpoint would concentrate a trending name's whole
   year onto a handful of prices and invent shelves out of the binning.

2. A LEVEL IS A BAND. The profile is built by spreading daily bars, so a point
   of control quoted to the rupiah is false precision. Every level here has a
   low and a high, and nothing returns a bare price.

3. A SHELF IS NOT SUPPORT UNTIL MEASURED. `usable` is false unless this
   market's calibration says otherwise, and the reading says which it is. The
   measured answer on IDX was a null, so this is the live path, not a
   hypothetical one.

4. BINS SCALE WITH THE NAME. Bin width is in average true ranges, so "a lot of
   volume at one price" means the same thing on a quiet utility and a miner.

The wording is free to change. Those four are not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import volumeprofile as VP


def frame(closes, volumes=None, spread=0.01, start="2023-01-02") -> pd.DataFrame:
    values = np.asarray(closes, dtype="float64")
    volume = (np.full(len(values), 1_000_000.0) if volumes is None
              else np.asarray(volumes, dtype="float64"))
    span = values * spread
    return pd.DataFrame(
        {"Open": values, "High": values + span, "Low": values - span,
         "Close": values, "Volume": volume},
        index=pd.bdate_range(start, periods=len(values)))


def flat(n=260, level=100.0, **kwargs) -> pd.DataFrame:
    return frame(np.full(n, level), **kwargs)


def calibration(usable: bool, market="ID") -> dict:
    return {"measuredOn": "2026-09-11",
            "markets": {market: {"usable": usable, "measuredOn": "2026-09-11",
                                 "reading": "measured"}}}


# ============================================================================ #
# 1. The distribution is exact
# ============================================================================ #
def test_a_bar_spreads_across_every_bin_its_range_covers():
    edges = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    one = pd.DataFrame({"Open": [1.0], "High": [3.0], "Low": [1.0], "Close": [3.0],
                        "Volume": [100.0]}, index=pd.bdate_range("2024-01-01", periods=1))
    totals = VP.distribute(one, edges)
    # The bar spans bins 1 and 2 equally and touches neither 0 nor 3.
    assert totals[0] == pytest.approx(0.0)
    assert totals[1] == pytest.approx(50.0)
    assert totals[2] == pytest.approx(50.0)
    assert totals[3] == pytest.approx(0.0)
    assert totals.sum() == pytest.approx(100.0)


def test_a_locked_session_goes_entirely_into_one_bin():
    """Limit up, or a halt that printed once. Its range is zero and the overlap
    arithmetic would divide by it."""
    edges = np.array([0.0, 1.0, 2.0, 3.0])
    locked = pd.DataFrame({"Open": [1.5], "High": [1.5], "Low": [1.5], "Close": [1.5],
                           "Volume": [80.0]},
                          index=pd.bdate_range("2024-01-01", periods=1))
    totals = VP.distribute(locked, edges)
    assert totals[1] == pytest.approx(80.0)
    assert totals.sum() == pytest.approx(80.0)


def test_no_volume_is_created_or_lost():
    rng = np.random.default_rng(4)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))
    data = frame(closes, volumes=rng.lognormal(12, 0.5, 300))
    edges = np.linspace(data["Low"].min(), data["High"].max(), 60)
    assert VP.distribute(data, edges).sum() == pytest.approx(
        data["Volume"].sum(), rel=1e-9)


def test_a_trending_name_does_not_pile_onto_its_midpoints():
    """The bug the exact overlap exists to prevent: with midpoint assignment a
    steady trend puts each session in one bin and the profile is flat-topped
    nonsense rather than a distribution."""
    rising = frame(np.linspace(100.0, 200.0, 300), spread=0.03)
    result = VP.build(rising)
    assert result["available"]
    shares = np.array([b["share"] for b in result["profile"]])
    # A linear trend visits every price about equally; no single band should hold
    # an outsized share of a year that spent one day at each level.
    assert shares.max() < 0.10


# ============================================================================ #
# 2. A level is a band
# ============================================================================ #
def test_every_level_has_a_low_and_a_high():
    rng = np.random.default_rng(7)
    data = frame(100.0 * np.exp(np.cumsum(rng.normal(0, 0.015, 300))),
                 volumes=rng.lognormal(12, 0.5, 300))
    result = VP.build(data)
    assert result["available"]
    for key in ("pointOfControl", "valueArea"):
        assert result[key]["low"] < result[key]["high"]
    for shelf in result["shelves"]:
        assert shelf["low"] < shelf["high"]
        assert shelf["side"] in ("above", "below", "here")


def test_the_value_area_holds_about_seventy_percent():
    rng = np.random.default_rng(9)
    data = frame(100.0 * np.exp(np.cumsum(rng.normal(0, 0.015, 300))),
                 volumes=rng.lognormal(12, 0.5, 300))
    result = VP.build(data)
    assert result["valueArea"]["share"] >= VP.VALUE_AREA_SHARE
    # It expands one bin at a time, so it should not overshoot by much.
    assert result["valueArea"]["share"] < VP.VALUE_AREA_SHARE + 0.15


def test_a_concentrated_band_becomes_one_shelf_not_several():
    """Adjacent qualifying bins are merged: a broad high-volume region is one
    fact, and reporting each quarter-ATR slice would count it four times."""
    rng = np.random.default_rng(11)
    # Two years around 100, then a long excursion with tiny volume.
    closes = np.concatenate([rng.normal(100.0, 0.6, 220),
                             np.linspace(100.0, 160.0, 80)])
    volumes = np.concatenate([np.full(220, 5_000_000.0), np.full(80, 50_000.0)])
    result = VP.build(frame(closes, volumes=volumes, spread=0.004))
    assert result["available"]
    assert len(result["shelves"]) == 1, [s["share"] for s in result["shelves"]]
    shelf = result["shelves"][0]
    assert shelf["share"] > 0.8
    assert shelf["bins"] > 1


# ============================================================================ #
# 3. A shelf is not support until measured
# ============================================================================ #
def test_without_a_calibration_nothing_is_read_as_support():
    result = VP.build(frame(np.linspace(90.0, 110.0, 300)),
                      market_code="ID", calibration={})
    assert result["available"]
    assert result["calibrated"] is False
    assert result["usable"] is False
    assert "has not been measured" in result["reading"]


def test_the_status_is_attached_even_when_there_are_no_shelves():
    """The early return for a shelf-less profile skipped it, and those are
    exactly the names where a reader goes looking at the bands instead."""
    result = VP.build(frame(np.linspace(90.0, 110.0, 300)),
                      market_code="ID", calibration=calibration(usable=False))
    assert result["shelves"] == []
    assert "does NOT hold reliably better" in result["reading"]


def test_a_measured_null_says_so_in_the_reading():
    result = VP.build(frame(np.linspace(90.0, 110.0, 300)),
                      market_code="ID", calibration=calibration(usable=False))
    assert result["calibrated"] is True
    assert result["usable"] is False
    assert "does NOT hold reliably better" in result["reading"]


def test_a_measured_positive_would_say_that_instead():
    result = VP.build(frame(np.linspace(90.0, 110.0, 300)),
                      market_code="ID", calibration=calibration(usable=True))
    assert result["usable"] is True
    assert "does hold more often" in result["reading"]


def test_one_market_never_borrows_another_markets_measurement():
    assert VP.calibration_for("US", calibration(usable=True, market="ID")) is None
    assert VP.calibration_for("ID", calibration(usable=True, market="ID")) is not None


def test_the_shipped_calibration_is_the_null_this_module_documents():
    """The measured answer on IDX was a null. If someone re-runs the script and
    it turns positive, this test should fail and the docstring should be
    rewritten — not the other way round."""
    row = VP.calibration_for("ID")
    if row is None:
        pytest.skip("no calibration artifact on disk")
    assert row["usable"] is False
    assert row["survivors"] == []


# ============================================================================ #
# 4. Bins scale with the name
# ============================================================================ #
def test_bin_width_tracks_the_names_own_range():
    quiet = VP.build(frame(100.0 + np.sin(np.arange(300) / 9.0) * 1.0, spread=0.002))
    wild = VP.build(frame(100.0 + np.sin(np.arange(300) / 9.0) * 30.0, spread=0.05))
    assert quiet["available"] and wild["available"]
    assert wild["binWidth"] > quiet["binWidth"] * 5
    # But both express the same amount of smoothing in the unit that matters.
    for result in (quiet, wild):
        assert result["binWidthAtr"] == pytest.approx(VP.BIN_ATR, abs=0.25)


def test_the_bin_count_stays_inside_its_guard_rails():
    rng = np.random.default_rng(13)
    violent = frame(100.0 * np.exp(np.cumsum(rng.normal(0, 0.12, 300))), spread=0.001)
    result = VP.build(violent)
    assert result["available"]
    assert VP.MIN_BINS <= result["bins"] <= VP.MAX_BINS


# ============================================================================ #
# Refusals
# ============================================================================ #
def test_too_little_history_declines_with_a_count():
    result = VP.build(frame(np.linspace(100.0, 110.0, 40)))
    assert result["available"] is False
    assert "40" in result["reason"]
    assert VP.build(None)["available"] is False


def test_a_window_with_no_volume_declines():
    result = VP.build(frame(np.linspace(100.0, 110.0, 300), volumes=np.zeros(300)))
    assert result["available"] is False
    assert "volume" in result["reason"]


def test_a_flat_price_declines_rather_than_dividing_by_a_zero_range():
    """A suspended listing, or one pinned at the exchange's tick floor. IDX has
    plenty of both, and the binning divides by the window's range."""
    assert VP.build(flat(300, spread=0.0))["available"] is False
