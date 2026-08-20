"""Route-level contracts, exercised through the real ASGI app.

Still offline: the engines are monkeypatched at the seam where they would call
yfinance, so what is under test is the routing, validation, error mapping and
guard-rails rather than Yahoo's uptime.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import index
from _lib.valuation import ValuationError


@pytest.fixture(autouse=True)
def clear_rate_limit():
    """The limiter is process-global; a leftover bucket would fail the next test."""
    index._RATE_HITS.clear()
    yield
    index._RATE_HITS.clear()


@pytest.fixture
def client():
    return TestClient(index.app)


# --------------------------------------------------------------------------- #
# C4 — ticker validation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("good", ["AAPL", "BBCA.JK", "BRK.B", "BTC-USD", "^TNX", "EURUSD=X"])
def test_ticker_pattern_accepts_real_symbols(good):
    assert index.TICKER_RE.match(good), f"{good} is a real symbol and must be accepted"


@pytest.mark.parametrize("bad", [
    "../../etc/passwd",         # path traversal into yfinance's URL path
    "AAPL/../../v8",            # ditto, embedded
    'AAPL"; rm -rf /',          # quote — reaches a Content-Disposition header
    "AAPL\r\nX-Injected: 1",    # CRLF header injection
    "AAPL AAPL",                # whitespace
    "<script>alert(1)</script>",
    "A" * 21,                   # over length
    "",
])
def test_ticker_pattern_rejects_hostile_input(bad):
    assert not index.TICKER_RE.match(bad)


@pytest.mark.parametrize("bad", ["../../etc/passwd", 'AAPL"x', "A" * 21])
def test_routes_reject_bad_tickers_with_422(client, bad):
    for path in ("/api/isolation-forest", "/api/technical-analysis",
                 "/api/intrinsic-value", "/api/news", "/api/confluence"):
        response = client.get(path, params={"ticker": bad})
        assert response.status_code == 422, f"{path} accepted {bad!r}"


def test_screener_names_the_invalid_symbol(client):
    response = client.get("/api/screener", params={"tickers": "AAPL, ../etc/passwd, MSFT"})
    assert response.status_code == 400
    assert "../etc/passwd" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# C2 — amplification guards
# --------------------------------------------------------------------------- #
def test_screener_universe_is_capped(client):
    universe = ",".join(f"SYM{i}" for i in range(index.SCREENER_MAX_UNIVERSE + 1))
    response = client.get("/api/screener", params={"tickers": universe})
    assert response.status_code == 400
    assert str(index.SCREENER_MAX_UNIVERSE) in response.json()["detail"]


def test_walkforward_screener_is_capped_harder(client):
    universe = ",".join(f"SYM{i}" for i in range(index.SCREENER_MAX_WALKFORWARD + 1))
    response = client.get("/api/screener",
                          params={"tickers": universe, "mode": "walkforward"})
    assert response.status_code == 400
    assert "walk-forward" in response.json()["detail"].lower()


def test_rate_limit_returns_429_with_retry_after(client):
    limit, _ = index.RATE_LIMITS["/api/screener"]
    params = {"tickers": "AAPL"}

    statuses = []
    for _ in range(limit + 2):
        statuses.append(client.get("/api/screener", params=params).status_code)

    assert statuses[-1] == 429
    assert statuses.count(429) == 2

    blocked = client.get("/api/screener", params=params)
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.headers["Cache-Control"] == "no-store"


def test_health_is_exempt_from_rate_limiting(client):
    for _ in range(60):
        assert client.get("/api/health").status_code == 200


def test_rate_limit_is_per_ip(client):
    limit, _ = index.RATE_LIMITS["/api/screener"]
    for _ in range(limit + 1):
        client.get("/api/screener", params={"tickers": "AAPL"},
                   headers={"x-forwarded-for": "10.0.0.1"})
    # A different client must be unaffected by the first one's budget.
    other = client.get("/api/screener", params={"tickers": "AAPL"},
                       headers={"x-forwarded-for": "10.0.0.2"})
    assert other.status_code != 429


def test_client_ip_prefers_the_original_forwarded_hop():
    class FakeRequest:
        def __init__(self):
            self.headers = {"x-forwarded-for": "203.0.113.9, 70.41.3.18, 150.172.238.178"}
            self.client = None

    assert index.client_ip(FakeRequest()) == "203.0.113.9"


# --------------------------------------------------------------------------- #
# Q1 — confluence leg isolation
# --------------------------------------------------------------------------- #
def test_confluence_preserves_structured_valuation_failure(client, monkeypatch):
    """The manual-rescue form exists only if `manualRequired` survives the leg."""
    def gap(symbol, **kwargs):
        raise ValuationError("Yahoo has a gap here.", manual_required=True,
                             missing=["base"], suggested={"base": 1234.0, "price": 9.0})

    monkeypatch.setattr(index.valuation, "analyze", gap)
    monkeypatch.setattr(index, "whale_payload", lambda *a, **k: {"stub": "anomaly"})
    monkeypatch.setattr(index.technical, "analyze", lambda *a, **k: {"stub": "technical"})
    monkeypatch.setattr(index.news, "fetch_news", lambda *a, **k: [])

    body = client.get("/api/confluence", params={"ticker": "FAKE"}).json()
    error = body["valuation"]["error"]

    assert body["valuation"]["ok"] is False
    assert isinstance(error, dict), "structured detail was flattened to a string"
    assert error["manualRequired"] is True
    assert error["suggested"]["base"] == 1234.0


def test_confluence_one_failing_leg_does_not_sink_the_others(client, monkeypatch):
    monkeypatch.setattr(index, "whale_payload", lambda *a, **k: {"stub": "anomaly"})
    monkeypatch.setattr(index.technical, "analyze",
                        lambda *a, **k: (_ for _ in ()).throw(
                            index.technical.TechnicalError("no bars")))
    monkeypatch.setattr(index.valuation, "analyze", lambda *a, **k: {"stub": "valuation"})
    monkeypatch.setattr(index.news, "fetch_news", lambda *a, **k: [])

    body = client.get("/api/confluence", params={"ticker": "FAKE"}).json()
    assert body["anomaly"]["ok"] is True
    assert body["valuation"]["ok"] is True
    assert body["news"]["ok"] is True
    assert body["technical"]["ok"] is False
    assert body["technical"]["error"] == "no bars", "leaked an exception class name"


def test_confluence_forwards_every_tuning_parameter(client, monkeypatch):
    """Without this, the endpoint silently runs DEFAULT detection while the UI
    reports the mode the user picked."""
    seen = {}

    def capture(symbol, **kwargs):
        seen.update(kwargs)
        return {"stub": True}

    monkeypatch.setattr(index, "whale_payload", capture)
    monkeypatch.setattr(index.technical, "analyze", lambda *a, **k: {})
    monkeypatch.setattr(index.valuation, "analyze", lambda *a, **k: {})
    monkeypatch.setattr(index.news, "fetch_news", lambda *a, **k: [])

    client.get("/api/confluence", params={
        "ticker": "AAPL", "mode": "mad", "mad_k": 2.5,
        "period": "5y", "recent_days": 30, "min_turnover": 1000,
    })
    assert seen["mode"] == "mad"
    assert seen["mad_k"] == 2.5
    assert seen["period"] == "5y"
    assert seen["recent_days"] == 30
    assert seen["min_turnover"] == 1000


# --------------------------------------------------------------------------- #
# Q5/Q8 — response headers and payload size
# --------------------------------------------------------------------------- #
def test_cache_header_serves_the_edge_and_revalidates_the_browser(client):
    cache = client.get("/api/health").headers["Cache-Control"]
    assert "s-maxage=60" in cache      # edge caches for a minute
    assert "max-age=0" in cache        # browser always revalidates
    assert "no-store" not in cache     # ...which would suppress the edge cache


def test_thin_for_wire_never_drops_a_flagged_day():
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    for rows in (10, index.SERIES_CAP, index.SERIES_CAP + 1, 16_265):
        frame = pd.DataFrame(
            {"Anomaly": rng.random(rows) < 0.03},
            index=pd.date_range("2000-01-03", periods=rows, freq="B"),
        )
        thinned, downsampled = index.thin_for_wire(frame)

        assert int(thinned["Anomaly"].sum()) == int(frame["Anomaly"].sum())
        assert thinned.index[0] == frame.index[0]
        assert thinned.index[-1] == frame.index[-1]
        assert downsampled == (rows > index.SERIES_CAP)
        if downsampled:
            # Anomalies are kept on top of the sample, so allow headroom.
            assert len(thinned) < rows


# --------------------------------------------------------------------------- #
# CORS posture
# --------------------------------------------------------------------------- #
def test_cors_is_same_origin_in_production(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert index._allowed_origins() == []


def test_cors_is_open_in_local_dev(monkeypatch):
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert index._allowed_origins() == ["*"]


def test_cors_honours_an_explicit_allowlist(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example, https://b.example")
    assert index._allowed_origins() == ["https://a.example", "https://b.example"]
