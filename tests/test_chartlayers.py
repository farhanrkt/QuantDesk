"""The annotated chart, and the four ways drawing an analysis quietly lies.

WHAT THESE TESTS PROTECT

1. THE DRAWN CURVE IS THE ONE THE DETECTOR SAW. Smoothing the whole series and
   plotting it is one line of code, looks better, and is a look-ahead: the
   kernel is two-sided, so a whole-series fit at a past date is built partly out
   of prices from after it. The curve under a detection must be identical to the
   curve computed from a frame that ENDS on the detection bar.

2. NOTHING IS PROJECTED. Every chart-pattern convention ends in a measured-move
   target. The measurement in `patterns.py` found the textbook direction carries
   no information, so a target arrow would put a claim on the chart that this
   app's own study declined. No guide may be a forecast.

3. THE OVERLAYS ARE COMPUTED ON THE HISTORY, NOT ON THE WINDOW. A 200-day
   average computed inside a 180-bar plot window is empty for every bar, and the
   line silently vanishes rather than erroring.

4. THE CHART AND THE READING CLASSIFY THE SAME DAYS. A heavy session circled on
   the chart that the Welch test never counted is worse than no circle at all,
   because it cannot be caught by reading either one alone.

The wording is free to change. Those four are not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import chartlayers as C
from _lib import patterns as P
from _lib import structure, tape

from test_patterns import calibration, padded

# Five turning points per shape, as LMW define them. Same planting helper and
# the same paths the pattern suite uses, so a shape that fails here fails there
# too.
#
# `per_leg` IS LOAD-BEARING AND IT IS NOT A STYLE CHOICE. Six legs at eight bars
# each spans 48 sessions, which is wider than the 35-bar detection window, so a
# perfectly formed head-and-shoulders planted that way is never detected at all
# — the window can only ever hold four of its five turns. The first version of
# this file used the default and every pattern test failed with "the planted
# path produced no detection", which reads like a broken detector rather than a
# fixture too long for it.
LEG = 5
HEAD_AND_SHOULDERS = [100, 118, 104, 133, 103, 119, 100]
INVERSE_HEAD_AND_SHOULDERS = [100, 82, 96, 67, 97, 81, 100]
RECTANGLE = [100, 100.2, 90.1, 100.1, 89.9, 100.0, 90.0]
TRIANGLE_TOP = [100, 130, 96, 120, 100, 112, 98]


def frame_for(points, per_leg: int = LEG, tail: int = 14, **kwargs) -> pd.DataFrame:
    return padded(points, per_leg=per_leg, tail=tail, **kwargs)


def volume_frame(n: int = 300, seed: int = 11) -> pd.DataFrame:
    """A series with real volume, so the tape layer has something to classify."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.014, n)))
    span = close * 0.02
    volume = rng.lognormal(13.0, 0.6, n)
    index = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame(
        {"Open": close, "High": close + span, "Low": close - span,
         "Close": close, "Volume": volume}, index=index)


def detect_one(frame: pd.DataFrame) -> tuple[dict, dict]:
    found = P.detect(frame)
    assert found["available"], found.get("reason")
    assert found["detections"], "the planted path produced no detection"
    return found, found["detections"][-1]


# ============================================================================ #
# 1. The drawn curve is the one the detector saw
# ============================================================================ #
def test_the_drawn_curve_does_not_change_when_later_prices_arrive():
    """The one test that would invalidate every pattern drawing in the app."""
    frame = frame_for(HEAD_AND_SHOULDERS)
    found, detection = detect_one(frame)
    prices = frame["Close"].to_numpy(dtype="float64")

    drawn = P.geometry(prices, detection, found["bandwidth"])
    assert drawn is not None

    # The same window, from a frame that cannot see past the detection bar.
    cut = prices[: detection["detectedIndex"] + 1]
    truncated = P.geometry(cut, detection, found["bandwidth"])
    assert truncated is not None

    a = [node["price"] for node in drawn["path"]]
    b = [node["price"] for node in truncated["path"]]
    assert a == pytest.approx(b, abs=1e-12)


def test_the_marked_points_are_the_closes_the_classifier_compared():
    """Not the smoothed values they turned on — the inequalities used closes."""
    frame = frame_for(HEAD_AND_SHOULDERS)
    found, detection = detect_one(frame)
    prices = frame["Close"].to_numpy(dtype="float64")
    drawn = P.geometry(prices, detection, found["bandwidth"])

    for point in drawn["points"]:
        assert point["price"] == pytest.approx(prices[point["index"]], abs=1e-9)
    # And the smoothed value is carried separately rather than substituted.
    assert any(point["price"] != point["smoothed"] for point in drawn["points"])


def test_the_curve_is_refused_rather_than_redrawn_on_a_window_it_cannot_reach():
    frame = frame_for(HEAD_AND_SHOULDERS)
    found, detection = detect_one(frame)
    short = frame["Close"].to_numpy(dtype="float64")[:10]
    assert P.geometry(short, detection, found["bandwidth"]) is None


def test_five_alternating_points_come_back_in_order():
    frame = frame_for(HEAD_AND_SHOULDERS)
    found, detection = detect_one(frame)
    drawn = P.geometry(frame["Close"].to_numpy(dtype="float64"), detection,
                       found["bandwidth"])
    kinds = [point["kind"] for point in drawn["points"]]
    assert len(kinds) == 5
    assert all(kinds[i] != kinds[i + 1] for i in range(4))
    indices = [point["index"] for point in drawn["points"]]
    assert indices == sorted(indices)


# ============================================================================ #
# 2. Nothing is projected
# ============================================================================ #
def test_no_guide_is_a_forecast():
    """Necklines and boundaries describe the five points. Targets do not."""
    for points in (HEAD_AND_SHOULDERS, RECTANGLE, TRIANGLE_TOP):
        frame = frame_for(points)
        found = P.detect(frame)
        if not found["detections"]:
            continue
        detection = found["detections"][-1]
        drawn = P.geometry(frame["Close"].to_numpy(dtype="float64"), detection,
                           found["bandwidth"])
        roles = {guide["role"] for guide in P.guides(drawn["points"],
                                                     detection["pattern"])}
        assert roles <= {"neckline", "upper", "lower"}, roles


def test_a_head_and_shoulders_gets_one_neckline_through_its_inner_turns():
    frame = frame_for(HEAD_AND_SHOULDERS)
    found, detection = detect_one(frame)
    assert detection["pattern"] == "headAndShoulders"
    drawn = P.geometry(frame["Close"].to_numpy(dtype="float64"), detection,
                       found["bandwidth"])
    lines = P.guides(drawn["points"], detection["pattern"])

    assert len(lines) == 1 and lines[0]["role"] == "neckline"
    inner = [drawn["points"][1], drawn["points"][3]]
    assert lines[0]["from"]["price"] == pytest.approx(inner[0]["price"])
    assert lines[0]["to"]["price"] == pytest.approx(inner[1]["price"])
    # Both ends are troughs: a neckline drawn through the shoulders would be a
    # different line entirely and would still render.
    assert all(point["kind"] == "trough" for point in inner)


def test_a_rectangle_gets_two_horizontal_edges():
    frame = frame_for(RECTANGLE)
    found = P.detect(frame)
    rectangles = [d for d in found["detections"] if d["pattern"].startswith("rectangle")]
    if not rectangles:
        pytest.skip("the planted path did not smooth into a rectangle")
    drawn = P.geometry(frame["Close"].to_numpy(dtype="float64"), rectangles[-1],
                       found["bandwidth"])
    lines = P.guides(drawn["points"], rectangles[-1]["pattern"])
    assert {line["role"] for line in lines} == {"upper", "lower"}
    for line in lines:
        assert line["from"]["price"] == pytest.approx(line["to"]["price"])


def test_a_triangle_gets_two_lines_that_are_not_horizontal():
    frame = frame_for(TRIANGLE_TOP)
    found = P.detect(frame)
    triangles = [d for d in found["detections"]
                 if d["pattern"] in ("triangleTop", "triangleBottom",
                                     "broadeningTop", "broadeningBottom")]
    if not triangles:
        pytest.skip("the planted path did not smooth into a triangle")
    drawn = P.geometry(frame["Close"].to_numpy(dtype="float64"), triangles[-1],
                       found["bandwidth"])
    lines = P.guides(drawn["points"], triangles[-1]["pattern"])
    assert {line["role"] for line in lines} == {"upper", "lower"}
    assert any(line["from"]["price"] != line["to"]["price"] for line in lines)


def test_guides_refuse_anything_that_is_not_five_points():
    frame = frame_for(HEAD_AND_SHOULDERS)
    found, detection = detect_one(frame)
    drawn = P.geometry(frame["Close"].to_numpy(dtype="float64"), detection,
                       found["bandwidth"])
    assert P.guides(drawn["points"][:4], "headAndShoulders") == []
    assert P.guides(drawn["points"], "flag") == []


# ============================================================================ #
# 3. Overlays are computed on the history, not on the window
# ============================================================================ #
def test_the_slow_average_survives_a_window_shorter_than_itself():
    frame = volume_frame(400)
    chart = C.build(frame, plot_sessions=120)
    assert chart["available"]
    assert chart["sessions"] == 120
    assert all(bar["sma200"] is not None for bar in chart["bars"]), \
        "a 200-day average computed inside a 120-bar window is empty everywhere"


def test_the_bollinger_band_is_the_right_way_up():
    """An inverted unpack still brackets the price and still looks correct."""
    chart = C.build(volume_frame(400))
    banded = [bar for bar in chart["bars"] if bar["bbUpper"] and bar["bbLower"]]
    assert banded
    assert all(bar["bbUpper"] > bar["bbLower"] for bar in banded)


def test_too_little_history_declines_with_a_count_rather_than_drawing():
    chart = C.build(volume_frame(12))
    assert chart["available"] is False
    assert "12" in chart["reason"]
    assert C.build(None)["available"] is False


# ============================================================================ #
# 4. The chart and the reading classify the same days
# ============================================================================ #
def test_the_heavy_sessions_drawn_are_the_ones_the_test_counted():
    frame = volume_frame(300)
    marks = tape.sessions(frame)
    stats = tape.statistics(frame)
    assert marks["available"] and stats["available"]

    drawn = [row for row in marks["sessions"]
             if row["heavy"] and row["closeLocation"] is not None]
    assert len(drawn) == stats["heavySessions"]
    assert marks["rvolCutoff"] == pytest.approx(stats["rvolCutoff"])


def test_the_classification_ignores_how_much_of_it_gets_drawn():
    """Trimming for the chart must not rebase the percentile."""
    frame = volume_frame(300)
    everything = {row["date"]: row["heavy"] for row in tape.sessions(frame)["sessions"]}
    short = C.build(frame, plot_sessions=60)
    for bar in short["bars"]:
        assert bar["heavy"] == everything[bar["date"]]


def test_a_frame_the_tape_cannot_read_still_draws_and_says_so():
    chart = C.build(volume_frame(80))
    assert chart["available"] is True
    assert chart["tape"]["available"] is False
    assert chart["tape"]["reason"]
    note = next(row for row in chart["legend"] if row["key"] == "heavy")
    assert note["note"] == chart["tape"]["reason"]


# ============================================================================ #
# The assembled payload
# ============================================================================ #
def test_the_nearest_levels_are_the_ones_the_ratio_was_computed_from():
    levels = {"usable": True, "price": 100.0, "atr": 2.0,
              "supports": [{"price": 95.0, "touches": 3, "distancePct": -0.05},
                           {"price": 88.0, "touches": 2, "distancePct": -0.12}],
              "resistances": [{"price": 108.0, "touches": 4, "distancePct": 0.08},
                              {"price": 120.0, "touches": 2, "distancePct": 0.20}]}
    site = structure.read(levels=levels)
    technical = {"shortTerm": {"levels": levels}}
    chart = C.build(volume_frame(300), technical=technical, structure_result=site)

    nearest = {row["price"] for row in chart["levels"] if row["nearest"]}
    assert nearest == {95.0, 108.0}
    assert chart["trade"]["stop"] == 95.0
    assert chart["trade"]["target"] == 108.0
    assert chart["trade"]["rewardRisk"] == pytest.approx(site["rewardRisk"])
    assert chart["trade"]["levelTolerance"] == pytest.approx(
        structure.AT_LEVEL_ATR * 2.0)


def test_a_refused_structure_draws_no_trade_rather_than_half_of_one():
    chart = C.build(volume_frame(300),
                    structure_result={"available": False, "reason": "no levels"})
    assert chart["trade"] is None
    assert chart["levels"] == []
    assert not any(row["key"] == "trade" for row in chart["legend"])


def test_a_pattern_whose_window_starts_before_the_chart_is_dropped():
    frame = frame_for(HEAD_AND_SHOULDERS)
    found = P.read(frame, market_code="ID",
                   calibration=calibration("headAndShoulders"))
    assert found["detections"]

    whole = C.build(frame, pattern_result=found, plot_sessions=len(frame))
    clipped = C.build(frame, pattern_result=found, plot_sessions=20)
    assert whole["patterns"], "the planted formation should draw in full"
    assert clipped["patterns"] == [], "half a formation is not a formation"


def test_a_drawn_pattern_carries_both_directions_and_never_merges_them():
    frame = frame_for(HEAD_AND_SHOULDERS)
    found = P.read(frame, market_code="ID",
                   calibration=calibration("headAndShoulders", effect=-0.032))
    chart = C.build(frame, pattern_result=found, plot_sessions=len(frame))
    shape = next(row for row in chart["patterns"]
                 if row["pattern"] == "headAndShoulders")

    assert shape["textbookBias"] == P.CATALOGUE["headAndShoulders"]["bias"]
    assert shape["significant"] is True
    assert shape["measuredExcess"] == pytest.approx(-0.032)
    assert shape["measuredHorizon"] == 63
    # THE EFFECTIVE SAMPLE IS MONTHS, NOT DETECTIONS. The study collapses by
    # calendar month because these shapes fire together in a selloff, so the
    # raw count overstates the evidence by more than an order of magnitude.
    # Both travel, and the panel is required to lead with the smaller one.
    assert shape["measuredMonths"] == 69
    assert shape["measuredObservations"] == 1475
    assert shape["points"] and shape["guides"] and shape["path"]
    assert all(point["date"] for point in shape["points"])


def test_an_uncalibrated_pattern_is_still_drawn_and_marked_unmeasured():
    frame = frame_for(HEAD_AND_SHOULDERS)
    found = P.read(frame, market_code="ID", calibration={})
    chart = C.build(frame, pattern_result=found, plot_sessions=len(frame))
    assert chart["patterns"], "a shape nobody measured is still a shape"
    assert all(shape["significant"] is False for shape in chart["patterns"])
    assert all(shape["measuredExcess"] is None for shape in chart["patterns"])


def test_the_caption_says_nothing_here_is_a_forecast():
    chart = C.build(volume_frame(300))
    assert "forecast" in chart["caption"]
    assert "no price target" in chart["caption"]


def test_every_layer_carries_its_own_note():
    frame = volume_frame(300)
    chart = C.build(frame)
    assert chart["legend"]
    for row in chart["legend"]:
        assert row["key"] and row["label"] and row["note"]


def test_crossovers_are_read_off_the_trend_lens_not_recomputed():
    frame = volume_frame(300)
    dates = [bar for bar in frame.index.strftime("%Y-%m-%d")]
    technical = {"signals": [
        {"date": dates[-5], "type": "Buy", "description": "Golden cross",
         "price": 101.0},
        # Before the plot window, so it must not be drawn on it.
        {"date": dates[0], "type": "Sell", "description": "Death cross",
         "price": 99.0},
    ]}
    chart = C.build(frame, technical=technical, plot_sessions=60)
    assert [row["date"] for row in chart["crossovers"]] == [dates[-5]]
