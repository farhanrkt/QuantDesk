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

console.log(`  ${n} frontend assertions passed`);
