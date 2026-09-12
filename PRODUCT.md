# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary: the motivated newcomer.** Someone who can read carefully and wants to
understand a company, but has no finance background — the reader `docs/field-manual.html`
is written for, which "assumes no prior finance". Confirmed as the primary audience for
the default view (29 Aug 2026). This matches the app's existing stance: the Guided reading
mode is the default, and the field manual is linked from the top of the README.

They are usually deciding whether to buy or keep a single listed company, at a desk, with
time to read but no way to tell an ordinary number from an alarming one. They arrive
knowing a ticker and little else.

**Secondary: the experienced investor, and the author.** Full mode is a standing promise
to them — "the app as it has always been: nothing moved, nothing renamed, nothing added".
That promise is load-bearing: a mode that simplifies by taking capability away from the
people who came for the capability is a mode they turn off once and never trust again.
Full mode may not be degraded to serve the newcomer.

## Product Purpose

Read one listed company through four models that use **different data** — order flow,
price trend, intrinsic value, accounting quality — and show where they agree, where they
disagree, and what none of them can tell you. Covers US and Indonesian (IDX) listings.

Success is a reader who finishes with a defensible view of what is and is not known about
a company, including the gaps. It is explicitly **not** a reader who has been told what to
do.

## Positioning

Most research tools give one opinion. This gives four that share no inputs, and then
spends real effort establishing how much that agreement is actually worth — publishing the
measurement whichever way it comes out. Five stamped artifacts already do this
(`backtest_results.json`, `check_calibration.json`, `correlation_stability.json`,
`lens_agreement.json`, `exposure_stability.json`, `tape_calibration.json`,
`patterns_calibration.json`, `verdict_backtest.json`), including a backtest that reports
its own ranking has **no detectable edge**, a beta study that refuses one of the four
factors it tested, a tape calibration that reports the signal it calibrates **does not
exist on US markets** — 4.2% of names firing against 5% expected by chance — a
chart-pattern study whose every surviving formation predicted the **opposite** of what the
textbooks claim for it, and a walk-forward on the scanner's own blended score that
publishes its own **40% coverage** rather than implying it measured the whole thing.

*The count said "three" while listing four, from before `lens_agreement.json`
existed. Corrected 31 August 2026 along with the fifth. A sixth landed 8 September
2026 with the market scanner; a seventh and an eighth on 9 September with the chart
patterns and the blend walk-forward.*

A neighbouring product could copy the four lenses. It could not truthfully copy
"we measured whether our own signal works and published the null result".

## Constraints

These are durable product facts. Future work preserves them; none is a style preference.

1. **No composite buy/hold/sell — on the published single-company view.** Not a number,
   letter, traffic light or sortable "conviction" column. Guarded by
   `tests/test_synthesis.py` and `tests/test_pretrade.py`. This is the direction any
   change toward "easier to interpret" will drift, and it is permanently refused *there*.

   *Confirmed boundary for v2 (29 Aug 2026):* per-lens status chips driven by the existing
   `explain.tone` are permitted — four chips side by side, one word each. They are **never
   summed, averaged, counted or ordered by strength**. Nothing may aggregate them.

   *Scoped by the owner, 8 September 2026.* This constraint previously read as absolute,
   and the private market scanner (`api/_lib/verdict.py`, `scripts/scan_market.py`,
   `GET /api/verdict`) produces exactly the composite it refuses: one 0-100 score and one
   action per name. The two are not in conflict, and saying why is the point of this
   paragraph rather than a footnote.

   The refusal was always an answer to a specific question. **"What is and is not known
   about this one company"** must not be compressed to a verdict, because the reader is
   forming their own view and a number takes that from them. The scanner asks a different
   question — **"of 837 Indonesian listings, which forty deserve my attention this
   week"** — which is not answerable without ordering. Refusing to order there is not
   restraint; it is refusing to answer.

   What holds the line, and is enforced rather than intended:

   - **The published surfaces cannot reach it.** `explain.for_synthesis` and
     `pretrade.assess` do not import `verdict`, and `tests/test_verdict.py` asserts the
     import direction by AST. Their own aggregate guards are untouched and still pass.
   - **`/api/confluence` is unchanged.** The single-company view has no score, no
     ordering and no new field.
   - **Every score ships with the null result.** `verdict.provenance()` returns the
     measured finding that this app's price ranking shows no detectable relationship to
     subsequent returns, and it is the first block on the report, above the table. Where
     the artifact is missing it gets *louder*, not quieter.
   - **The scanner is private.** It writes to `reports/`, which is gitignored. It is not
     linked from the app.
   - **The annotated chart is part of the private surface, not the published one.**
     `api/_lib/chartlayers.py` and `components/AnnotatedChart.tsx` draw the scanner's
     readings — defended levels with their touch counts, the detected formations, the
     sessions the tape test counted, the stop and the first ceiling — and they are
     reachable from `GET /api/verdict` and nowhere else. The technical panel's own chart
     is unchanged.

2. **No predictive claim that isn't measured.** If a feature implies something predicts
   returns, it is measured offline and published including nulls, or it does not ship.

   *Worked example, 11 September 2026.* `volumeprofile.py` was built to fix an observed
   gap: a full IDX sweep left 46 of 251 names with no usable floor, and volume-at-price
   is a second, independent way to find one. The measurement asked whether price arriving
   at a high-volume band holds more often than price arriving at an ordinary band the
   same distance away — 250 names, six years, 64,969 touches, paired within calendar
   month. Every distance bucket leaned positive and **not one survived a false-discovery
   correction** (q = 0.19 to 0.30); the nearest bucket, the only one where a level could
   act as a stop, came back negative at a 60-name sample and positive at 250.

   The same test on the US market came out with the **opposite sign** — pooled −1.4
   points against IDX's +2.9, nothing significant on either. Two markets disagreeing
   about the direction of an effect neither can detect is what no effect looks like.

   So the feature shipped as description: it draws, it reports where the year's trade
   sat, and `structure.py` finds its levels exactly as before. The motivating gap is not
   closed, and the module's own docstring says so. **A feature that survives its
   measurement by being scoped down is the normal outcome here, not a failure.**

3. **Absence of a flag is never evidence of quality.** An empty panel is not a clean bill
   of health and must say so in words.

4. **Direction is decided once, in Python.** Components read `explain.tone`; they never
   colour from the sign of a number. Six documented sign-based exceptions survive where
   Python has no interpretation to offer (a day's price change, the seasonality grid).

5. **Existing refusals stay.** `applicable: false` for financials on the accounting
   screens; the candlestick firewall; the `unavailable` band.

   *Scoped by the owner, 9 September 2026, for the multi-bar chart patterns only.*
   `swing.py` declines head-and-shoulders, flags, wedges, cups and double tops on three
   arguments, and two of them were always empirical claims rather than principles: that
   two honest implementations disagree, and that a matcher fires on noise. The private
   scanner answers the first by using Lo, Mamaysky and Wang's own kernel-regression
   definitions — inequalities on five extrema, no thresholds picked by eye — and the
   second by measuring the firing rate and publishing it.

   The third argument, that LMW found no demonstrated net edge, is not answered and is
   not waved away: `patterns.py` scores **nothing** until `calibrate_patterns.py` has
   run, and then only for formations whose forward returns survived a false-discovery
   correction across every pattern and horizon tested.

   **The published single-company view is unchanged.** `swing.UNDETECTABLE_PATTERNS`
   still renders and still names every refused shape. Flags, pennants, wedges and
   cup-and-handle stay refused everywhere, because LMW never defined them either.

   **No price target is ever projected from a formation.** *Added 11 September 2026, when
   the formations were first drawn.* Every chart-pattern convention ends in a measured
   move — the height of the head, projected from the neckline, as an arrow. It is the
   most persuasive mark available and it is refused here for the same reason the textbook
   direction is not scored: the measurement below found that direction carries no
   information. What is drawn beside each formation instead is its **measured** excess
   return with the horizon and the number of months behind it, and the textbook bias
   beside it, labelled as textbook. Where the two disagree — a bullish shape that measured
   negative — the panel says so in the same card.

   **The curve under a formation is refitted at detection time.** Smoothing the whole
   series once and drawing that is one line of code and is a look-ahead: a two-sided
   kernel at a past date is fitted partly from prices that came after it, so the drawn
   shape would be partly made of the returns it is about to be credited with predicting.
   The drawn curve ends on the detection bar.

   What the measurement found is worth recording here because it is a product fact:
   every formation that survived correction predicted **underperformance**, on both
   markets, whichever way the chart books read it. A head-and-shoulders and its bullish
   mirror image measured the same. The scanner therefore scores the presence of a
   formation by its measured sign and never by its textbook one.

6. **One data module, one serverless function, no server state, a generated glossary,
   offline tests against planted ground truth.**

   *Scoped 12 September 2026.* `market_data` may keep FILING-DERIVED data on local disk
   across days, because a 9,997-name sweep cannot finish inside one. This is not server
   state: it is off unless a caller opts in, only `scripts/scan_market.py` does, the
   deployed function never writes it, and every record is regenerable. The price and the
   FX rate are re-derived on every read and must stay that way — caching either would be
   a correctness bug rather than a staleness trade-off. The thesis journal and holdings never
   reach a server; `scripts/check_frontend.mjs` fails the build if `lib/api.ts` so much as
   mentions the journal.

7. **Every figure explains itself — in one sentence, on the page.** Each number carries
   what it measures and whether *this* value is good or bad. The rest — why, what would
   change it, the evidence grade — lives behind the figure's own info icon.

   *Revised 29 August 2026, by the owner.* This constraint previously read "may be
   restructured or progressively disclosed, may not be deleted", and that was wrong in
   practice: it produced a screen carrying **thirteen words of prose per word of data**,
   with the first control on a tab **4,300px down**. Text can now be cut.

   What may still never be cut, because the app's honesty rests on it:

   - any **number**, and any **base rate** a number is quoted against;
   - a **null result** or a refusal (`applicable: false`, the withheld checks, the
     candlestick firewall);
   - the sentence that says an **empty panel is not a clean bill of health**;
   - a **tone** — the judgement of whether a value is good or bad;
   - "not investment advice".

   What should be cut on sight: the app arguing for its own methodology. Why an estimator
   was chosen, what a statistic cannot identify, which paper it came from. That belongs in
   `RESEARCH_ROADMAP.md` and `docs/field-manual.html`, both linked from the page.

## Terminology

- **Lens** — one of the four models (Flow, Trend, Value, Quality).
- **Family** — the body of data a reading rests on: *price and volume*, *the filings*, or
  *the share register*. Flow and Trend are the first; Value and Quality the second. The
  third exists only in the private scanner (`verdict.py`) and holds free float and share
  issuance — facts no published lens reads. The single-company view still speaks of two.
- **Tone** — the server's judgement on a figure: `good` / `bad` / `warn` / `neutral` /
  `none`. The only permitted input to colour.
- **Guided / Full** — the two reading modes. Guided is the default.
- **Horizon** — how long the reader means to hold, stated once and read by several panels.

## Evidence and assets

- Measured artifacts, each stamped with its date, in `api/_lib/*.json`. Nothing draws its
  own version of one: `chartlayers.py` positions readings that `structure`, `patterns` and
  `tape` already took, and `tape._marks` is shared by the significance test and the chart
  so a session cannot be circled on one and uncounted by the other.
- `docs/field-manual.html` — beginner's guide; its glossary is **generated** from
  `api/_lib/explain.py` and CI fails if a metric is added without regenerating.
- Twelve network scripts in `scripts/` deliberately outside CI. Re-run after touching what
  they measure; a stale stamped number is worse than none. Two arrived with the market
  scanner: `refresh_listings.py` fetches the whole-market universe, and
  `calibrate_tape.py` measures the per-market baselines the tape reading is tested
  against — without which it has no null to test and reports no direction at all. A
  third, `calibrate_patterns.py`, decides whether any chart formation is allowed to
  score. A fourth, `backtest_verdict.py`, is the only one that measures the scanner's
  own blended score — partially, and it says by how much. A fifth,
  `calibrate_volume_profile.py`, asked whether a volume shelf holds better than an
  ordinary band and **came back null**, which is why `volumeprofile.py` draws and does
  not gate.

  **Every per-market artifact is merged, never overwritten.** These scripts take
  `--market` as a repeatable flag and used to write only what the current run measured,
  so `backtest_verdict.py --market US` silently deleted the Indonesian study — which it
  did, on 11 September 2026, printing "written to ..." and exiting zero. `_lib/artifacts`
  now merges, keeps each market's own `measuredOn`, and every run prints what it carried
  forward. A measurement is the only thing standing between a feature and constraint 2;
  losing one quietly turns a measured feature back into an unmeasured one.

## Accessibility

Audited and fixed 29 Aug 2026. What the audit found and what happened to it:

| Finding | Now |
|---|---|
| 48 of 74 interactive elements under 24×24 (the info icon was 14px) | 0 on desktop |
| Both tablists and both radiogroups declared an ARIA pattern with no keyboard contract | roving tabindex, arrow keys, Home/End |
| Eight `text-ash` alpha sites compositing to 2.2–3.2:1 | gone with the text ladder |
| Page-level horizontal overflow at 375px | 0, every tab |
| 25 `aria-controls` pointing at ids not in the document | 0 |
| Both tablists announcing as "Lenses" | the inner one is "Time horizon" |

Verified by walking the real tab order: 64 focusables, none unnamed, none without a
visible focus style, no positive `tabindex`. Seven of these rules are now enforced by
`npm run check:frontend` so they cannot come back.

**Not a conformance claim.** Nobody has listened to this with a screen reader — the
keyboard contract is implemented and measured, but how it *sounds* is untested.

## Voice

Precise, unhedged, and willing to report bad news about itself. States when a signal is
weak, when data is missing, when a model does not apply. Never prints a confident number
it cannot defend. Dense docstrings and comments say **why**, and name the bug or the
decision behind a choice.

## Open decisions

- Whether Guided and Full eventually become two genuinely distinct designs rather than one
  design with elements hidden. Not now; v2 keeps one design with Guided as the default.
- IDX fundamentals curation — the largest single effort, and blocked on an architectural
  decision about where curated figures live relative to `market_data.py`. **The market
  scanner has now measured the size of this gap rather than assuming it:** on a full
  sweep, seven of the top forty-five IDX names by price rank had no usable statements at
  all, so both filings lenses went quiet and the whole verdict rested on price history.
  Those rows are marked `crossChecked: false` and their scores are shrunk for it, but a
  shrunk score is a workaround, not a fix.
- ~~Whether the scanner's own composite should be backtested~~ **Partly answered,
  9 September 2026.** `scripts/backtest_verdict.py` runs a monthly walk-forward over the
  four components that can be reconstructed without reading the future — about 40% of the
  intended evidence — and publishes that coverage rather than implying it measured the
  whole score. The other five cannot be reconstructed at all: this data source has no
  point-in-time filings, so a historical value or quality reading would use numbers
  published years later. That half is now measured **prospectively** instead, by
  `_lib/scanlog.py`, which records what the scanner said on the day it said it and
  refuses to quote a rate under thirty resolved calls. It will say nothing useful for
  months, which is the nature of the instrument rather than a fault in it.
- What a round trip actually costs. The scanner reports one per name and the blend
  backtest reports a breakeven, but the estimator resolves a spread for only about one
  IDX listing in twenty — it clears its own noise floor on the widest names and almost
  nowhere else. So the app can say "this survives if a round trip costs under 2.2%" and
  cannot say what a round trip costs. That gap decides whether the only surviving result
  in the whole private tier is real, and closing it needs a data source with quoted
  spreads rather than an estimator.
- Whether the scanner should ever act on its own concentration measurement. It reports
  that a buy list spans fewer bets than names and stops there — dropping the most
  redundant name would be portfolio construction, which needs to know what is already
  owned and how much the holder has, and the app knows neither.
