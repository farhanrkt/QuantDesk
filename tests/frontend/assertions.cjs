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

console.log(`  ${n} frontend assertions passed`);
