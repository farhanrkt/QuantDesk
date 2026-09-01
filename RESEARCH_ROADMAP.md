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

This now appears in the confluence rail itself rather than in a footnote.

**Quantified in §15, and the answer was not the one the caveat predicted.** Across 168 names
in four index universes, the two families' verdicts agree at κ = +0.03 — indistinguishable
from chance, so the cross-check is sound. But Flow and Trend, the pair grouped together here
*because* they read the same series, agree at κ = +0.03 as well: the redundancy this section
asserts shows up in the code and not in the votes. The grouping was left alone anyway, because
a vote that correlates with nothing is what an independent reading and an uninformative one
both look like.

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

## 9. What a Beneish flag is worth — the posterior, not the flag

**Added 28 August 2026.** The quality lens has said since it shipped that Beneish catches
roughly three-quarters of manipulators, and that on a population where manipulation is rare
that also means most flags are false alarms. That sentence was prose. It can be a number, and
the number is more useful than the sentence because it can be argued with.

    P(manipulator | flag) = sens . p / (sens . p + fpr . (1 - p))

Two of the three inputs are published. The third — how common manipulation is — is not a
property of the model at all but a claim about the population the reader is drawing from,
which is exactly why it is explicit and movable rather than baked into one headline figure.

### Which probit, and why the answer changes the arithmetic

Beneish reports two estimations, and picking the wrong one would have quietly halved the
answer.

The **WESML (weighted) probit** assumes a population manipulation rate of **0.69%**. The
**unweighted probit** assumes **2.844%**, the rate in its own sample. The coefficients every
implementation uses — the `-4.84` constant and the eight weights in `quality.beneish_m_score`,
including this one — are the **unweighted** ones. So the classifier this app ships carries an
implicit prior of 2.844%, and that is the default: it is the only prior at which the published
error rates and the shipped coefficients describe the same model rather than two different
ones.

At the -1.78 cutoff Beneish reports the model classifying about **76%** of manipulators
correctly and misclassifying about **17.5%** of non-manipulators — a trade-off he chose for a
30-to-1 relative cost of missing a manipulator against raising a false alarm.

### The result, and why it does not depend on the prior

| Prior | Where it comes from | P(real manipulator \| flag) |
|---|---|---|
| 0.69% | Beneish's own WESML prior | **3%** |
| 2.0% | Detected financial fraud, low end (Dyck, Morse & Zingales) | **8%** |
| 2.844% | The sample these coefficients were fitted on | **11%** |
| 3.0% | Detected financial fraud, high end | **12%** |
| 10% | All securities fraud including the undetected | **33%** |
| 14% | Top of their 95% interval | **41%** |

**At every prevalence anybody has published, a Beneish flag is more likely a false alarm than
a real finding.** That is a considerably stronger claim than "most flags are false alarms",
because it survives disagreement about the one input a reader could reasonably dispute. The
panel says so, and the control goes past the literature at both ends so a reader can see how
far the prior has to be pushed — about 27% — before a flag becomes more likely true than not.

The wider priors are marked as extrapolations rather than quietly averaged in. Beneish's
sensitivity was measured against manipulators identified by SEC enforcement action; "all
securities fraud including the undetected" is a broader event, and the error rates were never
measured against it. Those anchors bracket the range; they do not answer the same question.

### The clean branch, and why it is framed as a move

The mirror number is P(manipulator | no flag) = **0.84%** at the default prior. Printed on its
own beside a clean score that reads as a clean bill of health, which is the misreading this
codebase works hardest against.

So both branches report a **shift** rather than a level: the test takes 2.8% to 11% when it
fires, and to 0.8% when it does not. That framing is what makes the clean case honest — it
says the probability was already small and the test made it somewhat smaller, rather than
announcing that nothing is wrong. The reading also states what the screen does not test.

### It is never coloured, for a specific reason

The M-Score already comes back `bad` when it flags. This number is the qualifier on that
alarm and at every published prior it qualifies **downward**. A second warning colour would
count one fact twice and, worse, would make the figure that deflates the flag look like a
second flag. It sits in `context` like the validation-domain block, and for a related reason:
neither is a verdict.

### The control selects; it never calculates

The whole prior/posterior curve is served already computed and already worded, and the slider
picks a point on it. Recomputing in the browser would be smoother by one round trip that never
happens anyway — and it would put the arithmetic, and the judgement about what the number
means, in TypeScript, which is the one place this codebase keeps neither. Every stop is a
round number somebody could defend rather than a point on a dense grid, so the control cannot
land on 4.17% and render it with two decimal places of authority it has not earned.

### What it does not claim

Nothing here is fitted, measured or predicted by this app: it is Bayes' theorem on two
published constants, and it inherits every limit of the study they came from. §8 states that
study's sample and how far this use sits from it — which is the other half of reading the
number, and why the two blocks sit on the same panel.

The pre-trade panel's Beneish check now quotes the posterior too. It was carrying the vaguer
prose version in the more prominent place while the figure sat one tab away.

---

## 10. A stated holding horizon

**Added 28 August 2026.** The rolling-return distribution is the strongest evidence in this
app. It replaces "it returned 16% a year" — which describes one start date — with what EVERY
start date got, and the worst entry in that distribution is the number position sizing exists
to survive. It sat behind a tab, a section and a fixed 1/3/5-year table nobody chose.

The missing piece was not the table. It was that **nothing in the app ever asked how long the
reader intends to hold**, so "the worst outcome at your horizon" was not a question the app
could be asked. It now is: a horizon is stated once, persisted like the reading mode, and read
by both the new bar above the tabs and the table itself.

Why it matters is visible in one ticker. On AAPL over the app's default five-year range:

| Held for | Worst any buyer did | Made money |
|---|---|---|
| 1 year | **-30.2%** a year | 84% of 1,002 windows |
| 2 years | **-2.3%** a year | 99% of 750 windows |
| 3 years | **+0.2%** a year | 100% of 498 windows |

Those are three completely different investments, and until now the app answered as though the
question had one answer.

### The horizon never reaches the API

Every horizon the loaded history supports arrives already computed in the technical payload, so
the control selects rather than re-runs. A query parameter would have put a ten-to-sixteen
second four-lens round trip behind a control whose entire purpose is to be moved around — and
the same discipline as the posterior curve applies: the server has already done the arithmetic,
so shipping it is cheaper than shipping the inputs and recomputing in the browser.

Three years is the default because it is the shortest horizon over which the distribution stops
being dominated by the entry date, and because it is what the plain-English summary has always
quoted. One year would flatter almost everything; ten would report "needs more history" for most
tickers at the range this app loads.

### The bug the horizon exposed

`rolling_returns` used to `continue` past a horizon the history could not support, so the row
simply was not there. **On the app's own default five-year range the five-year row was always
missing** — five years of daily bars is about twenty-six short of the twenty-one overlapping
five-year windows a distribution needs — and a reader could not tell whether the stock had
never had a bad five-year stretch or whether nobody had looked.

That is the absence-reads-as-evidence failure the pre-trade panel is built against, sitting
unnoticed in the oldest table in the app. Unsupported horizons now come back marked, carrying
the exact shortfall and the fix: *"Needs about 1,280 trading days to have 21 overlapping
5-year periods, and this range has 1,254 — 26 short. Widen the chart range."*

Two consumers had to change with it, and both would have been quietly wrong otherwise: the
plain-English summary picked the 3-year row by key, and the Simple-mode metric card did the
same. With unsupported horizons now present, "there is a 3-year row" stopped meaning "there is
a 3-year answer", and a summary built from one would have described windows it never measured.
Both now select the longest MEASURED horizon. Tests cover exactly that.

### The earnings check, and why it is not here

"Does an earnings date land inside the holding horizon" was the last of the pre-trade checks
listed in §7 and deferred for wanting a horizon. The horizon now exists and the check still
should not ship, for a reason the calibration rule supplies:

**Every listed company reports quarterly.** At any holding horizon of three months or more, an
earnings print inside the window is a certainty — the check would fire on essentially 100% of
any universe and §7's own rule would demote it to a base condition on the spot. It is only
informative at horizons of days to weeks, which is the short-term section's territory rather
than this one's, and it is the one candidate check that needs a new upstream call on the app's
busiest route. Building it would mean paying a fetch on every confluence run to print a line
that says "this company will report earnings", which everybody already knows.

---

## 11. Portfolio context, and the measurement that had to come first

**Added 28 August 2026.** Every other lens here evaluates one ticker in isolation, which hides
the most common way a retail portfolio goes wrong: **the candidate is the fourth copy of a bet
already held.** Four names that each look independently reasonable and all move together are
one position with four ticker symbols on it, and nothing on a single-ticker page can say so.

### Why this feature had to be earned before it was built

Reporting that a candidate correlated 0.82 with a holding is a description of history and needs
no defence. The moment that number informs how much to buy, it becomes a claim about the
future — that last year's correlation says something about next year's. This codebase does not
ship unmeasured predictive claims; the ranking tier carries its own null result for exactly
this reason.

So `scripts/measure_correlation_stability.py` measured it first, and the answer decided the
shape of what shipped. Daily returns are cut into consecutive non-overlapping windows; within
each, every pair gets a correlation, and consecutive windows' pairwise vectors are rank
correlated. At a one-year window:

| Universe | Rank correlation, year to year | t | Mean pairwise ρ |
|---|---|---|---|
| Dow 30 | **+0.54** | +10.2 | 0.36 |
| Nasdaq-100 | **+0.65** | +15.7 | 0.36 |
| IDX30 | **+0.59** | +9.5 | 0.21 |
| IDX LQ45 | **+0.50** | +10.3 | 0.20 |

**This is a different world from the return backtests.** The composite ranking's information
coefficient was indistinguishable from zero across 24 tests; correlations rank-correlate at
0.50 to 0.65 from one year to the next at t-statistics near or above ten. Correlations are
among the few things about equities that are genuinely persistent, and that is what licenses
them to inform position size where a return forecast may not. A test asserts the shipped
measurement still supports it, so a future re-measurement that found otherwise would fail the
build rather than let the panel quietly carry on.

### The same measurement found the limit, and it is on the panel

In the worst quarter of quarters for those markets the mean pairwise correlation runs about
**+0.06 higher** than in the rest — up to +0.12 on the LQ45. A correlation measured over an
ordinary year is therefore a **floor** on how correlated these positions will be in the stretch
a holder actually needs the diversification. The panel says so beside the numbers.

### A measurement mistake worth recording

The first version of the stress test selected the worst **days** and computed a correlation
within them. It reported correlations *falling* in a crash — which is not a finding about
markets, it is the selection doing the work. Conditioning on the size of the common factor
truncates that factor's variance inside the subsample while leaving each name's idiosyncratic
variance alone, so the measured correlation moves for a reason that has nothing to do with the
market. Forbes & Rigobon (2002) is the canonical statement of the problem, and it is why so
many published "contagion" results evaporate.

Selecting whole **windows** removes the worst of it: each window keeps its own full
distribution of factor realisations. The sign flipped from -0.03 to +0.06 on the correction. A
milder version of the objection survives — the windows are still classified by their own
returns — and is stated on the panel rather than argued away.

### What it computes, and what it refuses to

Descriptions of a historical covariance matrix and nothing more: correlation against each
holding, how many **independent** positions the book really amounts to before and after adding
the candidate, and what share of the portfolio's risk each name carries against its share of
the money.

It does **not** output a recommended weight. Risk contribution and money contribution diverging
is the finding; what to do about it depends on why the positions are held, which this app does
not know and does not ask.

The independence estimator is the participation ratio `ranking.py` already uses to say seven
correlated signals carry about 3.4 signals' worth of information. It moved to `riskmodel.py` so
there is one implementation: two copies would eventually disagree about what redundancy means,
in an app whose whole argument is that correlated measures are worth less than they look.

### Two bugs the build found

**`eigvalsh` reads one triangle.** Handed a matrix with NaN on the diagonal it returned
perfectly finite eigenvalues computed from the half it happened to look at — a plausible number
from an unusable matrix. The estimator now refuses a non-finite matrix outright rather than
filtering non-finite eigenvalues afterwards.

**A negative risk contribution is a real and different thing.** Marginal risk contribution goes
below zero when a position moves against the rest of the book: it *subtracts* from total risk,
which is diversification actually working. The first version put that through the same ladder
as everything else and told a reader holding a genuine hedge that risk and money were "broadly
in line" — the least useful thing that could have been said about it. Found by running the
panel against a real book with a defensive name in it.

### No state, and what that costs

Holdings live in the reader's own browser, alongside the reading mode and the holding horizon.
They are sent on the one request that needs them, used, and forgotten; there is nowhere on the
server to keep them. Nothing about them reaches the analytics event, which has always carried a
market code and a lens count and never a ticker.

**This route is the app's only `POST`, and the reason is the input rather than the size.** The
first version was a GET, disclosing on the panel that the holdings therefore landed in the
hosting platform's access log. Disclosure was the wrong answer. A company name in a URL is not a
fact about anybody; a holdings list is, and URLs are logged by every hop that handles them — the
access log, any proxy in between, the browser's own history. None of that is reachable by a
response header, and a caveat does not delete a log line. The input had to leave the address bar
rather than be labelled once it was in it.

The costs are real and small. The stated shape of this app was that everything the UI does is a
plain GET; it is now "everything except one route". The CORS allowlist gains POST, which a test
holds to that one route by asserting every other endpoint still refuses it. And there is one
preflight on the call. `no-store` stays on the response even though a POST is uncacheable by
default, because "uncacheable by default" is a property of the method that a refactor could
quietly change while an explicit header says what was meant.

---

## 12. A thesis journal, and the no-state principle it had to respect

**Added 28 August 2026.** The last of the directions in the brief, and the only one that asks
the reader for something rather than telling them something. Recorded before acting: what has
to be true, what would falsify it, the horizon, the size, and whether you believe more or less
growth than the reverse DCF says the price requires.

### Nothing about it reaches a server, and that decided the architecture

Every other panel here sends a ticker away and gets a reading back. A thesis is the opposite
kind of object: it is what the reader believes, which is nobody else's business and has no
reason to leave the machine it was typed on. So it does not. It lives in this browser's local
storage beside the reading mode, the holding horizon and the holdings list, and **no request in
this codebase carries it**.

That constraint puts the logic in TypeScript, where this project deliberately keeps none of its
judgement. The resolution is the escape hatch the project already built for exactly this case:
`scripts/check_frontend.mjs` compiles modules with the `tsc` already in the tree and runs
assertions on bare node. `agreementOf` went the same way for the same reason, and `lib/journal.ts`
joins it — seventeen assertions covering the contradiction checks, the drift comparison and the
storage layer, on top of the eighteen that were there.

The invariant itself is guarded at source level, because it is a property of what the request
layer does **not** contain and no unit test on a compiled module can see it. `check_frontend.mjs`
greps `lib/api.ts` for any mention of the journal and fails the build if it finds one. The
failure it exists to catch is somebody adding a convenient "sync your journal" call years from
now without noticing what it costs. Verified by breaking it deliberately and watching the build
go red.

### An entry cannot be edited, and that is the feature

A thesis you can revise once you know how it turned out is a rationalisation with a timestamp
on it. The only version worth keeping is the one written before the outcome, in the words
actually used — so `appendEntry` only ever appends, there is no update path, and the snapshot of
what the app was showing is frozen into the entry rather than re-fetched when it is read back.

Deleting is offered, because keeping something against someone's wishes is a different kind of
wrong. Nothing rewrites.

### Nothing is ever scored

Entries come back as written. Where the numbers have moved since, the movement is reported as
movement — *"growth the price requires: 52% → 38%"* — and the block says in words that it is not
a verdict on the thesis that preceded it.

A journal that graded its own entries would be a backtest of one, on a sample the reader chose,
with no control for what they did not write down. This app refuses composites elsewhere on far
better evidence than that, and it would be strange to make the exception here, on the weakest
sample in the building.

### The one live check, in three parts

The brief called for a check on whether a recorded thesis contradicts what the lenses already
say. Three are checkable, and each names the gap rather than blocking on it:

* **Growth belief against the reverse DCF.** Both directions, because believing *more* than the
  price requires is as much a thesis as believing less — and the panel says so: *"that gap is
  the thesis: you are betting the market is asking too little of this business."* A five-point
  tolerance, because two people agreeing imprecisely are not disagreeing.
* **Position size against this stock's own worst fall.** *"A 70% position in something that has
  already fallen 33% peak to trough is 23% of the account, gone, in a repeat of a fall this
  stock has actually had. Not a forecast — a thing that happened."*
* **A losing worst case at the stated horizon**, where the rolling-return distribution has one.

Disagreeing with the model is a respectable thing to do — the reverse DCF exists to be argued
with, and the Value lens has always said so. Disagreeing without noticing is not, and that is
the whole of what these name. A test asserts none of them ever instructs.

### What local storage costs, said out loud

One cleared cache, one private window or one new machine away from gone. The panel says that in
those words and offers a JSON export, because a journal that quietly evaporates is worse than
no journal: the reader would have believed they had a record.

---

## 13. A full correctness audit, and the five things it found

**28 August 2026.** Every formula in the app was checked against its published
definition by REIMPLEMENTING it independently — plain loops and closed forms, written
from the source rather than from the code — and comparing. Where a formula estimates
something, it was pointed at a planted quantity and asked to recover a number it was
never given. What follows is what that turned up.

### Verified correct, to the precision stated

| Checked against | Result |
|---|---|
| DCF present value, terminal value, Gordon growth | exact (0.00e+00) |
| Residual income, hand-summed; and the ROE = r identity | exact |
| Implied growth inverting the forward model | 1e-9 |
| Vasicek shrinkage vs the published precision weighting | exact |
| OLS beta, standard error, R² vs `scipy.linregress` | exact |
| Yang-Zhang volatility on a simulated intraday diffusion | 0.97x true, **3x** more variance-efficient than close-to-close |
| Corwin-Schultz and Abdi-Ranaldo against a planted spread | recovered across 0-5% |
| Amihud scaling in volume | exactly halves on doubled volume |
| Benjamini-Hochberg vs a hand-built step-up | exact, monotone, dominates Bonferroni |
| CUSUM finding a planted mean shift | right direction, right count |
| Euler risk decomposition, shares summing to one | 1e-16 |
| Participation ratio vs the equicorrelation closed form | exact |
| Floor-trader and Fibonacci pivots | exact |
| Position sizing: share x stop distance = the risk budget | exact 1.0000% |
| RSI, ADX, +DI/-DI, CCI, Aroon, Stochastic, Williams %R, MACD, EMA, ROC, true range | exact vs independent implementations |
| Piotroski's nine signals vs the 2000 paper | all nine match |
| Event study: market model on a planted alpha/beta; the estimation gap | recovered; poisoning the gap leaves the fit **identical** |
| Backtest look-ahead: a signal planted only after the rebalance | correlation with rank **+0.004** — it cannot see it |

### 1. Downside deviation was not the published quantity

`risk_metrics` computed `returns[returns < 0].std()` — the dispersion of losses about
their own mean. Sortino & Price (1994) define the root-mean-square shortfall below the
target, over **every** observation. These are different statistics, and the error does
not even have a consistent sign:

| Return shape | old / published |
|---|---|
| ordinary noisy returns | 0.85x — Sortino overstated by ~18% |
| small losses, rare crashes | 1.44x — Sortino understated |
| every down day the same size | **0.00x** |

That last row is the one that matters. Losses of identical size have zero dispersion
among themselves, so the old formula returned zero and **Sortino came back as 4.7e14** —
which the panel would have rendered as a superb risk-adjusted return for a holding that
loses money every third day. The published formula gives 0.0917 and a Sortino of 7.4.

Sortino is not a minor figure here: it is one of the six numbers Guided mode shows
without a click, and the long-horizon checklist's "Paid for its downside risk" line
tests it against 0.5.

### 2. Five metrics carried an arrow that contradicted their own colour

`explain.py` exists to make direction impossible to get wrong, and its docstring says
`goodDirection` is "carried for the UI to draw an arrow... Keeping it advisory means a
mismatch between the two shows up as a failing test". No test compared the two.

Maximum drawdown, current drawdown, VaR, CVaR and worst single day all reach the panel
as **negative** percentages and improve toward zero — so the honest arrow reads "higher
is better". All five declared `low`, rendering a down arrow labelled *lower is better*
underneath "-33%", which tells a reader that -60% is the better outcome. The colour
ladders were right throughout.

The old test could not catch it because it asserted the label against a hand-kept list
rather than against the ladder. The replacement derives the expected direction from
which end of each metric's own range the tone improves toward, so a new metric is
covered the day it is added — and it fails if any of the five is flipped back.

### 3. Two oscillators had three saturated cases and handled two

RSI divides by an average loss that can be zero, and sent every such window to 100.
That is right when there were gains and wrong when there were none: **a price that had
not moved for fourteen days came back as 100**, the most overbought reading on the
scale. Reachable on exactly the halted and thinly traded listings this app covers.

Money Flow Index had the mirror bug from a blanket `fillna(50)`: **fourteen consecutive
up days produced no negative flow and read as 50**, the exact middle, when they mean the
top. The same fill also disguised the warm-up window as a neutral reading.

Both now distinguish all three cases: saturated up, saturated down, and nothing
happened.

### 4. There were two Money Flow Index implementations

`whale.py` carried its own copy, differing from `indicators.py` by up to **50 points** —
half the scale — because the two chose different `min_periods`. The divergence was
confined to the warm-up window, which the anomaly engine drops, so no panel ever
disagreed with another; but two copies of one formula is how a disagreement that matters
eventually arrives. The anomaly engine now calls the shared one.

### 5. A window that reported before it was full, under a name that implied otherwise

`volume_trend` divided by a long average with `min_periods = long // 4`, so on a short
chart range it compared against a 63-day mean while the explanation layer called the
result "volume versus its year". Both windows are now required in full: the reading goes
missing on a three-month range rather than being computed over a quarter and labelled as
a year, which is the treatment the 200-day average already gets.

Donchian's channels keep their quarter-window minimum, and the reason is now written
down: nothing labels that output with its length. The user-facing "52-week high" is
`longterm.price_position`, which measures its own window and reports `windowDays` beside
the figure, and the breakout setups in `swing.py` use their 20- and 55-bar windows in
full.

### Deviations from a cited source that were left alone, deliberately

**Bollinger bands default to the sample standard deviation** (`ddof=1`) where Bollinger
uses the population one. Bands are 2.6% wider and %B moves by at most 0.02. The squeeze
percentile is unaffected, being a rank against the metric's own history. Documented
rather than changed, because the parameter is exposed and the difference is smaller than
the choice of 20 periods.

**Piotroski's ROA uses same-year assets** rather than the paper's beginning-of-year
figure — the common simplification, and it preserves the sign of every signal.

**Sharpe divides a geometric annual return** by an annualised standard deviation of
daily returns, where the textbook uses the arithmetic mean excess return. A widely used
variant; the panel states which risk-free rate was used so the number can be compared
with one from elsewhere.

**Wilder's smoothing seeds on the first observation**, not the published SMA of the first
`n`. The difference decays geometrically and measured below 1e-9 by the tail of a
500-bar series.

### Data boundary

`scripts/check_data_invariants.py` over 40 live companies: price x shares against market
capitalisation has a median ratio of exactly 1.000, and one name tripped the dividend
invariant — the pre-existing IDX coverage gap the script exists to surface. The
statement currency conversion was re-checked and is sound: the effective tax rate is a
ratio of two rows that are both scaled, so the exchange rate cancels, and every row the
app reads is monetary rather than a ratio.

---

## 14. The detector and the rendering paths — the two the audit had not swept

**28 August 2026.** §13 covered the calculation layer and said plainly that the anomaly
engine's internals and the React rendering paths had not been examined to the same depth.
This is that pass.

### The Isolation Forest is sound, and walk-forward is genuinely leakage-free

| Checked | Result |
|---|---|
| NaN reaching the model after the MFI warm-up change | **none** — `dropna` removes 13 of 500 rows first |
| Strength score bounds and weights | `[0, 100]`, weights sum to 1, logistic maps score 0 to exactly 0.5 |
| Flagged days score higher than unflagged | 60.1 against 18.4 |
| MAD mode's 1.4826 constant | recovers sigma = 1.0046 from a standard normal |
| Modes behaving as documented | threshold and MAD float with the regime; quota pins at 2% |
| **Walk-forward leakage** | a colossal shock at day 450 changes pre-shock scores by **0.000e+00** |

That last row is the one worth having. Walk-forward refits on `[0, t)` and scores day `t`
out of sample, and a planted future shock cannot reach a single earlier score.

### The default mode can see the future, and the event study inherits it

The default is `threshold`, which fits the scaler and the forest on the **whole loaded
window**. That is documented in the module header as caveat A and is defensible for the
question the Flow tab asks — *which days in this window were unusual?* is a descriptive
question about a fixed window.

It is less defensible one layer up. Planting the same late shock moved pre-shock scores by
up to 0.064 and **flipped the flag on seven days that preceded it**. `/api/event-study`
runs on that default, so the days it treats as events are chosen with information from
after each event. The route's docstring justified skipping walk-forward on the grounds
that "the market-model estimation already excludes look-ahead" — which is true, and which
answers a different question. The estimation window is clean; the **event selection** is
not.

Measured on four simulated histories, the whole-window detector picks about **93%** of the
events a point-in-time detector would, and slightly fewer of them. So the contamination is
real and modest.

Stated rather than fixed: walk-forward refits per step and costs minutes per ticker, which
does not fit the function limit this route runs under, and the Flow tab already offers that
mode to anyone who wants the stricter selection. The panel now carries a second caveat
naming the mechanism and the 93%, beside the one about the market model.

### The rendering paths: colour decided twice, and the second one was cruder

`explain.py` exists so direction is decided once, in Python, with a test. `LongTermPanel`'s
own docstring records replacing `tone={value >= 0 ? "text-acc" : "text-dist"}` for exactly
that reason. The fix reached that panel's stat cards and stopped there.

Four places still coloured by the sign of the raw number, and each disagreed with the
served tone **in the middle of its range**, where the ladder has a deliberate neutral band:

| Site | The disagreement |
|---|---|
| `ValuationPanel` gap to fair value | a **5% gap rendered bright green** where `_upside` calls it neutral — inside the noise of a model whose P25-P75 can span 60% |
| `RankingPanel` shortlist upside | the same, on the deepen table |
| `LongTermPanel` worst rolling outcome | **+0.4% a year rendered green**, where `_rolling_worst` grades break-even as neutral |
| `LongTermPanel` excess versus the index | -2% rendered red where the ladder says amber |

All four now read `explain.tone`.

**The event study was the worst of them**, and separately. It coloured the mean CAR by its
sign regardless of significance — so a +0.73% mean with a p-value of 0.34 rendered green,
on the one panel in the app whose entire purpose is to report that there is no effect. A
reader takes the colour, because colour is read first. An insignificant CAR is now neutral
whatever its sign, and only a result clearing the conventional cutoff takes a direction.

Six sign-based colourings were left alone and are listed in the components: a day's price
change, the change since a crossover, an anomaly day's move, and the seasonality grid that
is already labelled *descriptive only*. None of those is a judged metric with a ladder;
green-for-up is the whole meaning.

### Two copies of one rule, now compared by the build

`ConfluenceRail` keeps its own map of which lens reads which body of data, because it must
render while legs are still loading and cannot wait for the server. `explain.py` says so in
a comment. The app's central claim — that four lenses are two independent sources — rests
on the two agreeing, and nothing checked that they did. They do; `check_frontend.mjs` now
reads both files and fails if they ever stop, which was verified by breaking it.

### Smaller things

`ConfluenceRail` formatted the last close with `.toFixed(2)` on a value typed non-null.
`jsonsafe` turns any NaN into a null on the wire, and `.toFixed` on a null throws — which
would take down the panel that sits above every other one. It uses the shared formatters
now, which render an em dash for missing data and are asserted to.

Swept and clean: every mapped element carries a key; no unguarded index access; no division
in a component that can print anything but an em dash. Rendered every tab and every
technical sub-section for an IDX non-financial and for a bank — the two shapes that
exercise the currency conversion and the applicability refusal — and scanned the full text
for leaked `NaN`, `Infinity` and `[object Object]`. **None, on any tab.** Console clean on a
fresh load.

---

## 15. The claim the app makes loudest, finally measured

This app's central assertion is not that any lens is right. It is that four
lenses rest on **two independent bodies of data**, and therefore that when those
two agree, "agreement between them is not one fact counted twice". The
confluence rail prints a count built on that assertion on every single run, and
`explain._agreement` states it in prose: *"the price record and the filings share
no inputs."*

Nothing measured it. Both surfaces said so — the rail in smaller type
underneath, the field manual in its own section — and both gave the same reason:
*"the ranking panel measures its own overlap because a scan gives it a
cross-section to measure from, and a single ticker does not."*

That reason is true of a request and false of a script. §11 established the rule
this project runs on — a measurement that informs a decision has to be taken
before the decision is built — and this was the one place the rule had been
applied to everything except the app's own headline.

### Why chance-corrected agreement, and not agreement

Raw agreement between two lenses is uninterpretable, for exactly the reason a
raw screener hit count is. If the Value lens calls a company cheap on 70% of
names and the Quality lens calls one sound on 70%, the two land on the same
label **58% of the time while sharing nothing at all** — and 58% reported on its
own reads as substantial corroboration.

So the statistic is Cohen's kappa: observed agreement minus the agreement each
lens's *own marginal habits* already supply, over the room that leaves. It is 0
when two lenses agree exactly as often as chance predicts, 1 when they never
disagree, and negative when they agree less than chance. This is the third place
in the codebase the same correction appears — `eventstudy.screener_significance`
applies it to scan hits, `pretrade` to check flags — and it is the same argument
each time.

Kendall's tau-b rides alongside because kappa and tau-b answer different
questions. Kappa asks whether two lenses reach the same *label*; tau-b asks
whether, when they differ, they differ in a consistent *direction*, treating the
vote as the ordered scale it is. Two lenses that rarely produce an identical
word but never point opposite ways have a low kappa and a high tau-b, and that
combination means something neither number shows alone.

Intervals are bootstrapped over **names**, not derived from Cohen's closed-form
variance. That form conditions on the observed marginals, and here the marginals
are themselves estimates — how often the Value lens calls a company cheap is a
property of the sample, not a fixed design — so the closed form understates the
uncertainty. Same preference for resampling over an assumed standard error that
sized the Hurst band and found the spread estimator's resolution floor.

### What it ran on, and what that cost

`scripts/measure_lens_agreement.py` pushes all 168 deduplicated names of the four
index universes through the **production payload builders** — the same
`whale_payload`, `technical_payload`, `valuation_payload` and `quality_payload`
that `/api/confluence` calls, with the parameters the ticker bar actually sends.
The votes come out of `explain.for_synthesis` and the family votes out of
`explain._family_votes`, not out of a copy of either.

That fidelity is the whole point and it is why this could not reuse
`calibrate_checks.py`'s batched shortcut. A pre-trade check is three estimator
calls deep, so measuring it from a batch download costs nothing. A lens *vote* is
the end of a chain — fetch, engineer features, fit an Isolation Forest, classify
the flow bias — and reassembling that chain outside the payload builders would
have measured a lookalike of the app. Nothing batches, the run is fourteen
minutes, and that is the correct trade.

**A lens that could not read does not vote.** `None`, never 0. A bank's refused
accounting screens recorded as a neutral vote would manufacture agreement with
every other lens that happened to be quiet, which is the "absence is not
evidence" error §7 built a whole `notChecked` list to avoid, arriving in a new
place. A test asserts the two readings *differ*, so a later change that mapped
`None` to `0` fails rather than passing on a coincidence.

### The result: the claim survives

| Population | n | They agree | Chance agrees | κ | 95% interval |
|---|---|---|---|---|---|
| All four universes | 167 | 35.3% | 33.1% | **+0.03** | −0.07 to +0.14 |
| US — Dow 30 + Nasdaq-100 | 121 | 36.4% | 32.8% | **+0.05** | −0.08 to +0.17 |
| IDX — IDX30 + LQ45 | 46 | 32.6% | 25.6% | **+0.10** | −0.05 to +0.25 |

**Not distinguishable from zero on any population.** The price record and the
filings reach the same verdict about as often as two unrelated readings with
those habits would, so agreement between them really is two facts rather than
one counted twice. The rail's arithmetic is doing what it claims.

Two independent runs on the same day returned those three headline figures
**identical to three decimals** (+0.033, +0.053, +0.095), which is the
reproducibility a stamped number needs before it is worth stamping.

### The finding nobody was looking for: the redundant pair is not redundant

The grouping collapses Flow and Trend into one price vote *because they read the
same OHLCV series*. That is a fact about the code. Whether their **verdicts**
behave that way is not, and it had never been checked:

| Pair | κ (all) | κ (US) | κ (IDX) | τb (all) |
|---|---|---|---|---|
| **Flow · Trend** — declared redundant | **+0.03** | +0.07 | −0.02 | −0.02 |
| Flow · Value | +0.00 | +0.00 | +0.02 | +0.07 |
| Flow · Quality | **−0.10** | −0.10 | −0.05 | −0.24 |
| Trend · Value | **−0.14** | −0.10 | +0.01 | −0.18 |
| Trend · Quality | −0.05 | −0.10 | +0.05 | +0.00 |
| Value · Quality | +0.01 | +0.01 | −0.14 | −0.03 |

Flow and Trend — the one pair the app treats as a single reading — agree at
κ = +0.03. Their verdicts are all but unrelated. And the participation ratio
says the same thing from the other end: across the 138 names where every lens
read, the four carry **3.72 lenses' worth of independent information** (US 3.74,
IDX 3.59) rather than the two the rail collapses them to.

**The grouping was not loosened, and the reason matters more than the number.**
A kappa near zero is equally consistent with two readings carrying genuinely
separate information and with at least one of them being noise — votes that are
mostly noise are uncorrelated with everything too. The Flow lens's own event
study (§5) returns no significant effect on most tickers it is pointed at. A
lens that is independent *because it is uninformative* has not earned a vote of
its own, and this measurement cannot tell those two cases apart. So the
conservative collapse stands, and the panel now says why it stands rather than
implying the four were known to be two.

### Two negative pairs, one of which explains itself

Two intervals exclude zero, and both are **negative** — the lenses agree *less*
than chance.

**Trend · Value at −0.14** is mechanical rather than interesting. A stock that
has trended up is by construction less likely to sit below a discounted cash
flow's range: the same price is in the numerator of one lens's verdict and the
denominator of the other's. It is the strongest signed relationship in the table
and it is an artefact of what the two measure, not a fact about markets.

**Flow · Quality at −0.10, τb = −0.24** has no such explanation, and it is
recorded here without one. Unusual buying pressure showing up slightly more
often on companies whose accounting screens report concerns is either a real
pattern, a selection effect in which names produce anomalies, or noise at the
edge of what 153 names can resolve. Nothing here settles it.

### The IDX coverage gap, again, in a new place

`calibrate_checks.py` found that Yahoo's fundamentals coverage for smaller
Indonesian listings is the single biggest fragility in this project. It bites
here too, and it is why every figure is reported per market:

| Lens could read | US | IDX |
|---|---|---|
| Flow | 98% | 100% |
| Trend | 99% | 100% |
| Value | **94%** | **80%** |
| Quality | **94%** | **85%** |

Every pairwise n is bounded by that. The IDX filings agreement rests on 30 to 39
names against the US's 109 to 115, which is exactly why the IDX interval is
nearly twice as wide and why a blended figure would have described neither
market.

### What changed in the product

The warrant clause in `explain._agreement` used to assert. It now reports, and
**all three branches ship**: a kappa indistinguishable from zero earns the
claim, a positive one that excludes zero takes it away in the same sentence
("worth less than two independent readings"), and a negative one is reported as
the oddity it is. A module that could only phrase the result it hoped for would
have decided the answer before the run, and `test_synthesis.py` exercises each
branch against a planted measurement.

Underneath it, the working: the arithmetic, the interval, the declared-redundant
pair by name, the effective lens count against the collapse, and the two things
the measurement explicitly cannot settle. It is **never coloured** — same rule
§8 applies to provenance. A kappa is not good news or bad news about a company;
it would be the same number on a wonderful business and a failing one, and
tinting it green would turn "the cross-check is sound" into "the stock is fine".

The confluence rail's caveat lost the clause that is no longer true. Which lens
reads which data is still a stated assumption and always will be; how far the
two actually reach the same verdict is not.

### DO NOT: a voting fifth lens is one easy commit from here

> **The day came. See §18** — a fifth lens shipped on 1 September 2026, this section's
> sequence was followed in the order it sets out, and the re-run took the independence
> claim away rather than confirming it. Everything below is left exactly as written,
> because it was right and because the next person needs the warning as much as this
> one did. The numbers in §15 above are the FOUR-lens measurement and are superseded
> by §18's.

**The affordance that makes this measurement easy to invalidate is already in the
code, and it looks like an invitation.** `ConfluenceRail.tsx` declares

    type Family = "price" | "filings";

with a docstring explaining that the field is part of the type "so adding a fifth
lens forces you to say what it reads", and `agreementOf` already branches
`total === 2 ? "Both" : "All"` against the day there are three. Both were written
as good hygiene. Together they mean a fifth lens that carries a `vote` and a new
`Family` would compile, render a plausible headline, and silently make every
number in this section wrong — the kappa above is measured between the two
families that exist today, and `explain._family_votes` would be feeding a third.

So, explicitly: **a new panel may not vote.** A reading that has no bullish or
bearish direction — an exposure beta is the live example, since a negative beta
is not a bad beta — must return no `vote` at all, and then it never reaches
`agreementOf`, never touches `_family_votes`, and this artifact stays valid.

If a genuinely directional fifth lens is ever wanted, the sequence is not
negotiable: re-run `measure_lens_agreement.py` with the third family included,
publish the three pairwise kappas, and only then change the rail's headline. The
"two independent bodies of data" sentence is the loudest claim this app makes and
§15 exists because it was shipped for months unmeasured. It must not become
unmeasured again by accident.

### What it does not claim

**Kappa measures redundancy, not causation.** A high kappa would not prove two
families share inputs — two independent tests of a genuinely sound company
should agree — and a low one does not prove they read different data. What it
bounds is precisely the claim the rail makes, which is an *information* claim:
whether the second reading adds anything to the first. Where the overlap came
from is not identified and the panel says so.

**It is a measurement of this app, not of the market.** The unit is a vote
derived from a prose verdict, so what is measured is how often two panels'
headline stances coincide across 168 large caps — not how correlated the
underlying information is. Move a verdict band and this number moves, which is
why the script has to be re-run whenever one does.

**It never becomes a weight.** Nothing downstream reads the kappa except the
sentence that reports it. A measured agreement scaling a verdict would be the
composite score this app refuses to have, arrived at sideways through a
statistic that sounds too technical to be a recommendation. The payload's key
set is asserted for the same reason `test_pretrade.py` asserts on its own.

> Cohen (1960), *Educational and Psychological Measurement* 20(1).
> Kendall (1945), *Biometrika* 33(3). Efron & Tibshirani (1993), *An
> Introduction to the Bootstrap*. Measured 29 August 2026 by
> `scripts/measure_lens_agreement.py`; stamped in `api/_lib/lens_agreement.json`.

---

## 16. What a book has in common, and three things that did not work

The portfolio panel could report that four holdings correlate at 0.82 and amount
to about 1.6 independent positions. It could not say **why**, and "because they
are one bet on energy" is the sentence that tells a holder whether the
concentration is an accident or the whole thesis.

`_lib/exposure.py` answers that, and most of what it records is what failed.

### The market is removed first, and that is the design

The first principal component of any set of stocks in one market is largely that
market. Reporting it would fire on every portfolio ever entered — the same
failure §8 avoids by refusing to colour a condition that holds for everybody. So
the shared direction is split: the part that is the local index, reported
plainly, and the part that is not, which is the only part offered for naming.

Measured on real books, that second number is where the finding lives. A mixed
defensive Indonesian portfolio is 58% index. An Indonesian coal book is 19%, and
a US energy book is 5% — almost nothing of what moves those together is the
market they are listed in.

### Weekly, and the difference decided whether it shipped

Every reference settles in a different time zone from an IDX close. On a
concentrated coal book against crude the correlation is **0.17 daily and 0.52
weekly**. Daily would have shipped a panel that cannot find energy in a book of
energy companies.

### Three nulls, recorded so they are not rebuilt

**Foreign peer baskets.** Australian coal and Malaysian plantation pure-plays are
non-circular by construction — no holding can be inside them — and they carry
nine years of clean history where the Newcastle coal future stopped printing in
December 2025. Against four Indonesian coal miners they reached 0.19-0.27, and
on that book **palm oil scored higher than coal**. A labeller that cannot tell
palm from coal on four coal miners is not a labeller.

**Domestic leave-one-out baskets**, built from the resource names a holder does
not own, did better at 0.28-0.49 and still never cleared the naming threshold.
Worse, a nickel-and-gold book read **0.49 against coal** — a confident mislabel
rather than a miss.

**USDIDR is the dollar.** Of the 15 IDX names carrying a material raw USDIDR
loading, **12 fall below threshold once the ICE dollar index is projected out**.
The three survivors are BBNI, BBTN and CTRA — two domestically funded banks and
a property developer, which is a coherent set. And the sign settles it: a miner
with dollar revenue and rupiah costs should gain when the rupiah weakens, and
every one measured is negative (ADRO −0.69, INCO −1.85). They fall when the
rupiah falls, along with everything else in a risk-off week. That is global risk
appetite wearing translation exposure's name, and labelling it "the rupiah"
would have named the wrong fact.

What ships is four globally traded contracts — gold, energy, copper, the dollar
— because they cleared where the equity baskets did not. **The cost is stated on
the panel: this names an energy exposure, not a coal one.**

### It does not vote, and it is never coloured

A beta has no bullish or bearish direction; a negative loading on the dollar is
not a bad loading. Nothing here reaches `_family_votes` or `agreementOf`, so the
kappa in §15 stays valid — see the "DO NOT" note there. Every figure is
`context`, rendered neutral, for the reason §8 gives about provenance: a reader
who bought four coal miners on purpose has a concentrated book doing exactly
what they asked of it, and neither a green tint nor an amber one is a judgement
this app can make.

Two refusals are load-bearing. Two references landing within 0.10 name **neither**,
because picking the larger would present a precision the sample does not have.
And a reference that could not be *read* is reported as untested rather than as a
driver found absent — the seam where constraint 3 is easiest to lose, since an
empty result reads as "diversified" unless the words deny it.

### A stale series that passed every check

Found while looking for factor data: `MTF=F`, the Newcastle coal future, returns
834 immaculate bars through `market_data` and last printed **2025-12-26**.
`normalise` only drops a trailing row with no close, and every row in that frame
has one. Nothing raised, logged or marked it.

`ohlcv` and `ohlcv_batch` now refuse a series whose last bar is far older than
the window asked for — **measured against that window, not against today**, so a
backtest that asks for 2021 is not rejected for ending in 2021. Counted in
sessions and converted using the frame's own observed spacing, because the IDX
closes for the best part of a week around Idul Fitri and the US does not.

Four call sites opt out by name, all four because they read the reader's own
ticker: a suspended IDX listing has a last print that is old and still the fact
someone came for. The batch has no opt-out, and that is where it mattered most —
a holding delisted six months ago still clears `portfolio.MIN_OVERLAP` inside a
252-day window, so it was contributing a correlation computed against a price
that had stopped moving.

No stamped artifact needed re-running, verified rather than assumed: across the
Dow 30, IDX30, LQ45 and the curated resources list — 120 names — the rule drops
nothing.

### One list that is not an index

`universes.idxresources` breaks this repo's own rule that a constituent list must
be small, stable and **widely published**, and says so in its own note. It exists
because not one of the four Indonesian palm-oil names is in the IDX30 or the
LQ45, so a plantation basket could not be built from them at all.

It is a separate list rather than additions to the index lists because writing
AALI into the LQ45 would make that list say something false, undetectably from
the output — the argument `universes.py` already makes for refusing to ship an
S&P 500 list from memory. Keeping the index lists untouched also means all four
stamped artifacts still describe the populations they were measured on, so none
needed re-running and **κ cannot have moved off +0.03**.

UNTR is deliberately absent, with a test pinning the absence. United Tractors
files as Industrials, sells mining equipment, and reads R² 0.28 against the coal
names with the Jakarta Composite removed — higher than HRUM, an actual coal
miner, reads against its own peers. It is the best evidence in this repo that
measuring exposure beats assuming it, and a hand-specified sector map would never
have tested it. That result holds only while UNTR is outside the basket.

> Measured 31 August 2026 on 98 equities and 9 reference series, weekly W-FRI log
> returns, 2017-09 to 2026-08.

### The gate, and what it refused

`measure_exposure_stability.py` is the study the single-name reading was held
behind: do this year's betas describe next year's? Nine years, 475 weeks, nine
52-week blocks, **eight transitions** across 157 names — comparable to the six
the correlation study got, so the two can be read against each other.

**Measuring across every name mostly measures whether noise persists.** It asks
whether AAPL's gold beta this year predicts AAPL's gold beta next year, and AAPL
has no gold exposure, so both are estimation error and the honest answer is no.
§11's correlation study never had this problem because every *pair* of stocks has
a real correlation; not every stock has a real factor loading. So the arm that
would decide anything conditions on a material loading **in the first block of
each transition**, tested into the second — no information from the future, and
the situation a panel is actually in.

*Every figure below is from the run stamped 1 September 2026. An earlier run,
described next, produced different numbers and is superseded.* Across all names
the four factors read **+0.07 gold, +0.20 energy, +0.13 copper, +0.08 dollar**;
conditioned on a loading, none of them is measurable at all.

**What the first run got wrong, and it is the interesting part.**
It screened names with a fixed R-squared of 0.05 shared with the
panel, and measured RAW betas. Both were wrong in the same way: an R-squared is
a different evidential bar at every sample size — 0.05 is |t| = 5.0 over 469
weekly observations and |t| = 1.6 over 52 — and the panel does not report raw
betas, it removes the local market from both sides first.

Re-run on what the panel actually shows, **persistence cannot be measured at
all**: with the market removed and a real significance screen, fewer than ten
names per 52-week block carry a loading, which is too few to rank-correlate one
year against the next. Nine years also holds fewer than two independent
five-year windows, which is the window the panel now uses.

So the stamped headline is a null: *exposure beta persistence could not be
measured, so nothing in this app may print a forward-looking factor beta.* The
panel prints none. What it shows is five years of history, labelled as history,
which needs no gate for the same reason the portfolio driver label needed none.

The measurement that gated nothing still earned its place: it is why the feature
does not claim a forecast.

### The up/down gap does not persist, which is the clearest null here

§16 above printed two betas and declined to interpret the divergence, pending
this. Sign agreement between halves runs **49% to 76%**, and between the
factor's rising and falling years **46% to 66%** — a coin flip on gold.

The regime split was the point. A sample straddling one large one-directional
move produces unstable asymmetry for mechanical reasons, and a half-split alone
cannot tell that from the asymmetry not being real. Split by the factor's own up
years and down years, it is not real. Two betas may be printed; the gap between
them may not be interpreted.

### Weekly confirmed at scale, having been chosen on five pairs

Median absolute beta runs **1.2x to 3.5x** the daily estimate across every
factor — the non-synchronous attenuation the design predicted — and daily and
weekly disagree in *sign* on 1-10% of names. Gold is the worst of both at 3.5x
and 10%, which is a second reason not to print it.

### No stress story

Explanatory power in the worst blocks moves by -0.02 to +0.03 against the rest,
with no consistent direction. Whole blocks, never selected weeks — the third
place in this repo the Forbes & Rigobon selection has had to be caught.

### What shipped on the back of it

The Trend tab now reports what a name moves with, for the three factors that
cleared. **The gate is read from the artifact on every call, not hardcoded**:
gold failed a measurement rather than a rule, so re-running the study on more
history would start printing it without anyone editing a list, and a factor that
stopped clearing would stop appearing the same way.

**Newmont is the case that shows what the gate buys.** A gold miner, and the app
declines to print its gold beta — while reporting copper at 1.09x and the dollar
at -3.33x, which survive. The refusal is named on screen rather than dropped,
because a section that quietly omitted gold would read as a gold miner having no
gold exposure.

The reading carries its own persistence figure in the same sentence, which is
unusual and deliberate: the number that licensed the metric is also the number
that shrinks it. What is **not** printed is an upside and a downside beta —
printing two numbers a reader will inevitably compare, beside a note asking them
not to, is worse than printing neither.

> Measured 31 August 2026 by `scripts/measure_exposure_stability.py`; stamped in
> `api/_lib/exposure_stability.json`. Fifteen names excluded for short history
> and listed by name in the artifact rather than averaged in.

---

## 17. Every calculation, checked against something outside this repo

A full correctness pass, 1 September 2026. The rule was that no estimator is
verified against a second copy of its own arithmetic — each was checked against
scipy, a textbook formula written in the harness, or a planted case whose answer
is known by construction.

**Exact to 1e-9 or better.** `ols_beta` and its standard error against
`scipy.stats.linregress`; Vasicek and Blume against their closed forms; the
participation ratio against identity, rigid and two-block matrices; Cohen's kappa
against the marginal definition and Kendall tau-b against `scipy.stats.kendalltau`;
risk contributions against w(Sw)/wSw summing to one; the market-removed exposure
beta against scipy on residualised series; RSI, ATR, MACD, MFI, CCI, Williams %R
and Bollinger against Wilder and Lane; the DCF stream, terminal value and DDM
against discounting by hand, with `implied_growth` shown to invert
`dcf_implied_price`; CAGR, drawdown, downside deviation, Sharpe, Sortino, Calmar,
VaR, CVaR, skew and kurtosis against textbook formulas; Amihud including the 1e6
convention and Yang-Zhang against its published `k`; the binomial p-value against
`scipy.stats.binomtest` and Benjamini-Hochberg against the step-up procedure;
Altman Z'' end to end with its bands; Beneish end to end, where an unchanged
company scores exactly the sum of the coefficients.

**Piotroski** was planted twice: a company built to pass all nine scores 9, one
built to fail all nine scores 0, and a company missing seven inputs scores only
what it could measure — no free points for absent data.

**The detector.** Two controls settle §14's leakage claim. Every engineered
feature is backward-looking: detonating the last forty days changes no earlier
feature value. And walk-forward scoring is deterministic — the same frame twice
gives identical scores — so the earlier days keep their scores exactly when the
future changes. The three whole-window modes do move, which is the lookahead §14
already documents.

**Live end to end.** Every indicator and risk figure in a real AAPL payload
reproduces from a fresh fetch of the same window.

### Three things that look like bugs and are not

Recorded so the next audit does not re-open them.

- The **stochastic returns slow %K** — fast %K smoothed by three — which is why
  it disagrees with Williams %R computed on the same window. Both are right.
- **Downside deviation is already annualised**, so a Sortino reference must not
  multiply by sqrt(252) a second time.
- **`check_data_invariants.py` nulls `ttm_dividend` deliberately** to stress the
  fallback path, so its "resolved vs paid" gap measures the degraded route rather
  than the shipped one. The app resolves ADRO and AKRA correctly from actual
  payments. What the gap does say is worth keeping: where Yahoo has no dividend
  history, the fallback can be 3.5x out, and the DDM inherits that.

> Verification harnesses are throwaway and deliberately not committed — a test
> that reimplements the thing it checks belongs in the suite, and one that
> imports scipy to check scipy proves nothing on the next run.

---

## 18. A fifth lens, and the claim it cost

**Added 1 September 2026.** The four lenses all read one of two records. Flow and Trend
read price and volume; Value and Quality read the filings. Between them they answer what
the market did, what the company reported, what the filings are worth, and whether they
can be believed.

None of them reads what is already **expected**. That gap is not academic — it is the
difference between two companies the other four lenses cannot tell apart:

    Cheap on a DCF, sound on the accounting screens, consensus rising.
    Cheap on a DCF, sound on the accounting screens, consensus cut for a year.

The four print the same four verdicts for both, because a discounted cash flow reads last
year's statements and a Piotroski score reads the year before that. The second is the
shape of a value trap, and the record that separates them is one no existing lens fetched.

`_lib/expectations.py` is the fifth lens. It reads the analyst estimate record — a third
body of data, with its own failure modes: it is an opinion rather than a measurement, it
is revised, and the revisions are dated.

### The sequence §15 said was not negotiable, followed in order

§15 ends with a section headed **"DO NOT: a voting fifth lens is one easy commit from
here"**, and it was right. `ConfluenceRail.tsx` declared `type Family = "price" |
"filings"` with a docstring inviting the extension, and `agreementOf` already branched
`total === 2 ? "Both" : "All"` against the day there was a third. A fifth lens carrying a
vote and a new `Family` would have compiled, rendered a plausible headline, and silently
invalidated every number in §15.

That section also wrote down the only acceptable order: *re-run
`measure_lens_agreement.py` with the third family included, publish the three pairwise
kappas, and only then change the rail's headline.* That is the order this section
happened in. The measurement is dated the day the lens shipped, not after.

### What votes, and the four things that deliberately do not

One vote, from one quantity: **revision breadth**, the share of covering analysts who
raised their number against those who cut it. Everything else is supporting detail with
no direction attached.

| | votes | why not |
|---|---|---|
| revision breadth | **yes** | the direction of the consensus |
| revision drift | no | shares its direction with breadth — the same fact counted twice |
| surprise record | no | see below |
| target dispersion | no | disagreement is not bullish or bearish |
| analyst coverage | no | a widely covered company is not a better company |

**The surprise record does not vote, and the reason is not caution.** A beat is a fact
about the relationship between two numbers and its sign is not the company's. A firm that
has beaten four quarters running while its consensus was cut all year is a deteriorating
business that manages expectations well, and the beats are the *mechanism* of that rather
than evidence against it. Voting on the surprise would let that company outvote its own
estimate record.

### Breadth votes because magnitude cannot survive a fiscal-year roll

This is the hazard that decided which quantity carries the vote, and it is the reason the
obvious choice is the wrong one.

`eps_trend` is a **level** — the consensus now and as it stood 7, 30, 60 and 90 days ago.
The period is labelled relatively (`0y` is "the current fiscal year"), so at some point
every year the label rolls onto a different year and the level jumps for a reason that has
nothing to do with a revision. Nothing in the payload marks it and this module cannot
detect it: a 12% jump is what both a roll and a genuine re-rating look like.

`eps_revisions` is a **count**. A count carries no level, so it cannot be corrupted by a
relabelling — and it is the quantity the literature actually uses.

So the count votes, the level is reported as magnitude with the hazard on the panel, and a
sign change between two levels is reported as a sign change rather than a percentage. A
consensus moving from a profit to a loss is not a 140% revision; it is a different
forecast, and dividing by a number that crossed zero says nothing.

### The forward test, and the null it returned

The lens votes, so §2 applies: measured offline and published including nulls, or it does
not ship. `scripts/measure_revision_momentum.py` is that measurement, and
`revision_momentum.json` is the result.

**The problem is that the voting quantity has no history.** Yahoo serves `eps_revisions`
as a snapshot. There is no archive of it anywhere in the source, so the quantity that
actually votes cannot be back-tested at all. What does have history is the estimate level:
`eps_trend` carries four dated columns, which is a 90-day window available on every name
today without any stored panel.

So the study is two halves, and the second is what makes the first admissible:

1. **The forward test.** Signal = how far the consensus level moved between 90 and 60 days
   ago. Outcome = the market-adjusted return over the 60 days since. The signal is
   complete before the outcome window opens.
2. **The bridge.** Whether that level drift actually moves with the revision count. A
   forward result on a proxy that does not track the vote is worth nothing.

| Population | forward ρ | 95% interval | bridge ρ | 95% interval |
|---|---|---|---|---|
| All 164 names | **−0.01** | [−0.15, +0.14] | **+0.53** | [+0.39, +0.64] |
| US (119) | **0.00** | [−0.18, +0.18] | +0.50 | [+0.33, +0.64] |
| IDX (45) | +0.02 | [−0.27, +0.33] | +0.44 | [+0.14, +0.68] |

**The forward test is a clean null.** Over this one window the direction of estimate
revisions had no detectable relationship with what the price did next, in either market.
The bridge, meanwhile, is strong and excludes zero everywhere — so the null is a null
about the signal that votes, not an artefact of measuring the wrong thing. That is the
whole reason the bridge was measured.

The evidence grade the panel prints is therefore **weak**, and `_grade` is written so that
a broken bridge would cap it at weak however clean the forward number looked.

**The limit is severe and is on the panel, not in a footnote.** It is one window. Every
name shares the same sixty days, so the returns are correlated through whatever the market
did over them and 164 names is worth far fewer than 164 independent observations. Two
partial defences: returns are cross-sectionally demeaned *within market* before anything is
computed, and the statistic is a rank correlation rather than a slope. Neither is complete,
and the payload says so in the `limit` field so a redesign cannot drop it.

### The finding nobody was looking for: the redundancy is with PRICE, not the filings

The module docstring predicted where this would go wrong, and it predicted wrong.
`expectations.py` says so in as many words: *analysts read the filings, so if any pair of
families turns out to be redundant, this is the pair.*

It is not. Measured across 165 names:

| Family pair | κ | 95% interval | |
|---|---|---|---|
| price and volume · the filings | −0.02 | [−0.11, +0.09] | straddles zero |
| the filings · the estimate record | −0.06 | [−0.16, +0.05] | straddles zero |
| **price and volume · the estimate record** | **+0.11** | **[+0.02, +0.19]** | **excludes zero** |

The predicted redundancy — estimates against filings — is the *cleanest* pair in the
table. The one that fails is estimates against **price**, and it fails in both markets
independently (US +0.12 [+0.03, +0.21]; IDX +0.06, straddling zero on 44 names). The
lens-level detail names the culprit: **Trend · Expectations at κ = +0.11, τb = +0.30**, the
strongest positive ordinal relationship anywhere in the ten-pair table.

That is not mysterious in hindsight — a consensus being marked up and a price that has been
rising are both downstream of the same news, and the direction of causation is not
identified here. But it was not the pair anyone was watching.

**`Value · Expectations at κ = −0.18, τb = −0.24`** is the second-largest signed
relationship, and it is mechanical in exactly the way Trend · Value was in §15: a stock
whose consensus is rising has usually risen, which makes it less likely to sit below a
discounted cash flow's range. An artefact of what the two measure, recorded rather than
explained away.

### What it cost: the app's loudest claim is now qualified

`explain._warrant` has always had a branch that takes the independence claim away, and
this is the run that fires it. The governing pair — the *most redundant* of the three, not
an average — is price against estimates, its interval excludes zero, and the rail now says
so:

> ...with one measured qualification: across 165 names in [the four universes], price and
> volume and the estimate record agree rather more often than chance alone would produce
> (κ = +0.11 — the closest-matching of the 3 pairs), so that second reading is partly
> predictable from the first and the two together are worth less than two independent
> readings.

The governing pair is the maximum rather than the mean on purpose. A reader counting three
agreeing sources is over-counting exactly as much as the *worst* pair is redundant, and an
average would let two clean pairs bury one that is not.

The effective lens count is **4.48 of 5** on 137 complete cases (US 4.57 of 5 on 108) — so
five panels really are close to five opinions, which is the one number in this section that
came out better than the four-lens version.

### Coverage, and the first lens that is stronger on IDX than the filings are

`calibrate_checks.py` established that Yahoo's fundamentals coverage for smaller Indonesian
listings is this project's biggest fragility. The estimate record does not share it:

| Lens could read | US | IDX |
|---|---|---|
| Flow | 98% | 100% |
| Trend | 99% | 100% |
| Value | 94% | **80%** |
| Quality | 94% | **85%** |
| **Expectations** | **99%** | **96%** |

This matters more than the headline number suggests, because of *where* it is available.
The Quality lens refuses banks and insurers outright — Piotroski, Altman and Beneish were
none of them built on financial firms — and Indonesian large caps are heavily banks. On
BBRI.JK, where half the filings-side evidence is refused by design, the estimate record
comes back complete: 22 analysts, a full revision trail, four quarters of surprise. The
fifth lens is at its most useful exactly where the fourth declines to answer.

### The tenth pre-trade check, and the market where it is withheld

`consensusBeingCut` is the only condition on the pre-trade panel drawn from the estimate
record, and the only one whose underlying number is about the future rather than the past.
Every other check reads a balance sheet, a drawdown or an accrual pattern.

`calibrate_checks.py` was re-run for it, and the two markets came out differently enough to
be worth recording:

| | evaluable | fires on | |
|---|---|---|---|
| US (Dow + Nasdaq-100) | 118 of 122 | **17.8%** | market rate used |
| IDX (IDX30 + LQ45) | **29** of 46 | 34.5% | **unusable — one name short of the floor** |
| Combined | 147 of 168 | **21.1%** | the fallback the IDX uses |

The US rate is comfortably under `BASE_RATE_MAX`, so it renders as a genuine flag rather
than being demoted to a base condition.

The IDX rate is *not* usable: 29 evaluable names is one short of
`MIN_CALIBRATION_SAMPLE`. **The check is not withheld, though** — `_rate_for` falls back
to the combined rate, so an Indonesian company sees the flag quoted against the four
universes together: *"Fires on 21% of four index universes, measured across 147 companies;
a further 21 could not be tested at all."* That is the designed behaviour and the sentence
names the group it is a percentage of, which is the whole contract `scope` exists to keep.

**This paragraph originally claimed the check was withheld on the IDX.** It was written
from the calibration script's own summary line, which reports per-market usability and
says nothing about the fallback. Running an Indonesian ticker through the assembled panel
is what showed the flag rendering. A doc that contradicts the code is worse than no doc,
and the failure mode is worth recording: the summary of a measurement is not the same
artifact as the behaviour it feeds.

**Two different coverage numbers are both true and should not be conflated.** The lens reads
on 96% of IDX names; the *check* is evaluable on 63% of them. The gap is the QUIET and THIN
verdicts: analysts cover the company but too few of them have moved for a direction to be
read, so the check returns `unchecked` with the count in the reason rather than a quiet
"did not fire". Seventeen of the 46 Indonesian names are in that state. A check that treated
them as not-firing would have reported a firing rate against a denominator that included
every company it could not actually test.

### What it refuses

**The mean price target is fetched and deliberately not published.** It is the only figure
this app could show that is simultaneously a point forecast of a price, unattached to any
stated method, and produced by people with a commercial relationship to the company being
forecast. Rendering "mean target 3,700" beside a price of 3,380 states a 9% expected return
that nothing on the page and nothing in the source supports. The **spread** is published
instead, because disagreement survives the objection that the level does not.

**A listing nobody covers gets `applicable: false`, not a zero** — the same refusal
`quality.py` makes for a bank, and for a sharper reason. This lens has more uncovered
listings ahead of it than any other, and "no cuts" and "nobody watching" occupy the same
blank space on a screen. The empty state is louder than the populated one and says in words
that it is a gap in coverage rather than a clean bill of health.

**A quiet record is not a balanced one.** Analysts covering a name and none of them moving
is `QUIET`, votes zero, and is reported as a settled consensus. An absent revision is not a
neutral revision.

**No band on the target spread.** The first draft carried one at 0.60, and on the four
names it was tried against a 57% spread came out "narrow" and an 88% spread "wide" with
nothing justifying the line between them. The frame is measured instead: the median listing
spans **54%** of its own mean (US 53%, IDX 58%), and `explain._target_dispersion` quotes
this listing against that. Same argument `ranking.py` makes for percentiles over scores.

### A bug the tests found

`_read_expectations` originally handled `QUIET` and `THIN` explicitly and let everything
else fall through to the directional branch. `MIXED` — the most evenly split reading the
lens can produce, five analysts up against four — came out of it as **"Falling", with a
vote of −1**: a fabricated bear case on the one state that means "no direction". Caught by
`test_every_family_neutral_is_its_own_reported_state`, which asserted that a payload with
every family neutral reports itself that way and instead found one family voting. The
function now returns explicitly for every verdict and never falls through.

### What it does not claim

**The family grouping is still a declared assumption.** Nothing measures which data a lens
reads and nothing could. What is measured is the consequence, and this time the consequence
took something away.

**κ measures redundancy, not causation.** A +0.11 between price and estimates does not
establish that analysts follow prices, that prices follow analysts, or that both follow
news. What it bounds is the information claim the rail makes, which is whether the second
reading adds anything to the first.

**The forward null is not evidence that revisions do not predict returns.** It is one
60-day window on 164 large caps. Chan, Jegadeesh & Lakonishok found the effect over
decades and many windows; this study cannot contradict them and does not try to. What it
establishes is narrower and is the only thing the panel says: *this app has not been able
to show it, here.*

**Nothing became a weight.** The evidence grade is read by the explanation that prints it
and by nothing else, and no κ scales any verdict. A measured agreement multiplying a vote
would be the composite score this app refuses to have, arriving through a statistic that
sounds too technical to be a recommendation.

> Chan, Jegadeesh & Lakonishok (1996), *Journal of Finance* 51(5). Bernard & Thomas
> (1989), *Journal of Accounting Research* 27. Womack (1996), *Journal of Finance* 51(1).
> Diether, Malloy & Scherbina (2002), *Journal of Finance* 57(5). Measured 1 September
> 2026 by `scripts/measure_revision_momentum.py` and `scripts/measure_lens_agreement.py`;
> stamped in `api/_lib/revision_momentum.json` and `api/_lib/lens_agreement.json`.
---

## What is still open

| Item | Why it was not done now |
|---|---|
| Placing a company in a book-to-market quintile | §8 declines this rather than inventing a breakpoint. It needs a universe-wide scan of book values, and fundamentals do not batch |
| Multi-factor cost of equity (Fama-French) | Factor returns are freely available for the US; constructing IDX factors is a project in itself |
| Sensitivity grid (growth × discount rate) | Cheap, though not quite as cheap as this row used to claim: `pv_of_growing_stream` is vectorised over DRAWS, with growth, discount rate and terminal growth broadcast row-wise, so a grid means flattening a meshgrid into that axis rather than an outer product it already supports |
| Peer / sector relative multiples | Needs a peer-set source beyond yfinance |
| A real backtest of revision momentum | §18 ships one 60-day window because that is all the source can supply — `eps_revisions` is served as a snapshot with no archive anywhere. A genuine study needs many non-overlapping windows over years, which means storing the revision table daily from here on. That is a data-collection project with a lead time measured in quarters, not an analysis someone can run |
| Post-earnings drift on the surprise record | `earnings_history` carries four dated quarters per name, so unlike the revision signal this one IS back-testable with the existing `eventstudy` machinery. Not done because the surprise deliberately does not vote (§18), so §2 does not compel it — but it is the cheapest measurement still on this list |
| Long-term consensus growth against the reverse DCF | Yahoo's `LTG` row is null on every listing tested, US and Indonesian alike. §18 draws the comparison at one fiscal year and labels it as one year; the five-year figure that would match the DCF's horizon does not exist in this source |
| IDX fundamentals curation | The durable moat, and the largest single effort |
| Single-name exposure betas | §16 ships the portfolio half, which is descriptive. "This stock moves 0.7x as hard as its sector" invites forward use, so it is gated on a stability study — do this period's betas predict next period's — mirroring `measure_correlation_stability.py`. A four-year probe gives year-over-year rank correlations of +0.29 to +0.66, inside the band that licensed the portfolio feature, on three transitions where that study had six. Eight blocks are available; MBMA, NCKL and TAPG cannot supply them and must be excluded by name rather than quietly run on fewer |
| Fundamental exposure — revenue against commodity prices | **Rejected on feasibility, not deferred.** `market_data` fetches annual statements only, five columns, and yfinance's quarterlies for these names return five or six with gaps — ADRO and PTBA are both missing 2025-09-30. Five irregular observations is not a weak estimate, it is not an estimate. Consequence: the reverse DCF's implied growth cannot be restated as an implied commodity path |

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
