#!/usr/bin/env python3
"""
audit_repro.py
==============
One reproduction per finding in docs/AUDIT.md, each answering a single
question: is the defect still in the code?

WHY THIS EXISTS BESIDE THE TEST SUITE
--------------------------------------
A finding without a reproduction is an opinion, and an audit that lists forty
of them is forty opinions nobody can check. Every function here plants the
condition a finding describes — a hung provider, a ticker of two dots, a
company with no long-term debt line — and reports whether the app still does
the thing the audit says it does. `PRESENT` means the defect is there;
`absent` means it has been fixed, and the function is then the record of what
was once true.

It is not a test suite and must not become one. A test asserts the behaviour
that is WANTED and fails the build when it stops; these describe behaviour
that is NOT wanted, so wiring them into CI would redden the build on the day
the audit was written. Each fix lands with its own test in `tests/`, written
to fail without the fix; this script is how a reader confirms the audit's
claim before that, and watches it go away after.

EVERYTHING HERE RUNS OFFLINE, like the suite: the engines are driven with
planted frames and patched fetches. The findings that can only be seen
against the live provider or in a browser (latency, layout shift, the
provider returning different data to two identical requests) are documented
in docs/AUDIT.md with the command that measured them and are not repeated
here.

    python scripts/audit_repro.py            # every finding
    python scripts/audit_repro.py SEC-2      # one of them

Exit status is the number of findings still present, so 0 means the audit has
been worked through.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

FINDINGS: dict = {}


def finding(code: str):
    def register(fn):
        FINDINGS[code] = fn
        return fn
    return register


def _client():
    import index
    from fastapi.testclient import TestClient
    index._RATE_HITS.clear()
    return index, TestClient(index.app)


def _source(relative: str) -> str:
    return (ROOT / relative).read_text()


# --------------------------------------------------------------------------- #
# Reliability
# --------------------------------------------------------------------------- #
@finding("REL-1")
def a_slow_provider_holds_the_whole_read():
    """One slow lens delays every lens, with no deadline anywhere."""
    index, client = _client()
    slow = 1.5

    def stall(*args, **kwargs):
        time.sleep(slow)
        raise index.HTTPException(status_code=404, detail="planted")

    saved = {name: getattr(index, name) for name in
             ("whale_payload", "technical_payload", "valuation_payload",
              "quality_payload", "news_payload", "company_payload")}
    saved_canary = index.market_data.provider_answering
    try:
        for name in saved:
            setattr(index, name, (lambda *a, **k: {"planted": True}))
        index.company_payload = stall
        index.market_data.provider_answering = lambda market: True
        started = time.monotonic()
        client.get("/api/confluence", params={"ticker": "AAPL"})
        waited = time.monotonic() - started
    finally:
        for name, fn in saved.items():
            setattr(index, name, fn)
        index.market_data.provider_answering = saved_canary
    budgeted = "wait_for" in _source("api/index.py")
    return (waited >= slow and not budgeted,
            f"five lenses answered at once, the sixth took {slow}s, and the response took "
            f"{waited:.1f}s; no asyncio.wait_for in api/index.py: {not budgeted}")


@finding("REL-2")
def a_single_lens_route_blames_the_ticker_during_an_outage():
    index, client = _client()
    md, val = index.market_data, index.valuation
    saved = (val.fetch_company, md.provider_answering)
    try:
        val.fetch_company = lambda ticker: {"ok": False, "sector": "", "industry": ""}
        md.provider_answering = lambda market="US": False
        answers = {route: client.get(route, params={"ticker": "AAPL"}).json().get("detail")
                   for route in ("/api/quality", "/api/intrinsic-value")}
    finally:
        val.fetch_company, md.provider_answering = saved
    text = " | ".join(str(v) for v in answers.values())
    return ("suffix" in text or "symbol" in text.lower(),
            f"with the provider down, AAPL is told: {text[:200]}")


@finding("REL-3")
def one_failed_price_request_is_final():
    from _lib import market_data as md
    calls = {"n": 0}

    class Flaky:
        def __init__(self, ticker):
            pass

        def history(self, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("planted: connection reset")
            index = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=30)
            return pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0,
                                 "Volume": 1.0}, index=index)

    saved = md.yf.Ticker
    try:
        md.yf.Ticker = Flaky
        frame = md.ohlcv("AAPL", period="1mo")
    finally:
        md.yf.Ticker = saved
    return (frame is None and calls["n"] == 1,
            f"the first request failed, the second would have answered; ohlcv returned "
            f"{'None' if frame is None else 'a frame'} after {calls['n']} attempt(s)")


@finding("REL-4")
def ordinary_browsing_exhausts_the_board_limits():
    import index
    limit, window = index.RATE_LIMITS["/api/markets/headlines"]
    # Measured in a browser: the landing page asks for headlines twice and every
    # other page once, beside the board and the calendar.
    return (limit <= 20,
            f"/api/markets/headlines allows {limit} per {window}s per address; the landing "
            f"page spends 2 and every other page 1, so {limit // 2} to {limit} page loads "
            f"in a minute from one address (one reader, or one carrier NAT) reach a 429")


@finding("REL-5")
def the_client_has_no_timeout_and_cannot_read_a_validation_error():
    api = _source("lib/api.ts")
    no_timeout = "AbortSignal.timeout" not in api and "setTimeout" not in api
    bare_english = "`Request failed (${res.status})`" in api
    array_cast = 'typeof detail === "object") failure = detail as EngineFailure' in api
    return (no_timeout or bare_english or array_cast,
            f"no timeout on fetch: {no_timeout}; untranslated fallback message: {bare_english}; "
            f"a 422's list of errors cast to a failure with no message: {array_cast}")


@finding("REL-6")
def a_failed_thumbnail_draws_an_empty_box():
    source = _source("components/ui/headlines.tsx")
    return ("onError" not in source,
            "components/ui/headlines.tsx renders <Image> with no onError fallback")


# --------------------------------------------------------------------------- #
# Security
# --------------------------------------------------------------------------- #
@finding("SEC-2")
def the_ticker_pattern_accepts_dot_dot():
    import index
    hits = [t for t in ("..", ".", "-", "^", "=", "....") if index.TICKER_RE.match(t)]
    return bool(hits), f"TICKER_RE accepts {hits}; each is interpolated into a provider URL path"


@finding("SEC-3")
def validation_errors_are_english_lists_that_echo_their_input():
    _, client = _client()
    detail = client.get("/api/confluence", params={"ticker": "bad/one", "lang": "id"}).json()["detail"]
    echoed = client.post("/api/rank/list", json={"tickers": ["A" * 50_000 + "/"]})
    return (isinstance(detail, list) or len(echoed.text) > 5_000,
            f"a 422 asked for in Indonesian answers with a {type(detail).__name__} in English; "
            f"a 50,001-character symbol is echoed back in {len(echoed.text):,} bytes")


@finding("SEC-4")
def cors_is_open_everywhere_but_named_production():
    import index
    saved = {k: os.environ.pop(k, None) for k in ("ALLOWED_ORIGINS", "VERCEL_ENV")}
    try:
        os.environ["VERCEL_ENV"] = "preview"
        preview = index._allowed_origins()
        os.environ.pop("VERCEL_ENV")
        unset = index._allowed_origins()
    finally:
        for key, value in saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value
    return (preview == ["*"] or unset == ["*"],
            f"VERCEL_ENV=preview -> {preview}; VERCEL_ENV unset -> {unset}")


@finding("SEC-5")
def a_failed_lens_returns_the_exception_text():
    index, client = _client()
    builders = ("whale_payload", "technical_payload", "valuation_payload",
                "quality_payload", "news_payload", "company_payload")
    saved = {name: getattr(index, name) for name in builders}
    saved_canary = index.market_data.provider_answering

    def boom(symbol):
        raise RuntimeError("planted: /var/task/api/_lib/secret_path.py line 12")

    try:
        for name in builders:
            setattr(index, name, (lambda *a, **k: {"planted": True}))
        index.quality_payload = boom
        index.market_data.provider_answering = lambda market: True
        body = client.get("/api/confluence", params={"ticker": "AAPL", "lang": "id"}).json()
    finally:
        for name, fn in saved.items():
            setattr(index, name, fn)
        index.market_data.provider_answering = saved_canary
    error = str((body.get("quality") or {}).get("error"))
    return ("RuntimeError" in error and "secret_path" in error,
            f"quality leg error sent to an Indonesian reader: {error[:120]!r}")


@finding("SEC-7")
def the_api_sets_no_security_headers_of_its_own():
    _, client = _client()
    headers = client.get("/api/health").headers
    missing = [h for h in ("x-content-type-options", "x-frame-options", "referrer-policy")
               if h not in headers]
    powered = "poweredByHeader: false" not in _source("next.config.mjs")
    docs_public = client.get("/api/docs", headers={"x-vercel-id": "sin1::planted"}).status_code == 200
    return (bool(missing) or powered or docs_public,
            f"API responses lack {missing}; Next still sends X-Powered-By: {powered}; "
            f"/api/docs answers on a deployment: {docs_public}")


# --------------------------------------------------------------------------- #
# Correctness
# --------------------------------------------------------------------------- #
def _year_columns():
    return pd.to_datetime(["2025-12-31", "2024-12-31"])


@finding("COR-1")
def a_statement_row_is_found_by_substring():
    from _lib.valuation import _get_row
    cols = _year_columns()[:1]
    income = pd.DataFrame({cols[0]: [500.0, 520.0]}, index=["EBITDA", "Normalized EBITDA"])
    balance = pd.DataFrame({cols[0]: [900.0, 50.0]},
                           index=["Total Non Current Liabilities Net Minority Interest",
                                  "Other Current Liabilities"])
    ebit = _get_row(income, "ebit")
    current = _get_row(balance, "current_liabilities")
    return (ebit is not None or current is not None,
            f"with no EBIT row, 'ebit' reads {None if ebit is None else ebit.name!r}; with no "
            f"current-liabilities row, it reads {None if current is None else current.name!r}")


@finding("COR-2")
def beneish_leverage_is_neutral_when_there_is_no_debt_line():
    from _lib import quality
    now, prior = _year_columns()
    income = pd.DataFrame({now: [1000, 600, 100, 80], prior: [900, 540, 90, 70]},
                          index=["Total Revenue", "Cost Of Revenue",
                                 "Selling General And Administration", "Net Income"])
    balance = pd.DataFrame({now: [2000, 800, 300, 150, 400], prior: [1800, 700, 280, 120, 350]},
                           index=["Total Assets", "Current Assets", "Net PPE",
                                  "Accounts Receivable", "Current Liabilities"])
    cash = pd.DataFrame({now: [90, 30], prior: [80, 28]},
                        index=["Operating Cash Flow", "Depreciation And Amortization"])
    lvgi = quality.beneish_m_score(income, balance, cash)["indices"].get("LVGI")
    expected = (400 / 2000) / (350 / 1800)
    return (lvgi is None,
            f"a company with current liabilities and no long-term debt line gets LVGI={lvgi}; "
            f"the index on current liabilities alone is {expected:.3f}. `(x or 0)` keeps a NaN")


# --------------------------------------------------------------------------- #
# Performance
# --------------------------------------------------------------------------- #
@finding("PERF-3")
def nothing_is_code_split():
    hits = []
    for folder in ("app", "components", "lib"):
        for path in (ROOT / folder).rglob("*.ts*"):
            if re.search(r"next/dynamic|React\.lazy|\blazy\(", path.read_text()):
                hits.append(str(path.relative_to(ROOT)))
    return not hits, f"files using a dynamic import: {hits or 'none'}"


@finding("PERF-4")
def a_public_deployment_imports_the_private_scanner():
    source = _source("api/index.py")
    head = source[:source.index("app = FastAPI(")]
    eager = [name for name in ("tape", "patterns", "verdict", "chartlayers", "structure",
                               "volumeprofile") if re.search(rf"\b{name}\b", head)]
    return bool(eager), f"imported at module load on every deployment: {', '.join(eager)}"


# --------------------------------------------------------------------------- #
# Copy
# --------------------------------------------------------------------------- #
@finding("COPY-1")
def the_ulcer_index_explains_itself_with_its_own_number():
    from _lib import explain
    reading = explain.explain("ulcerIndex", 11.7)["reading"]
    first = re.split(r"(?<=[.!?])\s+(?=[A-Z])", reading)[0]
    return (bool(re.fullmatch(r"[\d.,]+\.?", first.strip())),
            f"the first sentence, which is all Guided mode shows, is {first!r}")


@finding("COPY-2")
def the_landing_says_the_models_share_no_data():
    landing = _source("components/landing/Landing.tsx")
    return ("share no data" in landing,
            "the landing headline says four models 'share no data'; the rail on every stock "
            "page says Flow and Trend read the same price-and-volume series")


@finding("COPY-4")
def a_loss_is_worded_as_a_gain():
    from _lib import explain
    out = explain.explain("rollingWorst", -0.164, years=3, positiveShare=0.55, windows=444) or {}
    text = str(out.get("reading", ""))
    return ("still returned -" in text,
            f"a worst case of -16.4% a year reads: {text[:110]!r}")


def main(argv: list[str]) -> int:
    wanted = [code.upper() for code in argv] or list(FINDINGS)
    present = 0
    for code in wanted:
        fn = FINDINGS.get(code)
        if fn is None:
            print(f"unknown   {code}")
            continue
        try:
            hit, evidence = fn()
        except Exception as exc:               # a reproduction that cannot run says so
            print(f"ERROR     {code:8} {fn.__name__}: {type(exc).__name__}: {exc}")
            continue
        present += bool(hit)
        print(f"{'PRESENT' if hit else 'absent '}   {code:8} {fn.__name__.replace('_', ' ')}\n"
              f"          {evidence}")
    print(f"\n{present} of {len(wanted)} still present.")
    return present


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
