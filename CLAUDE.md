# QuantDesk

QuantDesk reads one listed company, US or Indonesian (IDX), through four
models: Flow (who is trading it) and Trend (what the price did) read the price
history; Value (what the business is worth) and Quality (whether the accounts
look real) read the filings. It says where they agree, where they conflict, and
what none of them can see. It is educational and research tooling, not
investment advice, and it is written for a reader with no finance background.

- Front end: Next.js 15, React 19 and Tailwind, in `app/`, `components/` and `lib/`.
- Back end: one FastAPI app (`api/index.py`) deployed as a single Vercel Python
  function, with the engines in `api/_lib/`.
- Both halves speak English and Bahasa Indonesia.

## Read first

These documents are the source of truth, and they are specific:

- `PRODUCT.md`: who the app is for, and the constraints that outrank taste.
- `DESIGN.md`: the visual system, and the rules `scripts/check_frontend.mjs` enforces.
- `README.md`: what each part does and how it is built.
- `RESEARCH_ROADMAP.md`: why each model, what it does not claim, and which
  measured numbers a change can move.
- `NEXT_SESSION_PROMPT.md`: the current state, and the kinds of bug this
  codebase tends to produce.

## Checks

Changes reach `main` through pull requests, and CI runs these checks on each
one. Run them before you push:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check api tests scripts
.venv/bin/python scripts/build_glossary.py --check
npx tsc --noEmit && npm run lint && npm run check:frontend && npm run build
npm audit --omit=dev --audit-level=high
```

Run the app with `npm run dev` (port 3000) and `npm run dev:api` (port 8000).
`npm run build` overwrites `.next` under a running dev server: stop the dev
server first, and delete `.next` before you start it again.

## Rules, and why they exist

- **No composite verdict on the single-company view.** No score, grade or
  buy/hold/sell for one company, because the reader is forming their own view
  (PRODUCT.md, constraint 1). `tests/test_synthesis.py` and
  `tests/test_pretrade.py` guard it.
- **Market data goes through `api/_lib/market_data.py`.** It is the only module
  that imports yfinance, and it holds the lock that stops concurrent downloads
  from mixing their results.
- **Measured numbers are re-measured, not edited.** The stamped artifacts in
  `api/_lib/*.json` come from scripts in `scripts/`; RESEARCH_ROADMAP.md says
  which change can move which number.
- **Tests run offline on synthetic data**, so the suite still passes when the
  data provider is down.
- **Every user-facing string is bilingual.** In the interface, wrap it in
  `t("…")` (or `msg("…")` in a table) and add its Indonesian to `lib/i18n-id.ts`.
  On the server, write `tr("English", "Indonesian")` from `api/_lib/lang.py`.
  Identifiers (bands, tones, codes, keys) stay English, because components,
  caches and tests compare them. Check rule 20 and `tests/test_language.py`
  fail on a gap.
- **`docs/field-manual.id.html` is generated.** Edit `docs/field-manual.html`
  and `docs/field-manual.id.json`, then run `scripts/build_glossary.py`.
- **The private scanner tier** (`api/_lib/verdict.py`, `scripts/scan_market.py`)
  runs only on the owner's machine and stays out of the published views.
- **Docs are part of the change.** README.md, DESIGN.md, PRODUCT.md and
  RESEARCH_ROADMAP.md describe behaviour in detail, so update them with the code.

## Data

Prices, filings and US headlines come from Yahoo Finance through yfinance,
which is unofficial and rate-limited; Indonesian headlines come from Google
News. When a provider fails, the app says so rather than guessing. Synthetic
data is fine for testing layout or logic, labelled as synthetic, and is never
presented as market data, in the app or in a report.
