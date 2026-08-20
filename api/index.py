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
import yfinance as yf
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from _lib import (accumulation, eventstudy, microstructure, news, quality,
                  riskmodel, symbols, technical, valuation)
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


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "OPTIONS"],
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


def resolved(ticker: str, market: str) -> str:
    try:
        return symbols.resolve(ticker, market)
    except symbols.SymbolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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

    return {
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
    symbol = resolved(ticker, market)
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
# Engine 2 — Technical analysis
# --------------------------------------------------------------------------- #
def technical_payload(symbol: str, range_key: str = "1y", sr_window: int = 10,
                      sr_levels: int = 6) -> dict:
    """Engine 2 with its HTTP error mapping, so the route and the confluence
    leg fail identically instead of one of them leaking a class name."""
    try:
        return technical.analyze(
            symbol, range_key=range_key, sr_window=sr_window, sr_levels=sr_levels
        )
    except technical.TechnicalError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/technical-analysis")
def technical_analysis(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    range: str = Query("1y", pattern="^(3mo|6mo|1y|2y|5y)$"),
    sr_window: int = Query(10, ge=3, le=40),
    sr_levels: int = Query(6, ge=2, le=12),
):
    symbol = resolved(ticker, market)
    return ok(technical_payload(symbol, range, sr_window, sr_levels))


# --------------------------------------------------------------------------- #
# Engine 3 — Intrinsic value
# --------------------------------------------------------------------------- #
def _valuation_kwargs(
    market, engine, growth, terminal, rate, n_sims, sd_growth, sd_rate, sd_terminal,
    seed, fcf_basis, dps_basis, manual_base, manual_net_debt, manual_shares,
    manual_price, manual_payout,
) -> dict:
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
        return valuation.analyze(symbol, **kwargs)
    except valuation.ValuationError as exc:
        raise HTTPException(status_code=422, detail=exc.as_detail()) from exc


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
    symbol = resolved(ticker, market)
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
    symbol = resolved(ticker, market)
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
    """Piotroski / Altman / Beneish from the statements already fetched."""
    return quality.analyze(valuation.fetch_company(symbol))


@app.get("/api/quality")
def quality_scores(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
):
    """Fundamental strength, distress risk and earnings-manipulation screens.

    Returns `applicable: false` for banks and insurers rather than a number:
    none of the three models was built on financial firms and none transfers.
    """
    symbol = resolved(ticker, market)
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
    symbol = resolved(ticker, market)
    config = AnalysisConfig(period=period, detection_mode=mode,
                            score_threshold=score_threshold)
    try:
        result = WhaleTracker(config).analyze(symbol)
    except DataFetchError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WhaleTrackerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    index_symbol = riskmodel.MARKET_INDEX.get(market.upper(), "^GSPC")
    try:
        market_history = yf.Ticker(index_symbol).history(period=period, auto_adjust=True)
    except Exception:
        market_history = None
    if market_history is None or market_history.empty:
        raise HTTPException(
            status_code=503,
            detail=f"Could not fetch {index_symbol}, so abnormal returns cannot "
                   f"be measured against a market model.",
        )
    if getattr(market_history.index, "tz", None) is not None:
        market_history.index = market_history.index.tz_localize(None)

    prices = result.data.copy()
    if getattr(prices.index, "tz", None) is not None:
        prices.index = prices.index.tz_localize(None)
    events = result.anomalies.copy()
    if getattr(events.index, "tz", None) is not None:
        events.index = events.index.tz_localize(None)

    study = eventstudy.run_event_study(prices, market_history, events)

    # Bernard & Thomas: an anomaly beside an earnings print has a benign
    # explanation, and the drift afterwards is a documented effect rather than
    # anyone's footprint.
    try:
        earnings = yf.Ticker(symbol).earnings_dates
        earnings_index = list(earnings.index) if earnings is not None else []
    except Exception:
        earnings_index = []
    pead = eventstudy.tag_earnings_proximity(events, earnings_index)

    return ok({
        "ticker": symbol,
        "benchmark": index_symbol,
        "period": period,
        "anomalies": len(events),
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
    symbol = resolved(ticker, market)
    return ok({"ticker": symbol, "items": news.fetch_news(symbol, limit=limit)})


# --------------------------------------------------------------------------- #
# All three at once
# --------------------------------------------------------------------------- #
@app.get("/api/confluence")
async def confluence(
    ticker: str = Query(..., pattern=TICKER_PATTERN),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    period: str = Query("2y", pattern="^(6mo|1y|2y|5y|max)$"),
    range: str = Query("1y", pattern="^(3mo|6mo|1y|2y|5y)$"),
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
    """
    symbol = resolved(ticker, market)

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
        )),
        leg("valuation", lambda: valuation_payload(symbol, market_code=market.upper())),
        leg("quality", lambda: quality_payload(symbol)),
        leg("news", lambda: {"ticker": symbol,
                             "items": news.fetch_news(symbol, limit=news_limit)}),
    )
    return ok({"ticker": symbol, **dict(results)})
