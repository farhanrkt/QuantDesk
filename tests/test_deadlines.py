"""A provider that hangs costs one lens, or one worded refusal — never a minute.

WHY THIS EXISTS

`tests/test_outages.py` plants a provider that FAILS, and a failure is the
easy outage: every call returns at once and the page says so. The November
2026 audit planted the other kind, a socket that accepts a connection and then
says nothing, and one `/api/confluence` had not returned after 380 seconds.
Nothing in the app was counting: each provider call waits out its own ten to
thirty seconds, a lens makes several in a row, and the route waited for all six
lenses. The platform allows the function sixty seconds, so a reader got the
platform's own error page and not one lens.

These tests plant the hang with `time.sleep` in place of a lens and hold the
three budgets `api/index.py` now keeps: one per lens, one for the question "is
the provider answering", and one for any request at all.
"""

from __future__ import annotations

import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import index
from _lib import market_data

LENSES = ("whale_payload", "technical_payload", "valuation_payload",
          "quality_payload", "news_payload", "company_payload")

# Long enough to be unmistakably past a budget of a fifth of a second, short
# enough that the abandoned thread is gone before the next test.
HANG = 1.0


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    index._RATE_HITS.clear()
    market_data._CANARY_CACHE.clear()
    monkeypatch.setattr(index, "LEG_BUDGET_SECONDS", 0.2)
    monkeypatch.setattr(index, "CANARY_BUDGET_SECONDS", 0.2)
    yield
    index._RATE_HITS.clear()
    market_data._CANARY_CACHE.clear()


@pytest.fixture
def client():
    # ENTERED, so every request of a test shares one event loop. A bare
    # TestClient opens and closes a loop per request, and closing a loop waits
    # for its worker threads — which would make every response here appear to
    # take exactly as long as the hang it is supposed to have outrun. A server
    # keeps one loop for its life; this is the same.
    with TestClient(index.app) as entered:
        yield entered


def _answer_at_once(monkeypatch, *, except_for=()):
    for name in LENSES:
        if name not in except_for:
            monkeypatch.setattr(index, name, lambda *a, **k: {"planted": True})


def _hang(*_args, **_kwargs):
    time.sleep(HANG)
    return {"planted": "late"}


def test_one_hung_lens_costs_one_lens(client, monkeypatch):
    """Five lenses answer at once and the sixth never does. The reader gets the
    five, quickly, and a sentence about the sixth."""
    _answer_at_once(monkeypatch, except_for=("company_payload",))
    monkeypatch.setattr(index, "company_payload", _hang)

    started = time.monotonic()
    response = client.get("/api/confluence", params={"ticker": "AAPL"})
    waited = time.monotonic() - started

    assert response.status_code == 200
    assert waited < HANG, f"the response waited {waited:.2f}s for a lens that hung for {HANG}s"
    body = response.json()
    for leg in ("anomaly", "technical", "valuation", "quality", "news"):
        assert body[leg]["ok"], leg
    assert body["company"] == {"ok": False, "error": body["company"]["error"]}
    assert body["company"]["error"]["cause"] == "timeout"
    assert "took too long" in body["company"]["error"]["message"]


def test_a_lens_that_ran_out_of_time_is_not_kept_at_the_edge(client, monkeypatch):
    """It clears when the provider does, so it is held for seconds like every
    other transient failure — not for the six minutes a company's facts are."""
    _answer_at_once(monkeypatch, except_for=("quality_payload",))
    monkeypatch.setattr(index, "quality_payload", _hang)

    response = client.get("/api/confluence", params={"ticker": "AAPL"})
    assert response.headers["cache-control"] == index.CACHE_FAILED
    assert response.headers["cdn-cache-control"] == index.CDN_CACHE_FAILED


def test_both_price_lenses_hanging_is_an_outage_without_asking_again(client, monkeypatch):
    """The provider is hanging; asking its index the same question would hang
    for the same reason. Every lens says the provider is not answering."""
    _answer_at_once(monkeypatch, except_for=("whale_payload", "technical_payload",
                                             "valuation_payload", "quality_payload",
                                             "company_payload"))
    for name in ("whale_payload", "technical_payload", "valuation_payload",
                 "quality_payload", "company_payload"):
        monkeypatch.setattr(index, name, _hang)

    def must_not_be_asked(market):
        raise AssertionError("the canary was asked although both price lenses timed out")
    monkeypatch.setattr(market_data, "provider_answering", must_not_be_asked)

    started = time.monotonic()
    body = client.get("/api/confluence", params={"ticker": "AAPL"}).json()
    assert time.monotonic() - started < HANG
    assert body["providerAnswering"] is False
    assert body["anomaly"]["error"] == market_data.provider_outage_message("AAPL")
    # The outage sentence, and not the one that blames the ticker.
    assert body["technical"]["error"] == market_data.provider_outage_message("AAPL")


def test_a_canary_that_hangs_is_a_provider_that_is_not_answering(client, monkeypatch):
    """The lenses fail fast, as in an ordinary outage, and the question that
    decides whose fault it is hangs. It is bounded too, and off the event loop."""
    def fail(*_args, **_kwargs):
        raise HTTPException(status_code=404, detail="No data found for 'AAPL'.")
    for name in LENSES:
        monkeypatch.setattr(index, name, fail)

    def hung_canary(market):
        time.sleep(HANG)
        return True
    monkeypatch.setattr(market_data, "provider_answering", hung_canary)

    started = time.monotonic()
    body = client.get("/api/confluence", params={"ticker": "AAPL"}).json()
    assert time.monotonic() - started < HANG
    assert body["providerAnswering"] is False


def test_the_timeout_sentence_is_in_the_readers_language(client, monkeypatch):
    _answer_at_once(monkeypatch, except_for=("quality_payload",))
    monkeypatch.setattr(index, "quality_payload", _hang)

    body = client.get("/api/confluence", params={"ticker": "AAPL", "lang": "id"}).json()
    message = body["quality"]["error"]["message"]
    assert message.startswith("Lensa Kualitas terlalu lama tiba")
    assert "took too long" not in message


# --------------------------------------------------------------------------- #
# Any request at all
# --------------------------------------------------------------------------- #
def test_a_single_lens_route_that_hangs_is_answered_in_words(client, monkeypatch):
    """The routes that re-run one lens are ordinary functions on a worker
    thread, with no lens budget to fall back on. The request budget answers."""
    monkeypatch.setattr(index, "REQUEST_BUDGET_SECONDS", 0.2)
    monkeypatch.setattr(index, "quality_payload", _hang)

    started = time.monotonic()
    response = client.get("/api/quality", params={"ticker": "AAPL"})
    waited = time.monotonic() - started

    assert response.status_code == 504
    assert waited < HANG, f"waited {waited:.2f}s on a route that hung for {HANG}s"
    assert "took too long" in response.json()["detail"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["retry-after"] == "60"


def test_the_request_budget_answers_in_indonesian(client, monkeypatch):
    monkeypatch.setattr(index, "REQUEST_BUDGET_SECONDS", 0.2)
    monkeypatch.setattr(index, "quality_payload", _hang)

    response = client.get("/api/quality", params={"ticker": "AAPL", "lang": "id"})
    assert response.status_code == 504
    assert response.json()["detail"].startswith("Ini terlalu lama")


def test_a_request_inside_its_budget_is_untouched(client, monkeypatch):
    monkeypatch.setattr(index, "REQUEST_BUDGET_SECONDS", 5.0)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_the_budgets_fit_inside_the_platforms_limit():
    """A lens budget, then the canary's, then margin for the synthesis and the
    wire, all inside the request budget, which is inside the function's
    `maxDuration`. Read from vercel.json so the two cannot drift."""
    import json
    from pathlib import Path

    config = json.loads((Path(index.__file__).resolve().parents[1] / "vercel.json").read_text())
    platform = config["functions"]["api/index.py"]["maxDuration"]
    assert index.LEG_BUDGET_SECONDS + index.CANARY_BUDGET_SECONDS < index.REQUEST_BUDGET_SECONDS
    assert index.REQUEST_BUDGET_SECONDS < platform
