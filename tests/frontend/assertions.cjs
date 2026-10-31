/**
 * Frontend logic that runs in the browser and nothing else could reach.
 *
 * The Python suite covers every calculation on the server. It cannot reach
 * `agreementOf`, which decides the headline claim on the confluence rail — how
 * many INDEPENDENT readings agree, as opposed to how many panels are on screen.
 * That is real decision logic and it lived here untested because the project has
 * no browser test runner.
 *
 * It still has none. `scripts/check_frontend.mjs` compiles these modules with
 * the TypeScript compiler already in the tree and runs the assertions below on
 * bare node — no new dependency, and the same `tsc` that guards the build.
 *
 * CommonJS on purpose: the components import through the `@/...` path alias,
 * which `tsc` emits unchanged and which only resolves under CJS here.
 */

const assert = require("node:assert/strict");
const { agreementOf } = require("./components/ConfluenceRail.js");
const { verdictLabel, ordinal, pct, signedPct, num, compact, splitEmphasis } = require("./lib/utils.js");
const { toCsv } = require("./lib/csv.js");

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.log("  FAIL:", name, "\n     ", e.message); process.exitCode = 1; } };

const R = (lens, family, vote, verdict = "X") => ({ lens, family, vote, verdict, question: "", detail: "", color: "", tone: "" });

// ---- agreementOf: the decision logic with no test coverage until now ----
t("four agreeing lenses report TWO independent sources", () => {
  const a = agreementOf([R("Flow","price",1), R("Trend","price",1), R("Value","filings",1), R("Quality","filings",1)]);
  assert.equal(a.lenses, 4);
  assert.equal(a.independent, 2, "four panels are not four opinions");
  assert.match(a.headline, /Both independent readings constructive/);
  assert.match(a.footnote, /4 lenses, 2 independent sources/);
});
t("all-negative mirrors it", () => {
  const a = agreementOf([R("Flow","price",-1), R("Trend","price",-1), R("Value","filings",-1), R("Quality","filings",-1)]);
  assert.match(a.headline, /Both independent readings negative/);
});
t("a family that disagrees votes zero and is named as split", () => {
  const a = agreementOf([R("Flow","price",1), R("Trend","price",-1), R("Value","filings",1), R("Quality","filings",1)]);
  assert.match(a.footnote, /split on price and volume/);
  assert.match(a.headline, /1 of 2 independent readings constructive/);
});
t("dashes and n/a are excluded from the count", () => {
  const a = agreementOf([R("Flow","price",0,"—"), R("Trend","price",1), R("Value","filings",1), R("Quality","filings",0,"n/a")]);
  assert.equal(a.lenses, 2);
});
t("nothing live says Awaiting data", () => {
  const a = agreementOf([R("Flow","price",0,"—"), R("Trend","price",0,"—")]);
  assert.equal(a.independent, 0);
  assert.equal(a.headline, "Awaiting data");
});
t("one family alone never claims a cross-check", () => {
  const a = agreementOf([R("Value","filings",1), R("Quality","filings",1)]);
  assert.equal(a.independent, 1);
  assert.match(a.headline, /1 of 1 independent reading constructive/);
  assert.equal(a.footnote, "2 lenses, 1 independent source");
});
t("no footnote when lenses and sources are equal", () => {
  const a = agreementOf([R("Trend","price",1), R("Value","filings",1)]);
  assert.equal(a.footnote, null);
});
t("singular/plural grammar holds", () => {
  const a = agreementOf([R("Value","filings",1)]);
  assert.match(a.headline, /independent reading\b/, "singular for one");
});

// ---- the label the whole rail depends on ----
t("verdict labels never say overvalued", () => {
  assert.equal(verdictLabel("OVERVALUED"), "Above model range");
  assert.equal(verdictLabel("UNDERVALUED"), "Below model range");
  assert.equal(verdictLabel("FAIRLY VALUED"), "Within model range");
  assert.equal(verdictLabel("ANYTHING ELSE"), "ANYTHING ELSE", "unknown passes through");
});

// ---- ordinal, including the exception everyone forgets ----
t("ordinals handle the teens", () => {
  const got = [1,2,3,4,11,12,13,21,22,23,101,111,112].map(v => v + ordinal(v));
  assert.deepEqual(got, ["1st","2nd","3rd","4th","11th","12th","13th","21st","22nd","23rd","101st","111th","112th"]);
});

// ---- formatters must never print a number for missing data ----
t("formatters render an em dash for null/NaN/Infinity", () => {
  for (const bad of [null, undefined, NaN, Infinity, -Infinity]) {
    for (const [nm, f] of [["pct",pct],["signedPct",signedPct],["num",num],["compact",compact]]) {
      assert.equal(f(bad), "—", `${nm}(${bad}) printed ${f(bad)}`);
    }
  }
});
t("signedPct always carries a sign", () => {
  assert.equal(signedPct(0.1234), "+12.3%");
  assert.equal(signedPct(-0.1234), "-12.3%");
  assert.equal(signedPct(0), "+0.0%");
});
t("compact scales", () => {
  assert.equal(compact(1.5e12), "1.50T");
  assert.equal(compact(-2.5e9), "-2.50B");
  assert.equal(compact(999), "999");
});
t("splitEmphasis extracts bold spans without innerHTML", () => {
  assert.deepEqual(splitEmphasis("a **b** c"),
    [{bold:false,text:"a "},{bold:true,text:"b"},{bold:false,text:" c"}]);
});

// ---- CSV: RFC 4180 quoting ----
t("csv quotes delimiters, quotes and newlines", () => {
  const out = toCsv([{a:'x,y', b:'he said "hi"', c:"line1\nline2"}],
                    [{key:"a",label:"A"},{key:"b",label:"B"},{key:"c",label:"C"}]);
  assert.match(out, /"x,y"/);
  assert.match(out, /"he said ""hi"""/);
  assert.match(out, /"line1\nline2"/);
});
t("csv renders null and undefined as empty, not the word", () => {
  const out = toCsv([{a:null,b:undefined}], [{key:"a",label:"A"},{key:"b",label:"B"}]);
  assert.equal(out.split("\r\n")[1], ",");
});

t("csv neutralises formula-leading TEXT", () => {
  // `=HYPERLINK` passes this app's ticker validation, because the pattern must
  // allow `=` for FX symbols. It must not execute when the export is opened.
  const out = toCsv([{ticker:"=HYPERLINK(\"http://x\",\"click\")"}, {ticker:"-AAPL"},
                     {ticker:"@SUM"}, {ticker:"+X"}, {ticker:"AAPL"}],
                    [{key:"ticker",label:"Ticker"}]);
  const rows = out.split("\r\n").slice(1);
  assert.ok(rows[0].startsWith('"\'=HYPERLINK'), rows[0]);
  assert.equal(rows[1], "'-AAPL");
  assert.equal(rows[2], "'@SUM");
  assert.equal(rows[3], "'+X");
  assert.equal(rows[4], "AAPL", "an ordinary ticker is untouched");
});
t("csv leaves NEGATIVE NUMBERS alone", () => {
  // The guard applies to strings only. Prefixing numbers would turn every
  // negative return in every export into text no spreadsheet will sum.
  const out = toCsv([{v:-12.5},{v:0},{v:3.2}], [{key:"v",label:"V"}]);
  assert.deepEqual(out.split("\r\n").slice(1), ["-12.5","0","3.2"]);
});


// ---- the thesis journal: client-side by design, so tested here ------------
// A thesis is what the reader believes, which has no reason to leave their
// machine, so none of this can live in Python with the rest of the app's
// judgement. That makes this file the only thing standing between it and
// shipping untested.
const J = require("./lib/journal.js");

const SNAP = (over = {}) => ({
  impliedGrowth: 0.37, assumedGrowth: 0.10, maxDrawdown: -0.33,
  price: 300, priceLabel: "$300.00", worstAtHorizon: 0.004, firedChecks: [], ...over,
});
const ENTRY = (over = {}) => ({
  id: "AAPL-1", ticker: "AAPL", written: "2026-08-28T10:00:00.000Z",
  thesis: "Services keeps compounding.", falsifier: "Services growth stalls.",
  growthBelief: 0.10, horizonYears: 3, positionShare: 0.05, snapshot: SNAP(), ...over,
});
const keys = (list) => list.map((c) => c.key).sort();

t("believing less growth than the price requires is named as such", () => {
  const found = J.contradictions(ENTRY({ growthBelief: 0.10 }));
  assert.ok(keys(found).includes("belowImplied"));
  const one = found.find((c) => c.key === "belowImplied");
  assert.match(one.detail, /10% a year/);
  assert.match(one.detail, /37% a year/);
  assert.match(one.detail, /should be\s+deliberate/);
});

t("believing MORE than the price requires is named too, not only the bearish gap", () => {
  const found = J.contradictions(ENTRY({ growthBelief: 0.50 }));
  assert.ok(keys(found).includes("aboveImplied"));
  assert.match(found.find((c) => c.key === "aboveImplied").detail, /know something/);
});

t("agreeing with the price within the tolerance is not a contradiction", () => {
  const found = J.contradictions(ENTRY({ growthBelief: 0.34 }));
  assert.ok(!keys(found).includes("belowImplied"));
  assert.ok(!keys(found).includes("aboveImplied"));
});

t("no stated belief means no belief check rather than a default one", () => {
  const found = J.contradictions(ENTRY({ growthBelief: null }));
  assert.ok(!keys(found).some((k) => k.endsWith("Implied")));
});

t("a missing implied growth is silence, never a comparison against zero", () => {
  const found = J.contradictions(ENTRY({ snapshot: SNAP({ impliedGrowth: null }) }));
  assert.ok(!keys(found).some((k) => k.endsWith("Implied")));
});

t("size is checked against the fall this stock has actually had", () => {
  // 70% of the account in something that fell 33% is 23% of everything.
  const found = J.contradictions(ENTRY({ positionShare: 0.70 }));
  const one = found.find((c) => c.key === "sizeVsDrawdown");
  assert.ok(one, "a position this size must be named");
  assert.match(one.detail, /23% of the\s+account/);
  assert.match(one.detail, /a thing that happened/);
});

t("a modest position against the same drawdown is left alone", () => {
  assert.ok(!keys(J.contradictions(ENTRY({ positionShare: 0.05 }))).includes("sizeVsDrawdown"));
});

t("a losing worst case at the stated horizon is surfaced", () => {
  const found = J.contradictions(ENTRY({ snapshot: SNAP({ worstAtHorizon: -0.08 }) }));
  const one = found.find((c) => c.key === "negativeAtHorizon");
  assert.ok(one);
  assert.match(one.title, /3-year holders/);
  // ...and a positive worst case is not dressed up as a warning.
  assert.ok(!keys(J.contradictions(ENTRY())).includes("negativeAtHorizon"));
});

t("nothing in a contradiction ever instructs", () => {
  const all = [
    ...J.contradictions(ENTRY({ growthBelief: 0.02, positionShare: 0.9 })),
    ...J.contradictions(ENTRY({ growthBelief: 0.9 })),
  ].map((c) => `${c.title} ${c.detail}`).join(" ").toLowerCase();
  for (const phrase of ["do not buy", "you should", "we recommend", "sell", "avoid"]) {
    assert.ok(!all.includes(phrase), `journal said ${phrase}`);
  }
});

// ---- drift: movement, never a verdict ------------------------------------
t("drift reports what moved and does not judge it", () => {
  const moved = J.drift(ENTRY(), SNAP({ impliedGrowth: 0.24, priceLabel: "$210.00" }));
  const byKey = Object.fromEntries(moved.map((d) => [d.key, d]));
  assert.equal(byKey.impliedGrowth.then, "37%");
  assert.equal(byKey.impliedGrowth.now, "24%");
  assert.equal(byKey.price.then, "$300.00");
  assert.equal(byKey.price.now, "$210.00");
  // No field on a Drift may carry a judgement — only a label and two values.
  assert.deepEqual(Object.keys(byKey.impliedGrowth).sort(), ["key", "label", "now", "then"]);
});

t("a number that has not moved is not reported as drift", () => {
  assert.equal(J.drift(ENTRY(), SNAP()).length, 0);
  assert.equal(J.drift(ENTRY(), SNAP({ impliedGrowth: 0.372 })).length, 0);
});

t("drift needs both sides and never invents one", () => {
  assert.equal(J.drift(ENTRY(), SNAP({ impliedGrowth: null })).length, 0);
  assert.equal(J.drift(ENTRY({ snapshot: {} }), SNAP()).length, 0);
});

// ---- storage: append-only, and defensive about what comes back out -------
t("entries come back newest first", () => {
  const raw = JSON.stringify([
    ENTRY({ id: "a", written: "2026-01-01T00:00:00.000Z" }),
    ENTRY({ id: "b", written: "2026-06-01T00:00:00.000Z" }),
  ]);
  assert.deepEqual(J.readJournal(raw).map((e) => e.id), ["b", "a"]);
});

t("a corrupt store loses the bad rows, never the good ones", () => {
  const raw = JSON.stringify([ENTRY({ id: "good" }), { nonsense: true }, null, 7]);
  assert.deepEqual(J.readJournal(raw).map((e) => e.id), ["good"]);
});

t("unparseable storage is an empty journal, not an exception", () => {
  assert.deepEqual(J.readJournal("{not json"), []);
  assert.deepEqual(J.readJournal(null), []);
  assert.deepEqual(J.readJournal(JSON.stringify({ not: "an array" })), []);
});

t("saving appends and never rewrites an existing entry", () => {
  const first = ENTRY({ id: "one", thesis: "as written" });
  const list = J.appendEntry([first], ENTRY({ id: "two" }));
  assert.deepEqual(list.map((e) => e.id), ["two", "one"]);
  assert.equal(list[1].thesis, "as written", "an earlier entry must survive untouched");
});

t("ids carry the ticker and the instant, so two theses cannot collide", () => {
  const when = new Date("2026-08-28T10:00:00.000Z");
  assert.equal(J.newId(when, "aapl"), "AAPL-2026-08-28T10:00:00.000Z");
  assert.notEqual(J.newId(when, "AAPL"), J.newId(when, "MSFT"));
});

// ---- cn(): the custom type scale is a font size, not a colour ----
const { cn } = require("./lib/utils.js");

t("a toned figure keeps its size, and a small button keeps its text colour", () => {
  assert.equal(cn("num text-figure font-semibold", "text-acc"), "num text-figure font-semibold text-acc");
  assert.equal(cn("bg-tech text-ink", "h-9 px-3.5 text-meta"), "bg-tech text-ink h-9 px-3.5 text-meta");
  assert.equal(cn("text-meta text-ash", "text-warn"), "text-meta text-warn", "a later tone still replaces a colour");
  assert.equal(cn("text-meta", "text-lead"), "text-lead", "a later size still replaces a size");
});

// ---- analytics: a page view carries a route template, never a ticker ----
const { redactPath, redactUrl } = require("./lib/redact.js");

t("a stock page is reported as its template", () => {
  assert.equal(redactPath("/stock/AAPL"), "/stock/[symbol]");
  assert.equal(redactPath("/stock/BBCA.JK/"), "/stock/[symbol]");
  assert.equal(redactPath("/stock/%5EGSPC"), "/stock/[symbol]");
});
t("query strings and fragments never survive", () => {
  assert.equal(redactPath("/compare?symbols=AAPL,MSFT"), "/compare");
  assert.equal(redactPath("/stock/AAPL?tab=value#peers"), "/stock/[symbol]");
  assert.equal(redactUrl("https://q.example/compare?symbols=AAPL,BBCA.JK"), "https://q.example/compare");
});
t("an unknown path is /other, so a new route cannot leak by being forgotten", () => {
  assert.equal(redactPath("/AAPL"), "/other");
  assert.equal(redactPath("/stock/AAPL/extra"), "/other");
  assert.equal(redactPath(null), "/");
  assert.equal(redactUrl("not a url"), "/other");
});

// ---- lib/url: what the address bar means ----
const U = require("./lib/url.js");

t("a stock link writes only what differs from the defaults", () => {
  assert.equal(U.stockHref("aapl"), "/stock/AAPL");
  assert.equal(U.stockHref("AAPL", "trend"), "/stock/AAPL", "trend is the default tab");
  assert.equal(U.stockHref("BBCA.JK", "value"), "/stock/BBCA.JK?tab=value");
  assert.equal(U.stockHref("AAPL", "flow", { mode: "mad", madK: 4 }), "/stock/AAPL?tab=flow&mode=mad&k=4");
});
t("symbols that are not path-safe survive the round trip", () => {
  for (const sym of ["^GSPC", "EURUSD=X", "BRK-B", "BTC-USD", "BBCA.JK"]) {
    const segment = U.stockHref(sym).slice("/stock/".length);
    assert.equal(U.symbolFromSegment(segment), sym);
  }
});
t("a path segment that is not a ticker is refused, never guessed at", () => {
  assert.equal(U.symbolFromSegment("..%2F..%2Fetc"), null);
  assert.equal(U.symbolFromSegment("%E0%A4%A"), null, "malformed encoding");
  assert.equal(U.symbolFromSegment("A".repeat(21)), null);
});
t("a query is parsed defensively: unknown tabs and bad numbers fall back", () => {
  const q = U.parseStockQuery("?tab=nonsense&mode=evil&k=NaN&q=0.9&t=-0.2&range=10y");
  assert.equal(q.tab, U.DEFAULT_TAB);
  assert.equal(q.run.mode, "threshold");
  assert.equal(q.run.madK, 3);
  assert.equal(q.run.contamination, 0.02, "0.9 is outside what the API accepts");
  assert.equal(q.run.scoreThreshold, -0.2);
  assert.equal(q.run.range, "10y");
});
t("parse then write is the identity on a written link", () => {
  const href = U.stockHref("NVDA", "quality", { period: "5y", scoreThreshold: -0.2 });
  const back = U.parseStockQuery(href.split("?")[1]);
  assert.equal(U.stockHref("NVDA", back.tab, back.run), href);
});
t("a compare list keeps the reader's order, resolves, de-duplicates and caps at four", () => {
  assert.deepEqual(U.parseSymbolList("msft, aapl msft,BBCA.JK"), ["MSFT", "AAPL", "BBCA.JK"]);
  assert.deepEqual(U.parseSymbolList("bbca,tlkm", "ID"), ["BBCA.JK", "TLKM.JK"]);
  assert.equal(U.parseSymbolList("A,B,C,D,E,F").length, 4);
  assert.deepEqual(U.parseSymbolList("AAPL, ../x, <b>"), ["AAPL"]);
  assert.equal(U.compareHref(["B", "A"]), "/compare?symbols=B,A");
});

// ---- lib/symbols: the browser's copy of api/_lib/symbols.py ----
const S = require("./lib/symbols.js");

t("an explicit suffix beats the market dropdown, as on the server", () => {
  assert.equal(S.resolveSymbol("bbca", "ID"), "BBCA.JK");
  assert.equal(S.resolveSymbol("BBCA.JK", "US"), "BBCA.JK");
  assert.equal(S.resolveSymbol("BBCA.JK", "ID"), "BBCA.JK", "idempotent");
  assert.equal(S.resolveSymbol(" aapl ", "US"), "AAPL");
  assert.equal(S.marketOf("TLKM.JK"), "ID");
  assert.equal(S.marketOf("BRK.B"), "US");
  assert.equal(S.baseCode("BBCA.JK"), "BBCA");
});

// ---- lib/cache: what the browser keeps, and for how long ----
const { createTtlCache } = require("./lib/cache.js");

t("a cached value expires after its TTL and is never served stale", () => {
  let clock = 0;
  const c = createTtlCache({ ttlMs: 100, now: () => clock });
  c.set("k", 1);
  assert.equal(c.peek("k").value, 1);
  clock = 101;
  assert.equal(c.peek("k"), undefined);
});
t("the oldest entry is evicted past the cap", () => {
  const c = createTtlCache({ max: 2, now: () => 0 });
  c.set("a", 1); c.set("b", 2); c.set("c", 3);
  assert.equal(c.peek("a"), undefined);
  assert.equal(c.size(), 2);
});
const pending = [];
pending.push((async () => {
  let calls = 0;
  const c = createTtlCache({ now: () => 0 });
  const fetcher = () => new Promise((r) => { calls++; setTimeout(() => r("v"), 5); });
  const [x, y] = await Promise.all([c.getOrFetch("k", fetcher), c.getOrFetch("k", fetcher)]);
  t("two callers asking at once share one request", () => {
    assert.equal(calls, 1);
    assert.equal(x.value, "v"); assert.equal(y.value, "v");
  });
  let failures = 0;
  const failing = () => { failures++; return Promise.reject(new Error("throttled")); };
  await c.getOrFetch("bad", failing).catch(() => {});
  await c.getOrFetch("bad", failing).catch(() => {});
  t("a failure is never cached: the next caller asks again", () => {
    assert.equal(failures, 2);
    assert.equal(c.peek("bad"), undefined);
  });
})());

// ---- lib/watchlist: browser-only, and defensive on read ----
const W = require("./lib/watchlist.js");

t("a corrupt or hand-edited watchlist loses the bad rows, never the good ones", () => {
  assert.deepEqual(W.parseList(JSON.stringify({ v: 1, symbols: ["aapl", 7, "../x", "AAPL", "BBCA.JK"] })),
                   ["AAPL", "BBCA.JK"]);
  assert.deepEqual(W.parseList(JSON.stringify(["msft"])), ["MSFT"], "a bare array still reads");
  assert.deepEqual(W.parseList("{not json"), []);
  assert.deepEqual(W.parseList(null), []);
});
t("a full watchlist refuses an add rather than silently dropping something kept", () => {
  const full = Array.from({ length: W.WATCHLIST_MAX }, (_, i) => `T${i}`);
  assert.equal(W.toggle(full, "NEW"), full);
  assert.deepEqual(W.toggle(["AAPL"], "aapl"), [], "toggling an existing symbol removes it");
  assert.deepEqual(W.toggle(["AAPL"], "msft"), ["MSFT", "AAPL"]);
});
t("recent tickers are a trail: newest first, de-duplicated, capped", () => {
  assert.deepEqual(W.pushRecent(["A", "B", "C"], "b"), ["B", "A", "C"]);
  assert.equal(W.pushRecent(Array.from({ length: 20 }, (_, i) => `T${i}`), "X").length, W.RECENT_MAX);
});

// ---- lib/shortcuts: never while typing ----
const K = require("./lib/shortcuts.js");

t("shortcuts never fire in a text field, but the palette chord does", () => {
  const input = { tagName: "INPUT", type: "text" };
  assert.equal(K.matchShortcut({ key: "]" }, input), null);
  assert.equal(K.matchShortcut({ key: "w" }, { tagName: "TEXTAREA" }), null);
  assert.equal(K.matchShortcut({ key: "w" }, { isContentEditable: true }), null);
  assert.equal(K.matchShortcut({ key: "k", metaKey: true }, input), "palette");
  assert.equal(K.matchShortcut({ key: "]" }, { tagName: "INPUT", type: "checkbox" }), "nextTab");
});
t("a modified key is left to the browser, and composition is ignored", () => {
  assert.equal(K.matchShortcut({ key: "[", metaKey: true }), null, "cmd-[ is the browser's back");
  assert.equal(K.matchShortcut({ key: "w", ctrlKey: true }), null);
  assert.equal(K.matchShortcut({ key: "/", isComposing: true }), null);
  assert.equal(K.matchShortcut({ key: "?" }), "help");
});

// ---- lib/commands: the palette orders by how text matches, never by a company ----
const C = require("./lib/commands.js");

t("a label prefix outranks a word match outranks a keyword", () => {
  const cmds = [
    { id: "a", label: "Thesis journal", group: "Go to" },
    { id: "b", label: "Markets: rank a universe", group: "Go to", keywords: "journalism" },
    { id: "c", label: "Journal", group: "Go to" },
  ];
  assert.deepEqual(C.rankCommands(cmds, "jour").map((c) => c.id), ["c", "a", "b"]);
  assert.deepEqual(C.rankCommands(cmds, "zzz"), []);
  assert.deepEqual(C.rankCommands(cmds, "").map((c) => c.id), ["a", "b", "c"], "no query keeps order");
});

// ---- lib/compare: side by side, and never a decision ----
const { buildCompare } = require("./lib/compare.js");

const EXPLAIN = (valueText, tone) => ({ label: "x", what: "x", reading: `reads ${valueText}`, action: "x",
                                       band: "fair", tone, goodDirection: "high", evidence: null, valueText });
const PAYLOAD = (symbol, verdict, tone) => ({
  status: "ready",
  data: {
    ticker: symbol,
    anomaly: { ok: false, error: "no bars" },
    technical: { ok: false, error: "no bars" },
    quality: { ok: false, error: "no statements" },
    news: { ok: true, data: { ticker: symbol, items: [] } },
    valuation: { ok: true, data: {
      ticker: symbol, engine: "DCF", verdict, market: { code: symbol.endsWith(".JK") ? "ID" : "US" },
      monteCarlo: { upside: 0.2, p50Label: "$10", probUndervalued: 0.6 },
      explain: { impliedGrowth: EXPLAIN("12.0%", tone), terminalShare: EXPLAIN("70%", "warn") },
    } },
    company: { ok: true, data: {
      name: `${symbol} Corp`, profile: { industry: "Widgets", sector: "Industrials", summaryShort: null },
      listing: { exchange: "X", marketCap: 1e9 }, currency: { trading: symbol.endsWith(".JK") ? "IDR" : "USD" },
      nextEarnings: { date: null }, explain: {},
    } },
    synthesis: { headline: "Both independent readings constructive" },
    preTrade: { flags: [{ explain: { label: "Balance sheet in the distress zone" } }],
                caveat: "An empty panel is not a clean bill of health." },
  },
});

t("columns keep the reader's order under every permutation", () => {
  const a = { symbol: "AAA", state: PAYLOAD("AAA", "UNDERVALUED", "good") };
  const b = { symbol: "BBB.JK", state: PAYLOAD("BBB.JK", "OVERVALUED", "bad") };
  const c = { symbol: "CCC", state: { status: "error", failure: { message: "nope" } } };
  for (const order of [[a, b, c], [c, a, b], [b, c, a]]) {
    const model = buildCompare(order, 3);
    assert.deepEqual(model.columns.map((x) => x.symbol), order.map((x) => x.symbol));
    for (const section of model.sections) {
      for (const row of section.rows) assert.equal(row.cells.length, order.length);
    }
  }
});
t("each cell carries its own company's server tone, and nothing across columns", () => {
  const model = buildCompare([
    { symbol: "AAA", state: PAYLOAD("AAA", "UNDERVALUED", "good") },
    { symbol: "BBB", state: PAYLOAD("BBB", "OVERVALUED", "bad") },
  ], 3);
  const implied = model.sections.find((s) => s.key === "value").rows.find((r) => r.key === "impliedGrowth");
  assert.deepEqual(implied.cells.map((c) => c.tone), ["good", "bad"]);
});
t("no aggregate, winner or agreement count appears anywhere in the model", () => {
  const model = buildCompare([
    { symbol: "AAA", state: PAYLOAD("AAA", "UNDERVALUED", "good") },
    { symbol: "BBB.JK", state: PAYLOAD("BBB.JK", "OVERVALUED", "bad") },
  ], 3);
  const keys = new Set();
  const walk = (o) => { if (o && typeof o === "object") for (const [k, v] of Object.entries(o)) { keys.add(k); walk(v); } };
  walk(model);
  for (const banned of ["score", "total", "rank", "composite", "winner", "best", "overall", "count", "tally"]) {
    assert.ok(!keys.has(banned), `compare model carries "${banned}"`);
  }
  const text = JSON.stringify(model);
  assert.ok(!/independent reading/i.test(text), "the rail's agreement count must not repeat per column");
  assert.match(model.currencyNote, /not converted/);
});
t("fired conditions are listed, never counted", () => {
  const model = buildCompare([{ symbol: "AAA", state: PAYLOAD("AAA", "UNDERVALUED", "good") }], 3);
  const fired = model.sections.find((s) => s.key === "pretrade").rows[0].cells[0];
  assert.deepEqual(fired.items, ["Balance sheet in the distress zone"]);
  assert.ok(!/\d/.test(fired.text), "no number in the fired cell");
});

// ---- the market board: order kept, marks only from measured facts ----
{
  const MB = require("./lib/marketboard.js");
  const row = (key, extra = {}) => ({
    key, name: key.toUpperCase(), short: key, symbol: key, group: "stocks", change: "pct",
    unit: "points", markets: ["US", "ID"], note: null, exposureKey: null, topic: "market",
    digits: 2, weekends: false, tone: "neutral", available: true, last: 100, move: 0.01,
    direction: "up", percentile: 50, unusual: false, ...extra,
  });
  // Planted in an order that is NOT the order of the moves, so a sort would show.
  const board = {
    groups: [{ key: "stocks", label: "Stocks" }],
    rows: [
      row("sp500", { move: 0.001 }),
      row("jkse", { markets: ["ID"], move: -0.05, unusual: true, direction: "down", topic: "market" }),
      row("t10y", { change: "bp", move: 11, unusual: true, topic: "rates", digits: 3, last: 4.929 }),
      row("oil", { exposureKey: "oil", move: 0.03, unusual: true, topic: "oil" }),
      row("gold", { exposureKey: "gold", markets: ["US", "ID"], topic: "gold" }),
      row("bitcoin", { markets: ["US"], topic: "bitcoin", digits: 0, last: 77480.25, weekends: true }),
    ],
    missing: [], unusualAt: 95, minHistory: 120, fetchedAt: null, source: "", delay: "",
    markets: {
      US: { strip: ["bitcoin", "sp500", "oil"], unusual: [], unavailable: [], baseRate: null },
      ID: { strip: ["gold", "jkse"], unusual: [], unavailable: [], baseRate: null },
    },
    explain: { rows: {}, markets: {} },
  };

  t("a market's rows keep the declared order, never the order of the moves", () => {
    assert.deepEqual(MB.rowsFor(board, "US").map((r) => r.key), ["sp500", "t10y", "oil", "gold", "bitcoin"]);
    assert.deepEqual(MB.rowsFor(board, "ID").map((r) => r.key), ["sp500", "jkse", "t10y", "oil", "gold"]);
  });
  t("the strip is the declared subset, in board order not strip-list order", () => {
    assert.deepEqual(MB.stripFor(board, "US").map((r) => r.key), ["sp500", "oil", "bitcoin"]);
  });
  t("marks come only from measured exposure, the stock's market and the Value tab's rate", () => {
    const marks = MB.marksFor(board, { symbol: "ITMG.JK", market: "ID",
                                       factors: [{ key: "oil", label: "the energy complex", weeks: 257 }] });
    assert.deepEqual(Object.keys(marks).sort(), ["jkse", "oil"]);
    assert.equal(marks.oil[0].text, "ITMG.JK has moved with the energy complex over the past 5 years");
    assert.ok(!marks.t10y, "an IDX valuation does not discount from the US 10-year");
    const us = MB.marksFor(board, { symbol: "AAPL", market: "US", factors: [] });
    assert.deepEqual(Object.keys(us).sort(), ["sp500", "t10y"]);
    assert.deepEqual(MB.marksFor(board, null), {});
    const pending = MB.marksFor(board, { symbol: "AAPL", market: "US", factors: null });
    assert.ok(!Object.values(pending).flat().some((m) => m.kind === "movesWith"),
              "nothing is marked as moving with anything before the Trend tab has measured it");
  });
  t("related rows lead by partition, each part still in declared order", () => {
    const marks = { gold: [{ kind: "movesWith", text: "" }], jkse: [{ kind: "itsMarket", text: "" }] };
    assert.deepEqual(MB.relatedFirst(MB.rowsFor(board, "ID"), marks).map((r) => r.key),
                     ["jkse", "gold", "sp500", "t10y", "oil"]);
  });
  t("headlines: the market's own feed, then each unusual mover's topic, at most four", () => {
    assert.deepEqual(MB.headlineTopics(board, "US"), ["market", "rates", "oil"]);
    assert.deepEqual(MB.headlineTopics(board, "US", 2), ["market", "rates"]);
  });
  t("levels, dates and ages read the way a board is read", () => {
    assert.equal(MB.levelText(board.rows[5]), "77,480");
    assert.equal(MB.levelText(board.rows[2]), "4.929");
    assert.equal(MB.levelText(row("x", { last: null })), "—");
    assert.equal(MB.dayText("2026-10-30"), "30 Oct", "an ISO date is not shifted by the reader's time zone");
    const now = Date.parse("2026-11-01T12:00:00Z");
    assert.equal(MB.agoText("Sun, 01 Nov 2026 11:15:00 GMT", now), "45 min ago");
    assert.equal(MB.agoText("Sat, 31 Oct 2026 09:00:00 GMT", now), "27 h ago");
    assert.equal(MB.agoText("not a date", now), null);
    assert.equal(MB.periodText(260), " over the past 5 years");
    assert.equal(MB.periodText(40), " over the past 40 weeks");
  });
  t("'largest since' is said only of an unusual move", () => {
    assert.equal(MB.sinceText(row("a", { unusual: true, direction: "down", largestSince: "2026-06-05" })),
                 "largest fall since 5 Jun 2026");
    assert.equal(MB.sinceText(row("a", { unusual: false, largestSince: "2026-06-05" })), null);
  });
}

// ---- the exchange clock and the calendar: computed in the browser, every minute ----
{
  const MC = require("./lib/marketclock.js");
  const CAL = require("./lib/calendar.js");
  const MB = require("./lib/marketboard.js");
  const nyse = {
    name: "NYSE", tz: "America/New_York", source: "",
    sessions: { "mon-thu": [["09:30", "16:00"]], fri: [["09:30", "16:00"]] },
    closures: [
      { date: "2026-11-26", kind: "holiday", time: null, detail: "Thanksgiving Day." },
      { date: "2026-11-27", kind: "early-close", time: "13:00", detail: "The day after Thanksgiving." },
    ],
  };
  const idx = {
    name: "IDX", tz: "Asia/Jakarta", source: "", closures: [],
    sessions: { "mon-thu": [["09:00", "12:00"], ["13:30", "16:00"]], fri: [["09:00", "11:30"], ["14:00", "16:00"]] },
  };
  const at = (iso) => new Date(iso);

  t("a US release moves an hour in UTC when the clocks change", () => {
    assert.equal(MC.zonedInstant("2026-03-06", "08:30", "America/New_York").toISOString(), "2026-03-06T13:30:00.000Z");
    assert.equal(MC.zonedInstant("2026-03-10", "08:30", "America/New_York").toISOString(), "2026-03-10T12:30:00.000Z");
  });
  t("NYSE is open mid-session and says when it closes", () => {
    const status = MC.exchangeStatus(nyse, at("2026-11-02T15:00:00Z"));       // Mon 10:00 ET
    assert.equal(status.state, "open");
    assert.equal(status.next.kind, "closes");
    assert.equal(status.next.at.toISOString(), "2026-11-02T21:00:00.000Z");
  });
  t("before the bell it is closed and opens at 09:30 New York", () => {
    const status = MC.exchangeStatus(nyse, at("2026-11-02T13:00:00Z"));       // Mon 08:00 ET
    assert.equal(status.state, "closed");
    assert.equal(status.next.at.toISOString(), "2026-11-02T14:30:00.000Z");
  });
  t("a holiday is closed, says why, and points at the next session", () => {
    const status = MC.exchangeStatus(nyse, at("2026-11-26T15:00:00Z"));       // Thanksgiving
    assert.equal(status.state, "closed");
    assert.equal(status.reason, "Thanksgiving Day.");
    assert.equal(status.next.at.toISOString(), "2026-11-27T14:30:00.000Z");
  });
  t("an early close shuts at 1 p.m., and the weekend is skipped", () => {
    assert.equal(MC.exchangeStatus(nyse, at("2026-11-27T17:30:00Z")).state, "open");   // 12:30 ET
    const late = MC.exchangeStatus(nyse, at("2026-11-27T18:30:00Z"));                  // 13:30 ET
    assert.equal(late.state, "closed");
    assert.equal(late.next.at.toISOString(), "2026-11-30T14:30:00.000Z", "Monday 09:30 ET");
  });
  t("IDX takes a longer Friday break and reopens at 14:00 Jakarta", () => {
    const status = MC.exchangeStatus(idx, at("2026-11-06T05:00:00Z"));        // Fri 12:00 WIB
    assert.equal(status.state, "break");
    assert.equal(status.next.kind, "reopens");
    assert.equal(status.next.at.toISOString(), "2026-11-06T07:00:00.000Z");
    assert.equal(MC.exchangeStatus(idx, at("2026-11-05T04:45:00Z")).state, "open", "Thursday 11:45 is still session one");
    assert.equal(MC.exchangeStatus(idx, at("2026-11-06T04:45:00Z")).state, "break", "Friday 11:45 is already the break");
  });

  const ev = (extra) => ({ kind: "cpi", date: "2026-11-10", time: "08:30", tz: "America/New_York", market: "US",
                           source: "bls", title: "US consumer prices (CPI)", detail: "October 2026.",
                           utc: "2026-11-10T13:30:00Z", allDay: false, label: "CPI", ...extra });
  t("a timed event falls on the reader's own day; an all-day date keeps its own", () => {
    const fomc = ev({ kind: "fomc", date: "2026-12-09", time: "14:00", utc: "2026-12-09T19:00:00Z" });
    assert.equal(CAL.dayOf(fomc, "Asia/Jakarta"), "2026-12-10", "02:00 the next morning in Jakarta");
    assert.equal(CAL.dayOf(fomc, "America/New_York"), "2026-12-09");
    assert.equal(CAL.dayOf(ev({ utc: null, allDay: true, time: null, date: "2026-11-18" }), "Asia/Jakarta"), "2026-11-18");
    assert.equal(CAL.timeText(ev({}), "Asia/Jakarta"), "20:30");
    assert.equal(CAL.dayHeading("2026-11-10"), "Tue 10 Nov");
  });
  t("upcoming drops what has happened and keeps time order", () => {
    const list = CAL.upcoming([
      ev({ date: "2026-12-10", utc: "2026-12-10T13:30:00Z" }),
      ev({ date: "2026-10-14", utc: "2026-10-14T12:30:00Z" }),
      ev({}),
    ], at("2026-11-01T00:00:00Z"), 60, "UTC");
    assert.deepEqual(list.map((e) => e.date), ["2026-11-10", "2026-12-10"]);
  });
  t("an .ics is valid iCalendar, timed in UTC or all-day, with text escaped", () => {
    const timed = CAL.toIcs(ev({ title: "US CPI, October" }), at("2026-11-01T00:00:00Z"));
    assert.ok(timed.includes("DTSTART:20261110T133000Z\r\n"));
    assert.ok(timed.includes("SUMMARY:US CPI\\, October\r\n"), "commas are escaped");
    assert.ok(timed.startsWith("BEGIN:VCALENDAR\r\n") && timed.endsWith("END:VCALENDAR\r\n"));
    const allDay = CAL.toIcs(ev({ kind: "bi-rate", date: "2026-11-18", utc: null, allDay: true, time: null }), at("2026-11-01T00:00:00Z"));
    assert.ok(allDay.includes("DTSTART;VALUE=DATE:20261118") && allDay.includes("DTEND;VALUE=DATE:20261119"));
  });
  t("report dates become events once per ticker, on the ticker's own market", () => {
    const out = CAL.earningsEvents({ symbol: "ITMG.JK", date: "2026-11-20" },
      [{ ticker: "ITMG.JK", next: "2026-11-21" }, { ticker: "AAPL", next: "2027-01-28" }, { ticker: "MSFT", next: null }]);
    assert.deepEqual(out.map((e) => [e.ticker, e.date, e.market, e.origin]),
      [["ITMG.JK", "2026-11-20", "ID", "stock"], ["AAPL", "2027-01-28", "US", "watchlist"]]);
  });
  t("the panel's history line is history, and says when it is within chance", () => {
    assert.equal(MB.historyShort({ name: "S&P 500", available: true, events: 17, above: 7, p: 0.63 }),
      "S&P 500: bigger than a median day on 7 of the last 17 (half expected), within chance");
    assert.equal(MB.historyShort({ name: "S&P 500", available: false }), null);
    assert.equal(MB.relationLabel({ kind: "itsMarket", text: "" }), "its market");
  });
}

Promise.all(pending).then(() => {
  console.log(`  ${n} frontend assertions passed`);
});
