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
