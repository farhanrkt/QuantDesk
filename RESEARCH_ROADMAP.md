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

## What is still open

| Item | Why it was not done now |
|---|---|
| Placing a company in a book-to-market quintile | §8 declines this rather than inventing a breakpoint. It needs a universe-wide scan of book values, and fundamentals do not batch |
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
