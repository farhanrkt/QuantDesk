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
GET /api/news                       contextual catalyst headlines
GET /api/confluence                 all three at once, run concurrently
"""

from __future__ import annotations

import asyncio
import io
import sys

from pathlib import Path
sys.path.append(str(Path(__file__).parent))
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from _lib import news, symbols, technical, valuation
from _lib.jsonsafe import clean
from _lib.whale import AnalysisConfig, DataFetchError, WhaleTracker, WhaleTrackerError

app = FastAPI(title="QuantDesk API", version="1.1.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # same-origin on Vercel; open for local dev
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

CACHE = "public, s-maxage=60, stale-while-revalidate=300"


def ok(payload: dict) -> JSONResponse:
    # Cache at the edge: quotes move, but not within 60s, and every engine
    # re-runs a network fetch that we do not want to pay for on each keystroke.
    return JSONResponse(content=clean(payload), headers={"Cache-Control": CACHE})


def resolved(ticker: str, market: str) -> str:
    try:
        return symbols.resolve(ticker, market)
    except symbols.SymbolError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
        "engines": ["isolation-forest", "technical-analysis", "intrinsic-value"],
        "extras": ["screener", "news", "simulation-csv"],
    })


# --------------------------------------------------------------------------- #
# Engine 1 — Isolation Forest
# --------------------------------------------------------------------------- #
def whale_payload(symbol: str, period: str = "2y", mode: str = "threshold",
                  contamination: float = 0.02, mad_k: float = 3.0,
                  score_threshold: float = -0.10, recent_days: int = 10) -> dict:
    config = AnalysisConfig(
        period=period,
        detection_mode=mode,
        contamination=contamination,
        mad_k=mad_k,
        score_threshold=score_threshold,
    )
    try:
        result = WhaleTracker(config).analyze(symbol)
    except DataFetchError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WhaleTrackerError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    frame = result.data
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
        for index, row in frame.iterrows()
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

    return {
        "ticker": result.ticker,
        "config": {
            "period": period, "mode": mode,
            "contamination": contamination, "madK": mad_k,
            "scoreThreshold": config.score_threshold,
            "rollingWindow": config.rolling_window,
            "mfiWindow": config.mfi_window,
        },
        "stats": {
            "totalDays": result.total_days,
            "anomalyCount": result.anomaly_count,
            "anomalyRate": result.anomaly_rate,
            # Two horizons, deliberately separate. `netFlowBias` summarises the
            # whole look-back (two years by default); `recentFlowBias` is the
            # current-state reading and is what the confluence view votes with.
            "netFlowBias": result.net_flow_bias,
            "recentFlowBias": result.recent_flow_bias(recent_days),
            "maxStrength": int(result.anomalies["Strength"].max()) if result.anomaly_count else 0,
            "recentCount": int(len(recent)),
            "recentDays": recent_days,
            "latestClose": float(frame["Close"].iloc[-1]),
            "latestMfi": float(frame["MFI"].iloc[-1]),
        },
        "series": series,
        "anomalies": anomalies,
    }


@app.get("/api/isolation-forest")
def isolation_forest(
    ticker: str = Query(..., min_length=1, max_length=20),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    period: str = Query("2y", pattern="^(6mo|1y|2y|5y|max)$"),
    mode: str = Query("threshold", pattern="^(threshold|mad|quota|walkforward)$"),
    contamination: float = Query(0.02, gt=0.0, lt=0.5),
    mad_k: float = Query(3.0, gt=0.0),
    score_threshold: float = Query(-0.10, ge=-0.50, le=0.50),
    recent_days: int = Query(10, ge=1, le=60),
):
    symbol = resolved(ticker, market)
    return ok(whale_payload(symbol, period, mode, contamination, mad_k,
                            score_threshold, recent_days))


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
):
    """Cross-asset scan: which names show fresh whale activity in the last N days.

    `market` decides what happens to BARE codes only; anything already carrying
    a suffix keeps it. So a mixed universe ("AAPL, BBCA.JK") resolves correctly
    under market=US, and market=ID is for a list of bare Indonesian codes.
    Passing market=ID with bare US tickers turns them into AAPL.JK and friends,
    which fetch nothing and are dropped — the caller should default to US.
    """
    raw = [t.strip() for t in tickers.replace("\n", ",").split(",") if t.strip()]
    universe = list(dict.fromkeys(resolved(t, market) for t in raw))
    if not universe:
        raise HTTPException(status_code=400, detail="Provide at least one ticker.")
    if len(universe) > 50:
        raise HTTPException(
            status_code=400,
            detail="Universe too large. Limit the scan to 50 symbols to avoid rate limiting.",
        )

    config = AnalysisConfig(
        period=period, detection_mode=mode, contamination=contamination,
        mad_k=mad_k, score_threshold=score_threshold,
    )
    table = WhaleTracker(config).scan_watchlist(universe, recent_days=recent_days)

    rows = [
        {
            "ticker": r["Ticker"],
            "recentAnomalies": int(r["Recent Anomalies"]),
            "dominantFlow": r["Dominant Flow"],
            "topStrength": int(r["Top Strength"]),
            "latestSignal": r["Latest Signal"],
            "latestTag": r["Latest Tag"],
            "latestClose": float(r["Latest Close"]),
            "topRvol": float(r["RVOL (top)"]),
        }
        for _, r in table.iterrows()
    ]
    return ok({
        "scanned": len(universe),
        "universe": universe,
        "recentDays": recent_days,
        "config": {"period": period, "mode": mode},
        "rows": rows,
    })


# --------------------------------------------------------------------------- #
# Engine 2 — Technical analysis
# --------------------------------------------------------------------------- #
@app.get("/api/technical-analysis")
def technical_analysis(
    ticker: str = Query(..., min_length=1, max_length=20),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    range: str = Query("1y", pattern="^(3mo|6mo|1y|2y|5y)$"),
    sr_window: int = Query(10, ge=3, le=40),
    sr_levels: int = Query(6, ge=2, le=12),
):
    symbol = resolved(ticker, market)
    try:
        payload = technical.analyze(
            symbol, range_key=range, sr_window=sr_window, sr_levels=sr_levels
        )
    except technical.TechnicalError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ok(payload)


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


@app.get("/api/intrinsic-value")
def intrinsic_value(
    ticker: str = Query(..., min_length=1, max_length=20),
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
    try:
        payload = valuation.analyze(symbol, **_valuation_kwargs(
            market, engine, growth, terminal, rate, n_sims, sd_growth, sd_rate,
            sd_terminal, seed, fcf_basis, dps_basis, manual_base, manual_net_debt,
            manual_shares, manual_price, manual_payout,
        ))
    except valuation.ValuationError as exc:
        # Structured, so the client can tell "Yahoo has a gap you can fill in"
        # apart from "this business cannot be valued this way".
        raise HTTPException(status_code=422, detail=exc.as_detail())
    return ok(payload)


@app.get("/api/intrinsic-value/simulation")
def intrinsic_value_simulation(
    ticker: str = Query(..., min_length=1, max_length=20),
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
    try:
        payload = valuation.analyze(symbol, with_simulation=True, **_valuation_kwargs(
            market, engine, growth, terminal, rate, n_sims, sd_growth, sd_rate,
            sd_terminal, seed, fcf_basis, dps_basis, manual_base, manual_net_debt,
            manual_shares, manual_price, manual_payout,
        ))
    except valuation.ValuationError as exc:
        raise HTTPException(status_code=422, detail=exc.as_detail())

    sims = payload.pop("_simulation")
    return csv_response(sims, f"{symbol}_{payload['engine'].lower()}_monte_carlo.csv")


# --------------------------------------------------------------------------- #
# Contextual catalyst
# --------------------------------------------------------------------------- #
@app.get("/api/news")
def ticker_news(
    ticker: str = Query(..., min_length=1, max_length=20),
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
    ticker: str = Query(..., min_length=1, max_length=20),
    market: str = Query("US", pattern="^(US|ID|us|id)$"),
    period: str = Query("2y", pattern="^(6mo|1y|2y|5y|max)$"),
    range: str = Query("1y", pattern="^(3mo|6mo|1y|2y|5y)$"),
):
    """Runs the three engines concurrently in threads, all on the SAME resolved
    symbol. Each leg reports its own success or failure — a ticker with no
    dividend history should still return its anomaly and technical panels."""
    symbol = resolved(ticker, market)

    async def leg(name, fn):
        try:
            return name, {"ok": True, "data": await asyncio.to_thread(fn)}
        except HTTPException as exc:
            return name, {"ok": False, "error": exc.detail}
        except Exception as exc:  # noqa: BLE001 — one leg must not sink the others
            return name, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    results = await asyncio.gather(
        leg("anomaly", lambda: whale_payload(symbol, period=period)),
        leg("technical", lambda: technical.analyze(symbol, range_key=range)),
        leg("valuation", lambda: valuation.analyze(symbol, market_code=market.upper())),
    )
    return ok({"ticker": symbol, **dict(results)})
