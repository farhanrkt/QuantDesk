"""Pruning the scan cache, which is the one thing here that deletes files.

A full-market sweep leaves about 500MB of cached lens payloads behind per day,
and the cache is keyed by day so none of yesterday's is ever read again. Left
alone it fills the disk in about a month. Pruning it is therefore necessary and
is also the only destructive operation in this codebase, so it gets tests that
are specifically about what it must NOT delete.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def scan(tmp_path, monkeypatch):
    """`scan_market` with its cache pointed at a temporary directory."""
    sys.path.insert(0, str(ROOT / "api"))
    spec = importlib.util.spec_from_file_location(
        "scan_market_under_test", ROOT / "scripts" / "scan_market.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "CACHE_DIR", tmp_path)
    return module


def day(scan, name: str, files: int = 2) -> Path:
    target = Path(scan.CACHE_DIR) / name
    target.mkdir(parents=True, exist_ok=True)
    for index in range(files):
        (target / f"SYM{index}.json").write_text("{}")
    return target


def test_it_keeps_the_most_recent_days_and_drops_the_rest(scan):
    for name in ("2026-09-05", "2026-09-06", "2026-09-07", "2026-09-08",
                 "2026-09-09", "2026-09-12"):
        day(scan, name)
    removed = scan.prune_cache(keep=3, today="2026-09-12")
    assert sorted(removed) == ["2026-09-05", "2026-09-06", "2026-09-07"]
    survivors = sorted(p.name for p in Path(scan.CACHE_DIR).iterdir())
    assert survivors == ["2026-09-08", "2026-09-09", "2026-09-12"]


def test_today_is_never_deleted_even_when_keep_is_small(scan):
    """The run that prunes is about to write into today's directory."""
    for name in ("2026-09-10", "2026-09-11", "2026-09-12"):
        day(scan, name)
    scan.prune_cache(keep=1, today="2026-09-12")
    assert (Path(scan.CACHE_DIR) / "2026-09-12").exists()


def test_it_never_touches_anything_that_is_not_a_date(scan):
    """A stray directory in here is somebody's. Deleting it silently would be
    worse than leaving it."""
    day(scan, "2026-09-01")
    day(scan, "2026-09-02")
    day(scan, "2026-09-12")
    (Path(scan.CACHE_DIR) / "notes").mkdir()
    (Path(scan.CACHE_DIR) / "notes" / "keep.txt").write_text("mine")
    (Path(scan.CACHE_DIR) / "loose.json").write_text("{}")

    scan.prune_cache(keep=1, today="2026-09-12")
    assert (Path(scan.CACHE_DIR) / "notes" / "keep.txt").read_text() == "mine"
    assert (Path(scan.CACHE_DIR) / "loose.json").exists()


def test_nothing_stale_deletes_nothing(scan):
    day(scan, "2026-09-12")
    assert scan.prune_cache(keep=4, today="2026-09-12") == []


def test_a_missing_cache_directory_is_not_an_error(scan, tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "CACHE_DIR", tmp_path / "never-created")
    assert scan.prune_cache(keep=2, today="2026-09-12") == []


# --------------------------------------------------------------------------- #
# The one leg that costs nothing to fetch, and therefore must not go stale
#
# A full 771-name Indonesian sweep came back with every net-debt figure null.
# Nothing had failed: the leg payloads had been written an hour before the
# borrowings reading existed, and `deepen` served them unchanged because a cache
# hit is a cache hit. Every OTHER leg is a network fetch and is right to be
# served as written; this one reads a company record already on disk, so the
# right answer is to rebuild it rather than reserve two hours of provider quota
# re-downloading filings that have not changed.
# --------------------------------------------------------------------------- #
def test_a_stale_free_leg_is_rebuilt_and_nothing_else_is(scan, monkeypatch):
    rebuilt = {"version": scan.PROFILE_LEG_VERSION, "available": True,
               "profile": {"industry": "Cable"}}
    monkeypatch.setattr(scan, "read_profile", lambda symbol: rebuilt)

    legs = {
        "valuation": {"ok": True, "data": {"expensive": "network"}},
        "profile": {"ok": True, "data": {"version": 1, "available": True,
                                         "profile": {"industry": "Cable"}}},
    }
    assert scan.refresh_free_legs("K.JK", legs) is True
    assert legs["profile"]["data"] == rebuilt
    # The fetched legs are untouched: re-running them is a day of quota.
    assert legs["valuation"] == {"ok": True, "data": {"expensive": "network"}}


def test_a_current_free_leg_is_left_alone(scan, monkeypatch):
    monkeypatch.setattr(scan, "read_profile",
                        lambda symbol: pytest.fail("should not recompute"))
    legs = {"profile": {"ok": True,
                        "data": {"version": scan.PROFILE_LEG_VERSION,
                                 "available": True}}}
    assert scan.refresh_free_legs("K.JK", legs) is False


def test_a_leg_set_written_before_versions_existed_is_rebuilt(scan, monkeypatch):
    """No version at all is the oldest shape, and the commonest one on disk.

    The rebuild has to KNOW something for it to be taken — see
    `test_a_rebuild_that_knows_less_is_discarded` for why.
    """
    rebuilt = {"version": scan.PROFILE_LEG_VERSION, "available": True,
               "profile": {"industry": "Cable"}}
    monkeypatch.setattr(scan, "read_profile", lambda symbol: rebuilt)
    legs = {"profile": {"ok": True, "data": {"available": True}}}
    assert scan.refresh_free_legs("K.JK", legs) is True
    assert legs["profile"]["data"] == rebuilt


def test_a_missing_profile_leg_is_rebuilt_rather_than_skipped(scan, monkeypatch):
    monkeypatch.setattr(scan, "read_profile",
                        lambda symbol: {"version": scan.PROFILE_LEG_VERSION,
                                        "available": True})
    legs = {"valuation": {"ok": True, "data": {}}}
    assert scan.refresh_free_legs("K.JK", legs) is True
    assert legs["profile"]["data"]["version"] == scan.PROFILE_LEG_VERSION


def test_a_rebuild_that_knows_less_is_discarded(scan, monkeypatch):
    """The bug that emptied a 771-name report, as a test.

    `read_profile` reads the fundamentals cache and returns a stated gap when
    the record is not there. On the night the calendar rolled over, a
    `--fundamentals-days 1` run found every record one day old and expired, so
    the rebuild came back unavailable for every name — and the first version of
    `refresh_free_legs` wrote that over 771 good payloads and saved it. Nothing
    failed and nothing was reported; the next report simply had no business
    descriptions and an empty shortlist.

    A cache holds what was expensive to learn. Replacing that with "I could not
    find out" is the one thing it must never do.
    """
    monkeypatch.setattr(scan, "read_profile",
                        lambda symbol: {"version": scan.PROFILE_LEG_VERSION,
                                        "available": False,
                                        "reason": "the record was not in hand"})
    good = {"version": 1, "available": True, "profile": {"industry": "Cable"}}
    legs = {"profile": {"ok": True, "data": good}}

    assert scan.refresh_free_legs("K.JK", legs) is False
    assert legs["profile"]["data"] == good        # stale and true, not fresh and empty


def test_a_rebuild_is_taken_when_the_cached_leg_was_itself_a_gap(scan, monkeypatch):
    """Nothing is lost by replacing a gap with a gap, or with an answer."""
    fresh = {"version": scan.PROFILE_LEG_VERSION, "available": True,
             "profile": {"industry": "Cable"}}
    monkeypatch.setattr(scan, "read_profile", lambda symbol: fresh)
    legs = {"profile": {"ok": True, "data": {"version": 1, "available": False}}}
    assert scan.refresh_free_legs("K.JK", legs) is True
    assert legs["profile"]["data"] == fresh
