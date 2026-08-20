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

## What is still open

| Item | Why it was not done now |
|---|---|
| Measure the lens-vote correlation empirically | Needs a cross-sectional run over many tickers; the caveat is stated qualitatively meanwhile |
| Multi-factor cost of equity (Fama-French) | Factor returns are freely available for the US; constructing IDX factors is a project in itself |
| Sensitivity grid (growth × discount rate) | Cheap — `pv_of_growing_stream` is already vectorised over both axes |
| Peer / sector relative multiples | Needs a peer-set source beyond yfinance |
| IDX fundamentals curation | The durable moat, and the largest single effort |

**Explicitly rejected:** calendar effects (January, Halloween) — precisely where the
multiple-testing critique bites hardest; headline sentiment — Loughran-McDonald is the right
lexicon but Tetlock's results used full article text, and LM does not cover Indonesian.

---

*Every model here is educational and research tooling, not investment advice. Several are
screens with high false-positive rates on populations where the underlying event is rare, and
each panel says so where that applies.*
