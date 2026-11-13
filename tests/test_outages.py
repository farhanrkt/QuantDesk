"""A provider outage is reported as one, and the edge does not keep it.

WHY THIS EXISTS

In the November 2026 analysis the market-data provider was unreachable, which
is exactly what a Yahoo throttle or IP ban looks like to this app. Every lens
then told the reader their SYMBOL was wrong — "No data found for 'AAPL'.
Non-US listings need their exchange suffix" — inside an HTTP 200 carrying
`s-maxage=60, stale-while-revalidate=300`, so the edge would have served that
to every reader of the URL for up to six minutes after the provider recovered.
An empty ranking (0 of 30 names) and a failed headline feed went out the same
way, and the stock page's news panel called a feed it could not read "no
recent headlines".

These tests hold the four repairs: the benchmark index decides whether a
failure is the symbol's or the provider's; a transient failure is held for
seconds rather than minutes; a feed that could not be read says so; and a
quoted error is shortened at a word, not through one.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import index
from _lib import explain, market_data, news


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    index._RATE_HITS.clear()
    market_data._CANARY_CACHE.clear()

    # US headlines ask Yahoo's search before the feed these tests plant. Without
    # this, a runner that can reach Yahoo reads live headlines instead, and a
    # feed planted to fail is never asked.
    def no_yahoo(query, count=8):
        raise OSError("offline")
    monkeypatch.setattr(market_data, "news_search", no_yahoo)
    yield
    index._RATE_HITS.clear()
    market_data._CANARY_CACHE.clear()


@pytest.fixture
def client():
    return TestClient(index.app)


SYMBOL_BLAME = ("No data found for 'AAPL'. Non-US listings need their exchange suffix — "
                "Indonesian tickers end in .JK. Crypto takes a pair, such as BTC-USD.")


def _every_provider_leg_fails(monkeypatch, detail=SYMBOL_BLAME):
    def fail(*_args, **_kwargs):
        raise HTTPException(status_code=404, detail=detail)
    for name in ("whale_payload", "technical_payload", "valuation_payload",
                 "quality_payload", "company_payload"):
        monkeypatch.setattr(index, name, fail)
    monkeypatch.setattr(index.news, "fetch_news", lambda *a, **k: [])


# --------------------------------------------------------------------------- #
# The symbol's fault, or the provider's
# --------------------------------------------------------------------------- #
def test_an_outage_is_named_as_one_and_held_for_seconds(client, monkeypatch):
    _every_provider_leg_fails(monkeypatch)
    monkeypatch.setattr(index.market_data, "provider_answering", lambda market: False)
    response = client.get("/api/confluence", params={"ticker": "AAPL"})
    assert response.status_code == 200
    body = response.json()
    assert body["providerAnswering"] is False
    for leg in ("anomaly", "technical", "valuation", "quality", "company"):
        assert body[leg]["ok"] is False
        assert "not a problem with the symbol" in body[leg]["error"]
        assert "exchange suffix" not in body[leg]["error"]
    # The headlines come from a different provider and keep their own answer.
    assert body["news"]["ok"] is True
    assert response.headers["cache-control"] == index.CACHE_FAILED
    assert response.headers["cdn-cache-control"] == index.CDN_CACHE_FAILED
    assert "stale-while-revalidate" not in response.headers["cdn-cache-control"]


def test_a_symbol_that_does_not_exist_keeps_its_hint_and_its_cache(client, monkeypatch):
    """The provider answers the benchmark, so the failure IS about the symbol —
    a deterministic answer the edge may keep like any other."""
    _every_provider_leg_fails(monkeypatch)
    monkeypatch.setattr(index.market_data, "provider_answering", lambda market: True)
    response = client.get("/api/confluence", params={"ticker": "AAPL"})
    body = response.json()
    assert body["providerAnswering"] is True
    assert "exchange suffix" in body["anomaly"]["error"]
    assert response.headers["cache-control"] == index.CACHE


def test_the_benchmark_is_only_asked_when_both_price_legs_failed(client, monkeypatch):
    calls = []
    monkeypatch.setattr(index.market_data, "provider_answering",
                        lambda market: calls.append(market) or True)
    monkeypatch.setattr(index, "whale_payload", lambda *a, **k: {"stub": "anomaly"})
    monkeypatch.setattr(index.technical, "analyze", lambda *a, **k: {"stub": "technical"})
    monkeypatch.setattr(index.valuation, "analyze", lambda *a, **k: {"stub": "valuation"})
    monkeypatch.setattr(index.news, "fetch_news", lambda *a, **k: [])
    client.get("/api/confluence", params={"ticker": "FAKE"})
    assert calls == []


def test_a_throttled_company_fetch_is_transient(client, monkeypatch):
    """No sector is the throttle's signature, and it clears in minutes."""
    monkeypatch.setattr(index, "whale_payload", lambda *a, **k: {"stub": "anomaly"})
    monkeypatch.setattr(index.technical, "analyze", lambda *a, **k: {"stub": "technical"})
    monkeypatch.setattr(index.news, "fetch_news", lambda *a, **k: [])

    def throttled(*_args, **_kwargs):
        raise index.valuation.ValuationError("No sector came back.", cause="unknown-sector")

    monkeypatch.setattr(index.valuation, "analyze", throttled)
    response = client.get("/api/confluence", params={"ticker": "FAKE"})
    assert response.json()["valuation"]["error"]["cause"] == "unknown-sector"
    assert response.headers["cache-control"] == index.CACHE_FAILED


def test_the_canary_is_held_for_a_minute_either_way(monkeypatch):
    calls = []
    monkeypatch.setattr(market_data, "last_close",
                        lambda symbol, period="5d": calls.append(symbol))
    assert market_data.provider_answering("US") is False
    assert market_data.provider_answering("US") is False
    assert calls == ["^GSPC"]
    monkeypatch.setattr(market_data, "last_close", lambda symbol, period="5d": 7000.0)
    assert market_data.provider_answering("ID") is True       # its own index, its own entry


def test_the_outage_message_names_the_market_it_asked():
    assert "Jakarta Composite" in market_data.provider_outage_message("BBCA.JK")
    assert "S&P 500" in market_data.provider_outage_message("AAPL")


# --------------------------------------------------------------------------- #
# Empty scans are failures, not answers
# --------------------------------------------------------------------------- #
def test_a_ranking_that_ranked_nothing_is_not_kept(client, monkeypatch):
    monkeypatch.setattr(index.ranking, "scan", lambda symbols, market_code="US": {
        "rows": [], "ranked": 0, "missing": list(symbols), "signals": [], "correlation": None})
    monkeypatch.setattr(index.ranking, "validation", lambda universe: None)
    monkeypatch.setattr(index.explain, "for_ranking", lambda result: {})
    response = client.get("/api/rank", params={"tickers": "AAA,BBB"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == index.CACHE_FAILED


def test_a_headline_feed_that_failed_is_held_for_seconds(client, monkeypatch):
    def broken(url):
        raise OSError("timed out")
    monkeypatch.setattr(news, "_fetch_feed", broken)
    failed = client.get("/api/markets/headlines", params={"topics": "oil"})
    assert failed.headers["cache-control"] == index.CACHE_FAILED

    index._RATE_HITS.clear()
    monkeypatch.setattr(news, "_fetch_feed", lambda url: b"<rss><channel></channel></rss>")
    fine = client.get("/api/markets/headlines", params={"topics": "oil"})
    assert fine.headers["cache-control"] == index.HEADLINES_CACHE


# --------------------------------------------------------------------------- #
# A feed that could not be read is not "no news"
# --------------------------------------------------------------------------- #
def test_the_stock_page_feed_failure_reaches_the_panel_as_a_failure(client, monkeypatch):
    def broken(url):
        raise OSError("timed out")
    monkeypatch.setattr(news, "_fetch_feed", broken)
    monkeypatch.setattr(index, "whale_payload", lambda *a, **k: {"stub": "anomaly"})
    monkeypatch.setattr(index.technical, "analyze", lambda *a, **k: {"stub": "technical"})
    monkeypatch.setattr(index.valuation, "analyze", lambda *a, **k: {"stub": "valuation"})
    body = client.get("/api/confluence", params={"ticker": "FAKE"}).json()
    assert body["news"] == {"ok": False, "error": news.NEWS_UNAVAILABLE}

    index._RATE_HITS.clear()
    response = client.get("/api/news", params={"ticker": "FAKE"})
    assert response.status_code == 502
    assert response.json()["detail"] == news.NEWS_UNAVAILABLE


def test_the_lenient_reader_still_degrades_to_an_empty_list(monkeypatch):
    def broken(url):
        raise OSError("timed out")
    monkeypatch.setattr(news, "_fetch_feed", broken)
    assert news.fetch_news("FAKE") == []
    with pytest.raises(news.NewsUnavailable):
        news.fetch_news("FAKE", strict=True)


def test_a_link_that_is_not_https_never_becomes_an_anchor(monkeypatch):
    feed = (b"<rss><channel>"
            b"<item><title>Safe</title><link>https://example.com/a</link></item>"
            b"<item><title>Script</title><link>javascript:alert(1)</link></item>"
            b"<item><title>Plain</title><link>http://example.com/b</link></item>"
            b"</channel></rss>")
    monkeypatch.setattr(news, "_fetch_feed", lambda url: feed)
    assert [item["title"] for item in news.fetch_news("FAKE")] == ["Safe"]


# --------------------------------------------------------------------------- #
# A quoted error is shortened at a word
# --------------------------------------------------------------------------- #
def test_a_long_message_is_cut_at_a_sentence_or_a_word():
    message = ("No sector or industry came back for AAPL, so there is no way to tell whether "
               "it is a bank, and a bank cannot be valued on free cash flow. This is the "
               "signature of a throttled fetch rather than a company with no sector, and "
               "running the lenses again in a couple of minutes will usually resolve it.")
    clipped = explain._clip(message)
    assert clipped.endswith("free cash flow.")
    words = message.split()
    no_stop = " ".join(words[:60])
    clipped = explain._clip(no_stop.replace(".", ""), limit=80)
    assert clipped.endswith("…")
    assert clipped[:-1].split()[-1] in no_stop.replace(".", "").split()   # a whole word
    assert explain._clip("short") == "short"
