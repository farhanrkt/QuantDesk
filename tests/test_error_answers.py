"""What a reader is told when a request is wrong or a lens breaks.

WHY THIS EXISTS

Two answers reached a reader in the framework's or Python's own words
(docs/AUDIT.md, SEC-3 and SEC-5):

  * a request that failed validation got FastAPI's default: a list of
    objects, in English whatever language was asked for, each carrying the
    rejected input whole. The page could not read it either — it drew a blank
    card. And nothing bounded one item of a list, so a 50,000-character
    "symbol" was echoed back in a 50 KB error;
  * a lens that raised something unplanned returned
    `f"{type(exc).__name__}: {exc}"`, a Python exception with whatever path or
    value its message held.

Both are now a sentence, in the reader's language, that names what went
wrong without repeating it.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

import index


@pytest.fixture
def client():
    index._RATE_HITS.clear()
    return TestClient(index.app)


def test_a_malformed_ticker_is_answered_in_a_sentence(client):
    response = client.get("/api/confluence", params={"ticker": "bad/one"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str), "the page reads a string; it drew a list as a blank card"
    assert "`ticker`" in detail
    assert "bad/one" not in detail


def test_the_sentence_is_in_the_readers_language(client):
    response = client.get("/api/confluence", params={"ticker": "bad/one", "lang": "id"})
    assert response.json()["detail"].startswith("Permintaan ini tidak bisa dibaca")


def test_rejected_input_is_never_echoed_at_length(client):
    huge = "A" * 50_000 + "/"
    for body in ({"tickers": [huge]}, {"tickers": ["X" * 30 + "/"] * 3}):
        response = client.post("/api/rank/list", json=body)
        assert response.status_code in (400, 422)
        assert len(response.text) < 400, f"{len(response.text)} bytes for a rejected symbol"
        assert huge not in response.text


def test_a_rejected_symbol_is_named_but_cut_short(client):
    response = client.post("/api/rank/list", json={"tickers": ["AB/C", "Y" * 30 + "/"]})
    detail = response.json()["detail"]
    assert "AB/C" in detail
    assert "Y" * 30 not in detail


def test_a_lens_that_breaks_says_so_in_words_and_logs_the_cause(client, monkeypatch, caplog):
    for name in ("whale_payload", "technical_payload", "valuation_payload",
                 "news_payload", "company_payload"):
        monkeypatch.setattr(index, name, lambda *a, **k: {"planted": True})

    def boom(symbol):
        raise RuntimeError("planted: /var/task/api/_lib/secret_path.py line 12")
    monkeypatch.setattr(index, "quality_payload", boom)
    monkeypatch.setattr(index.market_data, "provider_answering", lambda market: True)

    with caplog.at_level(logging.ERROR, logger="quantdesk"):
        body = client.get("/api/confluence", params={"ticker": "AAPL", "lang": "id"}).json()

    error = body["quality"]["error"]
    assert error["cause"] == "internal"
    assert "RuntimeError" not in str(error) and "secret_path" not in str(error)
    assert error["message"].startswith("Ada yang salah di dalam lensa ini")
    assert any("secret_path" in str(record.exc_info) for record in caplog.records), \
        "the cause belongs in the log, where someone can fix it"


# --------------------------------------------------------------------------- #
# The API's own headers (docs/AUDIT.md, SEC-7)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path, params", [
    ("/api/health", {}),
    ("/api/confluence", {"ticker": "bad/one"}),      # the validation answer
    ("/api/nope", {}),                               # an unrouted path
])
def test_every_api_answer_carries_its_own_headers(client, path, params):
    headers = client.get(path, params=params).headers
    for name, value in index.API_HEADERS.items():
        assert headers.get(name) == value, f"{path}: {name}"


def test_a_rate_limit_refusal_carries_them_too(client, monkeypatch):
    monkeypatch.setitem(index.RATE_LIMITS, "/api/health", (1, 60))
    monkeypatch.setattr(index, "RATE_EXEMPT", set())
    client.get("/api/health")
    refused = client.get("/api/health")
    assert refused.status_code == 429
    assert refused.headers.get("X-Content-Type-Options") == "nosniff"


def test_the_web_layer_does_not_announce_its_framework():
    from pathlib import Path
    config = (Path(index.__file__).resolve().parents[1] / "next.config.mjs").read_text()
    assert "poweredByHeader: false" in config
