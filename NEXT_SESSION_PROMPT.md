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
Branch: feature/personal-verdict-scanner. 59 commits ahead of main, and
37 ahead of `origin/feature/personal-verdict-scanner`, which sits at
db2a753 — the branch WAS pushed before this session, contrary to what this
file used to say; nothing has been pushed since, and nothing was asked to be.
Tree clean apart from this file.
Stack: Next.js 15 + React 19 + Tailwind + Recharts on the front, FastAPI on a
single Vercel Python function on the back. 1,597 offline pytest tests, 35
frontend assertions and 10 enforced design rules. US and Indonesian (IDX)
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

SIX SILENT BUGS FROM 20-21 SEPTEMBER, ALL MINE OR LONG-STANDING
----------------------------------------------------------------
None threw. None changed a count. All exited zero. This is the shape of defect
this codebase actually produces, so it is worth knowing before adding anything.

1. A CACHE REFRESH THAT REPLACED ANSWERS WITH GAPS. At midnight the calendar
   rolled, `--fundamentals-days 1` expired every record, the rebuild came back
   "not in hand" for all 771 names, and `refresh_free_legs` wrote that over 771
   good payloads and saved them. A rebuild that knows LESS than what it would
   replace is now discarded. Related trap: `--fundamentals-days 1` means
   YESTERDAY's record is already expired; use 2+ when replaying.

2. A CSS CLAMP THAT COMPUTED CORRECTLY AND DID NOTHING. `line-clamp-3` sets
   `display: -webkit-box`; a later `block` in the same class list overrode it.
   The DOM read `webkitLineClamp: 3` and clamped nothing. A screenshot would not
   have told you; reading computed style did.

3. `neglect.py` READ `drawdown.current` FOR ITS WHOLE LIFE. The field has always
   been `currentDrawdown`. The module has no momentum filter BY DESIGN and
   compensates by reporting the drawdown as context — which had never rendered
   once. THE TEST PLANTED THE SAME WRONG KEY, so fixture and code agreed and
   neither agreed with the data. `scripts/check_payload_keys.py` now audits this
   class against a real sweep.

4. A MISSING BALANCE SHEET REPORTED AS NET CASH. Three lines each defaulted to
   zero, so subtracting gave zero net debt, which reads as "holds more cash than
   borrowings". A fabricated fact about a company nothing was known about.

5. A BUTTON NESTED INSIDE A BUTTON. Each specialist row was one big button and
   the term chips are buttons. Invalid HTML, React hydration error, browser
   rendered it anyway — visible only in the dev overlay's issue count.

6. NO KEYBOARD PATH TO THE TABLE'S PRIMARY ACTION. A `<tr onClick>` cannot be
   tabbed to. Seven rows had no focusable element at all and the rest had only
   the SEARCH buttons, so a keyboard user could reach every secondary action and
   none of the primary one.

THE INSTRUMENTS FAILED TOO, TWICE
----------------------------------
`check_payload_keys.py` did not catch the bug it was written for on its first
run: `finditer` returns no overlapping matches, so in a three-deep chain the
middle hop swallowed the call the next pair needed. A design rule for the
React-child bug was written, fired on four correct files, and was DELETED with
the reasoning left in `check_frontend.mjs` — a regex cannot tell a string map
from an object map, and a rule nobody trusts is worse than none.

Put the bug back and watch the instrument react. That is the only test these
have.

READ THIS BEFORE YOU TRUST A GREEN BATTERY
------------------------------------------
On 20 September the scan panel was opened in a browser for the first time and
showed "SOMETHING BROKE WHILE RENDERING". It had been failing since the day it
was written, a week earlier, with every check above passing — because the only
rendering that had been verified was the SERVER-SIDE one, which shows the
loading state. A panel fed by a fetch only fails once the data arrives.

So: the battery does not cover the page. Open it. The browser pane works.

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
          168 names in four universes: κ = +0.03 (US +0.05, IDX +0.09), every
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


  20-21 Sep  WHAT THE COMPANY DOES, AND WHO ELSE DOES IT. The scanner could say
          a business was cheap, solid and unwatched and could not say what the
          business WAS. Everything added is DESCRIPTION — nothing scores, gates
          or moves a verdict.

          `field.py`       the provider's business summary; a standing among the
                           scanned names sharing an industry label, by REVENUE
                           not market cap; and `distinctive_terms`, the words
                           common in one description and rare across the
                           market's. KETR reads cable, optic, fiber.
          `trackrecord.py` profits, cash, growth and borrowings over the years
                           the filings cover.
          the SEARCH       over the full description prose, in ScanPanel, with
                           each term a clickable chip.
          the SHORTLIST    `_specialists_summary`: largest or only measurable
                           name in its field, compounding, and uncovered.

          FIVE MEASUREMENTS CHANGED WHAT SHIPPED, all in the docstrings: a
          "niche" flag on field revenue share does not discriminate (the median
          field is 1/97 restated); "profitable every year" admits 67% of the IDX
          and is therefore description, not a screen; a leverage flag at the
          textbook 3x EBITDA sits exactly on this market's median for
          borrowers; no signal separates a closed-end trust from an operating
          asset manager, so no filter ships and the limitation is stated; and
          distinctive terms refuse a corpus under fifty descriptions because the
          ceiling and the floor cross.

          THE RESULT, ON A FULL 771-NAME INDONESIAN SWEEP: seven specialists,
          KETR.JK first at 28.6%/yr on an 18.5% net margin — the name this was
          asked for. All seven are gated, six on turnover, which is the expected
          outcome and is printed rather than hidden. Fifteen ungated buys, led
          by SRSN.JK at 77.3.

          A WRONG CURRENCY LABEL MANUFACTURES A CHAMPION: RIGS.JK took 99.4% of
          Indonesian marine shipping because rupiah statements are labelled USD.
          Guarded in `field.revenue_of` AND at the source in
          `market_data._apply_fx`, which is what every valuation reads.

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

- AFTER ANY THROTTLED SWEEP, REFETCH THE NAMES WHOSE DESCRIPTIVE FIELDS CAME
  BACK EMPTY, BEFORE READING THE BUY LIST. `field.profile` marks those `not
  returned`; 239 of 3,387 on the first US sweep. Their quality lens is a GAP
  rather than a refusal, and a missing component's weight is REMOVED from the
  blend, so the score goes UP.
  Measured on that sweep: refetching the 239 changed 30 verdicts, and 23 of them
  fell out of BUY. AAT went 60.5 to 46.3, BFH 72.2 to 50.2, BTX 72.9 to 58.3 —
  two of them had been STRONG BUYS at the top of the list purely on an absent
  lens. `reports/us-throttled.txt` is written by the analysis in the scratchpad;
  rebuild it from the report's `summaryState` and re-run those tickers with
  `--tickers @file --no-cache`, then replay the full scan.

- `scripts/check_payload_keys.py` finds reads of a key no real payload carries —
  the `drawdown.current` class of bug, where the parent hop resolves and the
  leaf never does, so Python returns None and a missing key is indistinguishable
  from a company that has no value for it. It needs a real sweep on disk and is
  therefore outside CI: an offline suite plants its own ground truth, and a key
  audit against planted data proves only that fixture and code agree, which is
  the failure that let the original through. Run it after a sweep and after
  changing what any module puts in a payload.

- THE SCAN PANEL RENDERS EVERY ROW, AND THAT IS MEASURED RATHER THAN ASSUMED.
  On the 3,364-name US report: payload 2.0MB, fetch 946ms, JSON.parse 5ms, and
  the "Everything" filter takes 889ms to paint 3,364 rows across 56,862 DOM
  nodes. Adding the business descriptions and term chips roughly quadruples the
  payload and adds about 13,000 nodes, so expect one to one and a half seconds
  on that filter and nothing noticeable on the default one. If it ever needs
  fixing the answer is row virtualisation, not trimming what is sent — the full
  description has to travel because the search reads it, and the character-361
  finding in `field.py` is why.

- `npm run check:frontend` now enforces 10 design rules by grep over source. Each
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
  0) OPEN AND UNFINISHED, in order:

     - `market_data._apply_fx` trusts the provider's `financialCurrency`
       unconditionally and is wrong on RIGS.JK and YPF, scaling their statements
       by 16,300x and 1/1000. The detector is already written and tested in
       `field.revenue_of`. Left alone because it moves every valuation.
     - THE SPECIALIST SCREEN IS A FRONTIER-MARKET TOOL AND THE US PROVES IT.
       On 2,136 US names the three conditions select NOTHING, because only 4%
       are uncovered against 79% on the IDX and the median US name is 85%
       institutionally held. Drop coverage and it returns StoneX and Microsoft.
       Measured, not assumed: across 2,171 US names with both readings — all
       already above the turnover floor — the uncovered share runs 0% in the
       highest turnover quintile to 11% in the lowest, monotonically. A US
       specialist hunt therefore has to go BELOW the floor, which means
       `--include-illiquid` and roughly 9,200 names at about ten a minute. The
       owner has been told and has not chosen; do not start it unasked.
     - THE US SWEEP HAS NEVER PRODUCED A USABLE BUY LIST. Asked for repeatedly;
       the 12 Sep run was contaminated by the quality throttle and two
       completion runs were killed. It is ~3,300 names at roughly 3.5s each with
       the fundamentals cache warm.
     - The specialist shortlist has been verified on cached data (5 names of
       729, KETR.JK at the top) but the card rendering it was verified only on
       an IDX scan. Look at it on a US scan.

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

     THIS IS NOW BETTER MOTIVATED THAN IT WAS. 201 of 722 cached IDX records
     carry no income statement at all, so a quarter of the exchange cannot be
     placed in a field or given a track record, and a field missing its largest
     member crowns the runner-up while looking no different.

  c) A real screen-reader pass. The keyboard walkthrough is clean (64
     focusables, zero unnamed, zero without a focus style, zero dangling
     aria-controls, all four roving groups at one tab stop), but nobody has
     listened to it.

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
- Before finishing: the full battery above, plus OPEN THE PAGE IN A BROWSER on
  both a US and an IDX ticker, and on the landing state where the scan panel
  lives. See the note under STATE: a green battery does not mean the page
  renders, and this has already cost a week.
- Commit on the current branch. Don't push.
- If you disagree with anything here, say so before building it.
