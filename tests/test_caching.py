"""Which answers the edge may serve stale when the function fails, and which not."""

from __future__ import annotations

from fastapi.testclient import TestClient

import index


def test_self_dating_answers_may_be_served_stale_on_error():
    for header in (index.BOARD_CDN_CACHE, index.HEADLINES_CDN_CACHE, index.CALENDAR_CDN_CACHE,
                   index.SYMBOLS_CACHE):
        assert "stale-if-error=" in header, header


def test_a_company_read_is_never_served_stale_on_error():
    # The page labels a company read with the time the browser fetched it, so
    # a stale copy would read as fresh.
    for header in (index.CACHE, index.CDN_CACHE, index.CACHE_FAILED, index.CDN_CACHE_FAILED):
        assert "stale-if-error" not in header, header


def test_the_routes_send_what_the_constants_say():
    index._RATE_HITS.clear()
    with TestClient(index.app) as client:
        assert "stale-if-error" in client.get("/api/markets/calendar").headers["CDN-Cache-Control"]
        assert "stale-if-error" in client.get("/api/symbols", params={"q": "bca"}).headers["Cache-Control"]
    index._RATE_HITS.clear()
