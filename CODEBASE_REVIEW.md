# QuantDesk — Codebase & Product Review

**Reviewed:** 20 August 2026 · `main` @ `0645002` · ~2,600 LOC Python + ~2,700 LOC TypeScript

---

## 0. What this app is

**Deduced purpose.** A three-lens equity research desk. One ticker is read simultaneously by three independent models, and the product's actual thesis — stated explicitly in `app/page.tsx:108` and built into `ConfluenceRail` — is that *agreement between independent methods is the finding*, not any single model's output.

| Engine | Method | Source |
|---|---|---|
| Flow / anomalies | Isolation Forest over 6 behavioural features (return, RVOL, \|return\|, MFI, OBV z-score, intraday range), + flow classification and a 0–100 strength score | `api/_lib/whale.py` |
| Technicals | SMA 50/200, RSI (Wilder), MACD, Bollinger, clustered support/resistance via `argrelextrema`, golden/death cross events, narrative readout | `api/_lib/technical.py` |
| Intrinsic value | DCF or DDM (sector-routed), CAPM/WACC build-up, 5-year explicit + Gordon terminal, 10k-draw Monte Carlo | `api/_lib/valuation.py` |

Plus a cross-asset screener, Google News RSS catalyst panel, and CSV export at every level.

**Target audience.** Self-directed retail/prosumer investors and finance students, with a deliberate and unusual **dual US + Indonesian (IDX)** focus — market conventions (Rf, ERP, tax), currency formatting, `.JK` symbol resolution and Indonesian-language news queries are all first-class. The IDX support is the genuine differentiator; nobody else is doing DDM-on-IDX-banks with a manual-input fallback for Yahoo's gaps.

**Stack.** Next.js 15.1.11 (App Router, React 19, all client-side) · Tailwind + Recharts · FastAPI on a single Vercel Python serverless function · numpy/pandas/scipy/scikit-learn · yfinance as the sole market data source. No database, no auth, no state persistence.

**Overall assessment.** This is unusually thoughtful code for a solo project. The module docstrings don't just describe behaviour — they document *past bugs and the reasoning that fixed them* (`symbols.py` on the BBCA/BBCA.JK collision, `whale.py` caveat C on `contamination="auto"` collapsing threshold-mode into quota-mode). That is senior-level work. The problems below are almost entirely **operational** — the things that separate a well-reasoned prototype from something that survives contact with real traffic — plus one class of frontend state bug that is the *same species* as the symbol bug the codebase is proud of having fixed.

---

# 🟢 CRITICAL ISSUES — **all resolved, 20 Aug 2026**

*Implemented and verified: `npm audit --omit=dev` reports 0 vulnerabilities, 122 offline
tests pass, `ruff`/`tsc --noEmit`/`eslint`/`next build` are clean, and the guards were
exercised against the live API. Each heading records what changed.*

### ✅ C1. Next.js upgraded 15.1.11 → 15.5.23; audit now clean
`package.json:14`

`npm audit --omit=dev` reports **4 vulnerabilities (1 critical, 3 high)** in production dependencies. The Next.js entry alone lists ~20 advisories, including cache poisoning in RSC responses, middleware/proxy bypass, HTTP request smuggling in rewrites, SSRF via WebSocket upgrades, and XSS in App Router apps using CSP nonces. `sharp` (libvips CVE-2026-33327/33328/35590/35591) and `nanoid` are also flagged.

Git history shows a merged branch named `vercel/react-server-components-cve-vu-6luodm` — a patch was applied once, but the pin has since fallen ~4 minor versions behind.

```bash
npm install next@latest && npm audit --omit=dev
```

Verify the build after: 15.5 is a minor bump from 15.1 with no App Router breaking changes for this codebase's surface (no middleware, no `next/image`, no RSC data fetching).

---

### ✅ C2. Amplification bounded and per-IP rate limiting added
`api/index.py:205-260`

There is no auth, no rate limit, no quota, and no per-IP budget anywhere in the app. `/api/screener` accepts up to 50 symbols and, for each, performs a **yfinance network fetch plus a full IsolationForest fit** (`whale.py:537-596`, 8 threads). One unauthenticated HTTP request therefore triggers up to 50 upstream Yahoo calls and 50 model fits.

Three separate consequences, all of which materialise under trivially small abuse:

1. **Yahoo rate-limits / IP-bans you.** yfinance is an unofficial scraper against an undocumented endpoint. Yahoo throttles aggressively by source IP. On Vercel your function shares egress IPs — a burst of screener calls gets the pool throttled and **every engine in the app starts returning "No data found"** with no way to distinguish that from a bad ticker.
2. **Your Vercel bill.** 60s `maxDuration` × unbounded concurrency × a ~250 MB dependency closure per invocation.
3. **`mode=walkforward` on 50 symbols will always time out.** Walk-forward refits every 5 steps over ~500 rows (`whale.py:417-440`) ≈ 88 fits + 440 scoring calls *per ticker*. At 8 workers across 50 tickers this comfortably exceeds 60s. The UI warns the user (`ScreenerPanel.tsx:150`) but the API accepts the request anyway and returns a non-JSON 504 that the client renders as a bare `Request failed (504)`.

**Fix, in order of effort:**
- Rate limit at the edge — Vercel Firewall rules, or `@upstash/ratelimit` in a Next.js middleware in front of `/api/*`. Per-IP: ~30 req/min general, ~3 req/min for `/api/screener`.
- Reject `mode=walkforward` when `len(universe) > 5`, server-side, with a clear 400.
- Lower the screener cap from 50 to ~20 until there's a job queue (see A3).

---

### ✅ C3. 122-test offline suite + CI — and it already caught a live bug
No test files, no CI, no `.github/`.

This is the highest-leverage gap in the repo, and the codebase itself makes the argument. `symbols.py:9-16` documents a bug where three panels showed *two different securities* under one ticker with no error. `whale.py:44-53` documents `threshold` mode silently behaving identically to `quota` mode on every input. Both were **silent wrong answers** — the failure class where a test suite pays for itself immediately, and the only class that matters for a tool people make money decisions with.

Nothing prevents either from regressing today.

**Minimum viable suite** (a day's work, most of the value):

| Test | Why |
|---|---|
| `resolve()` idempotency + explicit-suffix-wins, table-driven | Locks the `symbols.py` fix |
| `threshold` vs `quota` produce *different* flag sets on synthetic OHLCV | Locks the caveat-C fix |
| Golden-file: fixed synthetic OHLCV → indicator values (SMA/RSI/MACD/BB) within 1e-9 | Catches pandas/numpy upgrade drift |
| `pv_of_growing_stream` vs a closed-form Gordon calculation | Locks the valuation core |
| Monte Carlo determinism: same seed + params → identical percentiles | The CSV route promises exactly this (`index.py:369-373`) |
| `run_monte_carlo` terminal-growth clamp never lets `gt >= r` | Prevents an infinite terminal value |
| `clean()` on NaN/inf/NaT/np scalars | The whole wire format depends on it |

All of these run offline against fixtures — **no network, no yfinance**. Add `pytest` + a GitHub Actions workflow running `pytest`, `ruff`, and `tsc --noEmit`.

---

### ✅ C4. `ticker` is now pattern-constrained on every route
`api/index.py:188, 207, 268, 315, 349, 393`

Every other query parameter is pattern-constrained (`market`, `period`, `mode`, `range`). `ticker` is only length-bounded:

```python
ticker: str = Query(..., min_length=1, max_length=20)   # no pattern
```

That value reaches two places it shouldn't reach unvalidated:

1. **yfinance URL path.** yfinance interpolates the symbol into `.../v8/finance/chart/{ticker}`. Path separators and traversal sequences are not neutralised by the library.
2. **A response header.** `index.py:87` builds `f'attachment; filename="{symbol}_..._monte_carlo.csv"'`. A quote character breaks the header; a CRLF is rejected by `h11` and surfaces as a 500 rather than an injection — so the practical severity is low, but this is unvalidated user input flowing into a header, which is a pattern you should never leave in place.

**Fix — one line, applied to all six routes:**

```python
TICKER_RE = r"^[A-Za-z0-9.\-^=]{1,20}$"
ticker: str = Query(..., pattern=TICKER_RE)
```

`^` and `=` are needed for index (`^TNX`) and FX (`EURUSD=X`) symbols; `-` for crypto pairs (`BTC-USD`). For `/api/screener`, apply the same regex per element after splitting (`index.py:225`).

---

# 🟢 QUICK WINS — **all resolved, 20 Aug 2026**

*Every item below has been implemented and verified (`tsc --noEmit` strict, `next lint`, `next build`,
and a live browser pass against the real engines). Each heading records what changed.*

### ✅ Q1. The frontend never called `/api/confluence` — now it does — the optimisation is already written and unused
`api/index.py:405-430` vs `lib/api.ts:166`

`/api/confluence` exists specifically to run all three engines concurrently in threads against one resolved symbol, with per-leg error isolation. It is **dead code — nothing in `lib/`, `app/` or `components/` references it.**

Instead `run()` fires four separate `fetch` calls, which means **four independent serverless invocations**, each cold-starting numpy + pandas + scipy + scikit-learn, and each re-resolving the same symbol.

Upstream calls per single ticker run today:

| Route | Yahoo calls |
|---|---|
| `/api/isolation-forest` | 1 (`Ticker.history`) |
| `/api/technical-analysis` | 2 (`yf.download` + `fast_info`) |
| `/api/intrinsic-value` | ~5–7 (`info`, `fast_info`, `dividends`, income/balance/cashflow, **plus `^TNX` every single time**) |
| `/api/news` | 1 (Google RSS) |

≈ **9–11 upstream fetches and 4 cold starts per ticker.** Switching the client to the existing `/api/confluence` endpoint collapses that to one invocation. It's a ~20-line change in `lib/api.ts`, and the server side is already written and tested-by-design (each leg reports its own `{ok, error}`).

Keep the individual routes for the "refine one engine" flows — they're correct for that.

---

### ✅ Q2. Screener rows are now clickable
`components/ScreenerPanel.tsx:187`

The screener's entire purpose is *find an interesting name*. Having found one, the user must read the ticker, switch tabs, retype it into the ticker bar, and re-select the market. Every session's most important interaction is a manual copy-paste.

Make the ticker cell a button that calls `onRun({...INITIAL, ticker: r.ticker, market: r.ticker.endsWith(".JK") ? "ID" : "US"})` and switches to the Flow tab. Lift `handleRun` down as a prop. **~10 lines, and it's the single biggest UX improvement available in this codebase.**

---

### ✅ Q3. Valuation assumption state no longer goes stale across tickers — same bug class as the symbol collision
`components/ValuationPanel.tsx:54`, `components/ValuationControls.tsx:110-131`

`<ValuationControls>` has no `key`, and there is **no `useEffect` anywhere in the codebase** (verified). All its state comes from `useState` initialisers, which run once on mount. The component stays mounted across ticker changes, so:

- Run **AAPL** (DCF, growth default 10%) → run **JPM** (routes to DDM, whose default is 5%). The growth field still reads 10%. Press "Re-run valuation" and you value a bank on the DCF default.
- Enable manual input mode for a gap-y IDX listing, supply base FCF / shares / price → load a different company → press "Re-run valuation". **Company A's manual figures are silently applied to company B.** `run()` clears `lastValuation.current` (`lib/api.ts:164`) so the *initial* run is clean — but the control state isn't, so the first refine is wrong.
- `basisChoice` persists and may not exist in the new ticker's `basisOptions`, leaving the `<select>` displaying a value that isn't in its own option list.

This is exactly the failure mode `symbols.py:14-16` calls out: *"a plausible-looking wrong answer, which is the worst kind."*

**Fix — one line:**
```tsx
<ValuationControls key={`${data.ticker}:${data.engine}`} ... />
```

---

### ✅ Q4. Requests are now cancelled and sequence-guarded
`lib/api.ts:118-167`

`settle()` has no `AbortController` and no sequence guard. Run `AAPL`, then immediately `NVDA`: four in-flight requests per ticker, resolving at wildly different speeds (valuation makes ~6 upstream calls; anomaly makes 1). AAPL's slow valuation can land *after* NVDA's fast anomaly, and the page then shows **NVDA flow next to AAPL valuation under one header** — with `ConfluenceRail` computing an agreement score across two different companies.

**Fix:** a monotonic run counter checked before `set()`, or an `AbortController` per run stored in a ref and aborted at the top of `run()`.

---

### ✅ Q5. The client no longer suppresses the edge cache
`lib/api.ts:25` vs `api/index.py:63`

The API sets `Cache-Control: public, s-maxage=60, stale-while-revalidate=300` with a well-reasoned comment about not re-paying for network fetches on every keystroke. The client then sends every request with `cache: "no-store"`, and per RFC 9111 the `no-store` **request** directive instructs *caches* — including shared ones — not to store the request or its response.

So the 60s edge cache is plausibly never exercised. **Verify before changing anything:** check the `x-vercel-cache` response header in DevTools (`MISS` on every repeat request confirms it). If confirmed, drop `cache: "no-store"` — the CDN's 60s TTL is exactly the freshness policy you want, and it's the cheapest single fix for both latency and the Yahoo rate-limit exposure in C2.

---

### ✅ Q6. Security headers added, CORS gated
`next.config.mjs`

No `headers()` block at all. Add:

```js
async headers() {
  return [{
    source: "/:path*",
    headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
      { key: "Content-Security-Policy", value: "default-src 'self'; frame-ancestors 'none'; ..." },
    ],
  }];
}
```

`frame-ancestors 'none'` matters here specifically: an unauthenticated financial tool is a clipboard-hijacking / clickjacking target for "sign this transaction" overlays.

Related, in `api/index.py:56-61`: `allow_origins=["*"]` with the comment "same-origin on Vercel; open for local dev". Gate it on an env var so production is same-origin only — combined with C2, the wildcard is what lets any third-party site embed your compute for free.

---

### ✅ Q7. `^TNX` is now fetched once per day
`api/_lib/valuation.py:192-203`

The US 10-year Treasury yield is refetched on **every single valuation request**. It changes once a day. Cache it in module scope with a date key (survives warm invocations for free) or read it from an env var refreshed by a daily cron. One line, removes ~15% of valuation latency.

---

### ✅ Q8. Long series are downsampled for the wire
`api/index.py:124-138`

The anomaly `series` emits one object with 10 fields per trading day. `period=max` on a long-listed US name is ~11,000 rows ≈ 1.5–2 MB of JSON, then handed to Recharts to render ~11,000 points across two charts.

The histogram in the valuation engine already solves this correctly server-side ("*the wire carries 60 bins, not N floats*", `valuation.py:877`). Apply the same instinct: downsample `series` to ~750 points for `period` ≥ `5y` while **always preserving every anomaly row** (they're the signal; the line between them is decoration).

---

### ✅ Q9. App Router error boundaries added
`app/` contains only `layout.tsx`, `page.tsx`, `globals.css`, `icon.png`.

No `error.tsx`, `not-found.tsx`, or `global-error.tsx`. Any render-time exception in a panel — a malformed payload, an unexpected `null` in a Recharts accessor — blanks the entire page with React's default error screen. Three small files.

---

### ✅ Q10. Tooling gaps closed
- `tsconfig.json:12` — `"strict": false`. Turn on `strictNullChecks` at minimum; the codebase is already written null-safely (`num()`, `pct()`, `_nullable()` all guard), so the diff should be small and it would have caught Q3.
- **No ESLint config** — `npm run lint` is in `package.json` but there is no `.eslintrc` / `eslint.config.mjs`. The script doesn't do anything.
- `any` in chart tooltip props (`AnomalyPanel.tsx:21`, `TechnicalPanel.tsx:24`) — Recharts ships `TooltipProps<number, string>`.
- No `ruff`/`mypy` on the Python side.
- `AnalysisConfig.min_avg_turnover` defaults to `0.0` and **no caller ever sets it** (`whale.py:166, 510`) — the "benign-noise filtering" advertised in the module header (`whale.py:13`) is unreachable dead config. Either expose it as a query param or delete the claim.

---

# 🔵 LONG-TERM ROADMAP

## A. Architecture

### A1. Introduce a data-access layer — one fetch, one cache, one normalisation
**The single most valuable structural change.** Today all three engines fetch independently, with three different code paths (`Ticker.history`, `yf.download`, `Ticker.info`), three different error types (`DataFetchError`, `TechnicalError`, `ValuationError`), and three different column-handling conventions (`whale.py` assumes flat columns; `technical.py` has `_flatten_columns` for MultiIndex — a divergence that will bite when yfinance changes its return shape).

Create `api/_lib/market_data.py` as the *only* module that imports `yfinance`:

```python
def ohlcv(symbol: str, period: str) -> pd.DataFrame:  ...
def fundamentals(symbol: str) -> Fundamentals:        ...
def risk_free(market: str) -> tuple[float, str]:      ...
```

This buys four things at once: (1) a single cache insertion point, (2) a single provider-swap point, (3) one consistent `DataFetchError`, (4) the ability to test every engine against fixtures with zero network.

### A2. Add a real cache, and abstract away yfinance
`requests-cache` won't help on serverless — no shared filesystem, no warm process guarantee. You need external state: **Vercel KV / Upstash Redis**, keyed `(symbol, period, session_date)`, TTL to the next market close. Fundamentals change quarterly and can hold for 24h; OHLCV for 15 min intra-session.

This is what actually neutralises C2's Yahoo-ban exposure — cache hits don't touch Yahoo at all.

Then, the strategic point: **yfinance is an unofficial scraper of an undocumented endpoint with no SLA and no ToS blessing.** It is fine for a personal project and disqualifying for anything with users who depend on it or anything you charge for. Once A1 exists, swapping in a licensed provider (Tiingo, EODHD, Polygon, FMP — all have IDX or global coverage at reasonable price points) is a one-file change instead of a rewrite. Do A1 now precisely so this stays a cheap decision later.

### A3. The screener needs a job queue, not a request
50 symbols × cold upstream fetches does not belong inside a 60-second HTTP request (C2). Two viable paths:

- **Streaming:** convert `/api/screener` to Server-Sent Events, emitting one row per symbol as it completes. Results appear progressively, the 60s wall stops being a cliff, and the UX is strictly better than a spinner.
- **Queue:** `POST /api/screener` returns a job id; a background worker (Vercel Cron, Inngest, QStash) fills results into KV; the client polls. Necessary anyway for the scheduled-scan feature (F1).

### A4. Reconsider the runtime
The "one function, route internally" decision (`api/index.py:6-15`) is genuinely well-reasoned for Vercel's bundling model. But the honest read is that **Vercel serverless is the wrong runtime for this workload**: every request pays cold-start import of numpy + pandas + scipy + scikit-learn against an uncacheable, rate-limited upstream.

A single small always-warm container (Fly.io, Railway, Render — $5–10/mo) gives you warm imports, in-process caching, a persistent connection pool to your data provider, and no 60s ceiling. Keep Next.js on Vercel; point it at the container. Worth costing out before building A2, since a warm process makes half of the caching complexity disappear.

### A5. Generate TypeScript types from the OpenAPI schema
`lib/types.ts:1` says *"Keep in sync with the FastAPI handlers"* — manually. That contract will drift, and drift here means a runtime `undefined` in a chart.

FastAPI already serves a schema at `/api/docs`. Two steps: (1) give the routes Pydantic `response_model`s instead of returning bare `dict` → `JSONResponse` (currently the schema is empty, so it's not usable), (2) run `openapi-typescript` in a `predev`/`prebuild` script. Free, permanent correctness.

### A6. State and persistence
No database means no watchlists, no history, no saved assumptions, no accounts — and every feature in section F below needs at least one of those. Postgres (Neon/Supabase) + a light auth layer is the prerequisite for the entire roadmap. Defer until F1 is actually being built, but design A1's cache keys with it in mind.

---

## B. UX & Logic

### B1. Put the app's state in the URL — the highest-value UX change
`app/page.tsx:1` is `"use client"` with all state in `useState`. Consequences: **you cannot link to an analysis.** The back button does nothing. Refresh loses everything. Presets and market selection can't be bookmarked. And nothing is server-rendered, so there's no SEO surface and no shareable preview.

Move to a route like `/[market]/[ticker]` with `searchParams` carrying mode/period/range, using `useSearchParams` + `router.replace`. This unlocks deep links, browser history, refresh-safety, and the entire organic growth loop for a tool whose output people naturally want to send to someone.

### B2. Lead with the Confluence view
The product's stated thesis is that agreement between lenses is the finding (`page.tsx:108`), and `ConfluenceRail` is the only view that exists nowhere else. But the default tab is `flow` (`page.tsx:80`) and the rail is a thin strip above the tabs. Consider making the rail the default full tab — an "Overview" that expands each lens's reasoning — with the three engine tabs as drill-downs.

### B3. Per-engine progress, not one shared spinner
`busy` is `[anomaly, technical, valuation].some(loading)` (`page.tsx:81`), so the Run button stays disabled until the *slowest* engine finishes — and valuation makes ~6 upstream calls while anomaly makes 1. The user watches a dead button with no idea which engine is holding things up. The panels already render independently; surface per-engine state in the rail (a pulsing accent bar per lens) and enable the Run button as soon as the fastest returns.

### B4. Error messages for infrastructure failures
`get()` (`lib/api.ts:27`) falls back to `Request failed (${res.status})` when the body isn't JSON — which is exactly the 504/502 case from a screener timeout. The user gets a bare number. Map 502/504/429 to specific, actionable copy ("The scan exceeded the time limit — try fewer symbols or a faster detection mode").

### B5. Accessibility
The engines' entire output is charts, and the charts are invisible to assistive tech. Recharts renders inline SVG with no `role`, `aria-label`, or text alternative. At minimum give each `ResponsiveContainer` a wrapping `role="img"` with an `aria-label` built from the data already computed for the narrative readout (`technical.py:369` produces a perfectly good English `headline` — use it). The event-log tables are the accessible fallback and are already well-structured; make sure they're reachable without going through a chart.

Also: the ticker input isn't autofocused on an empty state that exists solely to say "enter a symbol above" (`page.tsx:120-127`).

### B6. Smaller logic notes
- `recent_anomalies` uses **calendar** days (`whale.py:215`, `pd.Timedelta(days=days)`), so the UI's "last 10 days" is ~7 trading days. Label it "last 10 calendar days" or switch to `iloc[-n:]` on trading rows.
- "UNDERVALUED" / "OVERVALUED" rendered as a large coloured verdict (`ValuationPanel.tsx:31`) is assertive framing for a retail audience. The footer disclaimer is correctly present and well-written, but if this ever monetises or grows an audience, a categorical buy/sell-adjacent verdict is the element that attracts regulatory attention. Consider "Below/Above model range" — same information, materially less advice-shaped.
- `key={i}` on news items (`NewsPanel.tsx:27`) and notices (`ValuationPanel.tsx:68`).
- `queryString` (`lib/api.ts:10`) skips `undefined`/`null`/`""` but not `NaN`, which would serialise as the literal string `"NaN"` and produce an opaque FastAPI 422. Reachability via `<input type="number">` is unlikely (browsers report `""` for invalid intermediate input), but adding `Number.isNaN` to the guard is free defensive hardening.

---

## C. Feature Expansion

Five features, ordered by value-to-effort. Each builds on the engines already written.

### F1. Watchlists + scheduled scans + alerts ⭐ *highest value*
**The one change that turns a tool into a product.** Today every session starts from zero, and the screener — the feature most likely to produce a genuine finding — must be run manually.

Persist named watchlists per user, run them on a schedule (Vercel Cron → the A3 queue), and notify when a name lights up: *"BBRI.JK — 3 accumulation events in the last 5 days, peak strength 87."* Email first, then push.

This is the retention mechanic. It is also the natural paywall (free = 1 watchlist / weekly; paid = unlimited / daily / instant). Requires A6 (persistence) and A3 (queue) — which is why those come first.

### F2. Signal validation & backtest — the credibility feature
The engine *already contains* leakage-free walk-forward scoring (`whale.py:417-440`), built expressly for historical evaluation, and nothing in the product surfaces its purpose. Every anomaly-detection tool for retail investors is asserted rather than evidenced; being the one that shows its own hit rate is a real differentiator.

Ship: forward returns at +5 / +20 / +60 trading days after each detected anomaly, segmented by flow direction and strength decile, with a benchmark-relative column and an honest sample-size warning. If accumulation signals at strength > 80 don't beat the index, **say so** — that credibility is worth more than the signal.

Moderate effort (the hard part, walk-forward, is written), and it's the feature that makes every other number in the app trustworthy.

### F3. Sensitivity grid + peer comparison for the valuation
Two additions that fix the DCF's biggest weakness — it values a company in a vacuum against assumptions the user has no basis to judge.

- **Sensitivity grid:** implied price across a growth × discount-rate matrix — the standard banker's two-way table. `pv_of_growing_stream` (`valuation.py:447`) is already fully vectorised over both axes, so this is **~30 lines and one heatmap component.** Far more decision-useful than a single Monte Carlo histogram, because it answers "what would have to be true" rather than "what does the model say".
- **Peer comparison:** implied multiples (EV/FCF, P/E, P/B, dividend yield) versus 3–5 peers and the sector median. Turns "10% growth" from an arbitrary default into a claim the user can sanity-check, and lets you auto-flag outlier assumptions.

Best effort-to-value ratio in the list.

### F4. Shareable permalinks + a one-page tearsheet
Building directly on B1: once state lives in the URL, add an export of the confluence view as a single PNG/PDF tearsheet — the three lenses, the price chart with anomalies, the valuation range, and the disclaimer. Stock analyses are inherently social; this is the organic acquisition loop, and it costs a route plus `@vercel/og` or a headless render.

### F5. An IDX fundamentals quality layer — the moat
IDX support is what makes QuantDesk distinct, and Yahoo's IDX coverage is exactly where it's weakest — which is *why* the manual-input rescue flow exists (`valuation.py:678-719`, `ValuationControls.tsx:38`). That flow is a good bandage on a structural problem.

Curate and cache a fundamentals table for the LQ45 / IDX30 constituents from IDX filings (which are public), so Indonesian valuations work on the first attempt instead of routing users through a manual form. Highest effort here, and the hardest thing for a competitor to copy. This is the durable advantage, whereas the three engines are reproducible by anyone.

---

## Suggested order of execution

| Phase | Work |
|---|---|
| **Done** | ~~All criticals C1–C4~~ ✅ · ~~All quick wins Q1–Q10~~ ✅ |
| **Next** | B1 (URL state) · A1 + A2 (data layer + cache) · A5 (generated types) |
| **This quarter** | A1 + A2 (data layer + cache) · A5 (generated types) · F3 (sensitivity grid — cheap, high value) · A4 decision (runtime) |
| **Next quarter** | A6 + A3 (persistence + queue) → F1 (watchlists & alerts) · F2 (backtest) · F5 (IDX data layer) |

---

*The engineering judgement in this codebase is well above the norm for a solo project — the docstrings reason about failure modes rather than describing syntax, and the three bugs they document catching are the exact bugs that make financial tools untrustworthy. What's missing is the operational layer: tests to keep those fixes fixed, caching and limits so the thing survives traffic, and persistence so it becomes something people return to.*
