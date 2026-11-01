"""Writing one market's measurement without destroying another's.

WHAT THIS PROTECTS

A stamped measurement is the only thing standing between a feature and
`PRODUCT.md` constraint 2. `patterns.py` scores nothing without one, `tape.py`
reports no direction without one, and the verdict panel's null result gets
LOUDER when one is missing. So silently deleting one does not break anything
visibly — it quietly turns a measured feature back into an unmeasured one, in
the direction of claiming the same while showing less.

That is not hypothetical. On 11 September 2026 `backtest_verdict.py --market US`
replaced the Indonesian measurement with a US-only artifact, printed "written
to ...", and exited zero. It was noticed by accident.
"""

from __future__ import annotations

import json

import pytest

from _lib import artifacts


@pytest.fixture
def artifact(tmp_path):
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps({
        "measuredOn": "2026-09-09",
        "alpha": 0.10,
        "markets": {
            "ID": {"measuredOn": "2026-09-09", "names": 250, "usable": True},
        },
    }))
    return path


def test_measuring_one_market_keeps_the_other(artifact):
    """The bug, stated as a test."""
    merged = artifacts.write_markets(
        artifact, {"markets": {"US": {"names": 120, "usable": False}}},
        today="2026-09-11")
    assert sorted(merged["markets"]) == ["ID", "US"]
    assert merged["markets"]["ID"]["names"] == 250
    assert json.loads(artifact.read_text())["markets"]["ID"]["names"] == 250


def test_a_carried_market_keeps_its_own_date(artifact):
    """Otherwise a two-week-old study inherits today's stamp from a run that
    never looked at it, and starts reporting itself as current."""
    merged = artifacts.write_markets(
        artifact, {"markets": {"US": {"names": 120}}}, today="2026-09-11")
    assert merged["markets"]["ID"]["measuredOn"] == "2026-09-09"
    assert merged["markets"]["US"]["measuredOn"] == "2026-09-11"
    assert merged["measuredOn"] == "2026-09-11"


def test_remeasuring_a_market_replaces_it_whole(artifact):
    """A re-measurement is the point. What must not happen is a half-study
    stitched onto half of an older one."""
    merged = artifacts.write_markets(
        artifact, {"markets": {"ID": {"names": 300}}}, today="2026-09-11")
    assert merged["markets"]["ID"] == {"names": 300, "measuredOn": "2026-09-11"}
    assert "usable" not in merged["markets"]["ID"]


def test_the_run_says_what_it_kept(artifact):
    merged = artifacts.write_markets(
        artifact, {"markets": {"US": {"names": 120}}}, today="2026-09-11")
    assert merged["measuredNow"] == ["US"]
    assert merged["carriedForward"] == ["ID"]
    note = artifacts.note(merged)
    assert "measured US" in note and "ID" in note


def test_measuring_every_market_carries_nothing_forward(artifact):
    merged = artifacts.write_markets(
        artifact, {"markets": {"ID": {"names": 1}, "US": {"names": 2}}},
        today="2026-09-11")
    assert merged["carriedForward"] == []
    assert "kept" not in artifacts.note(merged)


def test_top_level_fields_from_the_new_run_win(artifact):
    """Constants like the alpha or the window belong to the code that just ran,
    not to whatever wrote the file last."""
    merged = artifacts.write_markets(
        artifact, {"alpha": 0.05, "markets": {"US": {"names": 1}}},
        today="2026-09-11")
    assert merged["alpha"] == 0.05


def test_a_missing_artifact_is_written_rather_than_refused(tmp_path):
    path = tmp_path / "new.json"
    merged = artifacts.write_markets(
        path, {"markets": {"ID": {"names": 5}}}, today="2026-09-11")
    assert merged["markets"]["ID"]["names"] == 5
    assert merged["carriedForward"] == []
    assert path.exists()


def test_an_unreadable_artifact_does_not_strand_the_measurement(tmp_path):
    """Refusing to write would lose a ten-minute run to a corrupt byte."""
    path = tmp_path / "broken.json"
    path.write_text("{not json at all")
    merged = artifacts.write_markets(
        path, {"markets": {"ID": {"names": 5}}}, today="2026-09-11")
    assert merged["markets"]["ID"]["names"] == 5


def test_the_shipped_artifacts_all_still_carry_every_market_measured():
    """A guard on the real files: if a future run drops a market, this fails."""
    from _lib import patterns, tape, verdict, volumeprofile
    assert tape.calibration_for("ID") and tape.calibration_for("US")
    assert patterns.calibration_for("ID") and patterns.calibration_for("US")
    assert volumeprofile.calibration_for("ID")
    for market in ("ID", "US"):
        assert verdict.blend_validation(market).get("available") is not None
