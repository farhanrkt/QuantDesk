"""The command palette's symbol finder, against planted listing files.

Planted rather than read from the committed files so the ordering rules are
tested against a ground truth this file controls: which name should come first,
and why, is written down here beside the data it is about.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import index
from _lib import listings

US = {
    "market": "US", "asOf": "2026-09-11", "count": 4,
    "rows": [  # file order is market cap, largest first
        {"symbol": "AAPL", "name": "Apple Inc.", "marketCap": 3.1e12, "exchange": "NasdaqGS"},
        {"symbol": "BBCA", "name": "JPMorgan BetaBuilders Canada ETF", "marketCap": 8e9},
        {"symbol": "APLE", "name": "Apple Hospitality REIT, Inc.", "marketCap": 3.5e9},
        {"symbol": "BBCAX", "name": "Some Fund", "marketCap": 1e8},
    ],
}
ID = {
    "market": "ID", "asOf": "2026-09-08", "count": 2,
    "rows": [
        # Rupiah. Compared with the dollar figures above it would outrank
        # everything — which is the bug the ordering must never commit.
        {"symbol": "BBCA.JK", "name": "PT Bank Central Asia Tbk", "marketCap": 8.2e14,
         "exchange": "Jakarta"},
        {"symbol": "TLKM.JK", "name": "PT Telkom Indonesia (Persero) Tbk", "marketCap": 2.9e14},
    ],
}


@pytest.fixture(autouse=True)
def planted(monkeypatch):
    monkeypatch.setattr(listings, "_CACHE", {"US": US, "ID": ID})
    index._RATE_HITS.clear()
    yield
    index._RATE_HITS.clear()


def symbols(rows):
    return [r["symbol"] for r in rows]


def test_an_exact_code_beats_a_prefix_beats_a_name():
    rows = listings.search("bbca")
    assert symbols(rows)[:2] == ["BBCA", "BBCA.JK"], "the bare code matches both listings exactly"
    assert symbols(rows)[2] == "BBCAX", "a symbol prefix comes after the exact matches"


def test_across_markets_the_callers_own_market_wins_a_tie():
    assert symbols(listings.search("BBCA", "ID"))[:2] == ["BBCA.JK", "BBCA"]
    assert symbols(listings.search("BBCA", "US"))[:2] == ["BBCA", "BBCA.JK"]


def test_market_cap_is_never_compared_across_currencies():
    # Both match on a name word. File order within each market decides, and the
    # Indonesian rupiah figure (10^14) must not lift it above the US names.
    rows = listings.search("apple", "US")
    assert symbols(rows) == ["AAPL", "APLE"]


def test_a_name_matches_at_a_word_boundary_across_words():
    assert symbols(listings.search("bank central")) == ["BBCA.JK"]
    assert symbols(listings.search("telkom")) == ["TLKM.JK"]


def test_a_short_fragment_inside_a_word_does_not_match():
    # "pl" is inside "Apple" but starts no word; two letters anywhere in any
    # name would return half the market.
    assert listings.search("pl") == []


def test_empty_and_limits():
    assert listings.search("") == []
    assert listings.search("   ") == []
    assert len(listings.search("a", limit=1)) == 1
    assert len(listings.search("a", limit=999)) <= listings.SEARCH_MAX


def test_each_row_says_how_it_matched_and_where_it_lists():
    row = listings.search("AAPL")[0]
    assert row == {"symbol": "AAPL", "name": "Apple Inc.", "market": "US",
                   "exchange": "NasdaqGS", "match": "symbol"}


def test_the_finder_never_reaches_the_provider(monkeypatch):
    from _lib import market_data

    def boom(*_a, **_k):
        raise AssertionError("listings.search must not fetch")
    monkeypatch.setattr(market_data, "company", boom)
    monkeypatch.setattr(market_data, "ohlcv", boom)
    assert listings.search("apple")


# --------------------------------------------------------------------------- #
# The route
# --------------------------------------------------------------------------- #
@pytest.fixture
def client():
    return TestClient(index.app)


def test_route_returns_results_and_how_old_the_files_are(client):
    body = client.get("/api/symbols", params={"q": "tlkm", "market": "ID"}).json()
    assert symbols(body["results"]) == ["TLKM.JK"]
    assert body["listings"]["ID"] == {"asOf": "2026-09-08", "count": 2}
    assert "type a full symbol" in body["note"]


@pytest.mark.parametrize("bad", ["", "<script>", "a" * 41, "AAPL\r\nX: 1", "../etc"])
def test_route_rejects_hostile_queries(client, bad):
    assert client.get("/api/symbols", params={"q": bad}).status_code == 422


def test_route_is_cached_at_the_edge_for_a_day(client):
    response = client.get("/api/symbols", params={"q": "aapl"})
    assert "s-maxage=86400" in response.headers["cache-control"]


def test_route_allows_typing_speed_but_is_still_limited():
    limit, window = index.RATE_LIMITS["/api/symbols"]
    default, _ = index.RATE_LIMITS[None]
    assert limit > default, "a palette search per keystroke must not hit the default cap"
    assert window == 60
