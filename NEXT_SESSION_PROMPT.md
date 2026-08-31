I'm working on QuantDesk, a multi-lens equity research app at
~/PycharmProjects/QuantDesk. Read these first, in this order — between them they
say what exists, why, and what may not be broken:

  PRODUCT.md          who this is for and the constraints that outrank taste
  DESIGN.md           the visual system, written from the built surface
  README.md           what the app does
  RESEARCH_ROADMAP.md why each model, and what it does not claim

CODEBASE_REVIEW.md is older and partly superseded.

STATE
=====
Branch: feature/pre-trade-checks (41 commits ahead of main, NOT pushed, tree
clean apart from this file). Everything below is committed.

Stack: Next.js 15 + React 19 + Tailwind + Recharts on the front, FastAPI on a
single Vercel Python function on the back. 1,145 offline pytest tests, 35
frontend assertions and 7 enforced design rules. US and Indonesian (IDX)
listings.

The full battery, all green as of the last commit:
  .venv/bin/python -m pytest && .venv/bin/ruff check api tests scripts
  .venv/bin/python scripts/build_glossary.py --check
  npx tsc --noEmit && npm run lint && npm run check:frontend && npm run build
  npm audit --omit=dev --audit-level=high

Both halves run from .claude/launch.json (`quantdesk-web`, `quantdesk-api`) or
`npm run dev` / `npm run dev:api`. Both are pinned to `.venv/bin/python -m
uvicorn` — a bare `uvicorn` resolves to a system Python here carrying yfinance
1.5.2 against this project's 0.2.66.


WHAT THE LAST SESSIONS DID
==========================
Written up in RESEARCH_ROADMAP.md §7-§15 and DESIGN.md — read those rather than
re-deriving the reasoning.

  §7-§14  Pre-trade checks, validation domain, Beneish posterior, holding
          horizon, portfolio fit, thesis journal, and two audits (every formula
          against its source; the detector and the rendering paths).

  §15     THE CLAIM THE APP MAKES LOUDEST, MEASURED. The confluence rail asserts
          four lenses rest on two INDEPENDENT bodies of data. Nothing had
          checked it. Cohen's kappa between the two families' verdicts across
          168 names in four universes: κ = +0.03 (US +0.05, IDX +0.10), every
          interval straddling zero — so the claim is earned. The surprise was
          that Flow and Trend, the pair collapsed into ONE vote because they
          read the same series, also agree at κ = +0.03. The grouping was left
          alone anyway, because a vote that correlates with nothing is what an
          independent reading and an uninformative one both look like.

  v2      A design pass in two commits. The diagnosis was not "too much text":
          16 font sizes with 272 of 402 nodes inside a 3px band, section
          headings rendering at 10.88px BELOW the body they introduced, 54% of
          all text in the de-emphasis grey, 71 identical cards, 48 of 74
          interactive elements under 24x24. Not one sentence was deleted; the
          type got bigger and the desktop page got SHORTER, 8,415px to 7,034px.
          Then a second pass took the same treatment to every remaining panel
          plus a copy edit — Trend tab 2,476 visible words to 1,975, with ~1,100
          words one click away rather than gone.


PRINCIPLES THAT ARE LOAD-BEARING — do not quietly break these
=============================================================
PRODUCT.md holds the full list. The four that get broken by accident:

1. NO COMPOSITE BUY/HOLD/SELL. Not a number, letter, traffic light, sortable
   "conviction" column, count, badge, ring, meter, or size difference implying
   one lens outranks another. tests/test_synthesis.py and tests/test_pretrade.py
   guard the payload. This is the direction an agent building a decision feature
   drifts, and "make it easier to interpret at a glance" is the exact pressure
   that produces it.

   The one licensed exception: four per-lens status chips in the confluence
   rail, one word each, driven by explain.tone. Never summed, averaged, counted
   or ordered by strength.

2. NO PREDICTIVE CLAIM THAT ISN'T MEASURED. Measure it offline and publish the
   result INCLUDING nulls, or don't ship it. Five stamped artifacts do this:
   backtest_results.json, check_calibration.json, correlation_stability.json,
   lens_agreement.json, exposure_stability.json.

3. ABSENCE OF A FLAG IS NEVER EVIDENCE OF QUALITY. An empty panel is not a clean
   bill of health and must say so in words.

4. DIRECTION IS DECIDED ONCE, IN PYTHON. Components read `explain.tone`; they
   never colour from the sign of a number. Six documented exceptions survive
   where Python has no interpretation to offer, and `check_frontend.mjs` holds
   them as a per-file budget so the list cannot grow quietly.


WHERE TO BE CAREFUL
===================
- scripts/ holds SIX network scripts deliberately outside CI. Re-run
  calibrate_checks.py after touching a pre-trade check, backtest_ranking.py
  after ranking.py, measure_correlation_stability.py after the portfolio window,
  measure_lens_agreement.py after anything that changes what a lens CONCLUDES
  (a verdict band, a tone, the family grouping), and
  measure_exposure_stability.py after a change to exposure.REFERENCES or to the
  estimation window. A stale stamped number is worse than none.

- `npm run check:frontend` now enforces 7 design rules by grep over source. Each
  one describes a bug that was actually in this codebase. If one fires on
  something legitimate, widen the rule or add to its allowlist WITH the reason —
  do not delete the check.

- build_glossary.py --check fails CI if a metric is added without regenerating
  docs/field-manual.html. New metric groups also need a filter chip in the HTML.

- npm run build clobbers .next under a running dev server; clear .next and
  restart the preview if the page starts 500ing with __webpack_modules__.
  Tailwind config changes also need a dev-server restart.

- Four deviations from cited sources are deliberate and documented in §13
  (Bollinger ddof, Piotroski's ROA denominator, geometric Sharpe, Wilder's
  seed). Don't "fix" them without reading why.


WHAT I MIGHT WANT NEXT — pick with me before building
=====================================================
  a) The sensitivity grid (growth x discount rate) for the valuation. Open since
     §5. Note the roadmap's old claim was imprecise: pv_of_growing_stream is
     vectorised over DRAWS, with growth, rate and terminal broadcast row-wise,
     so a grid means flattening a meshgrid into that axis rather than an outer
     product it already supports. Still cheap. Watch principle 1: a grid of fair
     values against price, coloured, is a buy/sell heat map.

  b) IDX fundamentals curation — the durable moat and the largest single effort.
     Blocked on an architecture decision first: a curated overlay is a second
     source of truth beside market_data.py, and principle 6 says one data
     module. Where curated figures live, how they are dated, and how a reader
     tells them from fetched ones is a session on its own.

  c) Lens-vote correlation is DONE (§15). Accessibility and responsive layout is
     DONE for the single-ticker read and the panels. What has NOT been done is a
     real screen-reader pass — the keyboard walkthrough is clean (64 focusables,
     zero unnamed, zero without a focus style, zero dangling aria-controls, all
     four roving groups at one tab stop), but nobody has listened to it.

  d) Composition for Scan & rank, Screener, Portfolio and Thesis. They have the
     tokens, the copy pass and the Explainer treatment, but not the Section
     heading and surface-differentiation work the rail, synthesis and pre-trade
     got.

  e) Six sign-based colourings survive in components (a day's price change, the
     seasonality grid). I would leave them: the principle is "direction decided
     once in Python", and these are the cases where Python has nothing to say.
     They are now budgeted in check_frontend.mjs so they cannot multiply.


STANDARDS
=========
- Match the existing style: dense docstrings that say WHY, not what, and that
  name the bug or the decision behind a choice. Read a few modules first.
- Every new calculation gets tests written against an independently derived
  reference or planted ground truth — never against a second copy of the same
  formula. All tests run OFFLINE.
- Keep the intellectual honesty: say when a signal is weak, when data is
  missing, when a model doesn't apply. Never print a confident number you
  can't defend.
- Explanations may be restructured or progressively disclosed. They may not be
  deleted (PRODUCT.md constraint 7).
- Before finishing: the full battery above, plus verify the UI live in the
  browser on both a US and an IDX ticker.
- Commit on the current branch. Don't push.
- If you disagree with anything here, say so before building it.
