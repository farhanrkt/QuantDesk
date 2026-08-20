# QuantDesk

**Four independent models read the same stock, side by side.**

Most research tools give you one opinion. QuantDesk gives you four — order flow, price
trend, intrinsic value, and accounting quality — and shows you where they agree and where
they don't. Covers **US and Indonesian (IDX)** listings.

> Educational and research tooling. Not investment advice.

---

## The idea in one paragraph

Any single model can be fooled. A stock can look cheap on a spreadsheet while quietly
bleeding money; it can look strong on a chart because one fund happened to rebalance. So
instead of trusting one method, QuantDesk runs four that read **different data** — one
reads volume, one reads price, one reads cash flows, one reads the balance sheet — and puts
their verdicts in a row. When methods that share no inputs land in the same place, that's
worth more than any one of them shouting.

**The honest caveat, which the app shows you on screen:** the four are not equally
independent. Flow and Trend are both computed from the same price-and-volume series, so
they agree more often than four unrelated tests would. Value and Quality read the filings
and carry most of the genuinely separate information.

---

## Quickstart

Needs **Node 20+** and **Python 3.12**.

```bash
npm install
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

Then run the two halves in separate terminals:

```bash
npm run dev:api
```

```bash
npm run dev
```

Open <http://localhost:3000>, type a ticker (or click a preset), and hit **Run all lenses**.

Indonesian listings take a `.JK` suffix — type `BBCA.JK`, or type `BBCA` and switch the
market dropdown to IDX. Crypto takes a pair like `BTC-USD`.

---

## The four lenses

Each one answers a different question. For each, here's what it asks, how it answers, and —
just as importantly — what it *can't* tell you.

### Flow — "Is anyone unusual trading this?"

**How.** An Isolation Forest (an unsupervised outlier detector) reads six behavioural
features per day: return, relative volume, absolute return, Money Flow Index, an
on-balance-volume z-score, and intraday range. Days that don't look like other days get
flagged, labelled Accumulation or Distribution by a four-way vote of money-flow indicators,
and scored 0–100 for strength.

Alongside it, a **CUSUM change detector** looks for something the first model structurally
cannot see. An institution building a position splits its order across weeks precisely so
no single day stands out. A detector that scores each day on its own can only ever catch
the impatient buyer. CUSUM accumulates small deviations instead, so a long run of
unremarkable days trips a threshold that none of them would alone — on AAPL it surfaced a
27-day accumulation at just **1.04× average volume**, invisible to any volume-spike rule.

**What it can't tell you.** Whether the trader was an institution at all. Index rebalances,
options expiry, dividend dates and earnings all produce identical footprints. The panel
estimates the **bid-ask spread** and warns when a move is small enough to be swallowed by
trading costs — on a thin stock, "heavy volume moved the price" often just means the order
book is shallow.

### Trend — "What is the price doing?"

**How.** The standard toolkit, hand-implemented rather than pulled from a library: SMA
50/200, Wilder's RSI, MACD, Bollinger bands, and support/resistance levels clustered from
local extrema. Golden and death crosses are detected as *events* (the bar where they
happen), not states. It writes the result as a sentence in English.

**What it can't tell you.** Anything about the business. This lens is pure price history
and would say the same things about a company that is about to be delisted.

### Value — "What is the business actually worth?"

**How.** Three models, routed automatically by sector:

| Model | Used for | Values |
|---|---|---|
| **DCF** | Most companies | Discounted free cash flow |
| **DDM** | Banks and insurers | Discounted dividends |
| **Residual income** | Financials with no usable dividend data | Book value + excess returns |

Each runs a 5-year projection plus a terminal value, then a 10,000-draw Monte Carlo
simulation to produce a range rather than a single number.

**What it can't tell you.** Anything with confidence. A DCF is an opinion with arithmetic
attached — the answer moves enormously with the growth and discount rate you assume, which
is exactly why the output is a P5–P95 range and why every assumption is an editable field.
The panel warns you when the terminal value dominates (often 60–80% of a DCF), because that
means the answer rests on a perpetuity guess rather than the forecast.

### Quality — "Is the business sound, and are the numbers real?"

**How.** Three published accounting screens, computed from filings the app already fetched:

- **Piotroski F-Score** (0–9) — is the fundamental trend improving across profitability,
  leverage, and efficiency?
- **Altman Z''-score** — how far from financial distress? Uses the emerging-market variant,
  so an IDX listing and a US one are on the same scale.
- **Beneish M-Score** — do the accruals resemble those of companies later found to have
  manipulated earnings?

**What it can't tell you.** Anything about a bank or insurer — and it says so rather than
printing a number. None of the three was built on financial firms: there's no operating
cycle for "working capital" to describe, and revenue isn't a receivables-and-inventory
process. Financials get an explicit refusal. Beneish is also a *screen*, not a finding:
it catches roughly three-quarters of manipulators, which on a population where manipulation
is rare also means most flags are false alarms.

---

## Three more tools

**Screener.** Scan up to 20 tickers and surface only those with fresh activity. Critically,
it reports **how many hits you'd expect from noise** — each ticker is tested against its
*own* long-run flag rate, then a false-discovery-rate correction runs across the whole scan.
A fixed count threshold silently favours chronically noisy stocks; this doesn't. Click any
result to load it into all four lenses.

**Event study.** The one that decides whether the Flow lens is worth your attention. It
measures the cumulative abnormal return after *every* anomaly ever detected on a ticker,
against a market model, and reports the t-statistic. On JPM the answer was **no significant
effect at any horizon** — and reporting that is the point. A tool that only ever confirms
itself is worth nothing.

**News.** Recent headlines for context. Display only — nothing in the app reads them back
as data.

---

## Why these particular models

The short version: every number in the app should be traceable to something published, and
where a constant was invented, it got replaced by an estimator.

| Instead of | It uses | Because |
|---|---|---|
| Clipping beta to `[0.4, 2.5]` | **Vasicek (1973)** shrinkage | Shrinks each estimate toward the market *in proportion to its own error bars*, so a noisy small-cap beta is treated differently from a precise large-cap one |
| A flat `σ = 2%` in the Monte Carlo | Dispersion from the company's own history | The old constant came from nowhere and set the entire width of the fan chart |
| Close-to-close volatility | **Yang-Zhang (2000)** | Uses the high and low too — far less estimation noise from the same data |
| Ignoring trading costs | **Abdi-Ranaldo (2017)** spread | Recovers a planted spread to ~1% in simulation; tells you when a move is smaller than the cost of trading it |
| Assuming the signal works | **Event study** (Brown & Warner 1985) | Measures it, and reports null results |
| Reporting raw screener hits | **Benjamini-Hochberg (1995)** | Scanning many names produces hits by construction |

Full reasoning, effect sizes, and the validation results are in
**[RESEARCH_ROADMAP.md](RESEARCH_ROADMAP.md)**.

---

## How it's built

```
app/          Next.js App Router pages, error boundaries
components/   One panel per lens + shared UI primitives
lib/          API client, wire types, CSV export, formatting
api/
  index.py    One FastAPI app — routing, rate limiting, validation
  _lib/       The engines:
              whale.py          Isolation Forest anomaly detection
              technical.py      Indicators and narrative readout
              valuation.py      DCF / DDM / residual income
              quality.py        Piotroski, Altman, Beneish
              accumulation.py   CUSUM regime detection
              microstructure.py Spread, illiquidity, volatility
              riskmodel.py      Beta estimation and shrinkage
              eventstudy.py     Abnormal returns, FDR correction
              symbols.py        Ticker → Yahoo symbol, resolved once
              news.py           Google News RSS
              jsonsafe.py       NaN/inf → null before serialising
tests/        257 offline tests
```

**Stack.** Next.js 15 (App Router, React 19) · Tailwind · Recharts · FastAPI ·
numpy / pandas / scipy / scikit-learn · yfinance. No database, no auth, no accounts.

**One Python function, not several.** Vercel compiles every top-level `.py` under `/api`
into its own serverless function, each bundling the full dependency closure. Three files
would mean numpy + pandas + scipy + scikit-learn packaged three times. So it's one function
that routes internally.

**Symbols resolve once, at the edge.** Before this was enforced, asking for `BBCA` on the
IDX market valued PT Bank Central Asia while the charts analysed an unrelated US ETF of the
same name — three panels, two different companies, no error. Unsuffixed IDX codes are not
safely inert on Yahoo (`ASII`, `MAIN`, `LIFE` are all real US listings), so the failure mode
is a plausible wrong answer. `symbols.py` now does the resolution once and every engine
receives the resolved symbol.

---

## API

Everything the UI does is a plain `GET`. Interactive docs at `/api/docs`.

| Endpoint | What it returns |
|---|---|
| `GET /api/confluence` | **All four lenses in one call** — what the UI actually uses |
| `GET /api/isolation-forest` | Flow: anomalies, accumulation regimes, liquidity profile |
| `GET /api/technical-analysis` | Trend: indicators, levels, signals, narrative |
| `GET /api/intrinsic-value` | Value: DCF / DDM / RI with Monte Carlo percentiles |
| `GET /api/quality` | Quality: F-Score, Z''-score, M-Score |
| `GET /api/event-study` | Abnormal returns after each anomaly, with t-stats |
| `GET /api/screener` | Multi-ticker scan with FDR correction |
| `GET /api/news` | Recent headlines |
| `GET /api/intrinsic-value/simulation` | Every Monte Carlo draw, as CSV |
| `GET /api/health` | Liveness and engine inventory |

```bash
curl "http://localhost:8000/api/confluence?ticker=BBCA.JK&market=ID"
```

Each leg of `/api/confluence` reports its own success or failure, so a company with no
dividend history still returns its other three panels.

**Limits.** Per-IP rate limiting (40/min default, 3/min for the screener, 6/min for the
event study). The screener caps at 20 symbols, or 5 on walk-forward mode. These exist
because one screener request fans out to that many upstream fetches *and* model fits.

**Market conventions** are configured per market — US uses a 4.2% risk-free rate, 5.5%
equity risk premium, 21% tax and `^GSPC` as benchmark; IDX uses 6.5%, 7.0%, 22% and
`^JKSE`.

---

## Development

Python engines:

```bash
.venv/bin/python -m pytest && .venv/bin/ruff check api tests
```

Frontend:

```bash
npx tsc --noEmit && npm run lint && npm run build
```

**Every test runs offline.** No test touches yfinance or any network service — the engines
are exercised against deterministic synthetic data with a *planted* ground truth, so each
estimator has to recover a number it was never given. A suite that needs the network is a
suite that gets skipped, and an upstream outage can never redden CI.

CI (`.github/workflows/ci.yml`) runs pytest + ruff, tsc + eslint + build, and a production
`npm audit`.

---

## Known limits

**Data.** yfinance is an unofficial scraper against an undocumented endpoint, with no SLA.
Fundamentals for smaller IDX listings are patchy — where a figure is missing, the app offers
a manual-input form rather than guessing. This is the single biggest fragility in the
project.

**Statistical.** Results are in-sample, on one ticker at a time, with overlapping windows.
The event study is indicative, not a backtest. The Flow lens has no walk-forward validation
enabled by default because it costs minutes per ticker.

**Not implemented on purpose.** Order-flow toxicity (VPIN/PIN) needs trade-level data; a
daily approximation would be a different number wearing the name. Calendar effects
(January, Halloween) are where the multiple-testing critique bites hardest. Headline
sentiment would need full article text and a lexicon that covers Indonesian.

**No state.** No accounts, no saved watchlists, no persistence. Every session starts empty.

---

## Further reading

- **[RESEARCH_ROADMAP.md](RESEARCH_ROADMAP.md)** — every model, why that estimator, what it
  doesn't claim, with citations and validation results.
- **[CODEBASE_REVIEW.md](CODEBASE_REVIEW.md)** — engineering review: security, architecture,
  and what's still open.

---

Prices and filings from Yahoo Finance — unaudited and occasionally incomplete.
Educational and research use only. Not investment advice, and not a substitute for reading
the filings yourself.
