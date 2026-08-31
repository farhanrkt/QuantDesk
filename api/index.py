"""
api/index.py
============
One ASGI app, three engines.

WHY ONE FILE AND NOT THREE
--------------------------
Vercel compiles every top-level `.py` file under /api into its OWN function,
and each one bundles the full dependency closure. Three files means numpy +
pandas + scipy + scikit-learn + yfinance packaged three times — roughly 3x the
bundle and 3x the cold starts, for one shared dependency set.

So this is a single function that routes internally. The public URLs are
unchanged (`/api/isolation-forest`, `/api/technical-analysis`,
`/api/intrinsic-value`); `vercel.json` rewrites all of /api/* here.

SYMBOL RESOLUTION HAPPENS HERE, ONCE
------------------------------------
Every route resolves the user's ticker through `_lib.symbols.resolve` before it
touches an engine, and the resolved symbol is what gets passed down and echoed
back. Engines no longer each interpret the raw string — that is what let one
request value BBCA.JK while charting the BBCA ETF. See `_lib/symbols.py`.

Endpoints
---------
GET /api/health                     liveness + engine inventory
GET /api/isolation-forest           Engine 1 — whale / anomaly detection
GET /api/technical-analysis         Engine 2 — QuantDash technicals
GET /api/intrinsic-value            Engine 3 — INTRINSIC DCF/DDM + Monte Carlo
GET /api/intrinsic-value/simulation Engine 3 — full Monte Carlo draw set as CSV
GET /api/screener                   Engine 1 — multi-ticker watchlist scan
GET /api/quality                    Engine 4 — Piotroski / Altman / Beneish
GET /api/event-study                abnormal returns after each anomaly
GET /api/news                       contextual catalyst headlines
GET /api/confluence                 every lens at once, in ONE invocation
"""

from __future__ import annotations

import asyncio
import io
import math
import os
import re
import sys
import threading
import time
from collections import defaultdict, deque

from pathlib import Path
sys.path.append(str(Path(__file__).parent))
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from _lib import (accumulation, eventstudy, explain, exposure, market_data,
                  microstructure, news, portfolio, pretrade, quality, ranking,
                  riskmodel, symbols, technical, universes, valuation)
from _lib.jsonsafe import clean
from _lib.whale import AnalysisConfig, DataFetchError, WhaleTracker, WhaleTrackerError

app = FastAPI(title="QuantDesk API", version="1.1.0", docs_url="/api/docs")


def _allowed_origins() -> list[str]:
    """Wildcard CORS in local dev, same-origin only in production.

    On Vercel the frontend and this function share an origin, so production
    needs no CORS headers at all — an empty list means the middleware never
    matches and the browser enforces same-origin. `allow_origins=["*"]` let any
    site on the internet spend this deployment's compute (and its yfinance rate
    budget) for free, which is the part worth closing.

    Set ALLOWED_ORIGINS (comma separated) to permit specific external origins.
    """
    configured = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if configured:
        return configured
    return [] if os.environ.get("VERCEL_ENV") == "production" else ["*"]


# POST is permitted for exactly one route. `/api/portfolio` takes a body rather
# than a query string so that a reader's holdings never enter a URL — see the
# route itself. Everything else in this app is still a plain GET.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# `s-maxage` governs the Vercel edge cache; `max-age=0` keeps the browser
# revalidating so a reload always reflects the newest edge copy. Both matter:
# without an explicit browser directive the client falls back to heuristic
# freshness, and the client previously sent `cache: "no-store"`, which shared
# caches are specified to honour — so the edge cache below was never exercised.
# Verify with the `x-vercel-cache` response header (HIT on a repeat request).
CACHE = "public, max-age=0, s-maxage=60, stale-while-revalidate=300"

# The wire cap for daily series. `period=max` on a long-listed US name is ~11k
# rows x 10 fields, which is megabytes of JSON and as many Recharts points.
SERIES_CAP = 1500

# Every other query parameter is pattern-constrained; `ticker` was only
# length-bounded, and it reaches two places that must not take arbitrary text:
# yfinance interpolates it into a URL PATH (.../v8/finance/chart/{ticker}), and
# the CSV route interpolates it into a Content-Disposition HEADER.
#
# The character class is exactly what real symbols need and nothing more:
#   A-Z 0-9  ordinary listings           .  exchange suffixes (BBCA.JK, BRK.B)
#   -        crypto/FX pairs (BTC-USD)   ^  indices (^TNX)     =  FX (EURUSD=X)
# No slashes, no dots-dot, no quotes, no control characters, no whitespace.
TICKER_PATTERN = r"^[A-Za-z0-9.\-^=]{1,20}$"
TICKER_RE = re.compile(TICKER_PATTERN)


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
# Requests per window, per client IP, per route. `/api/screener` is far stricter
# than the rest because it is the amplifying route: one request there fans out
# to `universe` upstream fetches and `universe` model fits.
RATE_LIMITS: dict[Optional[str], tuple[int, int]] = {
    "/api/screener": (3, 60),
    # The ranking tier fans out too, but through BATCH downloads rather than
    # one fetch per name — a 100-symbol scan is a handful of upstream calls,
    # not a hundred. The per-IP cap stays as strict as the screener's anyway,
    # because the work per request is still far above a single-ticker route.
    "/api/rank": (3, 60),
    # Runs the identical universe scan and keeps one row of it, so it carries
    # the identical cost and the identical cap.
    "/api/peers": (3, 60),
    # One batch download of the whole book plus the candidate. Same shape of
    # cost as the ranking scan, same cap.
    "/api/portfolio": (3, 60),
    # One batch download of a whole universe plus three factor series, then
    # local arithmetic. Cheaper than the ranking scan — no indicators, no
    # per-name signals — but the fan-out to the upstream is the same shape, so
    # it takes the same cap rather than a looser one argued from being faster.
    "/api/exposure": (3, 60),
    # Deepening runs the fundamentals lenses per name and does NOT batch, so
    # this is the amplifying half of the funnel and is capped hardest.
    "/api/rank/deepen": (2, 60),
    "/api/confluence": (20, 60),
    "/api/intrinsic-value/simulation": (10, 60),
    # Five years of history plus the benchmark index, then a market model per
    # event — the heaviest single-ticker route in the app.
    "/api/event-study": (6, 60),
    None: (40, 60),                      # default for every other route
}
RATE_EXEMPT = {"/api/health", "/api/docs", "/openapi.json"}

# One screener request fans out to this many upstream fetches AND model fits.
# It was 50, which is a 50x amplification primitive available to anyone with
# curl — against both the function budget and the shared yfinance rate budget.
SCREENER_MAX_UNIVERSE = 20
SCREENER_MAX_WALKFORWARD = 5

# The ranking tier can afford a far larger universe because one batch call
# covers fifty symbols. Measured: 99 Nasdaq-100 names in ~7s including the
# benchmark, against a 60s function limit. 250 leaves room for a slow
# upstream day rather than sitting on the edge of a 504.
RANK_MAX_UNIVERSE = 250

# Deepening is the un-batchable half: `Ticker.financials` and `.info` are one
# call per symbol and take seconds each. Measured at ~2.9s per name cold, so
# eight is roughly 23s and leaves headroom inside the 60s limit; twelve sat
# close enough to the ceiling that one slow upstream response would have turned
# the whole shortlist into a 504. This is a shortlist size, not a screen size.
DEEPEN_MAX = 8

_RATE_HITS: dict[tuple[str, str], deque] = defaultdict(deque)
_RATE_LOCK = threading.Lock()
_RATE_MAX_KEYS = 10_000       # bound memory; a full reset is an acceptable flush


def client_ip(request: Request) -> str:
    """Best-effort client identity.

    `x-forwarded-for` is only trustworthy behind a proxy that sets it, which is
    the case on Vercel — the platform edge overwrites it. The FIRST entry is the
    original client; the rest are hops.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Per-IP request cap.

    SCOPE, HONESTLY: this counter lives in the process. On Vercel each warm
    instance keeps its own, so the effective ceiling is per-instance rather than
    global — it stops one client hammering one instance, and it does NOT stop a
    distributed flood. It is deliberately the whole of the defence only because
    the amplification itself is now bounded elsewhere (screener universe cap,
    walk-forward fit budget), which needs no shared state to be effective.

    To make this global, keep the same shape and move `_RATE_HITS` to Vercel KV
    or Upstash — the only thing that changes is where the deque is read from.
    """
    path = request.url.path
    if request.method == "OPTIONS" or path in RATE_EXEMPT:
        return await call_next(request)

    limit, window = RATE_LIMITS.get(path, RATE_LIMITS[None])
    key = (client_ip(request), path)
    now = time.monotonic()

    with _RATE_LOCK:
        if len(_RATE_HITS) > _RATE_MAX_KEYS:
            _RATE_HITS.clear()
        hits = _RATE_HITS[key]
        while hits and now - hits[0] >= window:
            hits.popleft()
        if len(hits) >= limit:
            retry_after = max(1, int(window - (now - hits[0])) + 1)
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit reached for this endpoint "
                                   f"({limit} requests per {window}s). "
                                   f"Try again in {retry_after}s."},
                headers={"Retry-After": str(retry_after),
                         "Cache-Control": "no-store"},
            )
        hits.append(now)

    return await call_next(request)


def ok(payload: dict) -> JSONResponse:
    # Cache at the edge: quotes move, but not within 60s, and every engine
    # re-runs a network fetch that we do not want to pay for on each keystroke.
    return JSONResponse(content=clean(payload), headers={"Cache-Control": CACHE})


def private_ok(payload: dict) -> JSONResponse:
    """A response that no cache anywhere may keep a copy of.

    THE ONLY ROUTE IN THIS APP WHOSE INPUT IS PERSONAL. Every other request says
    "tell me about this company"; the portfolio route says "here is what I own",
    which is a different kind of fact about the person asking.

    A POST response is already uncacheable by default, so this is belt and
    braces — and it is kept because "uncacheable by default" is a property of
    the method that a future refactor could quietly change, while an explicit
    `no-store` says what is intended. It also stops a browser applying heuristic
    freshness to a body that describes somebody's portfolio.
    """
    return JSONResponse(content=clean(payload),
                        headers={"Cache-Control": "no-store"})


def resolved(ticker: str, market: str) -> str:
    try:
        return symbols.resolve(ticker, market)
    except symbols.SymbolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def parse_ticker_list(tickers: str, market: str) -> list[str]:
    """A pasted universe, validated and resolved, deduplicated in typed order.

    ONE IMPLEMENTATION, TWO CALLERS. The ranking tier and the exposure scan take
    the identical input and must reject the identical things — the pattern has to
    hold because each symbol is interpolated into a yfinance URL path, and the
    resolution has to happen here because an unsuffixed IDX code is not inert
    (see `symbols.py`, where BBCA valued a bank and charted an ETF). A second
    copy would eventually accept something the first refuses.
    """
    raw = [t.strip() for t in tickers.replace("\n", ",").split(",") if t.strip()]
    bad = [t for t in raw if not TICKER_RE.match(t)]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"Not valid ticker symbols: {', '.join(bad[:5])}"
                   f"{'...' if len(bad) > 5 else ''}.")
    return list(dict.fromkeys(resolved(t, market) for t in raw))


def resolved_with_market(ticker: str, market: str) -> tuple[str, str]:
    """The symbol to fetch AND the market whose conventions describe it.

    Every single-ticker route wants both, and wanting only the first is the bug
    this returns a pair to prevent: the routes used to resolve the symbol from
    the typed suffix and then keep the dropdown's market code, so "ITMG.JK" on
    the default US setting fetched the Indonesian company and then priced it in
    dollars off a US risk-free rate against ^GSPC. Reassigning `market` at the
    point of resolution fixes currency, ERP, tax, benchmark index and screen
    domain together, because all of them read that one variable downstream.
    """
    symbol = resolved(ticker, market)
    return symbol, symbols.market_of(symbol)


def csv_response(frame, filename: str) -> StreamingResponse:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": CACHE,
        },
    )


# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return ok({
        "status": "ok",
        "engines": ["isolation-forest", "technical-analysis", "intrinsic-value",
                    "quality"],
        "extras": ["screener", "news", "simulation-csv", "event-study"],
    })


# --------------------------------------------------------------------------- #
# Engine 1 — Isolation Forest
# --------------------------------------------------------------------------- #
def thin_for_wire(frame):
    """Downsample a long daily series, never dropping a flagged day.

    The valuation engine already does this for its Monte Carlo draws — the wire
    carries 60 histogram bins rather than N floats. Same instinct here: the
    anomalies ARE the signal and every one of them survives; the line drawn
    between them is decoration and can be sampled. Stats are always computed on
    the full frame, so nothing user-visible changes except the payload size.
    """
    n = len(frame)
    step = max(1, math.ceil(n / SERIES_CAP))
    if step <= 1:
        return frame, False

    keep = (np.arange(n) % step == 0) | frame["Anomaly"].to_numpy(dtype=bool)
    keep[0] = keep[-1] = True          # never move the endpoints of the chart
    return frame[keep], True


def whale_payload(symbol: str, period: str = "2y", mode: str = "threshold",
                  contamination: float = 0.02, mad_k: float = 3.0,
                  score_threshold: float = -0.10, recent_days: int = 10,
                  min_turnover: float = 0.0) -> dict:
    config = AnalysisConfig(
        period=period,
        detection_mode=mode,
        contamination=contamination,
        mad_k=mad_k,
        score_threshold=score_threshold,
        min_avg_turnover=min_turnover,
    )
    try:
        result = WhaleTracker(config).analyze(symbol)
    except DataFetchError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WhaleTrackerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    frame = result.data
    plotted, downsampled = thin_for_wire(frame)
    series = [
        {
            "date": index.strftime("%Y-%m-%d"),
            "close": row["Close"],
            "volume": row["Volume"],
            "obv": row["OBV"],
            "mfi": row["MFI"],
            "rvol": row["Volume_vs_Avg"],
            "anomalyScore": row["Anomaly_Score"],
            "isAnomaly": bool(row["Anomaly"]),
            "flow": row["Flow"] if bool(row["Anomaly"]) else None,
            "strength": int(row["Strength"]) if bool(row["Anomaly"]) else None,
        }
        for index, row in plotted.iterrows()
    ]

    anomalies = [
        {
            "date": index.strftime("%Y-%m-%d"),
            "close": row["Close"],
            "flow": row["Flow"],
            "tag": row["Tag"],
            "strength": int(row["Strength"]),
            "rvol": row["Volume_vs_Avg"],
            "priceChangePct": row["Price_Change_%"],
            "mfi": row["MFI"],
            "anomalyScore": row["Anomaly_Score"],
        }
        for index, row in result.anomalies.iterrows()
    ]

    recent = result.recent_anomalies(recent_days)

    # Both of these read the frame the engine already built, so they cost no
    # extra network call. They answer the two questions the point detector
    # cannot: "is this move bigger than the spread?" and "is anyone accumulating
    # patiently rather than in one visible print?"
    liquidity = microstructure.liquidity_profile(frame)
    episodes = accumulation.detect(frame)

    payload = {
        "ticker": result.ticker,
        "liquidity": liquidity,
        "accumulation": episodes,
        "config": {
            "period": period, "mode": mode,
            "contamination": contamination, "madK": mad_k,
            "scoreThreshold": config.score_threshold,
            "rollingWindow": config.rolling_window,
            "mfiWindow": config.mfi_window,
            "minTurnover": min_turnover,
        },
        "stats": {
            "totalDays": result.total_days,
            # The chart may be sampled; the numbers never are.
            "seriesPoints": len(series),
            "downsampled": downsampled,
            "anomalyCount": result.anomaly_count,
            "anomalyRate": result.anomaly_rate,
            # Two horizons, deliberately separate. `netFlowBias` summarises the
            # whole look-back (two years by default); `recentFlowBias` is the
            # current-state reading and is what the confluence view votes with.
            "netFlowBias": result.net_flow_bias,
            "recentFlowBias": result.recent_flow_bias(recent_days),
            "maxStrength": int(result.anomalies["Strength"].max()) if result.anomaly_count else 0,
            "recentCount": len(recent),
            "recentDays": recent_days,
            "latestClose": float(frame["Close"].iloc[-1]),
            "latestMfi": float(frame["MFI"].iloc[-1]),
        },
        "series": series,
        "anomalies": anomalies,
    }
    # Plain-language layer. Attached after the payload is assembled so it reads
    # exactly the figures the panel renders rather than a parallel computation
    # that could drift from them.
    payload["explain"] = explain.for_flow(
        payload, currency="IDR" if symbol.upper().endswith(".JK") else "USD")
    return payload


@app.get("/api/isolation-forest")
def isolation_forest(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    period: str = Query("2y", pattern="^(6mo|1y|2y|5y|max)$"),
    mode: str = Query("threshold", pattern="^(threshold|mad|quota|walkforward)$"),
    contamination: float = Query(0.02, gt=0.0, lt=0.5),
    mad_k: float = Query(3.0, gt=0.0),
    score_threshold: float = Query(-0.10, ge=-0.50, le=0.50),
    recent_days: int = Query(10, ge=1, le=60),
    min_turnover: float = Query(
        0.0, ge=0.0,
        description="Minimum average daily turnover (price x volume) to keep a day. "
                    "0 disables the benign-noise filter.",
    ),
):
    symbol, market = resolved_with_market(ticker, market)
    return ok(whale_payload(symbol, period, mode, contamination, mad_k,
                            score_threshold, recent_days, min_turnover))


# --------------------------------------------------------------------------- #
# Engine 1b — watchlist screener
# --------------------------------------------------------------------------- #
@app.get("/api/screener")
def screener(
    tickers: str = Query(..., min_length=1, max_length=600,
                         description="Comma or newline separated symbols."),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    period: str = Query("2y", pattern="^(6mo|1y|2y|5y|max)$"),
    mode: str = Query("threshold", pattern="^(threshold|mad|quota|walkforward)$"),
    contamination: float = Query(0.02, gt=0.0, lt=0.5),
    mad_k: float = Query(3.0, gt=0.0),
    score_threshold: float = Query(-0.10, ge=-0.50, le=0.50),
    recent_days: int = Query(10, ge=1, le=60),
    min_turnover: float = Query(
        0.0, ge=0.0,
        description="Minimum average daily turnover (price x volume) to keep a day. "
                    "0 disables the benign-noise filter.",
    ),
):
    """Cross-asset scan: which names show fresh whale activity in the last N days.

    `market` decides what happens to BARE codes only; anything already carrying
    a suffix keeps it. So a mixed universe ("AAPL, BBCA.JK") resolves correctly
    under market=US, and market=ID is for a list of bare Indonesian codes.
    Passing market=ID with bare US tickers turns them into AAPL.JK and friends,
    which fetch nothing and are dropped — the caller should default to US.
    """
    raw = [t.strip() for t in tickers.replace("\n", ",").split(",") if t.strip()]
    # `tickers` is one free-text field, so the per-parameter pattern cannot reach
    # its elements — validate each one with the same rule the single-ticker
    # routes are constrained by, and name the offender rather than failing the
    # whole scan anonymously.
    bad = [t for t in raw if not TICKER_RE.match(t)]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"Not valid ticker symbols: {', '.join(bad[:5])}"
                   f"{'...' if len(bad) > 5 else ''}.",
        )
    universe = list(dict.fromkeys(resolved(t, market) for t in raw))
    if not universe:
        raise HTTPException(status_code=400, detail="Provide at least one ticker.")
    if len(universe) > SCREENER_MAX_UNIVERSE:
        raise HTTPException(
            status_code=400,
            detail=f"Universe too large. Limit the scan to {SCREENER_MAX_UNIVERSE} symbols — "
                   f"each one costs an upstream fetch and a model fit.",
        )
    # Walk-forward is roughly an order of magnitude more expensive per ticker
    # than the other modes even with the fit budget applied, so a large universe
    # on this mode is the one combination that reliably blows the 60s function
    # limit. Refusing it with a clear reason beats returning a bare 504.
    if mode == "walkforward" and len(universe) > SCREENER_MAX_WALKFORWARD:
        raise HTTPException(
            status_code=400,
            detail=f"Walk-forward refits per step and cannot scan {len(universe)} symbols "
                   f"inside the request limit. Use at most {SCREENER_MAX_WALKFORWARD} symbols "
                   f"on this mode, or scan with Threshold or Robust (MAD).",
        )

    config = AnalysisConfig(
        period=period, detection_mode=mode, contamination=contamination,
        mad_k=mad_k, score_threshold=score_threshold, min_avg_turnover=min_turnover,
    )
    table = WhaleTracker(config).scan_watchlist(universe, recent_days=recent_days)

    rows = [
        {
            "ticker": r["Ticker"],
            "recentAnomalies": int(r["Recent Anomalies"]),
            "anomalyRate": float(r["Anomaly Rate"]),
            "totalDays": int(r["Total Days"]),
            "dominantFlow": r["Dominant Flow"],
            "topStrength": int(r["Top Strength"]),
            "latestSignal": r["Latest Signal"],
            "latestTag": r["Latest Tag"],
            "latestClose": float(r["Latest Close"]),
            "topRvol": float(r["RVOL (top)"]),
        }
        for _, r in table.iterrows()
    ]
    # A scan over N names produces hits by construction. Test each one against
    # that ticker's OWN long-run flag rate and control the false discovery rate
    # across the scan, so "3 names flagged" arrives next to "about 1.4 expected
    # from noise" instead of standing alone.
    significance = eventstudy.screener_significance(
        rows, recent_trading_days=max(1, int(recent_days * 5 / 7)),
    )

    return ok({
        "scanned": len(universe),
        "universe": universe,
        "recentDays": recent_days,
        "config": {"period": period, "mode": mode},
        "rows": significance["rows"],
        "significance": {k: v for k, v in significance.items() if k != "rows"},
    })


# --------------------------------------------------------------------------- #
# Breadth tier — rank a universe, then deepen a shortlist
#
# THE TWO-TIER SHAPE IS FORCED BY WHAT BATCHES. Daily price history batches:
# one `yf.download` covers fifty symbols, so a hundred-name universe is a
# handful of upstream calls and ranks in about seven seconds. Fundamentals do
# not batch — `Ticker.financials` and `.info` are one call per symbol and cost
# seconds each — so quality and valuation cannot be computed universe-wide
# inside a request at any universe size worth calling breadth.
#
# Rather than show an empty Quality column for two hundred names, /api/rank
# ranks on price and volume alone and says so, and /api/rank/deepen runs the
# expensive lenses on a shortlist the reader chose from that ranking.
# --------------------------------------------------------------------------- #
@app.get("/api/rank/universes")
def rank_universes():
    """The predefined lists, with the date each was last transcribed.

    The as-of date is part of the payload rather than a comment in the source
    because index membership decays invisibly: a dropped constituent still
    fetches, so a stale list ranks a slightly wrong universe and reports no
    error. See `_lib/universes.py` for why there is no S&P 500 here.
    """
    return ok({"universes": universes.catalogue(), "asOf": universes.AS_OF,
               "maxUniverse": RANK_MAX_UNIVERSE, "maxDeepen": DEEPEN_MAX})


@app.get("/api/rank")
def rank(
    universe: Optional[str] = Query(
        None, pattern="^[a-z0-9]{1,24}$",
        description="A predefined universe id from /api/rank/universes."),
    tickers: Optional[str] = Query(
        None, min_length=1, max_length=4000,
        description="Comma or newline separated symbols, used when `universe` is absent."),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
):
    """Score every name in a universe on price-derived signals and rank them.

    Signals are converted to CROSS-SECTIONAL PERCENTILES before being combined,
    so the composite is a weighted mean of ranks within this scan rather than an
    absolute score on a scale nobody calibrated. The response carries the full
    per-signal breakdown and the rank correlation between signals, because
    momentum, nearness to the 52-week high and relative strength are three ways
    of saying "it went up" and a composite that hides that is overstating its
    own independence.
    """
    if universe:
        entry = universes.get(universe)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown universe '{universe}'. See /api/rank/universes.")
        symbols_list = entry["tickers"]
        market_code = entry["market"]
        label = entry["name"]
        as_of = entry["asOf"]
    else:
        if not tickers:
            raise HTTPException(
                status_code=400,
                detail="Provide either a `universe` id or a `tickers` list.")
        symbols_list = parse_ticker_list(tickers, market)
        market_code = market.upper()
        label = "Custom list"
        as_of = None

    if not symbols_list:
        raise HTTPException(status_code=400, detail="Provide at least one ticker.")
    if len(symbols_list) > RANK_MAX_UNIVERSE:
        raise HTTPException(
            status_code=400,
            detail=f"Universe too large. The ranking tier scans up to "
                   f"{RANK_MAX_UNIVERSE} symbols per request; this one has "
                   f"{len(symbols_list)}. Split it, or narrow the list.")

    result = ranking.scan(symbols_list, market_code=market_code)
    # THE PANEL THAT PRESENTS A RANKING CARRIES THE FINDING ABOUT WHETHER THAT
    # RANKING PREDICTS ANYTHING. The flow lens has had this since the event
    # study shipped; the breadth tier asserted its usefulness by omission until
    # now. Measured offline and stamped with its date, the same treatment the
    # constituent lists get — see scripts/backtest_ranking.py.
    result["validation"] = ranking.validation(universe)
    result["explain"] = explain.for_ranking(result)
    for row in result["rows"]:
        row["explain"] = explain.for_ranking_row(row)
    return ok({
        "universe": {"id": universe, "name": label, "market": market_code,
                     "asOf": as_of, "symbols": symbols_list},
        **result,
    })


@app.get("/api/peers")
def peers(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    universe: Optional[str] = Query(
        None, pattern="^[a-z0-9]{1,24}$",
        description="Peer group id. Defaults to the largest predefined universe "
                    "this ticker belongs to."),
):
    """Where one ticker sits among its own index, on the seven price signals.

    THIS IS A CALIBRATION AID, NOT A RANKING. The single-ticker lenses report
    everything in absolute terms — a 33% worst fall, 28% volatility — and a
    reader with no priors cannot tell an ordinary number from an alarming one.
    The ranking tier already computes the frame that answers it; this restates
    one row of that scan as sentences.

    It is a SEPARATE, DELIBERATE REQUEST rather than part of `/api/confluence`
    because it costs a whole universe scan — about six seconds for the
    Nasdaq-100 — and attaching that to every ticker run would multiply the cost
    of the app's most-used route by an order of magnitude for something most
    readers will not open.

    The peer group is echoed in the response and named in every sentence the
    explanation layer produces. Change the group and the same company moves,
    which is the one thing a percentile must never let a reader forget.
    """
    symbol, market = resolved_with_market(ticker, market)
    candidates = universes.containing(symbol)

    if universe:
        entry = universes.get(universe)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown peer group '{universe}'. See /api/rank/universes.")
    elif candidates:
        entry = universes.get(candidates[0]["id"])
    else:
        raise HTTPException(
            status_code=404,
            detail=f"{symbol} is not in any of the predefined universes, so there is no "
                   f"peer group to place it against. Pass `universe` explicitly, or use "
                   f"the Scan & rank tab with a list of your own.")

    result = ranking.scan(entry["tickers"], market_code=entry["market"])
    row = next((r for r in result["rows"] if r["ticker"] == symbol), None)
    if row is None:
        raise HTTPException(
            status_code=422,
            detail=f"{symbol} could not be ranked against {entry['name']}: it needs at "
                   f"least {ranking.MIN_BARS} trading days of history, and either the "
                   f"fetch failed or the listing is too recent.")

    context = {"id": entry["id"], "name": entry["name"], "market": entry["market"],
               "asOf": entry["asOf"], "count": entry["count"],
               "scanned": result["ranked"], "note": entry["note"]}

    return ok({
        "ticker": symbol,
        "universe": context,
        # Every group this name belongs to, so the panel can offer the switch
        # rather than presenting one denominator as if it were the only choice.
        "candidates": candidates,
        "rank": row.get("rank"),
        "composite": row.get("composite"),
        "coverage": row.get("coverage"),
        "benchmark": result.get("benchmark"),
        "explain": explain.for_peers(row, context, result["signals"],
                                     result.get("correlation")),
    })


@app.get("/api/exposure")
def exposure_scan(
    universe: Optional[str] = Query(
        None, pattern="^[a-z0-9]{1,24}$",
        description="A predefined universe id from /api/rank/universes."),
    tickers: Optional[str] = Query(
        None, min_length=1, max_length=4000,
        description="Comma or newline separated symbols, used when `universe` is absent."),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
):
    """What every name in a universe moves with, on the factors that persist.

    A SCAN RATHER THAN A LOOKUP, and that is the point. One beta is
    uninterpretable alone — 0.57 against the energy complex is remarkable or
    ordinary depending on what the other forty names read — so this returns the
    whole cross-section and lets the reader place a name in it. The same argument
    `/api/peers` makes about percentiles, applied to a quantity with no natural
    scale at all.

    Only factors whose year-to-year persistence was measured and survived appear
    here; the rest are named in `refused` with the reason rather than silently
    absent. Gold is one of them, at a rank correlation of +0.21 against a 0.25
    line set before the numbers were seen — see `exposure_stability.json`.

    Price only, so it batches: one upstream call for a whole universe.
    """
    if universe:
        entry = universes.get(universe)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown universe '{universe}'. See /api/rank/universes.")
        symbols_list, market_code = entry["tickers"], entry["market"]
        label, as_of = entry["name"], entry["asOf"]
    elif tickers:
        symbols_list = parse_ticker_list(tickers, market)
        market_code, label, as_of = market.upper(), "Your list", None
    else:
        raise HTTPException(status_code=400,
                            detail="Pass either `universe` or `tickers`.")

    if not symbols_list:
        raise HTTPException(status_code=400, detail="Provide at least one ticker.")
    if len(symbols_list) > RANK_MAX_UNIVERSE:
        raise HTTPException(
            status_code=400,
            detail=f"This scans up to {RANK_MAX_UNIVERSE} names at a time; "
                   f"this list has {len(symbols_list)}.")

    result = exposure.scan(symbols_list, market_code=market_code)
    return ok({
        "universe": {"id": universe, "name": label, "market": market_code,
                     "asOf": as_of, "count": len(symbols_list)},
        **result,
        "explain": explain.for_exposure_scan(result),
    })


@app.get("/api/rank/deepen")
def rank_deepen(
    tickers: str = Query(..., min_length=1, max_length=300,
                         description="Shortlist to run the fundamental lenses on."),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
):
    """Quality and valuation for a shortlist, the un-batchable half of the funnel.

    Each leg reports its own outcome, so a company with no usable dividend
    history still returns its quality reading instead of collapsing the row —
    the same contract `/api/confluence` uses, for the same reason.
    """
    raw = [t.strip() for t in tickers.replace("\n", ",").split(",") if t.strip()]
    bad = [t for t in raw if not TICKER_RE.match(t)]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"Not valid ticker symbols: {', '.join(bad[:5])}"
                   f"{'...' if len(bad) > 5 else ''}.")
    shortlist = list(dict.fromkeys(resolved(t, market) for t in raw))
    if not shortlist:
        raise HTTPException(status_code=400, detail="Provide at least one ticker.")
    if len(shortlist) > DEEPEN_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Deepening runs the filings-based lenses one symbol at a time and "
                   f"cannot do {len(shortlist)} inside the request limit. Pick at most "
                   f"{DEEPEN_MAX} from the ranking above.")

    rows = []
    for symbol in shortlist:
        row: dict = {"ticker": symbol}
        try:
            row["quality"] = {"ok": True, "data": quality_payload(symbol)}
        except HTTPException as exc:
            row["quality"] = {"ok": False, "error": exc.detail}
        except Exception as exc:
            row["quality"] = {"ok": False, "error": str(exc)}
        try:
            row["valuation"] = {"ok": True, "data": _deepen_valuation(symbol, market)}
        except HTTPException as exc:
            row["valuation"] = {"ok": False, "error": exc.detail}
        except Exception as exc:
            row["valuation"] = {"ok": False, "error": str(exc)}
        rows.append(row)

    return ok({
        "rows": rows,
        "caveat": ("Quality and valuation are computed one symbol at a time because the "
                   "filings behind them cannot be fetched in batch. That is why they are "
                   "a shortlist step rather than a column in the ranking table."),
    })


def _deepen_valuation(symbol: str, market: str) -> dict:
    """The valuation summary a shortlist row needs, without the full payload.

    The complete response carries a 10,000-point histogram and a full projection
    schedule per name. Twelve of those is megabytes of JSON for a table that
    shows four numbers, so the row carries the four.
    """
    payload = valuation_payload(symbol, **_valuation_kwargs(market=market))
    monte = payload["monteCarlo"]
    return {
        "engine": payload["engine"],
        "price": payload["price"],
        "priceLabel": payload["priceLabel"],
        "verdict": payload["verdict"],
        "medianLabel": monte["p50Label"],
        "upside": monte["upside"],
        "probUndervalued": monte["probUndervalued"],
        "terminalShare": payload["baseCase"].get("terminalShare"),
        "explain": payload.get("explain", {}),
    }


# --------------------------------------------------------------------------- #
# Portfolio context — where a candidate sits against what is already owned
#
# THE ONE POST IN THIS APP, AND THE REASON IS THE INPUT RATHER THAN THE SIZE.
# Everything else here answers "tell me about this company", and a company name
# in a URL is not a fact about anybody. A holdings list is. URLs are logged by
# every hop that handles them — the platform's access log, any proxy, the
# browser's own history — and none of that is reachable by a `Cache-Control`
# header or by anything else this code can set. A request body is not logged by
# default anywhere in that chain.
#
# The cost is real and worth naming: this app's stated shape was that everything
# the UI does is a plain GET, and that is now "everything except one route". The
# CORS allowlist gains POST, and a preflight now happens on this one call. That
# is a smaller price than putting somebody's portfolio in a log file.
#
# NO STATE EITHER. The holdings arrive, are used and are forgotten; nothing is
# stored, because there is nowhere to store it.
# --------------------------------------------------------------------------- #
PORTFOLIO_MAX_HOLDINGS = 40


class PortfolioRequest(BaseModel):
    """The body of the one POST.

    VALIDATED AS STRICTLY AS THE QUERY PARAMETERS IT REPLACED. Moving off the
    query string moves the input out of the logs, not out of reach — the ticker
    pattern still has to hold, because `candidate` is interpolated into a
    yfinance URL path, and the caps still have to hold, because one request here
    fans out to a batch download.
    """
    candidate: str = Field(..., pattern=TICKER_PATTERN)
    holdings: list[str] = Field(..., min_length=1, max_length=200)
    market: str = Field("US", pattern="^(US|ID|us|id)$")
    # Self-describing rather than positional. A parallel list aligned to
    # `holdings` would silently attach the wrong weight to the wrong name the
    # first time a symbol was dropped for thin history — a plausible wrong
    # answer rather than an error, which is the failure mode this codebase keeps
    # finding.
    weights: dict[str, float] = Field(default_factory=dict)


def _validated_weights(raw: dict) -> dict:
    """Ticker → weight, with the same rules the tickers themselves get."""
    out: dict = {}
    for ticker, value in (raw or {}).items():
        symbol = str(ticker).strip().upper()
        if not TICKER_RE.match(symbol):
            raise HTTPException(status_code=400,
                                detail=f"Not a valid ticker symbol in weights: {symbol!r}.")
        try:
            weight = float(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Weight for {symbol} must be a number.") from exc
        if not (weight > 0) or not math.isfinite(weight):
            raise HTTPException(status_code=400,
                                detail=f"Weight for {symbol} must be above zero.")
        out[symbol] = weight
    return out


@app.post("/api/portfolio")
def portfolio_context(body: PortfolioRequest):
    """Where a candidate sits against a book of holdings.

    Answers the question no single-ticker page can: is this the fourth copy of a
    bet already held? Correlation against each holding, how many INDEPENDENT
    positions the book really amounts to before and after, and what share of the
    portfolio's risk each name carries against its share of the money.

    It informs position size, which every other measured thing in this app
    refuses to do, and it is allowed to because the underlying claim was
    measured first: pairwise correlations persist year to year at rank
    correlations of 0.50-0.65 across four universes, where the composite
    ranking's information coefficient was indistinguishable from zero. See
    `scripts/measure_correlation_stability.py` and the caveat it also found —
    correlations run about 0.06 higher in the worst quarters, so an ordinary
    year's reading is a floor.

    A POST, alone in this app, because the input is a fact about the reader
    rather than about a company and URLs are logged by every hop that handles
    them. Nothing is stored either — see the note above the route.
    """
    raw = [t.strip() for t in body.holdings if t and t.strip()]
    bad = [t for t in raw if not TICKER_RE.match(t)]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"Not valid ticker symbols: {', '.join(bad[:5])}"
                   f"{'...' if len(bad) > 5 else ''}.")
    if not raw:
        raise HTTPException(status_code=400, detail="Provide at least one holding.")

    market = body.market
    # THE MARKET FOLLOWS THE SYMBOL, NOT THE DROPDOWN, and this route needed it
    # the moment it grew a benchmark. "ITMG.JK" left on the default US setting is
    # one of the two ways the README tells you to reach an IDX listing; before
    # this it resolved the right Indonesian company and then measured its shared
    # direction against ^GSPC, reporting "0% of it is the S&P 500" for a book of
    # Jakarta miners. Same bug `resolved_with_market` was written for, arriving
    # in a route that used to have no benchmark to get wrong.
    symbol, market = resolved_with_market(body.candidate, market)
    book = [s for s in dict.fromkeys(resolved(t, market) for t in raw) if s != symbol]
    if not book:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one holding other than the candidate itself.")
    if len(book) > PORTFOLIO_MAX_HOLDINGS:
        raise HTTPException(
            status_code=400,
            detail=f"This compares up to {PORTFOLIO_MAX_HOLDINGS} holdings at a time; "
                   f"this list has {len(book)}. A correlation matrix that size is also "
                   f"more than anyone reads.")

    result = portfolio.analyse(symbol, book, weights=_validated_weights(body.weights),
                               market_code=market)
    result["explain"] = explain.for_portfolio(result)
    return private_ok({"candidate": symbol, "market": market, **result})


# --------------------------------------------------------------------------- #
# Engine 2 — Technical analysis
# --------------------------------------------------------------------------- #
def technical_payload(symbol: str, range_key: str = "1y", sr_window: int = 10,
                      sr_levels: int = 6, market_code: str = "US") -> dict:
    """Engine 2 with its HTTP error mapping, so the route and the confluence
    leg fail identically instead of one of them leaking a class name."""
    try:
        return technical.analyze(
            symbol, range_key=range_key, sr_window=sr_window, sr_levels=sr_levels,
            market_code=market_code,
        )
    except technical.TechnicalError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/technical-analysis")
def technical_analysis(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    range: str = Query("1y", pattern="^(3mo|6mo|1y|2y|5y|10y|max)$"),
    sr_window: int = Query(10, ge=3, le=40),
    sr_levels: int = Query(6, ge=2, le=12),
):
    symbol, market = resolved_with_market(ticker, market)
    return ok(technical_payload(symbol, range, sr_window, sr_levels, market.upper()))


# --------------------------------------------------------------------------- #
# Engine 3 — Intrinsic value
# --------------------------------------------------------------------------- #
def _valuation_kwargs(
    market, engine="auto", growth=None, terminal=None, rate=None, n_sims=10000,
    sd_growth=None, sd_rate=None, sd_terminal=None, seed=42,
    fcf_basis="Latest fiscal year", dps_basis="Trailing 12 months",
    manual_base=None, manual_net_debt=None, manual_shares=None,
    manual_price=None, manual_payout=None,
) -> dict:
    """Route query parameters mapped onto the engine's keyword names.

    The defaults mirror the `/api/intrinsic-value` route's own, so a caller that
    wants the routed behaviour and nothing custom — the shortlist deepen step —
    can ask for it with `_valuation_kwargs(market=market)` instead of repeating
    seventeen positional arguments that would then silently drift from the
    route's defaults the next time one of them changes.
    """
    return dict(
        market_code=market.upper(),
        engine_choice=engine.lower(),
        growth=growth,
        terminal=terminal,
        rate_override=rate,
        n_sims=n_sims,
        sd_growth=sd_growth,
        sd_rate=sd_rate,
        sd_terminal=sd_terminal,
        seed=seed,
        fcf_basis=fcf_basis,
        dps_basis=dps_basis,
        manual_base=manual_base,
        manual_net_debt=manual_net_debt,
        manual_shares=manual_shares,
        manual_price=manual_price,
        manual_payout=manual_payout,
    )


def valuation_payload(symbol: str, **kwargs) -> dict:
    """Engine 3 with its HTTP error mapping.

    The 422 detail is a STRUCTURE, not a string: it carries `manualRequired`
    and the figures to prefill the rescue form with. Flattening it to
    `str(exc)` — which is what the confluence leg's generic handler used to do —
    silently costs the user the only path back from a Yahoo data gap.
    """
    try:
        payload = valuation.analyze(symbol, **kwargs)
    except valuation.ValuationError as exc:
        raise HTTPException(status_code=422, detail=exc.as_detail()) from exc
    payload["explain"] = explain.for_valuation(payload)
    return payload


@app.get("/api/intrinsic-value")
def intrinsic_value(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    engine: str = Query("auto", pattern="^(auto|dcf|ddm|DCF|DDM)$"),
    growth: Optional[float] = Query(None, ge=-0.50, le=1.00),
    terminal: Optional[float] = Query(None, ge=0.0, le=0.05),
    rate: Optional[float] = Query(None, gt=0.0, le=0.50),
    n_sims: int = Query(10000, ge=1000, le=25000),
    sd_growth: Optional[float] = Query(None, ge=0.0, le=0.20),
    sd_rate: Optional[float] = Query(None, ge=0.0, le=0.10),
    sd_terminal: Optional[float] = Query(None, ge=0.0, le=0.05),
    seed: int = Query(42, ge=0, le=10000),
    fcf_basis: str = Query("Latest fiscal year"),
    dps_basis: str = Query("Trailing 12 months"),
    manual_base: Optional[float] = Query(None),
    manual_net_debt: Optional[float] = Query(None),
    manual_shares: Optional[float] = Query(None, gt=0.0),
    manual_price: Optional[float] = Query(None, gt=0.0),
    manual_payout: Optional[float] = Query(None, ge=0.0, le=1.0),
):
    symbol, market = resolved_with_market(ticker, market)
    return ok(valuation_payload(symbol, **_valuation_kwargs(
        market, engine, growth, terminal, rate, n_sims, sd_growth, sd_rate,
        sd_terminal, seed, fcf_basis, dps_basis, manual_base, manual_net_debt,
        manual_shares, manual_price, manual_payout,
    )))


@app.get("/api/intrinsic-value/simulation")
def intrinsic_value_simulation(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    engine: str = Query("auto", pattern="^(auto|dcf|ddm|DCF|DDM)$"),
    growth: Optional[float] = Query(None, ge=-0.50, le=1.00),
    terminal: Optional[float] = Query(None, ge=0.0, le=0.05),
    rate: Optional[float] = Query(None, gt=0.0, le=0.50),
    n_sims: int = Query(10000, ge=1000, le=25000),
    sd_growth: Optional[float] = Query(None, ge=0.0, le=0.20),
    sd_rate: Optional[float] = Query(None, ge=0.0, le=0.10),
    sd_terminal: Optional[float] = Query(None, ge=0.0, le=0.05),
    seed: int = Query(42, ge=0, le=10000),
    fcf_basis: str = Query("Latest fiscal year"),
    dps_basis: str = Query("Trailing 12 months"),
    manual_base: Optional[float] = Query(None),
    manual_net_debt: Optional[float] = Query(None),
    manual_shares: Optional[float] = Query(None, gt=0.0),
    manual_price: Optional[float] = Query(None, gt=0.0),
    manual_payout: Optional[float] = Query(None, ge=0.0, le=1.0),
):
    """Every Monte Carlo draw as CSV — the full sample behind the percentiles.

    The run is seeded, so this reproduces exactly the distribution the JSON
    endpoint summarised for the same query string.
    """
    symbol, market = resolved_with_market(ticker, market)
    payload = valuation_payload(symbol, with_simulation=True, **_valuation_kwargs(
        market, engine, growth, terminal, rate, n_sims, sd_growth, sd_rate,
        sd_terminal, seed, fcf_basis, dps_basis, manual_base, manual_net_debt,
        manual_shares, manual_price, manual_payout,
    ))

    sims = payload.pop("_simulation")
    return csv_response(sims, f"{symbol}_{payload['engine'].lower()}_monte_carlo.csv")


# --------------------------------------------------------------------------- #
# Engine 4 — accounting quality and solvency
# --------------------------------------------------------------------------- #
def quality_payload(symbol: str) -> dict:
    """Piotroski / Altman / Beneish from the statements already fetched.

    A SYMBOL THAT DOES NOT EXIST IS A 404, NOT A REFUSAL. This lens has two very
    different "no score" outcomes and they must not look alike: `applicable:
    false` is a DESIGNED refusal — the three models were built on non-financial
    firms and do not transfer to a bank — while a symbol nothing came back for
    is a failed lookup. Reporting the second as the first told a reader that a
    company files no statements when in fact no such company was found, and it
    devalued the refusal, which is one of the more useful things here. The other
    three lenses already 404 on this input; now so does this one.
    """
    company = valuation.fetch_company(symbol)
    if not company.get("ok"):
        raise HTTPException(
            status_code=404,
            detail=f"No company data came back for '{symbol}'. {symbols.hint(symbol)}",
        )
    # The symbol reaches the lens only so the validation-domain block can say
    # whether THIS use sits inside each screen's published sample. No score
    # depends on it.
    #
    # THE MARKET COMES FROM THE RESOLVED SYMBOL, NOT FROM THE QUERY PARAMETER.
    # Asking "is this an Indonesian listing?" is a question about the security,
    # and reading the dropdown for it told a reader that TLKM.JK was a US
    # listing — the class of silent mismatch `symbols.py` exists to prevent.
    #
    # This lens got the rule first and the others have since been brought in
    # line: the conventions to VALUE with follow the listing too, because the
    # alternative was ITMG.JK priced in dollars off a US risk-free rate. The
    # routes now hand every lens a market derived the same way — see
    # `resolved_with_market` — so this call and its neighbours cannot diverge.
    payload = quality.analyze(company, symbol=symbol,
                              market_code=symbols.market_of(symbol))
    payload["explain"] = explain.for_quality(payload)
    return payload


@app.get("/api/quality")
def quality_scores(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
):
    """Fundamental strength, distress risk and earnings-manipulation screens.

    Returns `applicable: false` for banks and insurers rather than a number:
    none of the three models was built on financial firms and none transfers.
    """
    symbol, market = resolved_with_market(ticker, market)
    return ok({"ticker": symbol, **quality_payload(symbol)})


# --------------------------------------------------------------------------- #
# Signal validation — does the anomaly flag predict anything?
# --------------------------------------------------------------------------- #
@app.get("/api/event-study")
def event_study(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    period: str = Query("5y", pattern="^(2y|5y|max)$"),
    mode: str = Query("threshold", pattern="^(threshold|mad|quota)$"),
    score_threshold: float = Query(-0.10, ge=-0.50, le=0.50),
):
    """Cumulative abnormal returns after each detected anomaly.

    The one number that decides whether the flow engine is worth attention. A
    long window is the default because an event study needs events: at a strict
    cutoff a two-year window can yield fewer than ten, which is not enough to
    say anything. Walk-forward mode is not offered here — it would cost minutes
    and the market-model estimation already excludes look-ahead.
    """
    symbol, market = resolved_with_market(ticker, market)
    config = AnalysisConfig(period=period, detection_mode=mode,
                            score_threshold=score_threshold)
    try:
        result = WhaleTracker(config).analyze(symbol)
    except DataFetchError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WhaleTrackerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    index_symbol = riskmodel.MARKET_INDEX.get(market.upper(), "^GSPC")
    market_history = market_data.index_history(index_symbol, period)
    if market_history is None:
        raise HTTPException(
            status_code=503,
            detail=f"Could not fetch {index_symbol}, so abnormal returns cannot "
                   f"be measured against a market model.",
        )

    # No timezone stripping here any more. Three frames used to be localised by
    # hand at this call site because the flow engine handed back whatever
    # yfinance returned; `market_data.normalise` now guarantees a tz-naive index
    # on everything, so alignment is the boundary's job rather than the route's.
    study = eventstudy.run_event_study(result.data, market_history, result.anomalies)

    # Bernard & Thomas: an anomaly beside an earnings print has a benign
    # explanation, and the drift afterwards is a documented effect rather than
    # anyone's footprint.
    pead = eventstudy.tag_earnings_proximity(
        result.anomalies, market_data.earnings_dates(symbol))

    return ok({
        "ticker": symbol,
        "benchmark": index_symbol,
        "period": period,
        "anomalies": len(result.anomalies),
        "study": study,
        "earningsProximity": pead,
    })


# --------------------------------------------------------------------------- #
# Contextual catalyst
# --------------------------------------------------------------------------- #
@app.get("/api/news")
def ticker_news(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    limit: int = Query(5, ge=1, le=10),
):
    """Third-party headlines. Display-only context — never an instruction source."""
    symbol, market = resolved_with_market(ticker, market)
    return ok({"ticker": symbol, "items": news.fetch_news(symbol, limit=limit)})


# --------------------------------------------------------------------------- #
# All three at once
# --------------------------------------------------------------------------- #
@app.get("/api/confluence")
async def confluence(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    period: str = Query("2y", pattern="^(6mo|1y|2y|5y|max)$"),
    range: str = Query("1y", pattern="^(3mo|6mo|1y|2y|5y|10y|max)$"),
    mode: str = Query("threshold", pattern="^(threshold|mad|quota|walkforward)$"),
    contamination: float = Query(0.02, gt=0.0, lt=0.5),
    mad_k: float = Query(3.0, gt=0.0),
    score_threshold: float = Query(-0.10, ge=-0.50, le=0.50),
    recent_days: int = Query(10, ge=1, le=60),
    min_turnover: float = Query(0.0, ge=0.0),
    sr_window: int = Query(10, ge=3, le=40),
    sr_levels: int = Query(6, ge=2, le=12),
    news_limit: int = Query(5, ge=1, le=10),
):
    """Every lens for one ticker, in ONE invocation.

    Four separate client fetches meant four serverless cold starts, each paying
    the numpy + pandas + scipy + scikit-learn import, and each re-resolving the
    same symbol. This runs all of it concurrently in threads against a single
    resolved symbol.

    Every tuning parameter the individual routes accept is accepted here too.
    That is load-bearing rather than cosmetic: without them this endpoint would
    quietly run the DEFAULT detection mode while the user's ticker bar showed
    the one they picked — the same class of silent mismatch `_lib/symbols.py`
    exists to prevent.

    Each leg reports its own success or failure, so a ticker with no dividend
    history still returns its anomaly and technical panels, and a valuation
    data gap still arrives as the structured `manualRequired` payload.

    Carries a `synthesis` block: what the four lenses add up to, in sentences.
    It is a DESCRIPTION and never a recommendation — see `explain.for_synthesis`
    for why a single buy/hold/sell score is refused permanently.

    Carries a `preTrade` block too: the conditions that would give a careful
    buyer pause, each with the measured share of a universe it fires on. Like
    the synthesis it reads the ASSEMBLED payload rather than running anything,
    so it costs no extra fetch and cannot drift from the figures the panels
    render. See `_lib/pretrade.py` for why an uncalibrated check is withheld and
    why a common one is demoted from a flag to a base condition.
    """
    symbol, market = resolved_with_market(ticker, market)

    async def leg(name, fn):
        try:
            return name, {"ok": True, "data": await asyncio.to_thread(fn)}
        except HTTPException as exc:
            return name, {"ok": False, "error": exc.detail}
        except Exception as exc:  # one leg must not be able to sink the others
            return name, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    results = await asyncio.gather(
        leg("anomaly", lambda: whale_payload(
            symbol, period=period, mode=mode, contamination=contamination,
            mad_k=mad_k, score_threshold=score_threshold, recent_days=recent_days,
            min_turnover=min_turnover,
        )),
        leg("technical", lambda: technical_payload(
            symbol, range_key=range, sr_window=sr_window, sr_levels=sr_levels,
            market_code=market.upper(),
        )),
        leg("valuation", lambda: valuation_payload(symbol, market_code=market.upper())),
        leg("quality", lambda: quality_payload(symbol)),
        leg("news", lambda: {"ticker": symbol,
                             "items": news.fetch_news(symbol, limit=news_limit)}),
    )
    legs = dict(results)
    # The synthesis reads the ASSEMBLED payload rather than running its own
    # analysis, for the same reason every `explain` layer in this app does: it
    # must quote the figures the panels actually render, and a parallel
    # computation would eventually drift from them. A failed leg becomes a
    # stated blind spot inside it rather than an exception.
    return ok({"ticker": symbol, **legs,
               # The market reaches the synthesis for the same reason it reaches
               # `pretrade.assess`, and is taken from the RESOLVED symbol for the
               # same reason too: the measured agreement between the two families
               # was taken on a different population in each market, and a bare
               # code with the wrong market selected would quote the wrong one.
               "synthesis": explain.for_synthesis(
                   legs, market=symbols.market_of(symbol)),
               # The market decides which population the firing rates describe.
               # Taken from the RESOLVED symbol rather than the query parameter,
               # for the same reason every engine downstream of `symbols.resolve`
               # takes it from there: the suffix is what actually determines the
               # listing, and a bare code with the wrong market selected would
               # otherwise be scored against the wrong universe.
               "preTrade": pretrade.assess(legs, market=symbols.market_of(symbol))})
