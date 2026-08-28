# QuantDesk — Research Basis

**Implemented 20 August 2026.** Every model below is in the codebase, tested offline, and
wired into the API and UI. This document records *what* was added, *why that specific
estimator*, and *what it does not claim*.

---

## 0. The bug that started this

Auditing data availability for the new models surfaced a live defect.

IDX filers report cash flow by the **direct method**, which Yahoo labels
`Cash Flowsfromusedin Operating Activities Direct`. That string was not in `ROW_ALIASES`, and
the substring fallback could not reach it. Free cash flow still populated from the reported
`Free Cash Flow` row, so valuations were never wrong — but **every Indonesian company showed
`n/a` for operating cash flow**, on the one market this product exists to cover:

| Period | Operating CF | Capex | Free CF |
|---|---|---|---|
| 2025 (before) | **n/a** | -Rp 25.77T | Rp 38.07T |
| 2025 (after) | **Rp 63.84T** | -Rp 25.77T | Rp 38.07T |

The alias is **exact-match only**. `_get_row`'s substring fallback would otherwise match the
sibling rows that live beside it — `Other Cash Paymentsfrom Operating Activities` and friends
are components *within* the total, and silently selecting one would produce a confident, wrong
free cash flow. That is the failure mode `symbols.py` was written to prevent, in a new place.

---

## 1. Replacing arbitrary constants — `_lib/microstructure.py`, `_lib/riskmodel.py`

### Beta: Vasicek shrinkage replaces the `[0.4, 2.5]` clip

`clip_beta` was doing the right *job* — raw betas are noisy, extremes are usually estimation
error — with a hard edge applied identically to a mega-cap measured over 500 days and an IDX
small cap whose beta is barely distinguishable from noise.

Beta is now regressed against the stock's own market index (`^GSPC` / `^JKSE`) over a stated
window, and shrunk toward 1.0 **in proportion to its own standard error**:

| Ticker | Raw β | Std err | R² | Prior weight | Adjusted β |
|---|---|---|---|---|---|
| AAPL | 1.108 | 0.062 | 39% | 1.5% | 1.106 |
| TLKM.JK | 0.963 | 0.069 | 29% | 1.9% | 0.964 |
| BBCA.JK | 0.888 | 0.048 | 42% | 0.9% | 0.889 |

These are liquid names, so shrinkage is correctly near-zero. It bites where it should: a beta
with a standard error of 1.5 is pulled ~87% of the way to the market. A test measures this
directly — across 300 simulated noisy estimates of a true β = 1.0, Vasicek's mean squared error
beats the fixed clip. `clip_beta` survives as a last-resort sanity bound only.

> Blume (1971), *JoF* 26(1) — the rule Bloomberg ships as "adjusted beta".
> Vasicek (1973), *JoF* 28(5) — precision-weighted shrinkage.

### Monte Carlo σ: calibrated, and a units error caught in the process

`sd_growth = 0.02` set the entire width of the fan chart and came from nowhere. It is now
estimated from the company's own cash-flow record, shrunk toward a prior because four filings
give three growth observations.

**The first implementation was wrong and the fix matters.** Feeding raw year-over-year growth
dispersion in produced σ ≈ 0.18–0.24 and a $26–$347 range for AAPL. The Monte Carlo draws *one*
growth rate and applies it to all five years, so the quantity needing a standard deviation is
the **five-year average**, not one year's scatter:

```
predictive_sd = s · sqrt(1/n + 1/horizon)
```
(parameter uncertainty about the mean, plus realisation scatter around it)

| Ticker | Per-year scatter | Calibrated σ | P5 – P95 |
|---|---|---|---|
| AAPL | 0.111 | 0.060 | $68 – $180 |
| KO | 0.340 | 0.137 | $6 – $120 |
| BBCA.JK | 0.179 | 0.080 | Rp 2,212 – Rp 6,813 |

### Liquidity and volatility — the confound the flow engine could not see

The anomaly engine claims an unusual volume day is an institutional footprint. The most common
way that is wrong is liquidity: on a thin stock, "heavy volume moved the price" describes a
shallow order book. Four estimators, all from OHLCV already fetched:

- **Amihud (2002)** ILLIQ — price impact per dollar traded.
- **Corwin-Schultz (2012)** and **Abdi-Ranaldo (2017)** — effective bid-ask spread from daily
  bars.
- **Yang-Zhang (2000)** — drift-independent, gap-aware volatility, replacing the mean high-low
  range in "typical swing".

Validated against simulated paths with a *planted* spread. Abdi-Ranaldo recovers truth to ~1%
and is the headline estimate; Corwin-Schultz reads ~0.7% on a zero-spread series — the upward
bias its own authors describe:

| True spread | Corwin-Schultz | Abdi-Ranaldo |
|---|---|---|
| 0.0000 | 0.00705 | **0.00000** |
| 0.0100 | 0.01240 | **0.01014** |
| 0.0300 | 0.02728 | **0.03045** |
| 0.0500 | 0.04538 | **0.05047** |

Getting this right required following each paper's own aggregation order. Abdi-Ranaldo averages
the **squared** quantity and takes one square root at the end; clipping and rooting per
observation — the obvious way to write it — discards every negative draw and biases the estimate
up by roughly 2x on a liquid name.

One deliberate asymmetry: the point estimate is Abdi-Ranaldo, but the *"this move may be spread
noise"* warning uses the larger of the two. An unnecessary caveat costs a second of attention;
a missing one lets someone act on a signal that cannot survive a round trip.

**Not implemented, deliberately:** VPIN (Easley-López de Prado-O'Hara 2012) and PIN (Easley et
al. 1996) both need trade-level data with buy/sell classification. A "daily VPIN" is not a
weaker VPIN — it is a different number wearing its name.

---

## 2. A fourth lens: accounting quality — `_lib/quality.py`

Flow, trend and value all read the company from outside. None opens the filings. A DCF on a
company sliding toward insolvency is arithmetic, not a valuation.

| Model | Question | Reference |
|---|---|---|
| Piotroski F-Score | Is the fundamental trend improving? | Piotroski (2000), *JAR* 38 |
| Altman Z''-EM | How far from distress? | Altman (1968); Altman (2005), *Emerging Markets Review* 6(4) |
| Beneish M-Score | Do the accruals look manipulated? | Beneish (1999), *FAJ* 55(5) |

Live output:

| Ticker | Verdict | F-Score | Z''-EM | M-Score |
|---|---|---|---|---|
| AAPL | NEUTRAL | 8/9 strong | 5.56 grey | −2.29 clean (8/8) |
| KO | SOUND | 7/9 solid | 7.97 safe | −2.35 clean (8/8) |
| TLKM.JK | NEUTRAL | 5/9 mixed | 6.18 safe | −3.26 clean (7/8) |
| BBCA.JK | **not applicable** | — | — | — |

Two design decisions worth stating:

**Applicability is enforced, not assumed.** Piotroski explicitly excluded financials; Altman
built Z on manufacturers, and working capital and current ratio are meaningless for an
institution with no operating cycle; Beneish assumes a receivables-and-inventory revenue model.
For a bank the module returns `applicable: false` with the reason. Silence is the correct
output.

**A missing signal never scores a point.** An unavailable Piotroski test is reported as
unavailable and the denominator moves — 5/7 and 5/9 mean different things. Awarding a pass for
absent data is the easy bug here, and it would inflate every thin-coverage listing.

AAPL's "grey" Z'' is the known buyback artifact (negative working capital, depressed retained
earnings), not a defect — the model behaves as published.

---

## 3. Residual income — retiring a workaround, not adding a feature

The manual-rescue form exists largely because **Yahoo's dividend fields are empty for IDX
banks**: a DDM with no dividend has nothing to discount, so the engine stopped and asked the
user to type in a figure Yahoo does not have.

Ohlson's residual income model needs book value and ROE instead — both reliably reported in
exactly those filings, and both already computed by `bank_diagnostics`:

> V₀ = B₀ + Σ (ROEₜ − r)·Bₜ₋₁ / (1+r)ᵗ + fading continuing value

A dividend-less financial now **routes to RI automatically** rather than failing into the manual
form. The structural advantage shows up immediately:

| BBCA.JK | Implied | Terminal value share | P5 – P95 |
|---|---|---|---|
| DDM | Rp 3,950 | **63%** | Rp 2,212 – 6,813 |
| Residual income | Rp 3,274 (1.43× book) | **5%** | Rp 2,470 – 4,130 |

Abnormal earnings *fade* at a persistence factor rather than growing in perpetuity, so RI does
not inherit the terminal-value dominance the app has to warn users about on the DCF and DDM.

The model has an invariant the other two lack, and it is the strongest test in the suite:
**ROE = cost of equity must return exactly book value.** A company earning precisely its cost of
capital creates nothing beyond invested capital. Any error in the discounting, the clean-surplus
roll-forward or the continuing value breaks that identity immediately.

> Ohlson (1995), *Contemporary Accounting Research* 11(2).
> Persistence 0.62 from Dechow, Hutton & Sloan (1999).

---

## 4. Sustained accumulation — `_lib/accumulation.py`

A conceptual gap in the product's own thesis: **the Isolation Forest finds point anomalies, but
an institution building a position splits the order across weeks precisely so no single print is
remarkable.** A detector scoring each day independently is structurally blind to the patient
buyer the product is named after. It can only catch the impatient one.

Page's CUSUM accumulates small deviations, so a run of individually unremarkable days trips a
threshold none of them would alone. It runs on `OBV_Change_Z`, a feature `whale.py` already
engineers — no extra fetch. AAPL, two years:

| Direction | Began | Confirmed | Days | Price | Avg RVOL |
|---|---|---|---|---|---|
| Distribution | 2025-04-03 | 2025-04-08 | 10 | −4.4% | 1.65× |
| Accumulation | 2024-11-22 | 2024-12-20 | 27 | +6.1% | 1.04× |

Note the 28-day gap between changepoint and confirmation on the second episode: the regime is
backdated to where the statistic left zero, so the reader sees both when it began and when there
was enough evidence to say so. Note also the RVOL of **1.04×** — that accumulation was invisible
to any volume-spike rule.

**A bug found by testing:** a single 40σ print pushed the statistic far past the threshold, and
because CUSUM decays only by the slack per day, it reported a fictitious eleven-week "regime"
made entirely of one day's decay tail. Fixed with the winsorized CUSUM variant, capping each
observation at 4σ. That cap is also the conceptual boundary between the two detectors: an
extreme single day is the point detector's finding, not this one's.

> Page (1954), *Biometrika* 41. Basseville & Nikiforov (1993).

---

## 5. Does the signal work? — `_lib/eventstudy.py`

Every anomaly product asserts its signal means something. This measures it, and reports the
answer whatever it is. AAPL, 5 years, 39 anomalies, 35 studied against `^GSPC`:

| Horizon | Mean CAR | t | p | Hit rate |
|---|---|---|---|---|
| +5d | +0.73% | +0.97 | 0.338 | 46% |
| +20d | −0.28% | −0.20 | 0.844 | 44% |
| +60d | −0.55% | −0.26 | 0.793 | 35% |

**No evidence of predictive power on this ticker.** That is the feature working. A tool that
only ever confirms itself is worth nothing; being the one that publishes its own null result is
the differentiator.

The estimation window ends 10 days *before* each event. If an anomaly is the visible edge of a
multi-day episode — which §4 exists to detect — fitting through it contaminates the baseline with
the behaviour under test and shrinks the abnormal return toward zero.

**PEAD tagging:** 10 of AAPL's 39 anomalies sit within 3 days of an earnings release. The app's
disclaimer already said anomalies have benign causes; this names the most common one.

**Multiple testing on the screener:** each ticker's recent count is tested against *its own*
long-run flag rate by exact binomial test, then Benjamini-Hochberg controls the false discovery
rate across the scan. Per-ticker calibration is the point — a fixed count threshold silently
favours chronically noisy stocks. The UI now shows a q-value column and "about N hits would be
expected from base rates alone."

> Brown & Warner (1985), *JFE* 14(1). MacKinlay (1997), *JEL* 35(1).
> Bernard & Thomas (1989), *JAR* 27. Benjamini & Hochberg (1995), *JRSS-B* 57(1).
> Harvey, Liu & Zhu (2016), *RFS* 29(1).

---

## 6. The independence caveat, stated in the product

The header claimed "three independent models... where they agree is more interesting." Flow and
trend are both functions of the same price and volume series; only value and quality read the
filings. Four lenses that agree are therefore weaker evidence than four *independent* tests
agreeing.

This now appears in the confluence rail itself rather than in a footnote. Quantifying the
correlation between lens votes across a universe remains open work — see below.

---

## 7. Pre-trade checks, and why a flag without a base rate is not shippable

**Added 28 August 2026.** The app can describe a company well and correctly refuses to score
it. What it could not do was answer the narrower question a reader actually arrives with:
*what would argue against buying this?* Every ingredient was already computed — the distress
band on the Quality tab, the terminal-value share on Value, the Hurst verdict inside the
long-horizon section — but each lived in the panel a reader would only open if they already
suspected the problem, which is the one case where a warning is redundant.

`_lib/pretrade.py` collects nine of them onto one surface. It reads the ASSEMBLED
`/api/confluence` payload rather than recomputing anything, the same discipline
`explain.for_synthesis` uses and for the same reason: every line must quote the figure the
panel renders, and a parallel computation would eventually disagree with it. The panel costs
no extra fetch and no extra model fit.

### The measurement that had to come first

The conditions are not the contribution. "Altman says distress" is unreadable on its own —
whether it is a finding about this company or a description of the equity market depends
entirely on how often it is true of companies in general, and nothing in this repo knew that
number. Presenting nine conditions as nine alarms without it is the same multiple-testing
mistake the anomaly screener already corrects, arriving somewhere new: a scan produces hits
by construction, and the hit count means nothing until you know how many were expected.

So `scripts/calibrate_checks.py` runs each predicate across the four universes in
`universes.py` and writes `check_calibration.json`. The price half batches through
`market_data.ohlcv_batch`; the filings half is one `fetch_company` per symbol, which is why
this is an offline stamped script rather than a request — the same treatment
`backtest_ranking.py` gets, for the same two reasons.

Symbols are deduplicated across universes before the headline rate is taken. IDX30 is a
subset of LQ45, so adding four universes' counts would weight every Indonesian large cap
twice and tilt every rate toward one market.

Could-not-run is counted separately from did-not-fire. A bank whose accounting screens are
refused has not passed them, and folding the two together would give a check that is
inapplicable to half the universe an artificially low firing rate — promoting it from base
condition to flag by its own coverage gap.

### The blend that had to be undone

The first complete run reported one rate per check across all four universes, and one of the
results made that indefensible. **"Scores built from incomplete data" fires on 10% of the Dow
and 16% of the Nasdaq-100, and on 80% of IDX30 and 84% of LQ45.** That is not a fact about
companies — it is Yahoo's fundamentals coverage for smaller Indonesian listings, which this
README has always named as the project's single biggest fragility, showing up as a number for
the first time.

The blended rate lands near 40%. It is simultaneously alarming for a US large cap, where the
condition is genuinely unusual and worth a flag, and reassuring for an IDX one, where it is
the norm and should be demoted. **Neither reading is true of the company in front of the
reader**, which is the definition of the wrong number.

So each check now carries a per-market rate as well as a combined one, and `_rate_for` prefers
the market of the resolved symbol — falling back to the combined rate only for a market nobody
calibrated, and naming the group either way. The same discipline that made percentiles
preferable to scores in `ranking.py`: a rate is a claim about a stated population on a stated
date, and the population has to be one the reader is actually in.

### What the measurement changed

Measured 28 August 2026 over five years of daily data, US against the Dow and the Nasdaq-100,
IDX against IDX30 and LQ45. The denominator is names where the check could be **evaluated**;
where it could not — a refused lens, a missing statement — that is counted separately and
never as a pass.

| Condition | US | IDX | Reads as |
|---|---|---|---|
| Balance sheet inside the distress zone | 11% of 112 | 15% of 39 | flag |
| Accrual pattern flags on the manipulation screen | 3% of 115 | 8% of 39 | flag |
| Fundamental trend deteriorating | 1% of 115 | 3% of 39 | flag |
| Most of the valuation is a perpetuity guess | 90% of 115 | 95% of 37 | base condition |
| The price assumes more growth than the model does | 53% of 95 | 15% of 33 | **base in the US, flag on the IDX** |
| Scores built from incomplete data | 16% of 121 | 85% of 46 | **flag in the US, base on the IDX** |
| Price series indistinguishable from a random walk | 78% of 120 | 93% of 46 | base condition |
| The latest move is inside the cost of trading it | — | — | withheld, never evaluable |
| Has already fallen more than half | 46% of 120 | 67% of 46 | base condition |

Of the nine, three survive as flags in both markets, three are demoted in both, two split
along the market line, and one turned out never to be evaluable at all. The demotions are the
most interesting output here, and none of them was decided by argument.

**Almost every large-cap price series is indistinguishable from a random walk at five years
of daily data.** The app's own honesty check, which exists to say when the trend tools are
describing noise, turns out to say it about most of the market. That is a statement about
equities, not about any company on the panel, and printing it as a flag would have attached
alarm to the ordinary case.

**A discounted cash flow is terminal-heavy essentially always.** The 60% threshold the
synthesis already warns at is cleared by nearly every name measured. Worth stating; not worth
flagging.

**The price implies more growth than the model assumes on half the US universe** — which is
what happens when the model's growth input is a default and the default is not a forecast.
This one was predictable in advance and was deliberately left to the data to decide, because a
rule that only ever confirms a prior judgement is not being tested. On the IDX it fires on 15%
and stays a flag, which is the market split earning its keep on the first check that met it.

**And one condition can never be evaluated at all.** "The latest move is inside the cost of
trading it" returned no evaluable names in any universe: on every index constituent the
bid-ask spread sits below what daily bars can resolve, so `microstructure.py` correctly
declines to quote one and the check has nothing to compare against. It is withheld rather than
deleted — the app knows how to evaluate it, has no base rate for it, and says exactly that on
the panel. That is the rule biting a check that might well have been useful on a thinner
stock, and paying that cost is the point of having the rule.

Three rules follow from the calibration and all three are enforced in code rather than
intended: an uncalibrated check is **withheld from the panel entirely**, a check above
`BASE_RATE_MAX` is **demoted to a stated base condition and rendered uncoloured**, and a rate
measured on fewer than `MIN_CALIBRATION_SAMPLE` names is treated as no rate at all.

### What it does not claim

**An empty panel is not evidence of quality, and the design is built around refusing to imply
otherwise.** There is no pass state, no count, no score, no severity ordering and nothing
green anywhere on the surface. `tests/test_pretrade.py` asserts on the payload's key set
rather than on wording, because an aggregate field is exactly the thing a later change would
add without noticing — and once it exists, three flags on one company read as worse than two
on another, which is a comparison the firing rates exist to say is unavailable.

**No condition here predicts anything.** Every one is a present-tense statement about a figure
already on the page. None is a claim about subsequent returns, none was fitted, and the
firing rate is a measurement of prevalence rather than of skill. The panel names where each
number lives so it can be gone and checked, which is the only authority it asks for.

**Not checked is not clear.** A refused lens, a missing filing, a short chart range and a
spread below the estimator's resolution floor are each recorded, with the reason, in a list
the panel renders — and the last of those explicitly says the cost is small rather than
unknown, because reporting the estimator's own noise floor as a trading cost would be the
same bug `microstructure.py` already fixed once.

---

## 8. Validation domain — where each accounting score came from

**Added 28 August 2026.** `quality.py` has always enforced APPLICABILITY: the three screens
refuse to score a bank, because none of them was built on one. That is a binary gate and it is
the right one. It is also a different question from the one a reader needs answered next.

Piotroski's nine tests were fitted on US filings from 1976 to 1996, on the highest
book-to-market fifth of Compustat, and the paper reports the benefit concentrated in small and
medium firms with low share turnover and no analyst following. Altman's coefficients come from
sixty-six US manufacturers that did or did not go bankrupt on filings from before 1966.
Beneish was estimated on fifty manipulators found through SEC enforcement actions between 1982
and 1988, against 1,708 industry-matched controls. **An IDX large cap in 2026 is outside all
three, on several axes at once**, and the app printed all three numbers without saying so.

`_lib/screendomain.py` reports where each number came from, on the axes that can actually be
checked: the period, the market, the kind of business, the size of firm, and — for Beneish —
how common the event was in the sample the model was tuned on.

### It is provenance, so it is never a colour

Both directions would mislead and the second is the dangerous one.

**Outside is not a warning.** Every practical use of all three models today is outside their
samples, because the samples ended between 1965 and 1996. A panel that painted that amber
would be crying wolf on three scores for every company forever, which is how a reader learns
to ignore a colour.

**Inside is not reassurance**, and that is the trap. A green tick against "period: inside"
tells a reader the number can be trusted here — a claim about the model's accuracy on this
company that nothing in this app measures. It is the same rule the pre-trade panel is built
around: absence of a mismatch is not evidence of fit.

So every reading sits in the `context` band, which the tone map renders neutral, and the
emphasis is typographic rather than chromatic. There is also **no fit score and no count of
matching axes**, for the reason a composite is refused everywhere else here: "3 of 4 match"
would be a reliability rating, and none of these papers reports how its model behaves on a
company like this one.

### Two things it surfaced that were not obvious

**Altman's market dimension runs the other way.** The zone boundaries the app uses come from
Altman's 2005 emerging-market recalibration, so an Indonesian listing is on home ground where
a US one is not — while the coefficients underneath, from 1960s US manufacturers, are outside
for both. That inversion is now stated on the panel; before it, "emerging-market variant" was
a phrase in a footnote with no consequence attached.

**Size is answered with index membership rather than a cash threshold.** A market-cap cutoff
would need a figure in dollars, a rupiah exchange rate, and a view on what "small" meant in
1976 against what it means now — three invented constants to answer one qualitative question.
Membership of the Dow, the Nasdaq-100, IDX30 or LQ45 says the same thing with none of them,
is already in the repo, and carries its own as-of date.

### Where it declines to answer

The book-to-market axis reports **"cannot tell"** for anything that is not obviously expensive.
Piotroski's sample is the highest book-to-market *quintile*, and a quintile is a position in a
cross-section: placing a name in one needs a universe-wide scan of book values, which does not
batch and is not run here. The module makes the one call the data supports — a company priced
at more than three times book is outside any published breakpoint for that fifth — and refuses
the other, rather than inventing a threshold. A test asserts it keeps refusing.

### A bug it found

Threading the market through as the request's `market` query parameter reported TLKM.JK as a
"US listing", because the dropdown said US while the suffix said otherwise. Those two are
genuinely different questions — `market` selects the valuation conventions, the suffix decides
what the security is — and this is the class of silent mismatch `symbols.py` was written to
prevent. `symbols.market_of` already existed; both this block and the pre-trade panel's
firing-rate lookup now use it.

---

## What is still open

| Item | Why it was not done now |
|---|---|
| Posterior probability for a Beneish flag | The operating characteristics are published — roughly three-quarters of manipulators caught, against a stated false-positive rate — and §8 now states the enriched base rate the model was fitted on, which is the other half of the arithmetic. What remains is sourcing both figures from the paper itself and making the prevalence prior editable with its sensitivity shown |
| Placing a company in a book-to-market quintile | §8 declines this rather than inventing a breakpoint. It needs a universe-wide scan of book values, and fundamentals do not batch |
| Portfolio context — correlation, effective independent positions, marginal risk | The largest gap. Holdings must stay client-side to respect the no-state stance, and correlation-aware sizing is a predictive claim that needs its own measurement (does this period's correlation describe the next one?) before it can ship |
| A stated holding horizon | `rollingReturns` is fixed at 1/3/5 years, so "the worst outcome at YOUR horizon" cannot be answered, and neither can "does an earnings date land inside it" |
| Measure the lens-vote correlation empirically | Needs a cross-sectional run over many tickers; the caveat is stated qualitatively meanwhile |
| Multi-factor cost of equity (Fama-French) | Factor returns are freely available for the US; constructing IDX factors is a project in itself |
| Sensitivity grid (growth × discount rate) | Cheap — `pv_of_growing_stream` is already vectorised over both axes |
| Peer / sector relative multiples | Needs a peer-set source beyond yfinance |
| IDX fundamentals curation | The durable moat, and the largest single effort |

**Corrected while writing this:** README quoted the price-implied growth rate moving across
"24% to 42%" over a range of discount rates, in a sentence that read as something the app
shows. It does not: varying the discount rate is a query parameter a reader can drive by hand,
and the sensitivity grid that would present the range is the open item two rows above. The
sentence now says what the panel actually does, which is to state the conditionality and point
at the editable input.

**Explicitly rejected:** calendar effects (January, Halloween) — precisely where the
multiple-testing critique bites hardest; headline sentiment — Loughran-McDonald is the right
lexicon but Tetlock's results used full article text, and LM does not cover Indonesian.

---

*Every model here is educational and research tooling, not investment advice. Several are
screens with high false-positive rates on populations where the underlying event is rare, and
each panel says so where that applies.*
