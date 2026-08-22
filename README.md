# QuantDesk

**Four independent models read the same stock, side by side.**

Most research tools give you one opinion. QuantDesk gives you four — order flow, price
trend, intrinsic value, and accounting quality — and shows you where they agree and where
they don't. Covers **US and Indonesian (IDX)** listings.

> Educational and research tooling. Not investment advice.

**Every number in the app explains itself.** Each figure carries an info icon that says
what it measures in plain English, whether *this* value is good or bad and why, and what
would make you act differently — or admits that nothing would. A **Guided/Full** toggle
defaults to Guided: headline figures show their reading without a click, the expert tuning
controls fold behind one labelled disclosure, and the raw indicator grid steps aside. Full is
every control and every indicator, unchanged.

**And it says what the four add up to.** Above the tabs, a plain-English summary reports what
the lenses agree on, *names where they disagree*, states what it cannot tell you about this
particular company, and lists what to check next. It is deliberately prose and not a score —
see [the field manual](docs/field-manual.html) for why a single buy/hold/sell number would
discard every finding the rest of the app works to establish.

**New to any of this?** Start with the **QuantDesk Field Manual** —
[read it online](https://claude.ai/code/artifact/a73e6190-7252-430a-a57b-a84fe7cfd009) or open
[`docs/field-manual.html`](docs/field-manual.html) locally. Every lens and every term explained
from scratch, no prior finance assumed.

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

### Trend — "What is the price doing, and could I have held it?"

**How.** Five sections behind a horizon selector, ordered longest-first so that reading
left to right walks from the strongest evidence to the weakest.

**Long horizon** leads, because that is what a multi-year holder is actually asking. A
checklist — 200-day average, Faber's 10-month rule, 12-1 momentum, ADX, Hurst exponent,
trend-line fit, 52-week position, drawdown survivability — each line saying which way it
points and why. Then the table that matters most: **every overlapping holding period in the
history**, so "worst 3-year window" replaces a headline CAGR that only describes one lucky
start date. Then what holding it *cost* — maximum drawdown with its depth, duration and
recovery, plus the Ulcer index, which scores a long shallow grind as worse than a sharp
fall, because that is how it feels. Then relative strength against the index, since the real
alternative was never cash.

**Mid term** (weeks to months) and **Short term** (days to a few weeks) answer a different
question: not "could I have held this?" but "if I were buying in the next few weeks, where
would the levels be?". Support and resistance from confirmed swing points, each reporting
**how many times the market actually turned there**; a stop placed just beyond structure
with an ATR buffer, and widened when structure would have put it inside daily noise; a
target at real overhead resistance rather than at whatever number makes the arithmetic look
good; position size as the share of an account that risks exactly your budget. Plus pivot
points from the last *complete* period, anchored VWAP, Donchian breakouts, Bollinger
squeeze, gap analysis and RSI divergence.

**These sections never invent a setup.** Setups are pre-registered and checked in order,
and "none of them is present" is the most common answer — a test fires the detector across
twenty random walks and fails the build if a majority produce a trade. Candlestick patterns
are detected, graded weak, and **firewalled**: none is allowed to place an entry, stop or
target. Head and shoulders, flags, wedges and cup-and-handle are named on the panel as
things the app will not claim to detect, with the reason for each.

**Chart & signals** is the price chart with moving averages, Bollinger/Keltner/Donchian
bands, the Ichimoku cloud, and golden/death crosses detected as *events* rather than states.

**All indicators** is everything else — ADX/DMI, Aroon, Stochastic, Williams %R, CCI, ROC,
ATR, MFI, Chaikin money flow, Coppock — grouped by the horizon each one speaks to. That
grouping is deliberate: a long-term investor shown "Stochastic 82, overbought" next to
"price above its 200-day average" has been handed two statements of very different weight
presented identically.

**What it can't tell you.** Anything about the business. This lens is pure price history
and would say the same things about a company that is about to be delisted. It also cannot
tell you whether the trend is real: the Hurst exponent is there precisely to say when a
price series is close enough to a random walk that the trend tools are describing noise.

### Value — "What is the business actually worth?"

**How.** Three models, routed automatically by sector:

| Model | Used for | Values |
|---|---|---|
| **DCF** | Most companies | Discounted free cash flow |
| **DDM** | Banks and insurers | Discounted dividends |
| **Residual income** | Financials with no usable dividend data | Book value + excess returns |

Each runs a 5-year projection plus a terminal value, then a 10,000-draw Monte Carlo
simulation to produce a range rather than a single number.

**Run it backwards.** The panel also solves the model in reverse: what growth rate would make
today's price correct? On AAPL that came out at **37% a year for five years** against a 10%
assumption — which is a claim about the world you can agree or disagree with, rather than a fair
value you have no basis to judge. It is stated as conditional on the other inputs, because it is:
across plausible discount rates the same price implies anywhere from 24% to 42%.

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

**Scan & rank.** The breadth half of a two-tier workflow: rank a whole universe, then open
the four lenses on the few names worth it.

*Tier one* batch-downloads up to 250 symbols in a handful of upstream calls — the Nasdaq-100
ranks in about six seconds — and scores every name on seven price-and-volume signals:
momentum, trend, nearness to the 52-week high, steadiness, holdability, relative strength
and money flow. Each becomes a **cross-sectional percentile** before anything is combined,
because "top decile of this scan" is a claim the data supports and "82/100" is not. Click a
row's arrow to see exactly how it earned its score.

The panel then does something a composite score usually hides: it reports the **measured**
rank correlation between every pair of signals and the participation ratio of that matrix —
how many genuinely independent signals the composite is actually averaging. On a real Dow
scan, momentum and trend correlate at +0.98 and seven columns carry about **3.4 signals'
worth** of information. That is printed in the header.

*Tier two* runs quality and valuation on a shortlist of up to eight. Those need the filings,
which fetch one company at a time, which is exactly why they are a second step and not
another column.

**Compare with peers.** The ranking tier's percentiles, pointed at a single name. Every other
figure in the app is absolute — a 33% worst fall, 28% volatility — and a reader with no priors
cannot tell an ordinary number from an alarming one. On the Trend tab, one button places the
ticker against its own index and says it in sentences: *"its worst fall was milder than 95% of
the Nasdaq-100"*. It is a button rather than a column because it costs a whole universe scan,
and it covers the price family only — the filings do not batch, so Value and Quality have no
peer comparison and the panel says so.

**Anomaly screener.** Still there, answering what the ranking cannot: *has something unusual
just happened here?* Scans up to 20 tickers and reports **how many hits you'd expect from
noise** — each ticker tested against its *own* long-run flag rate, then a false-discovery-rate
correction across the whole scan.

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
| A headline CAGR | **Rolling-return distribution** | One CAGR describes one start date; the distribution shows the worst entry point you'd have survived |
| Drawdown depth alone | **Ulcer index** (Martin & McCann 1989) | Duration breaks conviction as much as depth — a long shallow grind is harder to hold than a sharp fall |
| Assuming a trend exists | **Hurst exponent** | If H sits near 0.5 the series is a random walk and every trend indicator is describing noise |
| A bare Hurst reading against a fixed 0.45–0.55 band | **A band scaled to the sample size** | Measured against exact fractional Brownian motion, the estimator's standard error is ~0.05 on five years of daily bars — so the fixed band was barely one standard error wide and called a *genuine random walk* trending 35% of the time. The band now widens when there is less history: 7% at five years, and real persistence (H = 0.7) is still detected 82% of the time |
| Quoting an estimated bid-ask spread as a cost | **The estimator's own resolution floor** | Both spread estimators have a noise floor proportional to volatility — 0.148× and 0.361× the daily standard deviation, measured with the true spread set to zero. On a mega-cap that floor is an order of magnitude above the real spread, so the app reported a cost the stock does not charge. Below the floor it now reports a ceiling |
| Assuming the signal works | **Event study** (Brown & Warner 1985) | Measures it, and reports null results |
| Reporting raw screener hits | **Benjamini-Hochberg (1995)** | Scanning many names produces hits by construction |
| A composite score across signals | **Percentile ranks + a measured overlap** | Momentum, 52-week-high and relative strength are three phrasings of "it went up"; the panel reports how many *independent* signals the composite really averages |
| Colouring metrics at each call site | **One ladder per metric, in Python** | A third of them are "low is good" and sit in the same grid as the rest; direction is encoded once and asserted by tests |

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
              market_data.py    THE ONLY MODULE THAT IMPORTS YFINANCE —
                                one fetch, one normalisation, one cache
              whale.py          Isolation Forest anomaly detection
              technical.py      Indicators and narrative readout
              valuation.py      DCF / DDM / residual income
              quality.py        Piotroski, Altman, Beneish
              accumulation.py   CUSUM regime detection
              microstructure.py Spread, illiquidity, volatility
              riskmodel.py      Beta estimation and shrinkage
              eventstudy.py     Abnormal returns, FDR correction
              swing.py          Short/mid-horizon setups, levels, risk plans
              ranking.py        Batch download + cross-sectional ranking
              universes.py      Predefined ticker lists, each date-stamped
              explain.py        Plain-English interpretation for every metric,
                                and the cross-lens synthesis
              symbols.py        Ticker → Yahoo symbol, resolved once
              news.py           Google News RSS
              jsonsafe.py       NaN/inf → null before serialising
docs/
  field-manual.html   Beginner's guide; glossary generated from _lib/explain.py
scripts/
  build_glossary.py   Regenerates that glossary, and CI's drift check
tests/        826 offline tests
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
| `GET /api/confluence` | **All four lenses in one call, plus the synthesis** — what the UI actually uses |
| `GET /api/isolation-forest` | Flow: anomalies, accumulation regimes, liquidity profile |
| `GET /api/technical-analysis` | Trend: indicators, levels, signals, narrative |
| `GET /api/intrinsic-value` | Value: DCF / DDM / RI with Monte Carlo percentiles |
| `GET /api/quality` | Quality: F-Score, Z''-score, M-Score |
| `GET /api/event-study` | Abnormal returns after each anomaly, with t-stats |
| `GET /api/rank` | **Rank a universe** on price signals, with per-signal breakdown |
| `GET /api/rank/universes` | The predefined lists, each with its as-of date |
| `GET /api/peers` | **Where one ticker sits among its own index** on the seven price signals |
| `GET /api/rank/deepen` | Quality + valuation for a shortlist of up to 8 |
| `GET /api/screener` | Multi-ticker anomaly scan with FDR correction |
| `GET /api/news` | Recent headlines |
| `GET /api/intrinsic-value/simulation` | Every Monte Carlo draw, as CSV |
| `GET /api/health` | Liveness and engine inventory |

```bash
curl "http://localhost:8000/api/confluence?ticker=BBCA.JK&market=ID"
```

Each leg of `/api/confluence` reports its own success or failure, so a company with no
dividend history still returns its other three panels.

**Limits.** Per-IP rate limiting (40/min default; 3/min for the screener and the ranking
scan; 2/min for shortlist deepening, which is the one route that does *not* batch; 6/min for
the event study). The screener caps at 20 symbols, the ranking tier at 250, and deepening at
8. These exist because each of those requests fans out to upstream calls — the caps are sized
to what actually batches.

**Market conventions** are configured per market — US uses a 4.2% risk-free rate, 5.5%
equity risk premium, 21% tax and `^GSPC` as benchmark; IDX uses 6.5%, 7.0%, 22% and
`^JKSE`.

---

## Development

Python engines:

```bash
.venv/bin/python -m pytest && .venv/bin/ruff check api tests scripts
```

Frontend:

```bash
npx tsc --noEmit && npm run lint && npm run build
```

**Every test runs offline.** No test touches yfinance or any network service — the engines
are exercised against deterministic synthetic data with a *planted* ground truth, so each
estimator has to recover a number it was never given. A suite that needs the network is a
suite that gets skipped, and an upstream outage can never redden CI.

The field manual's glossary is generated, so regenerate it after touching the explanation
layer — CI fails if you forget:

```bash
.venv/bin/python scripts/build_glossary.py
```

CI (`.github/workflows/ci.yml`) runs pytest + ruff, the manual's drift check, tsc + eslint +
build, and a production `npm audit`.

---

## Analytics

Visitor counts come from **Vercel Web Analytics**, chosen because it was the only option
that did not require relaxing anything:

- **Same origin.** The script loads from `/_vercel/insights/script.js` and beacons to
  `/_vercel/insights/event`, both proxied by the platform on this app's own domain — so
  `script-src 'self'` and `connect-src 'self'` already permit it and the CSP is unchanged.
  Every third-party alternative would have meant adding an external host to both.
- **No cookies, no storage.** Verified in the package source rather than taken on trust:
  zero references to `document.cookie`, `localStorage` or `sessionStorage`. That is what
  keeps this app free of a consent banner.
- **One aggregate event, and not the ticker.** A run reports the market (`US`/`ID`) and how
  many of the four lenses succeeded. *Which* companies someone looks up is behavioural data
  about an individual — a watchlist is one of the more revealing things a person can tell
  you — and this app has no business collecting it.

It renders in production only, so local development neither pollutes the numbers nor trips
the CSP on the debug script. `track()` is a no-op off Vercel, so a self-hosted copy sends
nothing.

**It still has to be switched on in the dashboard** — Vercel project → Analytics → Enable.
The code alone does not start collection.

---

## Known limits

**Data.** yfinance is an unofficial scraper against an undocumented endpoint, with no SLA.
Fundamentals for smaller IDX listings are patchy — where a figure is missing, the app offers
a manual-input form rather than guessing. This is the single biggest fragility in the
project.

**Estimator resolution.** Two numbers are reported as bounds rather than measurements, because that is what the data supports. The bid-ask spread cannot be resolved below roughly 0.15× a stock's daily volatility from daily bars, so on liquid names the panel says "at most X" instead of quoting a figure. The Hurst exponent is noisy enough that its "random walk" band is sized from the sample, so a short range says "cannot tell" rather than guessing. Both floors were measured by simulation, not assumed — see `_lib/microstructure.py` and `_lib/indicators.py`.

**Statistical.** Results are in-sample, on one ticker at a time, with overlapping windows.
The event study is indicative, not a backtest. The Flow lens has no walk-forward validation
enabled by default because it costs minutes per ticker.

**Constituent lists go stale.** Index membership is transcribed by hand and date-stamped in
`_lib/universes.py`. It decays invisibly — a dropped name still fetches, a newly added one is
simply absent — which is why the date is shown on the panel. There is deliberately **no S&P
500 list**: five hundred symbols is the length at which transcription goes wrong, and a
mistyped ticker produces a plausible ranking row for a company nobody asked about rather than
an error. Paste your own from a source that maintains one.

**Shorter horizons rest on weaker evidence, and say so.** The long-horizon section draws on
decades of published work. The short- and mid-term sections mostly do not, and every reading
there carries its evidence grade. Over one to four weeks prices have historically shown mild
*reversal* rather than continuation — the opposite of the twelve-month effect — which the
panel states rather than hides.

**Not implemented on purpose.** Order-flow toxicity (VPIN/PIN) needs trade-level data; a
daily approximation would be a different number wearing the name. Multi-bar chart patterns
(head and shoulders, flags, wedges) are named and declined rather than matched with fixed
thresholds that would fire on noise. Calendar effects
(January, Halloween) are where the multiple-testing critique bites hardest. Headline
sentiment would need full article text and a lexicon that covers Indonesian.

**No state.** No accounts, no saved watchlists, no persistence. Every session starts empty.

---

## Further reading

- **[docs/field-manual.html](docs/field-manual.html)** — a beginner's guide to the whole app
  ([published copy](https://claude.ai/code/artifact/a73e6190-7252-430a-a57b-a84fe7cfd009)). All four
  lenses, the synthesis that reads them together, the statistics that decide whether to believe any
  of it, and every one of the 78 metrics in a searchable glossary. Assumes no prior finance.

  Its glossary is **generated**, not transcribed: `scripts/build_glossary.py` injects the same
  strings `_lib/explain.py` puts on screen, and CI fails if a metric is added without regenerating.
  Run it after touching the explanation layer:

  ```bash
  python scripts/build_glossary.py
  ```
- **[RESEARCH_ROADMAP.md](RESEARCH_ROADMAP.md)** — every model, why that estimator, what it
  doesn't claim, with citations and validation results.
- **[CODEBASE_REVIEW.md](CODEBASE_REVIEW.md)** — engineering review: security, architecture,
  and what's still open.

---

Prices and filings from Yahoo Finance — unaudited and occasionally incomplete.
Educational and research use only. Not investment advice, and not a substitute for reading
the filings yourself.
