"""Route-level contracts, exercised through the real ASGI app.

Still offline: the engines are monkeypatched at the seam where they would call
yfinance, so what is under test is the routing, validation, error mapping and
guard-rails rather than Yahoo's uptime.
"""

from __future__ import annotations

import pathlib

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


def planted_company(**overrides) -> dict:
    """A company record shaped like `market_data.company`, with no network behind it."""
    import pandas as pd
    years = [pd.Timestamp(f"{2025 - i}-12-31") for i in range(4)]
    income = pd.DataFrame({y: {"Total Revenue": r, "Net Income": n, "Operating Income": o}
                           for y, r, n, o in zip(years, [400.0, 360.0, 330.0, 300.0],
                                                 [40.0, 36.0, 30.0, 25.0],
                                                 [60.0, 55.0, 48.0, 40.0], strict=True)})
    cashflow = pd.DataFrame({y: {"Operating Cash Flow": c, "Free Cash Flow": f}
                             for y, c, f in zip(years, [50.0, 45.0, 40.0, 30.0],
                                                [20.0, -5.0, 10.0, 8.0], strict=True)})
    balance = pd.DataFrame({y: {"Stockholders Equity": 200.0, "Cash And Cash Equivalents": 30.0,
                                "Total Debt": 90.0, "Long Term Debt": 90.0} for y in years})
    record = {
        "ok": True, "name": "Planted Corp", "sector": "Technology",
        "industry": "Software - Infrastructure", "business_summary": "Planted Corp sells planted things.",
        "employees": 1200.0, "country": "United States", "website": "https://example.com",
        "exchange": "NasdaqGS", "price": 50.0, "shares": 10.0, "beta": 1.0, "currency": "USD",
        "financial_currency": "USD", "market_cap": 500.0, "price_as_of": "2026-10-23",
        "price_source": "last daily close", "ttm_dividend": 1.0,
        "dividend_history": pd.DataFrame({"Year": ["2026", "2025", "2024"],
                                          "Dividend / Share": [0.5, 1.0, 0.9]}),
        "income": income, "cashflow": cashflow, "balance": balance, "fx_rate": None,
    }
    record.update(overrides)
    return record


@pytest.fixture(autouse=True)
def offline_company(monkeypatch):
    """Every route test gets a planted company record and earnings calendar.

    THE QUALITY LEG OF /api/confluence WAS REACHING THE NETWORK. The confluence
    tests stubbed the anomaly, technical, valuation and news engines but not the
    company fetch the quality leg makes, so each of them called yfinance and
    passed on whatever came back — which is the test that gets skipped the day
    the upstream is down. The company leg reads the same record plus the
    earnings calendar, so both are planted here for every test; a test that
    needs a different record patches over this one.
    """
    monkeypatch.setattr(index.valuation, "fetch_company", lambda symbol: planted_company())
    monkeypatch.setattr(index.market_data, "earnings_calendar", lambda symbol: {
        "available": True, "dates": [], "past": ["2026-07-30"], "next": "2026-10-30",
        "asOf": "2026-10-25"})


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
                 "/api/intrinsic-value", "/api/news", "/api/confluence", "/api/company"):
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


def test_the_market_a_lens_is_told_comes_from_the_symbol_not_the_dropdown(client, monkeypatch):
    """`market` picks the valuation conventions; the SUFFIX decides what the
    listing is. Asking "is this an Indonesian listing?" is a question about the
    security, and reading the dropdown for it reported TLKM.JK as a US listing —
    the class of silent mismatch `symbols.py` exists to prevent."""
    seen = {}

    def capture(company, symbol=None, market_code=None):
        seen["symbol"], seen["market_code"] = symbol, market_code
        return {"applicable": False, "cause": "no-statements", "reason": "stub"}

    monkeypatch.setattr(index.valuation, "fetch_company", lambda s: {"ok": True})
    monkeypatch.setattr(index.quality, "analyze", capture)

    # Market says US, the symbol says otherwise. The symbol wins.
    client.get("/api/quality", params={"ticker": "TLKM.JK", "market": "US"})
    assert seen == {"symbol": "TLKM.JK", "market_code": "ID"}

    client.get("/api/quality", params={"ticker": "AAPL", "market": "US"})
    assert seen == {"symbol": "AAPL", "market_code": "US"}


def test_every_lens_is_told_the_market_the_suffix_implies(client, monkeypatch):
    """The quality lens got this rule first; these are the ones that had not.

    Typing "ITMG.JK" and leaving the dropdown on its US default resolved the
    right Indonesian company and then handed the valuation and technical
    engines `market_code="US"`. Measured before the fix: Rp 25,650 rendered as
    "$25,650.00", the cost of equity built from the US 10-year and a 5.5% ERP
    rather than the IndoGB proxy and 7%, beta regressed against ^GSPC instead of
    ^JKSE, and a fair value of Rp 98,000 where the correct run says Rp 67,525 —
    an upside of +282% on the page instead of +159%.
    """
    seen = {}
    monkeypatch.setattr(index.valuation, "analyze",
                        lambda ticker, **kw: seen.update(
                            valuation=kw.get("market_code")) or {"stub": True})
    monkeypatch.setattr(index.technical, "analyze",
                        lambda symbol, **kw: seen.update(
                            technical=kw.get("market_code")) or {"stub": True})

    client.get("/api/intrinsic-value", params={"ticker": "ITMG.JK", "market": "US"})
    assert seen["valuation"] == "ID", "a typed .JK suffix must beat the dropdown"

    client.get("/api/technical-analysis", params={"ticker": "ITMG.JK", "market": "US"})
    assert seen["technical"] == "ID"

    # The ordinary case is untouched, in both directions.
    client.get("/api/intrinsic-value", params={"ticker": "AAPL", "market": "US"})
    assert seen["valuation"] == "US"
    client.get("/api/intrinsic-value", params={"ticker": "BBCA", "market": "ID"})
    assert seen["valuation"] == "ID"


def test_a_feed_that_declares_entities_is_refused():
    """BILLION LAUGHS, ON A PAYLOAD THIS APP FETCHES FROM THE INTERNET.

    `xml.etree.ElementTree` resolves no EXTERNAL entities, so there is no XXE —
    a `file:///etc/passwd` entity raises rather than reads. It does expand
    INTERNAL ones, and this parser turned a sub-400-byte three-level nest into
    300 bytes of output with the depth chosen by the sender; a deeper nest is
    unbounded memory inside a serverless function.

    A news feed has no reason to declare a doctype, so the declaration is
    refused before parsing rather than bounded afterwards.
    """
    from _lib import news

    laughs = (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
              b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
              b"<rss><item><title>&lol2;</title></item></rss>")
    external = (b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                b"<rss><item><title>&x;</title></item></rss>")
    import xml.etree.ElementTree as ET
    for payload in (laughs, external):
        with pytest.raises(ET.ParseError):
            news._parse_feed(payload)

    ordinary = (b"<rss><channel><item><title>Acme beats estimates - Reuters</title>"
                b"<link>https://example.com/a</link></item></channel></rss>")
    assert news._parse_feed(ordinary).find(".//title").text.startswith("Acme")


def test_the_feed_read_is_bounded():
    """`response.read()` with no argument lets the far end choose how much memory
    this function allocates, and a timeout does not help — a slow drip inside the
    timeout still fills it. The cap is roughly forty times the largest real feed."""
    from _lib import news

    assert news.MAX_FEED_BYTES == 1_048_576
    source = pathlib.Path(news.__file__).read_text()
    assert "response.read(MAX_FEED_BYTES + 1)" in source
    assert "raw = response.read()" not in source, "an unbounded read must not return"


def planted_board(available: bool = True) -> dict:
    """A board built offline: every instrument on a quiet two-year walk."""
    import numpy as np
    import pandas as pd

    from _lib import marketboard

    if not available:
        return marketboard.build({})
    index_ = pd.bdate_range(end="2026-10-30", periods=500)
    frames = {}
    for n, instrument in enumerate(marketboard.INSTRUMENTS):
        closes = 100 * np.exp(np.cumsum(np.random.default_rng(n).normal(0, 0.01, 500)))
        frames[instrument.symbol] = pd.DataFrame(
            {"Open": closes, "High": closes, "Low": closes, "Close": closes,
             "Volume": np.full(500, 1.0)}, index=index_)
    return marketboard.build(frames, fetched_at="2026-11-01T09:00+00:00")


def test_the_market_board_takes_no_parameters_and_is_cached_five_minutes(client, monkeypatch):
    """One cache entry for every reader, and no ticker anywhere in the request."""
    monkeypatch.setattr(index.marketboard, "fetch", lambda: planted_board())
    response = client.get("/api/markets/today")
    assert response.status_code == 200
    assert "s-maxage=300" in response.headers["Cache-Control"]
    assert "max-age=0" in response.headers["Cache-Control"]
    assert "stale-while-revalidate=600" in response.headers["CDN-Cache-Control"]
    body = response.json()
    assert [row["key"] for row in body["rows"]] == [i.key for i in index.marketboard.INSTRUMENTS]
    assert set(body["explain"]["markets"]) == {"US", "ID"}
    assert all(row["tone"] == "neutral" for row in body["rows"])


def test_a_board_with_no_prices_at_all_is_an_error_not_an_empty_board(client, monkeypatch):
    monkeypatch.setattr(index.marketboard, "fetch", lambda: planted_board(available=False))
    assert client.get("/api/markets/today").status_code == 502


def test_headline_topics_come_from_a_declared_list(client, monkeypatch):
    """A request picks a topic; it can never write the query."""
    from _lib import news
    monkeypatch.setattr(news, "_fetch_feed", lambda url: b"<rss><channel></channel></rss>")
    assert client.get("/api/markets/headlines", params={"topics": "market,oil"}).status_code == 200
    assert client.get("/api/markets/headlines", params={"topics": "market,evil"}).status_code == 422
    assert client.get("/api/markets/headlines",
                      params={"topics": "market,oil,gold,copper,rates"}).status_code == 422
    assert client.get("/api/markets/headlines",
                      params={"topics": "stock market"}).status_code == 422


def test_a_headline_feed_that_failed_is_not_reported_as_no_news(client, monkeypatch):
    from _lib import news

    def broken(url):
        raise OSError("timed out")

    monkeypatch.setattr(news, "_fetch_feed", broken)
    feed = client.get("/api/markets/headlines",
                      params={"market": "ID", "topics": "oil"}).json()["topics"][0]
    assert feed["available"] is False and feed["items"] == [] and feed["reason"]

    monkeypatch.setattr(news, "_fetch_feed", lambda url: b"<rss><channel></channel></rss>")
    feed = client.get("/api/markets/headlines",
                      params={"market": "ID", "topics": "oil"}).json()["topics"][0]
    assert feed["available"] is True and feed["items"] == []
    assert feed["query"] == "harga minyak", "Indonesian readers get the Indonesian query"


def test_market_headlines_are_newest_first_and_ask_for_the_past_day(monkeypatch):
    from _lib import news
    seen = {}
    feed = (b"<rss><channel>"
            b"<item><title>Older story - Wire</title><source>Wire</source>"
            b"<pubDate>Fri, 30 Oct 2026 08:00:00 GMT</pubDate></item>"
            b"<item><title>Newer story - Desk</title><source>Desk</source>"
            b"<pubDate>Sat, 31 Oct 2026 16:00:00 GMT</pubDate></item>"
            b"</channel></rss>")

    def fetch(url):
        seen["url"] = url
        return feed

    monkeypatch.setattr(news, "_fetch_feed", fetch)
    out = news.fetch_headlines("oil", "US")
    assert [item["title"] for item in out["items"]] == ["Newer story", "Older story"]
    assert "when%3A1d" in seen["url"]


def test_the_rate_limiter_reads_the_routed_path_not_the_reconstructed_url(client):
    """A FORGED HOST HEADER USED TO TURN THE CAP OFF ENTIRELY.

    Starlette rebuilds `request.url` from the Host header without validating it
    against the RFC 3986 host grammar, so a Host carrying a slash moves the
    authority boundary: `Host: x/api/health?q=` on a request for `/api/rank`
    made `request.url.path` read `/api/health` while the router still dispatched
    `/api/rank` off the raw scope path.

    Measured against this app before the fix: with a normal Host the fourth call
    to `/api/rank` returned 429; with the forged Host every call returned 200,
    each running a full universe scan, and forging the path onto a RATE_EXEMPT
    route skipped the limiter altogether. The per-endpoint cap is the whole of
    the defence here, so a bypass of it is a bypass of everything.

    This pins the middleware to `scope["path"]` — the value the router itself
    uses — so the bucket can never disagree with the endpoint that executes.
    """
    import index as _index

    source = pathlib.Path(_index.__file__).read_text()
    limiter = source[source.index("async def rate_limit"):]
    limiter = limiter[:limiter.index("return await call_next")]
    assert 'request.scope.get("path")' in limiter, (
        "the limiter must key on the raw ASGI path")
    assert "path = request.url.path" not in limiter, (
        "request.url.path is forgeable through the Host header")


def test_the_portfolio_route_also_takes_its_market_from_the_suffix(client, monkeypatch):
    """The same bug, in the route that had no benchmark until it grew one.

    `/api/portfolio` used to need no market code at all — a correlation matrix
    over holdings has no index in it. Naming what those holdings share does: the
    market is projected out first, and with the dropdown's value instead of the
    symbol's, a book of Jakarta miners was measured against ^GSPC and the panel
    read "0% of it is the S&P 500". True, and about the wrong index.

    Caught in the browser rather than by a test, which is why this one exists.
    """
    seen = {}
    monkeypatch.setattr(index.portfolio, "analyse",
                        lambda candidate, holdings, **kw: seen.update(
                            market=kw.get("market_code"), candidate=candidate)
                        or {"usable": False, "reason": "stub"})

    client.post("/api/portfolio",
                json={"candidate": "ITMG.JK", "holdings": ["ADRO.JK"], "market": "US"})
    assert seen["candidate"] == "ITMG.JK"
    assert seen["market"] == "ID", "a typed .JK suffix must beat the dropdown"

    client.post("/api/portfolio",
                json={"candidate": "AAPL", "holdings": ["MSFT"], "market": "US"})
    assert seen["market"] == "US", "and the ordinary case is untouched"


def test_confluence_carries_the_pre_trade_block_even_when_legs_fail(client, monkeypatch):
    """The panel that names what could not be checked has to survive the case
    where nothing could be checked. A failed leg is its input, not its enemy."""
    monkeypatch.setattr(index, "whale_payload",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(index.technical, "analyze", lambda *a, **k: {})
    monkeypatch.setattr(index.valuation, "analyze", lambda *a, **k: {})
    monkeypatch.setattr(index.news, "fetch_news", lambda *a, **k: [])

    body = client.get("/api/confluence", params={"ticker": "FAKE"}).json()
    pre_trade = body["preTrade"]
    assert pre_trade["caveat"] and pre_trade["framing"]
    assert isinstance(pre_trade["flags"], list)
    # The one guarantee worth asserting at the wire boundary: no aggregate ever
    # reaches the client, whatever the engines did.
    assert not ({"score", "count", "total", "verdict", "severity"} & set(pre_trade))


# --------------------------------------------------------------------------- #
# The one route whose input is personal
# --------------------------------------------------------------------------- #
def portfolio(client, **body):
    """The one POST in this app. See the route for why it is not a GET."""
    payload = {"candidate": "NVDA", "holdings": ["AAPL", "MSFT"]}
    payload.update(body)
    return client.post("/api/portfolio", json=payload)


def test_holdings_travel_in_a_body_and_never_in_a_url(client, monkeypatch):
    """THE WHOLE REASON THIS ROUTE IS A POST. A company name in a URL is not a
    fact about anybody; a holdings list is, and URLs are logged by every hop
    that handles them — the platform's access log, any proxy, the browser's own
    history. None of that is reachable by a response header, so the input has to
    leave the address bar rather than be labelled once it is there."""
    monkeypatch.setattr(index.portfolio, "analyse",
                        lambda *a, **k: {"usable": True, "pairs": []})
    response = portfolio(client)
    assert response.status_code == 200
    # The query string is empty, which is the property under test.
    assert not response.request.url.query, "holdings must not reach the URL"
    assert "AAPL" not in str(response.request.url)

    # And the old shape is gone rather than quietly still working.
    assert client.get("/api/portfolio",
                      params={"candidate": "NVDA", "holdings": "AAPL"}).status_code == 405


def test_the_portfolio_response_is_never_stored_in_any_cache(client, monkeypatch):
    """A POST response is uncacheable by default, so this is belt and braces —
    kept because "uncacheable by default" is a property of the method that a
    refactor could quietly change, while an explicit header says what is meant."""
    monkeypatch.setattr(index.portfolio, "analyse",
                        lambda *a, **k: {"usable": True, "pairs": []})
    cache = portfolio(client).headers["Cache-Control"]
    assert "no-store" in cache
    assert "s-maxage" not in cache


def test_weights_are_matched_by_name_rather_than_by_position(client, monkeypatch):
    """A positional list would attach the wrong weight to the wrong name the
    first time a symbol was dropped for thin history — a plausible wrong answer
    rather than an error."""
    seen = {}
    monkeypatch.setattr(index.portfolio, "analyse",
                        lambda c, h, weights=None, **k: seen.update(
                            candidate=c, holdings=list(h), weights=weights) or {"usable": False})
    portfolio(client, weights={"MSFT": 2, "AAPL": 0.5})
    assert seen["weights"] == {"MSFT": 2.0, "AAPL": 0.5}
    assert seen["holdings"] == ["AAPL", "MSFT"]


@pytest.mark.parametrize("weights", [
    {"AAPL": "nonsense"}, {"AAPL": -1}, {"AA PL": 1}, {"AAPL": 0},
])
def test_a_malformed_weight_is_refused_by_name(client, weights):
    """Moving off the query string moved the input out of the logs, not out of
    reach. A body is still user input and is validated as such."""
    assert portfolio(client, holdings=["AAPL"], weights=weights).status_code in (400, 422)


@pytest.mark.parametrize("body", [
    {"candidate": "NOT A TICKER", "holdings": ["AAPL"]},
    {"candidate": "NVDA", "holdings": []},
    {"candidate": "NVDA"},
    {"candidate": "NVDA", "holdings": ["AAPL"], "market": "FR"},
    {"candidate": "NVDA", "holdings": "AAPL"},
])
def test_the_body_is_validated_as_strictly_as_the_query_string_was(client, body):
    assert client.post("/api/portfolio", json=body).status_code in (400, 422)


def test_the_candidate_is_never_correlated_against_itself(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(index.portfolio, "analyse",
                        lambda c, h, **k: seen.update(holdings=list(h)) or {"usable": False})
    portfolio(client, candidate="AAPL", holdings=["AAPL", "MSFT"])
    assert seen["holdings"] == ["MSFT"]
    assert portfolio(client, candidate="AAPL", holdings=["AAPL"]).status_code == 400


def test_the_holdings_list_is_capped(client):
    too_many = [f"AA{i:02d}" for i in range(index.PORTFOLIO_MAX_HOLDINGS + 5)]
    response = portfolio(client, holdings=too_many)
    assert response.status_code == 400
    assert str(index.PORTFOLIO_MAX_HOLDINGS) in response.json()["detail"]


def test_an_idx_holding_keeps_its_suffix_under_a_us_market(client, monkeypatch):
    """The same rule every other route follows: an explicitly typed suffix wins
    over the dropdown, because the user was more specific than it."""
    seen = {}
    monkeypatch.setattr(index.portfolio, "analyse",
                        lambda c, h, **k: seen.update(holdings=list(h)) or {"usable": False})
    portfolio(client, holdings=["BBCA.JK", "MSFT"], market="US")
    assert seen["holdings"] == ["BBCA.JK", "MSFT"]


# THE ROUTES WHOSE INPUT IS PERSONAL, AND NO OTHERS. Each is a POST for the same
# reason — a list somebody keeps is a fact about them and URLs are logged by every
# hop — and each answers `no-store`. A third entry here should come with that
# argument made again, not by analogy.
PERSONAL_POST_ROUTES = {"/api/portfolio", "/api/rank/list"}


def test_post_is_permitted_for_personal_input_and_nothing_else(client):
    """POST exists for routes whose input is personal. Every other endpoint must
    still refuse it, so the relaxation stays as narrow as it was argued to be."""
    for path in ("/api/confluence", "/api/rank", "/api/quality", "/api/technical-analysis",
                 "/api/symbols", "/api/peers"):
        assert client.post(path, json={}).status_code == 405, path
    posts = {route.path for route in index.app.routes
             if "POST" in getattr(route, "methods", set())}
    assert posts == PERSONAL_POST_ROUTES


def test_ranking_a_readers_own_list_is_never_cached(client, monkeypatch):
    seen = {}

    def fake_scan(symbols, market_code):
        seen["symbols"], seen["market"] = symbols, market_code
        return {"rows": [], "signals": [], "weights": {}, "correlation": {"available": False},
                "requested": len(symbols), "fetched": 0, "ranked": 0, "missing": [],
                "benchmark": None}
    monkeypatch.setattr(index.ranking, "scan", fake_scan)
    monkeypatch.setattr(index.ranking, "validation", lambda universe: {"available": False})
    response = client.post("/api/rank/list", json={"tickers": ["bbca", "TLKM.JK"], "market": "ID"})
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert seen == {"symbols": ["BBCA.JK", "TLKM.JK"], "market": "ID"}
    assert response.json()["universe"]["name"] == "Your list"


@pytest.mark.parametrize("body", [
    {"tickers": []},
    {"tickers": ["../etc/passwd"]},
    {"tickers": ["AAPL"] * 251},
    {"tickers": ["AAPL"], "market": "XX"},
])
def test_ranking_a_list_validates_like_the_query_did(client, body):
    assert client.post("/api/rank/list", json=body).status_code in (400, 422)


# --------------------------------------------------------------------------- #
# Q5/Q8 — response headers and payload size
# --------------------------------------------------------------------------- #
def test_cache_header_serves_the_edge_and_revalidates_the_browser(client):
    headers = client.get("/api/health").headers
    cache = headers["Cache-Control"]
    assert "s-maxage=60" in cache      # edge caches for a minute
    assert "max-age=0" in cache        # browser always revalidates
    assert "no-store" not in cache     # ...which would suppress the edge cache
    # Browsers honour stale-while-revalidate too, and with max-age=0 it let
    # Chrome serve the previous answer for five minutes. Edge only, now.
    assert "stale-while-revalidate" not in cache
    assert "stale-while-revalidate=300" in headers["CDN-Cache-Control"]


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


# ============================================================================ #
# Breadth tier — the guards that bound amplification
#
# These matter more than they look. `/api/rank` fans out to upstream fetches and
# `/api/rank/deepen` fans out to per-symbol filings requests, so the caps are
# the only thing standing between a curl loop and both the function budget and
# the shared yfinance rate budget.
# ============================================================================ #
def test_the_universe_catalogue_carries_an_as_of_date(client):
    """A stale constituent list is invisible unless it is dated."""
    body = client.get("/api/rank/universes").json()
    assert body["universes"]
    for entry in body["universes"]:
        assert entry["asOf"]
        assert entry["count"] > 0
        assert entry["market"] in ("US", "ID")
    assert body["maxUniverse"] > body["maxDeepen"]


def test_there_is_deliberately_no_sp500_universe(client):
    """Absence by decision, not omission — see `_lib/universes.py`.

    Five hundred symbols is the length at which transcription goes wrong, and a
    mistyped ticker is not inert: it produces a plausible ranking row for a
    company nobody asked about.
    """
    ids = {entry["id"] for entry in client.get("/api/rank/universes").json()["universes"]}
    assert not any("500" in name or "sp5" in name for name in ids)


def test_an_unknown_universe_is_refused_by_name(client):
    response = client.get("/api/rank", params={"universe": "sp500"})
    assert response.status_code == 404
    assert "sp500" in response.json()["detail"]


def test_rank_needs_either_a_universe_or_a_list(client):
    assert client.get("/api/rank").status_code == 400


def test_rank_refuses_an_oversized_custom_universe(client):
    tickers = ",".join(f"AA{i:03d}" for i in range(300))
    response = client.get("/api/rank", params={"tickers": tickers})
    assert response.status_code == 400
    assert "250" in response.json()["detail"]


def test_rank_names_an_invalid_symbol_rather_than_failing_anonymously(client):
    response = client.get("/api/rank", params={"tickers": "AAPL, not a ticker"})
    assert response.status_code == 400
    assert "not valid ticker symbols" in response.json()["detail"].lower()


def test_deepen_refuses_more_than_a_shortlist(client):
    tickers = ",".join(f"AA{i:03d}" for i in range(20))
    response = client.get("/api/rank/deepen", params={"tickers": tickers})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "one symbol at a time" in detail


def test_deepen_validates_its_symbols_too(client):
    response = client.get("/api/rank/deepen", params={"tickers": "AAPL, ../etc/passwd"})
    assert response.status_code == 400


def test_the_ranking_routes_are_rate_limited_more_tightly_than_the_default(client):
    """The amplifying routes must not inherit the ordinary per-IP allowance."""
    from index import RATE_LIMITS

    default_limit, _window = RATE_LIMITS[None]
    assert RATE_LIMITS["/api/rank"][0] < default_limit
    assert RATE_LIMITS["/api/rank/list"] == RATE_LIMITS["/api/rank"], (
        "the same scan in a POST body costs the same and is capped the same"
    )
    assert RATE_LIMITS["/api/rank/deepen"][0] < RATE_LIMITS["/api/rank"][0], (
        "deepening does not batch, so it must be capped harder than ranking"
    )


# --------------------------------------------------------------------------- #
# The company block: description, never a lens
# --------------------------------------------------------------------------- #
def _stub_lenses(monkeypatch):
    monkeypatch.setattr(index, "whale_payload", lambda *a, **k: {"stub": "anomaly"})
    monkeypatch.setattr(index.technical, "analyze", lambda *a, **k: {"stub": "technical"})
    monkeypatch.setattr(index.valuation, "analyze", lambda *a, **k: {"stub": "valuation"})
    monkeypatch.setattr(index.news, "fetch_news", lambda *a, **k: [])


def test_confluence_carries_the_company_block(client, monkeypatch):
    _stub_lenses(monkeypatch)
    company = client.get("/api/confluence", params={"ticker": "FAKE"}).json()["company"]
    assert company["ok"] is True
    data = company["data"]
    assert data["name"] == "Planted Corp"
    assert data["listing"]["exchange"] == "NasdaqGS"
    assert data["history"]["fiscalYears"] == ["FY2022", "FY2023", "FY2024", "FY2025"]
    assert data["history"]["rows"]["revenue"] == [300.0, 330.0, 360.0, 400.0]
    assert data["history"]["rows"]["operatingIncome"] == [40.0, 48.0, 55.0, 60.0]
    assert data["nextEarnings"]["date"] == "2026-10-30"
    assert "estimate" in data["nextEarnings"]["reading"]
    assert data["profile"]["summary"].startswith("Planted Corp")
    assert set(data["explain"]) >= {"yearsProfitable", "revenueCagr"}


def test_the_company_block_never_changes_what_the_lenses_say(client, monkeypatch):
    """The synthesis and the pre-trade checks read the lenses only. Their
    output must be identical whether the company block arrived or failed."""
    _stub_lenses(monkeypatch)
    with_company = client.get("/api/confluence", params={"ticker": "FAKE"}).json()
    index._RATE_HITS.clear()
    monkeypatch.setattr(index, "company_payload",
                        lambda symbol: (_ for _ in ()).throw(RuntimeError("no record")))
    without = client.get("/api/confluence", params={"ticker": "FAKE"}).json()
    assert without["company"]["ok"] is False
    assert with_company["synthesis"] == without["synthesis"]
    assert with_company["preTrade"] == without["preTrade"]


def test_a_failed_company_block_sinks_nothing_else(client, monkeypatch):
    _stub_lenses(monkeypatch)
    monkeypatch.setattr(index.valuation, "fetch_company", lambda symbol: {"ok": False})
    body = client.get("/api/confluence", params={"ticker": "FAKE"}).json()
    assert body["company"]["ok"] is False
    assert body["anomaly"]["ok"] and body["technical"]["ok"] and body["valuation"]["ok"]


def test_the_company_route_returns_the_same_block(client):
    body = client.get("/api/company", params={"ticker": "fake"}).json()
    assert body["ticker"] == "FAKE"
    assert body["dividends"]["perShare"][-1] == {"year": "2026", "amount": 0.5, "partial": True}
    assert body["dividends"]["available"] is True


def test_a_dividend_record_off_by_an_exchange_rate_is_withheld(client, monkeypatch):
    import pandas as pd
    # A rupiah price with a dividend recorded in dollars: 0.016 against Rp 9,000
    # is a 0.0002% "yield" — a units problem, not a dividend.
    monkeypatch.setattr(index.valuation, "fetch_company", lambda symbol: planted_company(
        price=9000.0, currency="IDR",
        dividend_history=pd.DataFrame({"Year": ["2025", "2024"], "Dividend / Share": [0.016, 0.015]})))
    body = client.get("/api/company", params={"ticker": "FAKE.JK"}).json()
    assert body["dividends"]["available"] is False
    assert body["dividends"]["perShare"] == []
    assert "units problem" in body["dividends"]["reading"]


def test_statements_in_another_currency_say_they_were_converted(client, monkeypatch):
    monkeypatch.setattr(index.valuation, "fetch_company", lambda symbol: planted_company(
        currency="IDR", financial_currency="USD", fx_rate=16000.0))
    body = client.get("/api/company", params={"ticker": "FAKE.JK"}).json()
    assert body["currency"]["note"] and "converted" in body["currency"]["note"]
    assert body["history"]["currency"] == "IDR"
