# Audit before launch, November 2026

A read of the whole app as a reviewer would before strangers use it: are the
numbers right, is it safe to expose, what happens when the data provider
misbehaves, how fast is it, and can a newcomer read it in either language.

Taken on 14 November 2026 against commit `4d0aace`, with the provider reachable,
so every claim below about real companies was measured on real data.

**How to read a finding.** Each has a code, what is wrong in one sentence, where
it is (`file:line`), how it was seen, and what fixing it involves. Findings that
can be shown offline have a reproduction in `scripts/audit_repro.py`:

```bash
.venv/bin/python scripts/audit_repro.py          # every finding: PRESENT or absent
.venv/bin/python scripts/audit_repro.py SEC-2    # one of them
```

It prints `PRESENT` while a defect is in the code and `absent` once it is
fixed. Findings that need the live provider or a browser name the instrument
that measured them, all in `scripts/audit/`:

| Instrument | What it does |
|---|---|
| `sweep.py` | Runs the production payload builders over 198 real companies and records every statement lookup, statement shape and quality score; `--compare` diffs two passes |
| `hang.py` | Times one company read against a provider that accepts a connection and never answers. Touches no real network |
| `walk.mjs` | Opens pages of the production build at given widths and languages: screenshot, visible text, sideways scroll, axe-core |
| `perf.mjs` | Load cost on an emulated mid-range phone: layout shift, blocking time, bytes |
| `overflow.mjs` | Finds the element that makes a page scroll sideways |
| `keys.mjs` | Walks a page by keyboard and tries everyday company names in the palette |

The four browser scripts need Playwright, which is not a dependency of this
project; each says how to run it in its first lines.

**Status** is filled in as the work is done: *open*, *fixed* (with the commit),
*decision* (the owner's to make, with a recommendation at the end of this file),
or *deferred* (with the reason).

## Summary

| Code | Impact | Finding | Status |
|---|---|---|---|
| REL-1 | High | A provider that hangs holds one company read for minutes; the platform kills it at 60 s | open |
| REL-7 | High | The provider sometimes returns a statement with a row missing, and the app keeps it as fact for a day | open |
| COR-1 | High | A statement line is found by substring: six Indonesian banks chart the wrong line as operating income | open |
| SEC-1 | High | Eighteen known advisories in the Python dependencies; CI audits npm only | open |
| REL-4 | High | Ordinary browsing reaches the rate limit; limits are per address | open |
| PERF-1 | High | The stock page jumps as results arrive (layout shift 0.62 on a phone) | open |
| UX-1 | High | A company cannot be found by its everyday name, and "apple" opens a ticker called APPLE | open |
| PERF-2 | Medium | One company read is 1.35 MB of JSON, 1.1 MB of it the chart series | open |
| REL-2 | Medium | During an outage the single-lens routes tell the reader their ticker is wrong | open |
| REL-3 | Medium | One failed price request is final: no second attempt | open |
| REL-5 | Medium | The browser never gives up on a request, and cannot read a validation error | open |
| COR-4 | Medium | Two lenses on one page use two risk-free rates (4.2% and the live 5.15%) | open |
| COR-5 | Medium | A company that stopped trading is told to "widen the date range" | open |
| COR-3 | Medium | Three names in the Nasdaq-100 list no longer trade | decision |
| SEC-2 | Medium | The ticker pattern accepts `..` | open |
| SEC-3 | Medium | Validation errors are English lists that echo their input without limit | open |
| SEC-4 | Medium | Any website may call the API on a preview deployment | open |
| SEC-5 | Medium | A failed lens returns the raw exception text to the reader | open |
| PERF-3 | Medium | Nothing is code-split: every page ships every panel, and the Indonesian catalogue | open |
| PERF-4 | Medium | A public deployment imports the private scanner on every cold start | open |
| UX-2 | Medium | The Flow tab scrolls sideways at 375 px | open |
| UX-3 | Medium | The holding-period control offers 5 and 10 years the default load cannot answer | open |
| UX-4 | Medium | On a phone the company's name is below the first screen | open |
| UX-5 | Medium | Identifiers and provider text reach an Indonesian reader in English | open |
| COPY-1 | Medium | The Ulcer index explains itself with only its own number | open |
| COPY-2 | Medium | The landing says the four models "share no data"; two of them share a series | open |
| COPY-3 | Medium | "More growth than you assumed", said of a default the reader never set | open |
| COPY-4 | Medium | A loss is worded as a gain ("still returned −16.4%", "you earned −0.49") | open |
| SEC-6 | Low | The rate limiter counts per serverless instance | decision |
| SEC-7 | Low | The API sets no security headers of its own; `/api/docs` is public; `X-Powered-By` is sent | open |
| SEC-8 | Low | The content security policy allows inline scripts | deferred |
| COR-2 | Low | The Beneish leverage index is silently neutral when a company has no long-term debt line | open |
| REL-6 | Low | A news thumbnail that fails to load draws an empty box | open |
| COPY-5 | Low | The rate-limit message says "endpoint" | open |
| DOC-1 | Low | Three statements in the README no longer match the app | open |

## What was done

- **The check battery**, green before and after: 1,920 tests, ruff, the glossary
  check, tsc, eslint, 20 design rules, 85 frontend assertions, the production
  build, `npm audit`.
- **A live sweep of 198 real companies** through the production payload
  builders: all 122 names of the Dow 30 and Nasdaq-100, all 46 of IDX30 and
  LQ45, and 30 Indonesian listings drawn at random from the rest of the
  exchange (seeded). It recorded every statement line the app looked up and how
  it was found, each statement's shape, and each quality score. The US names
  were then fetched a second time and compared.
- **Independent recomputation** from one saved company read: fifteen indicators,
  the discounted cash flow bridge and the Altman score, each from its textbook
  formula.
- **The API driven directly**: every route with hostile input, with the
  provider's functions patched to fail, and once with the provider replaced by a
  socket that accepts a connection and never answers.
- **`pip-audit`** on the runtime requirements and `npm audit` on all of them.
- **The production build in Chromium**, through Playwright: 48 page loads of the
  landing, markets, journal, compare and not-found pages at 375, 768 and 1440 px
  in both languages, every tab of the AAPL page at 375 px, BBCA.JK at 1440 px in
  Indonesian, a small Indonesian listing with no statements, and a delisted US
  name. Each with axe-core (WCAG 2.0 and 2.1, A and AA), a sideways-scroll check
  and the visible text saved for reading. A keyboard walk of the landing page,
  and load cost measured on an emulated mid-range phone.

## High impact

### REL-1. A provider that hangs holds one company read for minutes

`/api/confluence` runs six legs in threads and waits for all of them
(`api/index.py:2487`, `asyncio.gather` with no deadline). Each leg makes several
provider calls, each with the library's own timeout of ten to thirty seconds and
no overall budget. `vercel.json:6` allows the function 60 seconds.

**Seen.** `scripts/audit/hang.py 400`: with the provider replaced by a socket
that accepts and never answers, `GET /api/confluence?ticker=AAPL` had not
returned after 380 seconds, when the probe gave up. On the platform that request is killed at 60 seconds and the
reader gets a bare gateway error with no lens at all, although the app has a
careful, worded outage state that needs only the price legs to fail fast.
`audit_repro.py REL-1` shows the mechanism offline: five legs answer at once,
the sixth stalls, and the response waits for it.

**Fix.** Give each leg a time budget well inside the function limit and report
a leg that ran out as its own failure, so the other five still arrive. A thread
cannot be cancelled, so the budget bounds the response, not the work.

### REL-7. The provider sometimes returns a statement with a row missing, and the app keeps it

The same request for the same company, minutes apart with both markets closed,
does not always return the same statements. Two passes over the 122 US names
read **six of them differently (5%)**: five had one statement a row shorter or
longer (AZN, LULU, MNST, NFLX, NVDA) and one changed a Piotroski score with the
same shapes (MELI). NVDA's balance sheet came back with 79 rows where the other
pass, and five later fetches, had 80; with that one row gone its Altman score
went from "safe" to "cannot score".

`market_data.company` keeps whatever arrived for the rest of the day
(`api/_lib/market_data.py:864`), and the scanner's disk cache keeps it for a
week. The only test of a record's completeness is whether a sector arrived
(`market_data.py:705`), which a record with one row missing passes.

This is also why the lens agreement did not reproduce to the third decimal
(RESEARCH_ROADMAP §15): two runs ninety minutes apart returned −0.025 and
−0.054 with identical coverage and seeded engines.

**Seen.** `scripts/audit/sweep.py out1.json`, then `sweep.py out2.json --group
US` without the statement cache, then `sweep.py --compare out1.json out2.json`.
One fetch in twenty is not rare, and each record is served for a day.

**Fix.** There is no ground truth to check a row against, so this cannot be
closed, only narrowed: when a score comes back "cannot score" for want of a
line that the same statement normally carries, ask once more before keeping
the record, and never let a record with fewer rows replace one with more inside
the same day. The limit that remains belongs in the README's known limits.

### COR-1. A statement line is found by substring, and it finds the wrong line

`valuation._get_row` (`api/_lib/valuation.py:218`) looks a line up by exact
name first and then falls back to any row whose name *contains* an alias. The
fallback is what reads Indonesian direct-method cash flows, and it is also
loose enough to read the wrong row.

**Seen on real data** (`scripts/audit/sweep.py`, 198 companies, every lookup
recorded):

- **Six Indonesian banks** (BBRI, BMRI, BBNI, BBTN, BRIS, ARTO) have no
  "Operating Income" row. The alias matches inside "Other **Non Operating
  Income** Expenses", so the "What it is" tab charts non-operating items as the
  line "the business earns from operations", and `ebit` resolves to the same
  row.
- **Jasa Marga** (JSMR.JK) has no "Accounts Receivable" row, so `receivables`
  reads "Other Receivables", which feeds the Beneish receivables index of a
  non-financial company.
- **None of the 122 US names** used the fallback at all.

`audit_repro.py COR-1` shows the two worst cases the rule permits: `ebit`
reading EBITDA and `current_liabilities` reading "Total Non Current
Liabilities". Neither occurred in the sweep.

**Fix.** Make the fallback opt-in per alias, as the cash-flow comment in
`ROW_ALIASES` already argues for one row, and refuse a match that is preceded
by "non", "other" or "total non". A line that cannot be found exactly is then
missing, which every consumer already handles. This changes what the Quality
lens concludes for JSMR.JK, so `measure_lens_agreement.py` and
`calibrate_checks.py` run again afterwards.

### SEC-1. Eighteen known advisories in the Python dependencies

`pip-audit -r requirements.txt` reports 18 advisories in three packages:
Starlette 0.41.3 (seven distinct, fixed between 0.47.2 and 1.3.1), lxml 6.0.2
(fixed in 6.1.0) and certifi 2026.7.22 (fixed in 2026.10.18). FastAPI 0.115.6
pins Starlette below 0.42, so the Starlette fixes need a FastAPI upgrade. One
of them is the Host-header flaw the rate limiter already works around by hand
(`api/index.py:332`).

CI runs `npm audit` (`.github/workflows/ci.yml:75`) and nothing for Python, so
this backlog was invisible in the same way the Next.js one once was. The
production npm tree is clean; nine advisories sit in development dependencies.

**Fix.** Upgrade FastAPI and Starlette, lxml and certifi; run the suite; add
`pip-audit` to the CI audit job.

### REL-4. Ordinary browsing reaches the rate limit

Every page asks for the market board, the calendar and the headlines (the
landing page asks for headlines twice). `/api/markets/headlines` allows 20
requests a minute per address and the other two allow 30
(`api/index.py:255-259`).

**Seen.** `scripts/audit/walk.mjs` over sixteen pages in under a minute from one
address: every later page showed "Rate limit reached for this endpoint (30 requests per 60s). Try
again in 3s." in place of the board. On the platform the edge cache answers
most repeats before they reach the function, which softens this. Two things do
not soften: the limit is per address, and Indonesian mobile carriers put very
many readers behind one address, so one busy carrier gateway shares one
budget; and the page does not retry after the three seconds it has just
announced.

**Fix.** Keep the board, calendar and headlines in the browser for their cache
lifetime so navigation does not refetch them; raise the limits on the three
routes whose cost the edge already absorbs; retry once after `Retry-After`.

### PERF-1. The stock page jumps as results arrive

Measured by `scripts/audit/perf.mjs` on the production build with a
four-times slower processor and a 9 Mbit connection, at 375 px:

| Page | Layout shift | Blocking time | Script transferred |
|---|---|---|---|
| `/stock/AAPL` | **0.62** | 633 ms | 428 KB |
| `/` | 0.19 | 234 ms | 354 KB |
| `/markets` | 0.14 | 375 ms | 354 KB |

A layout shift under 0.1 is good and over 0.25 is poor. The stock page draws
skeletons, then replaces them with panels of a different height, and the
markets band above the page arrives after the page has drawn and pushes
everything down. A reader who has started on the first paragraph loses their
place.

**Fix.** Reserve the band's height before its data arrives, and size each
skeleton to the panel it stands in for (DESIGN.md already says they are "shaped
like what they stand in for"; the heights are what drifted).

### UX-1. A company cannot be found by its everyday name

The command palette searches the provider's legal names
(`api/_lib/listings.py:169`), and its first option is always the literal text
(`components/palette/CommandPalette.tsx:115`).

**Seen** (`scripts/audit/keys.mjs`, production build):

| Typed | Offered |
|---|---|
| `telkom` | only "Open TELKOM as typed" |
| `bca` | BCAP.JK, BCAT, BCAX. Bank Central Asia is not listed |
| `apple` | "Open APPLE as typed" **first**, then Apple Inc. |
| `astra` | "Open ASTRA as typed" first, then Astra International |

Pressing Enter on "apple" opens a page for a ticker called APPLE. "As typed
first" is right for someone who typed a ticker and a trap for someone who typed
a name, and the landing page's main box takes only a ticker. RESEARCH_ROADMAP
§23.3 recorded the legal-name half of this and left it.

**Fix.** Put a company that matches by name above "as typed" unless the text is
itself a listed symbol; add the names people use (Telkom, BCA, BRI, Mandiri,
Google, Facebook) as an alias table beside the listings; let the landing box
offer the same matches.

## Medium impact

### PERF-2. One company read is 1.35 MB of JSON

`GET /api/confluence?ticker=AAPL` at the defaults is 1,354,160 bytes, 409 KB
compressed. `technical.series` is 1.10 MB of it: 1,255 days as a list of
objects with about thirty keys each (`api/_lib/technical.py:687`), and the
drawdown series is sent a second time inside `longTerm`. The first call takes 3
to 5 seconds and a repeat about 1 second, because prices are fetched again.

**Fix.** Send the series as named columns instead of one object per day, and
drop the duplicate. The numbers do not change; the client rebuilds the rows.

### REL-2. During an outage the single-lens routes blame the ticker

Only `/api/confluence` asks whether the provider is answering
(`api/index.py:2518`). The routes the page uses to re-run one lens answer a
dead provider with "No company data came back for 'AAPL'. Non-US listings need
their exchange suffix" (`api/index.py:2028`, `2097`). A reader who changes one
valuation assumption during an outage is told their ticker is wrong.
`audit_repro.py REL-2`.

**Fix.** Ask the same question on those routes before blaming the symbol.

### REL-3. One failed price request is final

`market_data.ohlcv` turns any exception into "no data" on the first attempt
(`api/_lib/market_data.py:310`). A single reset connection therefore reads as a
symbol that does not exist. During planning the first call of a fresh process
failed once this way and succeeded seconds later; six later attempts to
reproduce it all succeeded, so it is rare, but on a serverless platform every
cold start is a first call. `audit_repro.py REL-3`.

**Fix.** One more attempt after a short pause, for the reader's own ticker.

### REL-5. The browser never gives up, and cannot read a validation error

`lib/api.ts:73-79` and `98-110` call `fetch` with no timeout. Three smaller
faults sit beside it (`lib/api.ts:46-59`, `112`): the fallback message
"Request failed (502)" is bare English; a validation error arrives as a list,
which is cast to a failure with no message, so the card is blank; and a dropped
connection is shown as "TypeError: Failed to fetch". `audit_repro.py REL-5`.

**Fix.** A deadline on every request, and worded, translated messages for the
three cases.

### COR-4. Two lenses on one page use two risk-free rates

The Value lens discounts from the live ten-year Treasury yield
(`market_data.risk_free_rate`), 5.15% on the day of the audit. The Trend lens
computes its Sortino ratio against a constant 4.2%
(`api/_lib/technical.py:738`). The markets band on the same page prints "US
10Y 5.154 · Value tab's rate" and the Sortino tile says "above a 4.2%
risk-free rate". README line 1332 says the US "uses a 4.2% risk-free rate",
which is true of one lens.

**Fix.** Read the same rate in both. The Sortino figure feeds the long-horizon
checklist and so the Trend vote, so the lens agreement is measured again.

### COR-5. A company that stopped trading is told to widen the date range

For Electronic Arts, whose history ends on 4 August 2026, the Trend lens
answers with one bar and the headline "too little history here to read a
trend. Widen the date range", and votes neutral. The Flow lens says "Only 0
usable rows; need at least 40. Try a longer period." Neither says the one
thing that is true: the last trade was three months ago. The same happens in
miniature for a young listing: SPRE.JK has traded for 569 sessions, and the
holding-period card tells the reader to widen a range that already covers its
whole life.

**Fix.** When the last bar is old, say when trading stopped; when the series
starts inside the requested range, say the company has not traded that long.

### COR-3. Three names in the Nasdaq-100 list no longer trade

`api/_lib/universes.py:95-103` still lists ANSS (no prices), EA (last bar
4 August 2026) and WBD (5 October 2026). The lists are transcribed by hand and
the README says they go stale. Every stamped measurement is taken over them.
Decision 3.

### SEC-2. The ticker pattern accepts `..`

`TICKER_PATTERN` (`api/index.py:207`) is `^[A-Za-z0-9.\-^=]{1,20}$`, and the
comment above it promises "no dots-dot". It accepts `..`, `.`, `-` and `^`
alone, each of which is interpolated into a provider URL path:
`GET /api/isolation-forest?ticker=..` sent a request for `/v8/finance/chart/..`.
The reach is the provider's own host, so this is a correctness-of-the-fence
finding, not a breach. `audit_repro.py SEC-2`.

**Fix.** Require a letter, digit or `^` first and forbid two dots together, in
the Python pattern and its mirror in `lib/symbols.ts`.

### SEC-3. Validation errors are English lists that echo their input

A request that fails validation gets the framework's default: a list of
objects, in English whatever language was asked for, each carrying the
rejected input. The app's own "Not valid ticker symbols" message joins the
offending symbols untruncated (`api/index.py:470-477`, `711-718`), and the
list bodies have no per-item length limit, so a 50,001-character "symbol" is
returned in a 50 KB error. `audit_repro.py SEC-3`.

**Fix.** One handler that answers a validation failure with a short sentence
in the reader's language and never the input; a length limit on list items.

### SEC-4. Any website may call the API on a preview deployment

`_allowed_origins` (`api/index.py:92-106`) returns `*` unless `VERCEL_ENV` is
exactly `production`. A preview deployment is as public as production
(`private_tier_enabled` says so two functions later), and `on_vercel`'s own
docstring warns that those variables are absent when the project does not
expose them, in which case production is open too. Local development does not
need the wildcard: the dev server proxies `/api`, so the browser sees one
origin. `audit_repro.py SEC-4`.

**Fix.** No wildcard unless `ALLOWED_ORIGINS` asks for one.

### SEC-5. A failed lens returns the raw exception text

`api/index.py:2493` (and `1089` on the private route) put
`f"{type(exc).__name__}: {exc}"` in the response. An unexpected failure
therefore shows a reader a Python exception, in English, with whatever path or
value the message carried. `audit_repro.py SEC-5`.

**Fix.** A worded, translated sentence for the reader; the exception goes to
the log (and to error reporting, Phase 6).

### PERF-3. Nothing is code-split

No file uses a dynamic import. The stock page's first load is 355 KB and the
markets page 316 KB; the chart library is one 388 KB chunk; the private
scanner's three largest components are imported by public pages that never
draw them (`components/workspace/StockWorkspace.tsx:24`,
`components/markets/MarketsView.tsx:7`); and the 110 KB Indonesian catalogue is
sent to every reader in every language. `audit_repro.py PERF-3`.

**Fix.** Load the tab panels, the private panels and the Indonesian catalogue
on demand.

### PERF-4. A public deployment imports the private scanner on every cold start

`api/index.py:80-84` imports `tape`, `patterns`, `verdict`, `chartlayers`,
`structure` and `volumeprofile` at module load. A public deployment refuses
both routes that use them. Importing the app takes 1.15 seconds here, of which
`tape` and `chartlayers` (through `scipy.stats`) are 0.36. `audit_repro.py
PERF-4`.

**Fix.** Import them inside the two private routes.

### UX-2. The Flow tab scrolls sideways at 375 px

The page is 383 px wide on a 375 px screen. The figure "Accumulation" at 24 px
is wider than its half-width tile (`components/AnomalyPanel.tsx:92`,
`grid-cols-2` with no minimum-width reset). DESIGN.md says no tab scrolls
sideways at 375 px.

**Seen.** `scripts/audit/overflow.mjs "/stock/AAPL?tab=flow" 375 en`, which
hides one node at a time until the width returns to 375.

### UX-3. The holding-period control offers horizons the default load cannot answer

The control offers 1, 2, 3, 5 and 10 years. The default range is five years
(1,255 bars), which cannot hold 21 overlapping five-year periods, so choosing
"5y" or "10y" answers "Needs about 1,280 trading days of history … Widen the
chart range" with nothing beside it to widen. The range lives under "Advanced
settings".

**Fix.** A button on the message that loads the range it asks for.

### UX-4. On a phone the company's name is below the first screen

At 375 px the markets band and the ticker form fill the first 770 px of
`/stock/AAPL`; the name of the company the reader asked for is on the second
screen (`components/shell/AppShell.tsx:50`). Tab content begins near 3,200 px,
below the summary and the pre-trade panel that head every tab.

**Fix.** On a stock page at phone width, the company first and the band after
it.

### UX-5. Identifiers and provider text reach an Indonesian reader in English

- The plain-language card prints its band identifier as a label: "WEAK" under
  "Dalam bahasa sederhana".
- Page titles and descriptions are English in both languages ("Markets ·
  QuantDesk", "Thesis journal").
- The company description and industry are the provider's English text, with
  nothing saying so.
- The holding-period chips read "1y 2y 3y 5y 10y" and a tile reads "(36M)".
- "Rp 4,031" uses English separators, which an Indonesian reader reads as four
  rupiah. PRODUCT.md lists this as an open decision; see Decision 4.

### COPY-1. The Ulcer index explains itself with only its own number

The tile reads "ULCER INDEX 11.7" and beneath it "11.7." The reading opens with
the bare number and a full stop (`api/_lib/explain.py:841`), and Guided mode
shows only the first sentence (`components/ui/explain.tsx:381`). It is the only
reading in `explain.py` that opens this way. PRODUCT.md constraint 7 says every
figure explains itself in one sentence. `audit_repro.py COPY-1`.

### COPY-2. The landing says the four models "share no data"

`components/landing/Landing.tsx:91`: "Read one company through four models
that share no data." Every stock page then says, correctly, "Flow and Trend
both read price and volume". README line 3 ("Four independent models") and
PRODUCT.md's positioning ("four that share no inputs") make the same claim.
The measured version is better and is true: four models, two bodies of data.
`audit_repro.py COPY-2`.

### COPY-3. "More growth than you assumed"

`api/_lib/explain.py:2712`: "the market is pricing in 22.5% a year MORE growth
than you assumed", and beside it "you assumed 10.0%". A newcomer assumed
nothing; 10% is the model's default, which RESEARCH_ROADMAP itself calls "a
default and … not a forecast". The same panel uses "WACC" once where
everything else says "discount rate".

### COPY-4. A loss is worded as a gain

"The unluckiest 3-year entry **still returned** −16.4% a year"
(`api/_lib/explain.py:1306`) and "you **earned** −0.49 units of return"
(`explain.py:437`) are sentences written for a positive number. In Indonesian
they read the same way. `audit_repro.py COPY-4`.

## Low impact

### SEC-6. The rate limiter counts per serverless instance

Stated in its own docstring (`api/index.py:322`). Making it global needs a
shared store, which is a service and a key. Decision 1.

### SEC-7. The API sets no security headers of its own

Responses from the Python function carry no `X-Content-Type-Options`,
`X-Frame-Options` or `Referrer-Policy`; they rely on the web layer adding
them. `/api/docs` is served, unlimited, on every deployment (`api/index.py:89`)
and loads its script from a third-party CDN, which the site's policy either
blocks or does not reach; this sandbox cannot reach a deployment to see which.
`next.config.mjs` still sends `X-Powered-By`. `audit_repro.py SEC-7`.

### SEC-8. The content security policy allows inline scripts

`next.config.mjs` needs `'unsafe-inline'` because the framework injects inline
bootstrap scripts. Removing it means a nonce per request, which makes every
page dynamically rendered. The app renders no user-supplied HTML (one
`dangerouslySetInnerHTML`, a constant), so the exposure is small. Deferred;
Decision 6.

### COR-2. The Beneish leverage index is silently neutral with no debt line

`api/_lib/quality.py:394-395` writes `(ltd_now or 0)` to treat a missing line
as zero, but a missing line is NaN and NaN is truthy, so the index is dropped
and defaults to "no change". In the sweep that is 8 of 115 US companies and 3
of 39 Indonesian ones; none of the eleven changes band when it is computed.
`audit_repro.py COR-2`.

### REL-6. A news thumbnail that fails to load draws an empty box

`components/ui/headlines.tsx:36` has no fallback. This sandbox blocks the two
image hosts, so every thumbnail here is the failure state, and the success
path could not be checked. `audit_repro.py REL-6`.

### COPY-5. The rate-limit message says "endpoint"

`api/index.py:377`, in both languages.

### DOC-1. Three statements in the README no longer match the app

- Line 195: "On AAPL that came out at **37% a year**"; the page shows 32.5%.
  An example that depends on the day needs its date.
- Line 1332: "US uses a 4.2% risk-free rate" (COR-4).
- `CODEBASE_REVIEW.md` is dated 20 August and describes a codebase a fifth of
  this size; NEXT_SESSION_PROMPT already calls it "partly superseded".

## Checked and found sound

Recorded because an audit that lists only faults reads as though everything
else was assumed.

- **Fifteen indicators** recomputed from the raw closes of one saved read (RSI,
  four moving averages, MACD and its signal, Bollinger %B, maximum drawdown,
  Ulcer index, two rates of change, both Donchian bounds, ATR): all equal to
  six decimals.
- **The discounted cash flow bridge** for AAPL by hand: present value of five
  years 663.12bn, terminal 1.583tn, 152.92 a share, terminal share 0.7047. All
  equal. **Altman Z''** from its four ratios: 6.4524, equal.
- **A stock split does not read as dilution.** The provider's balance-sheet
  share count is already restated: across 121 US companies, including NVDA,
  AVGO, NFLX and KLAC, no year-on-year count moved by a split ratio. (The
  scanner's share-count *series* is a different field and is not restated;
  farhanrkt/QuantDesk#10 handles that.)
- **No company in the sweep returned a whole statement missing while its
  sector arrived.** REL-7 is the subtler case of one row.
- **The private tier is fenced.** With a deployment's header present,
  `/api/verdict` answers 404 and `/api/scan/latest` says it is not served.
- **Input reaching a URL or a header** is pattern-checked on every route (SEC-2
  is the one gap in the pattern itself). The news feed refuses entity
  declarations, caps its size, and keeps only `https` links.
- **Accessibility**: zero axe-core violations on 58 page loads across three
  widths and both languages; no sideways scroll except UX-2; 61 keyboard stops
  on the landing page, none unnamed, none without a visible focus; `<html
  lang>` follows the language switch.
- **The outage state, the throttled-company state, a company with no
  statements, and the rate-limited state** are each worded, bilingual and
  honest about what is missing.
- **The first request of a cold process** failed once during planning and
  could not be made to fail again in six fresh processes (see REL-3).

## What this audit did not cover

- **A real deployment.** This sandbox cannot reach the preview deployment, so
  the edge cache, the security headers as served, cross-origin behaviour on a
  preview and the function bundle's size are reasoned about, not observed.
  They are in the deployment checklist Phase 6 adds.
- **News thumbnails**, for the same reason (REL-6).
- **A screen reader.** Still nobody has listened to it.
- **The private scanner's own arithmetic** (`verdict`, `tape`, `patterns`,
  `structure`, `ownership`), beyond its gating. It does not reach a visitor.
- **The event study, the change detector and the Isolation Forest** were not
  re-derived; RESEARCH_ROADMAP §13, §14, §17 and §23 did that.
- **The Indonesian** was read by the same hand that wrote the English. A
  native-speaking investor has still not read it.
- **Print**, and the walk-forward detection mode beyond its timing (15.6 s for
  one ticker).

## Decisions for the owner

Each of these is outside what this work may decide. The recommendation is what
I would do; the work that does not depend on the answer continues.

1. **A shared rate limiter needs a store** (SEC-6). *Recommendation:* add it as
   an optional adapter that switches on when two environment variables are set
   and falls back to the per-instance limiter when they are not; Phase 6 builds
   the adapter. Which store, and whether to pay for one, is yours. Until then
   the amplification caps, which need no shared state, remain the real defence.
2. **Which error-reporting service** receives the reports Phase 6 can send.
   *Recommendation:* any service that accepts the Sentry envelope format, so
   the code is not tied to one vendor.
3. **Updating the index lists** (COR-3). Replacing ANSS, EA and WBD changes the
   population behind every stamped measurement, so all of them are measured
   again. *Recommendation:* do it, as its own change, before the next
   scheduled re-measurement, and add a check that fails when a listed name has
   no recent prices.
4. **Indonesian number formatting** (UX-5). PRODUCT.md holds this open because
   the server, the interface and the exports must change together.
   *Recommendation:* do it, server first, because "Rp 4,031" is the single
   most misleading thing an Indonesian newcomer meets on the page.
5. **The colour and wording of the rail's headline.** On BBCA.JK the page
   opens with "Both independent readings negative" in red and "That is the
   strongest thing this app can say", when one of those two readings is a
   dividend model alone, the Quality lens having declined a bank. PRODUCT.md
   licenses the rail's count. To a newcomer it reads as a call to sell.
   *Recommendation:* keep the count, draw the headline in the neutral text
   colour, and name which lens each family's reading rests on when only one of
   its two lenses could read.
6. **The inline-script allowance in the content security policy** (SEC-8).
   *Recommendation:* leave it until the app renders something a reader wrote.
7. **`/api/docs` on a deployment** (SEC-7). *Recommendation:* serve it locally
   only. It is listed here, not done, because it is a page a visitor can open
   today.
8. **The data provider.** REL-7, the stale lists and the quarter of the
   Indonesian exchange with no statements (11 of the 30 small names drawn
   here) all come from an unofficial source with no guarantee. Nothing in this
   work changes the provider.
9. **The published copy of the field manual**, linked from the README, still
   carries August's figures. It is your page to republish.
10. **A native-speaking investor's read of the Indonesian.**
