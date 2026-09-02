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

**And it says what would stop a careful buyer.** Underneath that summary, a pre-trade panel
collects the conditions that argue against acting — a balance sheet in the distress zone, a
valuation that is mostly a perpetuity guess, a price series the app cannot tell apart from a
random walk. Each one arrives with **the measured share of a real universe it fires on**,
because a condition true of a third of the market describes the market rather than this
company. There is no count, no score, and nothing on it is ever green: an empty panel is not
a clean bill of health, and the panel says so in words rather than leaving a row of ticks to
imply otherwise.

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
independent. Flow and Trend are both computed from the same price-and-volume series, so the
app collapses them into one vote rather than counting four.

**And that caveat is now measured, not asserted.** Across 168 names in four index universes,
the price record and the filings reach the same verdict about as often as chance puts them
there — **κ = +0.03, on an interval that straddles zero** — so agreement between them really
is two facts rather than one counted twice. The surprise was the other half: Flow and Trend,
the pair grouped together *because* they read the same series, agree at κ = +0.03 too, and
the four lenses together carry **3.7 lenses' worth of independent information** rather than
the two the count collapses them to. The grouping was left alone anyway, and the panel says
why: a vote that correlates with nothing is what an independent reading and an uninformative
one both look like, and the Flow lens's own event study already returns nulls.

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

`dev:api` runs `.venv/bin/python -m uvicorn` rather than a bare `uvicorn`, so it does not
depend on the environment being activated — and, more to the point, cannot pick up a different
one. A bare `uvicorn` resolves through `PATH`, and a system Python that happens to have it
installed will happily serve this app on whatever yfinance and pandas *it* has, which on the
machine this was written on is a major version apart from the pinned ones. The cost is that
the venv has to be at `.venv/`, exactly as the command above creates it; if you keep your
environment somewhere else, point the script at your own interpreter.

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

**You say how long you would hold it**, once, and the app answers that question rather than a
fixed one. Above the tabs sits what every holder of that length actually got: the worst entry,
the typical one, and how many of those overlapping periods made money. On AAPL the one-year
worst case is **-30% a year** and the three-year worst case is **+0.2%** — three completely
different investments, and until there was a horizon the app answered as though the question
had one answer. A horizon the loaded history cannot support says so, with the shortfall and
the fix, rather than quietly going missing.

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
lower the discount rate and the implied growth falls with it. The panel says so and tells you
to change the input and watch the number move — there is no sensitivity grid computing that
range for you, which is a gap rather than a claim (see RESEARCH_ROADMAP).

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

**And what a flag is actually worth.** Beneish catches roughly three-quarters of manipulators
and misclassifies about one non-manipulator in six. Put those against how rare manipulation is
and a flag comes out **about 11% likely to be real** — so roughly nine flags in ten are false
alarms. The prevalence is the input that decides the answer and the one nobody can measure
exactly, so it is a control rather than a constant: drag it across every estimate the
literature supports, from 0.69% to 14%, and the posterior runs from 3% to 41%. **It never
reaches even odds**, which is a much stronger statement than "most flags are false alarms"
because it does not depend on winning the argument about the prior.

A clean reading gets the same treatment, reported as a *shift* rather than a level — 2.8%
before the test, 0.8% after. On its own that second number would read as a clean bill of
health; the pair reads as what the test actually did, which was move a small number slightly.

**Where each number came from, beside the number.** Applicability is one question and the app
has always enforced it; *whether this use resembles the sample the screen was fitted on* is a
different one, and it went unanswered. Each score now carries its provenance on the axes that
can be checked — period, market, kind of business, size of firm, and how common the event was
in the sample the model was tuned on. An IDX large cap in 2026 is outside all three original
samples on several axes at once.

It is provenance, so **none of it is coloured**. Outside is not a warning — every practical use
of all three is outside, because the samples ended between 1965 and 1996 — and inside is not
reassurance, because matching a sample says nothing about accuracy on this company. There is no
fit score either: counting matching axes would be a reliability rating none of these papers
supports. One nice inversion falls out of it: Altman's zone boundaries come from a 2005
emerging-market recalibration, so an *Indonesian* listing is on home ground where a US one is
not, while the 1960s coefficients underneath are outside for both.

**What it can't tell you.** Anything about a bank or insurer — and it says so rather than
printing a number. None of the three was built on financial firms: there's no operating
cycle for "working capital" to describe, and revenue isn't a receivables-and-inventory
process. Financials get an explicit refusal. And Beneish is a *screen*, not a
finding — quantified above rather than hedged: at the prevalence its own coefficients were
fitted under, a flag is about 11% likely to be real.

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

**Thesis journal.** Write down what has to be true, what would falsify it, your horizon, your
size and the growth you expect — before you act. The entry is timestamped, snapshotted against
what the app was showing at the time, and **cannot be edited once saved**: a thesis you can
revise after the outcome is a rationalisation with a timestamp on it.

Three things get checked as you write, and each names a gap rather than blocking on it: your
growth expectation against what the price requires (both directions — believing *more* is as
much a thesis as believing less), your position size against this stock's own worst fall
(*"a 70% position in something that has already fallen 33% is 23% of the account, gone"*), and
whether any holder at your stated horizon lost money.

**Nothing is ever scored.** Entries come back as written. Where the numbers have moved since,
the movement is shown as movement and labelled as not a verdict. A journal that graded itself
would be a backtest of one, on a sample you chose, with no control for what you left out.

It never reaches a server — not even to draw those checks, which run in the browser. That
invariant is enforced by the build: `check_frontend.mjs` fails if `lib/api.ts` so much as
mentions the journal.

**Portfolio fit.** The question no single-ticker page can answer: *is this the fourth copy of a
bet I already hold?* Paste what you own and it reports the candidate's correlation with each
holding, how many **independent** positions the book really amounts to before and after adding
it — nine names that all move together are closer to one position than to nine — and what share
of the portfolio's risk each name carries against its share of the money. A holding with a
sixth of the money and half the risk is the portfolio wearing a smaller name.

**This is the only place in the app where a measurement informs position size, and it was
earned.** Using a correlation to size something is a claim that last year's correlation says
something about next year's, so that was measured first: across four index universes, one
year's pairwise correlations rank-correlate **0.50 to 0.65** with the next year's, at
t-statistics near or above ten. The composite ranking's information coefficient, by contrast,
was indistinguishable from zero. The same measurement found the limit and the panel carries it:
correlations run about **0.06 higher in the worst quarters**, so an ordinary year's reading is a
floor on how correlated these will be when it matters.

Holdings live in your browser, never on a server — this app still has no database. They are sent
to answer that one question and forgotten, and they never reach the analytics event.

**It is the one `POST` in the app, and the reason is the input rather than the size.** A company
name in a URL is not a fact about anybody; a holdings list is, and URLs are logged by every hop
that handles them — the platform's access log, any proxy in between, the browser's own history.
None of that is reachable by a response header, so the input has to leave the address bar rather
than be labelled once it is in it. The cost is that "everything the UI does is a plain GET" is
now "everything except this", plus one CORS preflight on that call.

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

**Does the ranking work?** The panel that presents an order now carries the finding about
whether that order predicts anything. Twelve backtests — four universes at three holding
periods — rank each universe using only data available on the date, then measure the
correlation between rank and what happened next.

**The answer is no, and the app says so.** One of the twenty-four tests cleared the
conventional 5% cutoff, against 1.2 expected by chance from running that many, and none
survives a Benjamini-Hochberg correction. The panel also reports the smallest effect the
sample could have detected — around 0.08 at best, where a genuinely useful information
coefficient is nearer 0.03 — so the honest reading is *no edge large enough to see here*,
not *no edge*. Survivorship, costs and sample size are stated alongside.

Measured offline by `scripts/backtest_ranking.py` and stamped with its date. Re-run it after
changing anything in `ranking.py`.

**Do the four lenses actually say different things?** The app's loudest claim is not that any
lens is right — it is that four lenses rest on **two independent bodies of data**, so agreement
between those two is not one fact counted twice. The rail prints a count built on that claim on
every run, and until now nothing had checked it.

The check is Cohen's κ between the two families' actual verdicts across 168 names in four index
universes, because raw agreement is uninterpretable: a lens calling 70% of companies cheap and
one calling 70% sound land on the same label **58% of the time while sharing nothing at all**.
Chance-corrected, price and filings come out at **κ = +0.03 (US +0.05, IDX +0.09)**, on
intervals that straddle zero in all three. **The claim survives** — measured now, not asserted,
and the sentence on the panel is written from whichever way the number came out.

The unexpected half: **Flow and Trend, the pair the app collapses into one vote precisely
because they read the same price series, agree at κ = +0.03 as well.** The four together carry
3.7 lenses' worth of independent information rather than the two they are counted as. The
grouping was left alone regardless, and the panel says why — a vote uncorrelated with everything
is what an independent reading and an uninformative one both look like, and the Flow lens's own
event study returns nulls. Two pairs came out *negatively* correlated; one of those (a rising
price making a DCF look expensive) explains itself, and the other is recorded without an
explanation.

Measured offline by `scripts/measure_lens_agreement.py`, which pushes every name through the
same four production engines a real request uses. Re-run it after changing what any lens
concludes.

**Pre-trade checks.** Nine conditions that would give a careful buyer pause, drawn entirely
from figures the four lenses already computed — so the panel costs no extra fetch and every
line can be traced to the tab that owns it.

The new part is not the conditions, it is the **firing rate** beside each one, measured
offline across the four index universes by `scripts/calibrate_checks.py` and stamped with its
date. Without it, nine conditions read as nine independent alarms; with it, the panel can say
which are rare enough to mean something here. Three rules follow, and all three are enforced
rather than intended: a check with no measured rate is **withheld entirely**, a check that
fires on more than a third of the universe is **demoted from a flag to a stated base
condition**, and a condition that could not be tested lands under *not checked* — never under
*clear*.

**The rates are per market, and the run is what forced that.** "Scores built from incomplete
data" fires on 16% of US large caps and 85% of Indonesian ones — which is Yahoo's coverage of
smaller IDX filings, not a fact about the companies. A blended rate near 40% would be
simultaneously alarming for a US listing and reassuring for an IDX one, so each check carries
a rate for each market and the panel uses the one the ticker actually belongs to.

Of the nine, three survive as flags in both markets, three are ordinary in both, two split
along the market line, and one — "the move is inside the cost of trading it" — turned out
never to be evaluable, because on every index constituent the spread sits below what daily
bars can resolve. It is withheld and the panel says so.

That last distinction is the panel's whole design. A bank's refused accounting screens, a
failed leg and a spread below the estimator's resolution floor are all reasons a condition
was never evaluated, and a checklist that rendered them as green ticks would have made the
app more authoritative than its evidence supports.

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
| `returns[returns < 0].std()` for Sortino | **The published root-mean-square shortfall** | They are different statistics. The old one ran 0.85x on ordinary returns, 1.44x where losses are rare and large, and exactly zero when every loss is the same size — where Sortino came back as 4.7e14. See RESEARCH_ROADMAP §13 |
| A journal that tells you whether you were right | **One that shows what you wrote, and what has moved** | Grading its own entries would be a backtest of one, on a self-selected sample, with no control for the theses never written down. Movement is reported as movement |
| Asserting that four lenses are two independent readings | **Cohen's κ between the families' actual verdicts** | Two lenses with skewed habits agree most of the time while sharing nothing: one that calls 70% of companies cheap and one that calls 70% sound land on the same label 58% of the time by construction. Chance-corrected, the price record and the filings come out at κ = +0.03 across 168 names — so the cross-check is earned. The same run found the pair the app declares REDUNDANT agrees no more than that |
| Sizing on a correlation because it seems reasonable | **Measuring whether correlations persist first** | One year's pairwise correlations rank-correlate 0.50-0.65 with the next year's across four universes, where the ranking's information coefficient was indistinguishable from zero. That gap is the whole licence for the portfolio panel, and a test fails if a re-measurement removes it |
| A bare screen flag | **Bayes on the screen's published error rates** | A screen that catches most manipulators on a population where manipulation is rare still produces mostly false alarms. The prevalence decides the answer and nobody can measure it, so it is a control — and the conclusion holds across every value the literature supports |
| An accounting score with no provenance | **The published sample, on the axes that can be checked** | Piotroski was fitted on US value stocks in 1976-1996, Altman on 1960s manufacturers, Beneish on 1980s SEC cases. Every use today is outside all three, which is provenance rather than a defect — so it is stated, never coloured, and never counted into a fit score |
| A pre-trade flag on its own | **The flag plus its measured firing rate** | "Altman says distress" is unreadable without knowing how often Altman says distress. Measured across four index universes: the conditions that turned out to fire on most of the market are demoted to base conditions rather than presented as findings, and an uncalibrated check is withheld |
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
              journal.ts  The thesis journal — client-only by design, so its
                          logic is tested by scripts/check_frontend.mjs
api/
  index.py    One FastAPI app — routing, rate limiting, validation
  _lib/       The engines:
              market_data.py    THE ONLY MODULE THAT IMPORTS YFINANCE —
                                one fetch, one normalisation, one cache
              backtest.py       Does the composite ranking predict anything?
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
              pretrade.py       The conditions that would stop a careful buyer,
                                each gated on a measured firing rate
              screendomain.py   Whether a use of an accounting screen sits inside
                                the sample it was validated on
              portfolio.py      The candidate against a book of holdings —
                                correlation, independence, risk against money
              lensagreement.py  How much the four lenses actually agree, once
                                each one's own habits are accounted for
              posterior.py      What a flag is worth once you account for how
                                rare the thing it screens for is
              explain.py        Plain-English interpretation for every metric,
                                and the cross-lens synthesis
              symbols.py        Ticker → Yahoo symbol, resolved once
              news.py           Google News RSS
              jsonsafe.py       NaN/inf → null before serialising
docs/
  field-manual.html   Beginner's guide; glossary generated from _lib/explain.py
scripts/
  build_glossary.py   Regenerates that glossary, and CI's drift check
  calibrate_checks.py How often each pre-trade check fires, measured offline
  measure_correlation_stability.py
                      Do correlations persist? The measurement that
                      licenses the portfolio panel to inform position size
  measure_lens_agreement.py
                      Do the four lenses actually carry separate
                      information? The measurement behind the rail's
                      "two independent sources"
tests/        1,100 offline tests
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

Everything the UI does is a plain `GET`, with one deliberate exception noted below.
Interactive docs at `/api/docs`.

| Endpoint | What it returns |
|---|---|
| `GET /api/confluence` | **All four lenses in one call, plus the synthesis and the pre-trade checks** — what the UI actually uses |
| `GET /api/isolation-forest` | Flow: anomalies, accumulation regimes, liquidity profile |
| `GET /api/technical-analysis` | Trend: indicators, levels, signals, narrative |
| `GET /api/intrinsic-value` | Value: DCF / DDM / RI with Monte Carlo percentiles |
| `GET /api/quality` | Quality: F-Score, Z''-score, M-Score |
| `GET /api/event-study` | Abnormal returns after each anomaly, with t-stats |
| `GET /api/rank` | **Rank a universe** on price signals, with per-signal breakdown |
| `GET /api/rank/universes` | The predefined lists, each with its as-of date |
| `POST /api/portfolio` | **A candidate against a book of holdings** — correlation, independent positions, risk against money. The one POST, and the one `no-store` |
| `GET /api/peers` | **Where one ticker sits among its own index** on the seven price signals |
| `GET /api/rank/deepen` | Quality + valuation for a shortlist of up to 8 |
| `GET /api/exposure` | **What a whole universe moves with** — every name against the factors whose betas were measured to persist, as a cross-section. Needs no ticker |
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

After touching anything that reads a field from the data source, run the invariant hunt. It
asserts relationships that must hold for every real company — price × shares against market
cap, the resolved dividend against what was actually paid, statement magnitudes against market
cap — and reports the ones that break. It needs the network, so it is deliberately **not** in
CI; an upstream outage must never redden the build.

```bash
.venv/bin/python scripts/check_data_invariants.py
```

Both currency bugs found so far were invisible to the offline suite and turned up here.

The pre-trade panel's firing rates are measured the same way — offline, network-dependent,
outside CI, and stamped with the date. Re-run it after adding a check or moving a threshold,
because a stale rate attached to a changed check is worse than no rate at all: it is a number
the panel prints with confidence.

```bash
.venv/bin/python scripts/calibrate_checks.py
```

The rail's claim that four lenses are two independent readings is measured the same way, and
re-run on the same terms: after anything that changes what a lens CONCLUDES — a verdict band,
a tone, the family grouping itself. It costs a full pass through all four production engines
for every name in four universes, which is why it is a script rather than a request.

```bash
.venv/bin/python scripts/measure_lens_agreement.py
```

The field manual's glossary is generated, so regenerate it after touching the explanation
layer — CI fails if you forget:

```bash
.venv/bin/python scripts/build_glossary.py
```

CI (`.github/workflows/ci.yml`) runs pytest + ruff, the manual's drift check, tsc + eslint +
build, and a production `npm audit`. `npm run check:frontend` covers the logic that only ever
runs in a browser — the confluence rail's independence count and the thesis journal — and
enforces one source-level invariant the compiled assertions cannot see: that nothing about a
reader's own thesis appears in the request layer.

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

**Currency, and the fields that follow it.** A company can keep its accounts in one currency
and trade in another, and on
the IDX that is not an edge case: **13 of the 46 names in IDX30 and LQ45** report in US dollars
because they sell coal, nickel or gas priced in dollars, while their shares trade in rupiah.
The statements are converted to the trading currency at spot before anything is valued, the
panel says so, and where no rate can be fetched the valuation refuses rather than comparing
dollars to rupiah. A five-year projection converted at today's rate carries the currency's risk
as well as the company's. The data source is not internally consistent about which of its
dividend fields follows which currency, so every dividend figure is checked against the share
price it will be compared with before it is used.

**Data.** yfinance is an unofficial scraper against an undocumented endpoint, with no SLA.
Fundamentals for smaller IDX listings are patchy — where a figure is missing, the app offers
a manual-input form rather than guessing. This is the single biggest fragility in the
project.

**Estimator resolution.** Two numbers are reported as bounds rather than measurements, because that is what the data supports. The bid-ask spread cannot be resolved below roughly 0.15× a stock's daily volatility from daily bars, so on liquid names the panel says "at most X" instead of quoting a figure. The Hurst exponent is noisy enough that its "random walk" band is sized from the sample, so a short range says "cannot tell" rather than guessing. Both floors were measured by simulation, not assumed — see `_lib/microstructure.py` and `_lib/indicators.py`.

**Statistical.** Results are in-sample, on one ticker at a time, with overlapping windows.
The event study is indicative, not a backtest — and its *events* are chosen by a detector
fitted on the whole loaded window, so selection is not point-in-time even though each CAR's
market model is. That picks about 93% of the events a strictly point-in-time detector would;
the Flow tab's walk-forward mode has no look-ahead at all. The Flow lens has no walk-forward validation
enabled by default because it costs minutes per ticker.

**Measured lens agreement is a measurement of this app, not of the market.** The unit is a vote
derived from a prose verdict, so what κ describes is how often two panels' headline stances
coincide across 168 large caps — not how correlated the underlying information is. Move a verdict
band and the number moves. It also cannot say *why* two readings overlap: two independent tests
of a genuinely sound company should agree, so redundancy and a shared truth look identical from
there. And a κ near zero cannot distinguish a reading that carries separate information from one
that is mostly noise.

**Firing rates decay with the lists they were measured on.** The pre-trade panel's base rates
come from the four universes below, so they inherit every one of that section's problems plus
one of their own: they are today's constituents measured over today's five years, and a
different half-decade would move them. The panel prints the measurement date beside them. A
rate is a prevalence, never a probability that this company is in trouble.

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

**Not implemented on purpose.** An "earnings inside your holding horizon" check: every listed
company reports quarterly, so at any horizon of three months or more it fires on essentially
everything and the pre-trade panel's own calibration rule demotes it to a base condition
immediately. Order-flow toxicity (VPIN/PIN) needs trade-level data; a
daily approximation would be a different number wearing the name. Multi-bar chart patterns
(head and shoulders, flags, wedges) are named and declined rather than matched with fixed
thresholds that would fire on noise. Calendar effects
(January, Halloween) are where the multiple-testing critique bites hardest. Headline
sentiment would need full article text and a lexicon that covers Indonesian.

**No state.** No accounts, no saved watchlists, no persistence on any server. The reading mode,
the holding horizon, the holdings list and the thesis journal live in your own browser's storage
and go no further — the journal never crosses the wire at all, and the build fails if it starts
to;
every session starts empty on a new machine. The portfolio route is the one place personal
input crosses the wire, and what that does and does not cost is set out on the panel itself.

---

## Further reading

- **[docs/field-manual.html](docs/field-manual.html)** — a beginner's guide to the whole app
  ([published copy](https://claude.ai/code/artifact/a73e6190-7252-430a-a57b-a84fe7cfd009)). All four
  lenses, the synthesis that reads them together, the statistics that decide whether to believe any
  of it, and every one of the 85 metrics in a searchable glossary. Assumes no prior finance.

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
