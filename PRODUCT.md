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
measurement whichever way it comes out. Three stamped artifacts already do this
(`backtest_results.json`, `check_calibration.json`, `correlation_stability.json`,
`lens_agreement.json`), including a backtest that reports its own ranking has **no
detectable edge**.

A neighbouring product could copy the four lenses. It could not truthfully copy
"we measured whether our own signal works and published the null result".

## Constraints

These are durable product facts. Future work preserves them; none is a style preference.

1. **No composite buy/hold/sell.** Not a number, letter, traffic light or sortable
   "conviction" column. Guarded by `tests/test_synthesis.py` and `tests/test_pretrade.py`.
   This is the direction any change toward "easier to interpret" will drift, and it is
   permanently refused.

   *Confirmed boundary for v2 (29 Aug 2026):* per-lens status chips driven by the existing
   `explain.tone` are permitted — four chips side by side, one word each. They are **never
   summed, averaged, counted or ordered by strength**. Nothing may aggregate them.

2. **No predictive claim that isn't measured.** If a feature implies something predicts
   returns, it is measured offline and published including nulls, or it does not ship.

3. **Absence of a flag is never evidence of quality.** An empty panel is not a clean bill
   of health and must say so in words.

4. **Direction is decided once, in Python.** Components read `explain.tone`; they never
   colour from the sign of a number. Six documented sign-based exceptions survive where
   Python has no interpretation to offer (a day's price change, the seasonality grid).

5. **Existing refusals stay.** `applicable: false` for financials on the accounting
   screens; the candlestick firewall; the declined multi-bar chart patterns; the
   `unavailable` band.

6. **One data module, one serverless function, no server state, a generated glossary,
   offline tests against planted ground truth.** The thesis journal and holdings never
   reach a server; `scripts/check_frontend.mjs` fails the build if `lib/api.ts` so much as
   mentions the journal.

7. **Every figure explains itself.** Each number carries what it measures in plain English,
   whether *this* value is good or bad and why, and what would make you act differently —
   or admits nothing would. This content may be restructured or progressively disclosed.
   It may not be deleted.

## Terminology

- **Lens** — one of the four models (Flow, Trend, Value, Quality).
- **Family** — the body of data a lens reads: *price and volume*, or *the filings*. Flow
  and Trend are one family; Value and Quality are the other.
- **Tone** — the server's judgement on a figure: `good` / `bad` / `warn` / `neutral` /
  `none`. The only permitted input to colour.
- **Guided / Full** — the two reading modes. Guided is the default.
- **Horizon** — how long the reader means to hold, stated once and read by several panels.

## Evidence and assets

- Measured artifacts, each stamped with its date, in `api/_lib/*.json`.
- `docs/field-manual.html` — beginner's guide; its glossary is **generated** from
  `api/_lib/explain.py` and CI fails if a metric is added without regenerating.
- Four network scripts in `scripts/` deliberately outside CI. Re-run after touching what
  they measure; a stale stamped number is worse than none.

## Accessibility

Audited 29 Aug 2026, and the findings are open work rather than a claim of conformance:
48 of 74 interactive elements on the Trend tab are under the 24×24 WCAG 2.2 minimum (the
info icon is 14×14); both tablists and both radiogroups declare an ARIA pattern without
its keyboard contract; eight sites use `text-ash` at 40–70% alpha, which composites to
2.2–3.2:1. The base palette itself clears AA (`ash` on `panel` is 5.18:1).

Page-level horizontal overflow at 375px was fixed in `08627c1`.

## Voice

Precise, unhedged, and willing to report bad news about itself. States when a signal is
weak, when data is missing, when a model does not apply. Never prints a confident number
it cannot defend. Dense docstrings and comments say **why**, and name the bug or the
decision behind a choice.

## Open decisions

- Whether Guided and Full eventually become two genuinely distinct designs rather than one
  design with elements hidden. Not now; v2 keeps one design with Guided as the default.
- IDX fundamentals curation — the largest single effort, and blocked on an architectural
  decision about where curated figures live relative to `market_data.py`.
