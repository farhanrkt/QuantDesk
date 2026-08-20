"""CUSUM regime detection, tested by planting regimes in noise.

The claim this module makes is that it catches drift a point-anomaly detector
cannot: a long run of individually unremarkable days. So the key test plants
exactly that — a shift small enough that no single day is an outlier — and
checks both that CUSUM finds it and that the Isolation Forest's kind of
per-day thresholding does not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import accumulation as A


def series_with_regime(n=400, start=150, length=60, shift=0.8, seed=5):
    """Standard normal noise with a sustained mean shift planted in the middle."""
    rng = np.random.default_rng(seed)
    values = rng.normal(0.0, 1.0, n)
    values[start:start + length] += shift
    index = pd.bdate_range("2024-01-01", periods=n)
    return pd.Series(values, index=index), index[start], index[start + length - 1]


# --------------------------------------------------------------------------- #
# Core behaviour
# --------------------------------------------------------------------------- #
def test_finds_a_planted_accumulation_regime():
    series, planted_start, _ = series_with_regime()
    episodes = A.cusum_episodes(series)

    assert episodes, "no episode detected at all"
    accumulation = [e for e in episodes if e["direction"] == "Accumulation"]
    assert accumulation

    hit = max(accumulation, key=lambda e: e["days"])
    # The changepoint estimate should land near the planted start, and the
    # episode should overlap the planted window substantially.
    assert abs((hit["start"] - planted_start).days) < 30
    assert hit["days"] >= 20


def test_finds_a_planted_distribution_regime():
    series, _, _ = series_with_regime(shift=-0.8)
    episodes = A.cusum_episodes(series)
    assert any(e["direction"] == "Distribution" for e in episodes)


def test_catches_drift_that_no_single_day_reveals():
    """The whole argument for this module.

    A +0.7 sigma shift means not one day in the regime is an outlier by any
    per-day rule, yet the run is unmistakable in aggregate.
    """
    series, _, _ = series_with_regime(shift=0.7, length=80, seed=9)

    # A per-day detector at a conventional 3-sigma cutoff sees almost nothing
    # special inside the regime.
    per_day_flags = int((series.abs() > 3.0).sum())
    assert per_day_flags <= 3

    episodes = A.cusum_episodes(series)
    assert any(e["direction"] == "Accumulation" and e["days"] >= 20 for e in episodes)


def test_stationary_noise_produces_few_or_no_episodes():
    """False alarms have to be rare or the feature is worthless."""
    rng = np.random.default_rng(3)
    counts = []
    for seed in range(12):
        rng = np.random.default_rng(100 + seed)
        noise = pd.Series(rng.normal(0.0, 1.0, 400),
                          index=pd.bdate_range("2024-01-01", periods=400))
        counts.append(len(A.cusum_episodes(noise)))
    assert np.mean(counts) < 1.0, f"mean false episodes per year: {np.mean(counts):.2f}"


# --------------------------------------------------------------------------- #
# Parameters behave sensibly
# --------------------------------------------------------------------------- #
def test_a_higher_threshold_detects_fewer_episodes():
    series, _, _ = series_with_regime(shift=0.6, length=90, seed=2)
    counts = [len(A.cusum_episodes(series, threshold=h)) for h in (2.0, 5.0, 12.0, 30.0)]
    assert counts == sorted(counts, reverse=True)


def test_more_slack_detects_fewer_episodes():
    series, _, _ = series_with_regime(shift=0.6, length=90, seed=2)
    counts = [len(A.cusum_episodes(series, slack=k)) for k in (0.1, 0.5, 1.5, 3.0)]
    assert counts == sorted(counts, reverse=True)


def test_a_single_spike_does_not_manufacture_a_regime():
    """One enormous day is the point detector's finding, not this one's.

    Without winsorising, a 40-sigma print alone pushes the statistic to ~39.5,
    which then bleeds off at `slack` per day and reports an eleven-week
    "accumulation regime" made entirely of the decay tail of one observation.
    """
    values = np.zeros(200)
    values[100] = 40.0
    series = pd.Series(values, index=pd.bdate_range("2024-01-01", periods=200))
    assert A.cusum_episodes(series, min_days=5) == []


def test_winsorising_is_what_suppresses_the_spike():
    """Turn the cap off and the artefact comes straight back."""
    values = np.zeros(200)
    values[100] = 40.0
    series = pd.Series(values, index=pd.bdate_range("2024-01-01", periods=200))
    unguarded = A.cusum_episodes(series, min_days=5, winsor=1e9)
    assert unguarded, "expected the artefact without winsorising"
    assert unguarded[0]["days"] > 50


def test_changepoint_is_backdated_before_detection():
    """The regime started before there was enough evidence to declare it."""
    series, _, _ = series_with_regime(shift=1.0, length=70, seed=4)
    episodes = A.cusum_episodes(series)
    assert episodes
    for episode in episodes:
        assert episode["start"] <= episode["detected"]


def test_an_ongoing_regime_is_marked():
    rng = np.random.default_rng(7)
    values = rng.normal(0.0, 1.0, 300)
    values[240:] += 1.2                       # still running at the last bar
    series = pd.Series(values, index=pd.bdate_range("2024-01-01", periods=300))
    episodes = A.cusum_episodes(series)
    assert any(e.get("ongoing") for e in episodes)


# --------------------------------------------------------------------------- #
# Edge cases and the frame-level wrapper
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("data", [[], [0.1], [0.1, 0.2, 0.3]])
def test_short_series_return_nothing(data):
    series = pd.Series(data, index=pd.bdate_range("2024-01-01", periods=len(data)))
    assert A.cusum_episodes(series) == []


def test_nan_and_inf_are_dropped_not_propagated():
    values = [0.5, np.nan, 1.2, np.inf, 0.9, -np.inf] + [1.4] * 60
    series = pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)))
    episodes = A.cusum_episodes(series)
    assert all(np.isfinite(e["peak"]) for e in episodes)


def test_detect_enriches_episodes_with_price_and_volume():
    n = 400
    rng = np.random.default_rng(1)
    obv_z = rng.normal(0.0, 1.0, n)
    obv_z[150:230] += 1.0
    index = pd.bdate_range("2024-01-01", periods=n)
    frame = pd.DataFrame(
        {
            "OBV_Change_Z": obv_z,
            "Close": np.linspace(100, 160, n),
            "Volume_vs_Avg": rng.uniform(0.8, 2.0, n),
        },
        index=index,
    )
    result = A.detect(frame)
    assert result["episodes"]
    first = result["episodes"][0]
    assert set(first) >= {"direction", "start", "detected", "end", "days",
                          "priceChangePct", "avgRvol", "ongoing"}
    assert first["priceChangePct"] is not None
    assert result["config"]["threshold"] == A.DEFAULT_THRESHOLD


def test_detect_handles_a_frame_without_the_feature():
    frame = pd.DataFrame({"Close": [1.0, 2.0, 3.0]})
    result = A.detect(frame)
    assert result["episodes"] == [] and result["current"] is None


def test_detect_output_is_json_safe():
    import json
    from _lib.jsonsafe import clean

    n = 300
    rng = np.random.default_rng(2)
    obv_z = rng.normal(0.0, 1.0, n)
    obv_z[100:180] += 1.1
    frame = pd.DataFrame(
        {"OBV_Change_Z": obv_z, "Close": np.linspace(50, 90, n),
         "Volume_vs_Avg": rng.uniform(0.5, 3.0, n)},
        index=pd.bdate_range("2024-01-01", periods=n),
    )
    json.dumps(clean(A.detect(frame)), allow_nan=False)
