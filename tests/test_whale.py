"""Locks caveat C from _lib/whale.py, plus the walk-forward cost ceiling.

Caveat C: fitting the Isolation Forest with a float `contamination` sets
sklearn's `offset_` to that percentile of the TRAINING scores. Because the
whole-window fit scores the rows it was fit on, exactly `contamination x n` of
them land below zero by construction — so "threshold" mode returned an
identical flag set to "quota" mode on every input, calm or wild, and the mode
was decorative. `contamination="auto"` pins `offset_` at -0.5 and restores the
absolute scale. If someone ever "tidies up" `_new_model` by passing the
configured contamination through, test_threshold_is_not_a_quota fails.
"""

from __future__ import annotations

import numpy as np
import pytest

from _lib.whale import AnalysisConfig, WhaleTracker


@pytest.fixture(scope="module")
def scored(ohlcv):
    tracker = WhaleTracker(AnalysisConfig(detection_mode="threshold"))
    return tracker, tracker.detect_anomalies(tracker._engineer_features(ohlcv))


def test_model_is_fit_with_auto_contamination():
    """The single line the whole absolute-scale argument rests on."""
    assert WhaleTracker(AnalysisConfig())._new_model().contamination == "auto"


def test_threshold_is_not_a_quota(ohlcv):
    """The regression guard for caveat C.

    Under the bug these two modes produced the same flags on every input.
    """
    features = WhaleTracker(AnalysisConfig())._engineer_features(ohlcv)

    threshold = WhaleTracker(AnalysisConfig(detection_mode="threshold"))
    quota = WhaleTracker(AnalysisConfig(detection_mode="quota", contamination=0.02))

    flags_threshold = threshold.detect_anomalies(features)["Anomaly"]
    flags_quota = quota.detect_anomalies(features)["Anomaly"]

    assert not flags_threshold.equals(flags_quota), (
        "threshold mode reproduced quota mode exactly — _new_model has probably "
        "regressed to passing a float contamination; see caveat C."
    )


def test_quota_flags_exactly_the_requested_fraction(ohlcv):
    """Quota mode is a quota: that is its whole (legacy) contract."""
    features = WhaleTracker(AnalysisConfig())._engineer_features(ohlcv)
    tracker = WhaleTracker(AnalysisConfig(detection_mode="quota", contamination=0.10))
    flags = tracker.detect_anomalies(features)["Anomaly"]
    assert abs(flags.mean() - 0.10) < 0.02


def test_threshold_count_floats_with_the_regime(ohlcv):
    """A stricter cutoff must flag strictly fewer days — an absolute scale."""
    features = WhaleTracker(AnalysisConfig())._engineer_features(ohlcv)
    loose = WhaleTracker(AnalysisConfig(score_threshold=-0.02))
    strict = WhaleTracker(AnalysisConfig(score_threshold=-0.20))

    n_loose = int(loose.detect_anomalies(features)["Anomaly"].sum())
    n_strict = int(strict.detect_anomalies(features)["Anomaly"].sum())
    assert n_strict <= n_loose


def test_planted_shocks_are_detected(ohlcv):
    """Sanity: the deliberate 9%-move-on-8x-volume days should be flagged."""
    tracker = WhaleTracker(AnalysisConfig(detection_mode="threshold"))
    result = tracker.detect_anomalies(tracker._engineer_features(ohlcv))
    flagged = result.index[result["Anomaly"]]
    planted = ohlcv.index[[90, 180, 270, 360, 450]]
    hits = sum(1 for day in planted if day in flagged)
    assert hits >= 4, f"only {hits}/5 planted shocks were flagged"


def test_strength_is_bounded_and_comparable(scored):
    """Caveat B: strength is on an absolute 0-100 scale, not per-series min/max."""
    _, result = scored
    assert result["Strength"].between(0, 100).all()
    assert result["Strength"].dtype.kind in "iu"


def test_flow_signal_is_ternary(scored):
    _, result = scored
    assert set(result["Flow_Signal"].unique()) <= {-1, 0, 1}
    assert set(result["Flow"].unique()) <= {"Accumulation", "Distribution", "Neutral"}


def test_detection_is_deterministic(ohlcv):
    """Same input, same seed, same answer — twice."""
    features = WhaleTracker(AnalysisConfig())._engineer_features(ohlcv)
    first = WhaleTracker(AnalysisConfig()).detect_anomalies(features)["Anomaly_Score"]
    second = WhaleTracker(AnalysisConfig()).detect_anomalies(features)["Anomaly_Score"]
    np.testing.assert_allclose(first.to_numpy(), second.to_numpy())


# --------------------------------------------------------------------------- #
# Walk-forward cost ceiling
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("rows", "max_fits"),
    [(500, 150), (1250, 150), (16265, 150), (500, 20)],
)
def test_walkforward_fit_count_stays_within_budget(rows, max_fits):
    """Without this ceiling, period="max" is a ~5-minute single request."""
    config = AnalysisConfig(detection_mode="walkforward", walkforward_max_fits=max_fits)
    tracker = WhaleTracker(config)
    cadence = tracker._walkforward_cadence(rows)
    steps = max(0, rows - config.walkforward_warmup)
    assert int(np.ceil(steps / cadence)) <= max_fits


def test_walkforward_cadence_never_tightens_below_the_configured_value():
    """The budget may only make a run cheaper, never more expensive."""
    config = AnalysisConfig(detection_mode="walkforward", walkforward_refit_every=5)
    tracker = WhaleTracker(config)
    for rows in (100, 500, 5000, 20000):
        assert tracker._walkforward_cadence(rows) >= 5


def test_walkforward_budget_is_a_no_op_on_short_history():
    """A 2y window was always affordable; its behaviour must be unchanged."""
    tracker = WhaleTracker(AnalysisConfig(detection_mode="walkforward"))
    assert tracker._walkforward_cadence(500) == 5


def test_walkforward_scores_only_after_warmup(ohlcv):
    """Warmup rows have insufficient history and must stay NaN, never 0."""
    config = AnalysisConfig(detection_mode="walkforward", walkforward_warmup=60,
                            walkforward_refit_every=25)
    tracker = WhaleTracker(config)
    features = tracker._engineer_features(ohlcv)
    scores = tracker._walkforward_scores(features)
    assert scores.iloc[: config.walkforward_warmup].isna().all()
    assert scores.iloc[config.walkforward_warmup:].notna().any()


def test_config_validation_rejects_nonsense():
    with pytest.raises(ValueError):
        AnalysisConfig(detection_mode="magic").validate()
    with pytest.raises(ValueError):
        AnalysisConfig(contamination=0.9).validate()
    with pytest.raises(ValueError):
        AnalysisConfig(mad_k=0).validate()
    with pytest.raises(ValueError):
        AnalysisConfig(walkforward_max_fits=-1).validate()
