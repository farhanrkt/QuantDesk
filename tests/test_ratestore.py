"""The shared rate-limit store: off without keys, global with them, never the
reason a request fails. Offline: the store's REST API is a fake in this file."""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

import index
from _lib import ratestore


class FakeUpstash:
    """Counts like Redis INCR with a fixed window, and records what it was sent."""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.bodies: list[str] = []
        self.fail = False

    def urlopen(self, request, timeout=None):
        if self.fail:
            raise TimeoutError("store did not answer")
        body = request.data.decode()
        self.bodies.append(body)
        commands = json.loads(body)
        key = commands[0][1]
        self.counts[key] = self.counts.get(key, 0) + 1
        answer = [{"result": self.counts[key]}, {"result": 1}, {"result": 42}]
        return io.BytesIO(json.dumps(answer).encode())


@pytest.fixture
def store(monkeypatch):
    fake = FakeUpstash()
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-store.upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "planted-token")
    monkeypatch.setattr(ratestore.urllib.request, "urlopen", fake.urlopen)
    return fake


@pytest.fixture
def client():
    index._RATE_HITS.clear()
    with TestClient(index.app) as c:
        yield c
    index._RATE_HITS.clear()


def test_without_keys_nothing_is_asked(monkeypatch):
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    monkeypatch.setattr(ratestore.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("asked a store with no keys"))
    assert ratestore.configured() is None
    assert ratestore.count("1.2.3.4", "/api/rank", 60) is None


def test_with_keys_the_store_decides_and_its_reset_is_the_retry_after(client, store):
    limit = index.RATE_LIMITS["/api/symbols"][0]
    for _ in range(limit):
        assert client.get("/api/symbols", params={"q": "bca"}).status_code == 200
    refused = client.get("/api/symbols", params={"q": "bca"})
    assert refused.status_code == 429
    assert refused.headers["Retry-After"] == "42"
    assert not index._RATE_HITS, "the in-process count was not used"


def test_the_address_never_reaches_the_store_in_clear(store):
    ratestore.count("203.0.113.9", "/api/rank", 60)
    assert "203.0.113.9" not in store.bodies[0]
    assert ratestore.key_for("203.0.113.9", "/api/rank", "t") != \
        ratestore.key_for("203.0.113.10", "/api/rank", "t")


def test_a_store_that_fails_hands_back_to_the_in_process_count(client, store):
    store.fail = True
    limit = index.RATE_LIMITS["/api/symbols"][0]
    codes = [client.get("/api/symbols", params={"q": "bca"}).status_code for _ in range(limit + 1)]
    assert codes[:limit] == [200] * limit and codes[-1] == 429
    assert index._RATE_HITS, "the in-process count took over"


def test_a_plain_http_url_is_not_a_store(monkeypatch):
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "http://example-store.upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "planted-token")
    assert ratestore.configured() is None, "a token is never sent over plain HTTP"
