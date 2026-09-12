"""Fundamentals kept across days, and the two things that must never be.

WHY THIS CACHE EXISTS
A whole-market sweep of the 9,997 US listings is about twelve hours at the rate
the provider tolerates, so it cannot finish inside a day — and the scan's own
cache is keyed by calendar day, so every run threw away the statements the last
one paid for. Filings move quarterly; refetching them daily is the waste that
made a full sweep impossible rather than merely slow.

WHAT THESE TESTS PROTECT
1. THE PRICE IS NEVER SERVED FROM THE CACHE. A valuation is a comparison between
   a model and today's price. A week-old price against fresh statements would
   move every verdict in the report with nothing saying so.
2. THE FX RATE IS NEVER SERVED FROM THE CACHE. Thirteen of the forty-six names
   in the IDX30 and LQ45 report in dollars and trade in rupiah. The disk holds
   unconverted statements and the rate is re-applied on every hit.
3. IT IS OFF UNLESS ASKED FOR. The deployed app is serverless with no persistent
   disk; a cache that silently does nothing is worse than no cache.
4. A BAD RECORD IS A MISS, NOT A WRONG ANSWER. The cost of a miss is one
   refetch; the cost of trusting a truncated file is a wrong valuation.
"""

from __future__ import annotations

import datetime as dt
import pickle

import numpy as np
import pandas as pd
import pytest

from _lib import market_data as MD


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(MD, "FUNDAMENTALS_DIR", tmp_path)
    monkeypatch.setenv("QUANTDESK_FUNDAMENTALS_TTL_DAYS", "7")
    MD._COMPANY_CACHE.clear()
    MD._REGISTER_CACHE.clear()
    return tmp_path


def statements() -> dict:
    return {
        "ok": True, "name": "Test Co", "sector": "Energy", "industry": "Oil",
        "price": 100.0, "shares": 1e9, "currency": "IDR",
        "financial_currency": "USD", "market_cap": 1e11,
        "income": pd.DataFrame({"Revenue": [1.0]}),
        "balance": pd.DataFrame({"Assets": [2.0]}),
        "cashflow": pd.DataFrame({"Ops": [3.0]}),
        "fx_rate": None,
    }


def bars(close: float) -> pd.DataFrame:
    index = pd.bdate_range("2026-09-01", periods=3)
    return pd.DataFrame({"Open": close, "High": close, "Low": close,
                         "Close": close, "Volume": 1.0}, index=index)


# ============================================================================ #
# 1 & 2. What is re-derived rather than served
# ============================================================================ #
def test_a_cache_hit_refetches_the_price(cache, monkeypatch):
    calls: list = []

    def fetch(ticker, convert=True):
        calls.append(ticker)
        return statements()

    monkeypatch.setattr(MD, "_company_uncached", fetch)
    monkeypatch.setattr(MD, "ohlcv", lambda *a, **k: bars(250.0))
    monkeypatch.setattr(MD, "fx_rate", lambda *a: None)

    # On a MISS the price comes from the fetch itself, which in the real
    # `_company_uncached` reads the last daily bar. `_refresh_price` exists only
    # for the hit path, where the statements come off the disk and the price
    # cannot.
    first = MD.company("TEST")
    assert calls == ["TEST"]
    assert first["price"] == pytest.approx(100.0)

    MD._COMPANY_CACHE.clear()                 # a new day, same disk
    monkeypatch.setattr(MD, "ohlcv", lambda *a, **k: bars(310.0))
    second = MD.company("TEST")

    assert calls == ["TEST"], "the statements were refetched"
    assert second["price"] == pytest.approx(310.0), "a stale price was served"
    assert second["price_source"] == "last daily close"
    assert second["income"]["Revenue"].iloc[0] == 1.0, "statements did not survive"


def test_market_cap_is_recomputed_rather_than_carried(cache, monkeypatch):
    """Yahoo's figure was quoted against the price on the day it was written."""
    monkeypatch.setattr(MD, "_company_uncached", lambda t, convert=True: statements())
    monkeypatch.setattr(MD, "ohlcv", lambda *a, **k: bars(100.0))
    monkeypatch.setattr(MD, "fx_rate", lambda *a: None)
    MD.company("TEST")

    MD._COMPANY_CACHE.clear()
    monkeypatch.setattr(MD, "ohlcv", lambda *a, **k: bars(200.0))
    again = MD.company("TEST")
    assert again["market_cap"] == pytest.approx(200.0 * 1e9)


def test_the_fx_rate_is_reapplied_at_todays_rate_not_the_cached_one(cache, monkeypatch):
    monkeypatch.setattr(MD, "_company_uncached", lambda t, convert=True: statements())
    monkeypatch.setattr(MD, "ohlcv", lambda *a, **k: bars(100.0))

    monkeypatch.setattr(MD, "fx_rate", lambda *a: 16_000.0)
    first = MD.company("TEST")
    assert first["fx_rate"] == pytest.approx(16_000.0)
    assert first["income"]["Revenue"].iloc[0] == pytest.approx(16_000.0)

    MD._COMPANY_CACHE.clear()
    monkeypatch.setattr(MD, "fx_rate", lambda *a: 17_000.0)
    second = MD.company("TEST")
    assert second["fx_rate"] == pytest.approx(17_000.0), "a week-old rate was reused"
    assert second["income"]["Revenue"].iloc[0] == pytest.approx(17_000.0), \
        "the cache stored converted statements and double-converted them"


# ============================================================================ #
# 3. Off unless asked for
# ============================================================================ #
def test_it_is_disabled_without_the_environment_variable(tmp_path, monkeypatch):
    monkeypatch.setattr(MD, "FUNDAMENTALS_DIR", tmp_path)
    monkeypatch.delenv("QUANTDESK_FUNDAMENTALS_TTL_DAYS", raising=False)
    assert MD.fundamentals_ttl() == 0
    MD._fundamentals_store("company", "TEST", {"ok": True})
    assert MD._fundamentals_load("company", "TEST") is None
    assert not any(tmp_path.rglob("*.pickle"))


@pytest.mark.parametrize("value", ["0", "not-a-number", "-3"])
def test_a_bad_or_zero_ttl_disables_it(tmp_path, monkeypatch, value):
    monkeypatch.setattr(MD, "FUNDAMENTALS_DIR", tmp_path)
    monkeypatch.setenv("QUANTDESK_FUNDAMENTALS_TTL_DAYS", value)
    assert MD.fundamentals_ttl() == 0


# ============================================================================ #
# 4. A bad record is a miss
# ============================================================================ #
def test_a_record_past_its_ttl_is_a_miss(cache):
    MD._fundamentals_store("company", "TEST", {"ok": True})
    path = MD._fundamentals_path("company", "TEST")
    stale = (dt.date.today() - dt.timedelta(days=9)).isoformat()
    with path.open("wb") as handle:
        pickle.dump({"fetchedOn": stale, "payload": {"ok": True}}, handle)
    assert MD._fundamentals_load("company", "TEST") is None


def test_a_record_inside_its_ttl_is_a_hit(cache):
    MD._fundamentals_store("company", "TEST", {"ok": True, "name": "kept"})
    assert MD._fundamentals_load("company", "TEST")["name"] == "kept"


def test_a_truncated_record_is_a_miss_rather_than_a_crash(cache):
    path = MD._fundamentals_path("company", "TEST")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x80\x04 not a pickle")
    assert MD._fundamentals_load("company", "TEST") is None


def test_a_record_from_an_older_layout_is_a_miss(cache):
    path = MD._fundamentals_path("company", "TEST")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump({"no-fetchedOn-key": True}, handle)
    assert MD._fundamentals_load("company", "TEST") is None


def test_an_unwritable_cache_never_breaks_the_fetch(cache, monkeypatch):
    """A full disk is not a reason to fail a scan."""
    monkeypatch.setattr(MD, "FUNDAMENTALS_DIR", cache / "file-not-a-dir")
    (cache / "file-not-a-dir").write_text("in the way")
    MD._fundamentals_store("company", "TEST", {"ok": True})   # must not raise
    assert MD._fundamentals_load("company", "TEST") is None


# ============================================================================ #
# The register, which carries no price at all
# ============================================================================ #
def test_the_register_is_served_whole_because_nothing_in_it_moves_daily(cache,
                                                                        monkeypatch):
    calls: list = []

    def fetch(ticker):
        calls.append(ticker)
        return {"ok": True, "insidersPercentHeld": 0.4, "shareCount": [1, 2, 3]}

    monkeypatch.setattr(MD, "_register_uncached", fetch)
    assert MD.share_register("TEST")["insidersPercentHeld"] == 0.4
    MD._REGISTER_CACHE.clear()
    again = MD.share_register("TEST")
    assert calls == ["TEST"], "the register was refetched"
    assert again["shareCount"] == [1, 2, 3]


def test_symbols_with_awkward_characters_get_their_own_file(cache):
    MD._fundamentals_store("company", "BRK.B", {"ok": True, "name": "b"})
    MD._fundamentals_store("company", "BRK-B", {"ok": True, "name": "dash"})
    assert MD._fundamentals_load("company", "BRK.B")["name"] == "b"
    assert MD._fundamentals_load("company", "BRK-B")["name"] == "dash"
    assert np.isfinite(1.0)
