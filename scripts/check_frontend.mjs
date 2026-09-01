#!/usr/bin/env node
/**
 * check_frontend.mjs
 * ==================
 * Run the browser-side logic tests in `tests/frontend/`.
 *
 * WHY THIS EXISTS RATHER THAN A TEST FRAMEWORK
 * --------------------------------------------
 * The Python suite covers every calculation on the server, and it cannot reach
 * the handful of pure functions that only ever run in a browser. The most
 * important of them is `agreementOf`, which decides the confluence rail's
 * headline claim — how many INDEPENDENT readings agree rather than how many
 * panels are on screen. That is real decision logic, and it shipped untested.
 *
 * Adding vitest or jest would mean a test framework, a config, and a transform
 * pipeline for one file's worth of assertions. Instead this compiles the modules
 * with the TypeScript compiler that already guards the build, and runs plain
 * `node:assert` against the output. No new dependency, and the compile step
 * doubles as a second type-check of exactly the code under test.
 *
 * WHAT IT HAS TO DO BY HAND
 * -------------------------
 * `tsc` emits the `@/...` path alias unchanged — it type-checks aliases but does
 * not rewrite them — so the output would not resolve on node. The temp tree
 * therefore gets a `node_modules/@` symlink pointing back at itself, plus links
 * to the few real packages the compiled components import. Both are confined to
 * a temp directory that is removed on exit.
 *
 * USAGE
 *   node scripts/check_frontend.mjs
 */

import { spawnSync } from "node:child_process";
import {
  mkdtempSync, readdirSync, readFileSync, rmSync, symlinkSync, writeFileSync, cpSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

// Modules under test, plus everything they import from the project. Adding a
// file here is what makes its exports reachable from the assertions.
const SOURCES = [
  "components/ConfluenceRail.tsx",
  "lib/utils.ts",
  "lib/csv.ts",
  // The thesis journal never reaches the API by design, so its logic cannot
  // live in Python with the rest of this project's judgement. This is the
  // escape hatch that already exists for exactly that case.
  "lib/journal.ts",
];

// Real packages the compiled output requires at load time.
const PACKAGES = ["react", "react-dom", "lucide-react", "clsx", "tailwind-merge"];

// --------------------------------------------------------------------------- //
// A source-level invariant the compiled assertions cannot express
// --------------------------------------------------------------------------- //
// THE THESIS JOURNAL MUST NEVER REACH THE API. It is the one thing this app
// holds that is about the reader rather than about a company, and the whole
// design rests on it staying in the browser. That is a property of what the
// request layer does NOT contain, so no unit test on a compiled module can see
// it — but a grep can, and the failure it guards against is somebody adding a
// convenient "sync your journal" call years from now without noticing what it
// costs.
const FORBIDDEN_IN_REQUESTS = /\b(journal|thesis|falsifier|growthBelief)\b/i;
const requestLayer = readFileSync(join(ROOT, "lib/api.ts"), "utf8")
  // "synthesis" contains "thesis". Strip the word before looking.
  .replace(/synthesis/gi, "");
if (FORBIDDEN_IN_REQUESTS.test(requestLayer)) {
  console.error("lib/api.ts mentions the thesis journal. Nothing about a reader's own "
                + "thesis may cross the wire — see components/ThesisPanel.tsx.");
  process.exit(1);
}

// THE CONFLUENCE RAIL KEEPS ITS OWN COPY OF WHICH LENS READS WHICH DATA, and
// `explain.py` says so in a comment: the rail must render while legs are still
// loading, so it cannot wait for the server's answer. Two copies of one rule is
// the arrangement this codebase distrusts most, and the whole claim the app
// makes — that five lenses are three independent sources — rests on them
// agreeing. Compared here rather than assumed.
const railSource = readFileSync(join(ROOT, "components/ConfluenceRail.tsx"), "utf8");
const pySource = readFileSync(join(ROOT, "api/_lib/explain.py"), "utf8");
const LENS_KEYS = "flow|trend|value|quality|expectations";
const FAMILY_KEYS = "price|filings|estimates";
const pyFamilies = Object.fromEntries(
  [...pySource.matchAll(new RegExp(`"(${LENS_KEYS})":\\s*"(${FAMILY_KEYS})"`, "g"))]
    .map((m) => [m[1], m[2]]));
const railFamilies = {};
for (const block of railSource.split(/\n(?=function |const )/)) {
  const lens = block.match(/lens:\s*"(\w+)"/);
  const family = block.match(new RegExp(`family:\\s*"(${FAMILY_KEYS})"`));
  if (lens && family) railFamilies[lens[1].toLowerCase()] = family[1];
}
for (const [lens, family] of Object.entries(pyFamilies)) {
  if (railFamilies[lens] && railFamilies[lens] !== family) {
    console.error(`ConfluenceRail puts ${lens} in "${railFamilies[lens]}" while `
                  + `explain.py puts it in "${family}". The rail's independence `
                  + `count and the synthesis would disagree about the same ticker.`);
    process.exit(1);
  }
}
// THE COUNT IS ASSERTED AGAINST PYTHON, NOT AGAINST A LITERAL. This was `< 4`,
// and a hardcoded count is exactly the check that goes stale the moment a lens
// is added: a fifth lens with no rail entry would have left this passing on the
// original four while the drift check silently stopped covering the new one.
// The rail must now account for every lens `explain.py` classifies.
const pyLensCount = Object.keys(pyFamilies).length;
if (pyLensCount < 5) {
  console.error(`Only found ${pyLensCount} lens families in explain.py; the drift `
                + "check between it and ConfluenceRail.tsx is not running.");
  process.exit(1);
}
for (const lens of Object.keys(pyFamilies)) {
  if (!railFamilies[lens]) {
    console.error(`explain.py classifies "${lens}" but ConfluenceRail.tsx has no `
                  + "reading for it. The rail's independence count would be taken "
                  + "over fewer families than the synthesis uses.");
    process.exit(1);
  }
}

// --------------------------------------------------------------------------- //
// The v2 design rules, encoded so they cannot come back
// --------------------------------------------------------------------------- //
// EVERY RULE BELOW DESCRIBES A BUG THAT WAS ACTUALLY IN THIS CODEBASE, found by
// measuring the rendered page rather than by reading the source. A design system
// that lives only in DESIGN.md is a document; one the build enforces is a
// system. This file already encodes two invariants for the same reason.
//
// Each check is a grep over source, so each is deliberately narrow: a rule that
// fires on something legitimate would be turned off within a week, and a rule
// nobody trusts protects nothing.
//
// COMMENTS ARE STRIPPED FIRST, and that is not an optimisation. This file's own
// docstrings quote the patterns being banned — `LongTermPanel` explains the
// sign-colouring rule by showing the expression it forbids — so a naive grep
// fails the build on the comment that documents the rule. Caught by rule 7
// firing on its own explanation the first time it ran.
const stripComments = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const uiFiles = [];
for (const dir of ["components", "components/ui", "app"]) {
  for (const name of readdirSync(join(ROOT, dir))) {
    if (!/\.(tsx|css)$/.test(name)) continue;
    uiFiles.push([join(dir, name), stripComments(readFileSync(join(ROOT, dir, name), "utf8"))]);
  }
}

const designFailures = [];
const fail = (file, rule, detail) => designFailures.push(`  ${file}\n    ${rule}\n    ${detail}`);

// 1. A HEADING IS NEVER AN EYEBROW. `.eyebrow` is an 11px uppercase field label.
//    v1 rendered its two most important section headings through it, which put
//    them BELOW the body text they introduced — the inverted hierarchy the whole
//    redesign existed to fix.
for (const [file, src] of uiFiles) {
  for (const m of src.matchAll(/<h[1-6][^>]*className="[^"]*\beyebrow\b/g)) {
    fail(file, "A heading is wearing `.eyebrow`.",
         "`.eyebrow` is a field label at 11px. Use the h2/h3 sizes from globals.css.");
  }
}

// 2. PROSE IS NEVER SET AT THE CAPTION SIZE. `leading-relaxed` is what you set
//    on a paragraph; `text-micro` is 11px, for units and footnotes. Together
//    they mean a paragraph rendered as furniture — which is how a 96-word
//    caveat ended up as the smallest text on its own panel.
for (const [file, src] of uiFiles) {
  if (/text-micro\s+leading-relaxed|leading-relaxed\s+text-micro\b/.test(src)) {
    fail(file, "Prose set at `text-micro` (11px).",
         "`leading-relaxed` marks a paragraph. Use `text-meta` or larger.");
  }
}

// 3. FONT SIZES COME FROM THE SCALE. v1 rendered sixteen distinct sizes, 272 of
//    402 nodes inside a 3px band, so no amount of colour could build a hierarchy
//    on top of them. The allowlist is the two places an arbitrary value is
//    correct and documented.
const SIZE_ALLOWED = new Set([
  "text-[1rem]",        // inputs below `sm`: iOS zooms a focused field under 16px
  "text-[0.6875rem]",   // the `.eyebrow` definition itself, in globals.css
]);
for (const [file, src] of uiFiles) {
  for (const m of src.matchAll(/text-\[[0-9.]+rem\]/g)) {
    if (!SIZE_ALLOWED.has(m[0])) {
      fail(file, `Arbitrary font size ${m[0]}.`,
           "Use a step from the scale in tailwind.config.ts (micro/meta/base/lead/h3/h2/figure/h1).");
    }
  }
}

// 4. TEXT COLOUR COMES FROM THE LADDER, NOT FROM ALPHA. `text-chalk/80` and
//    friends were how v1 faked a body colour it did not have; eight of them
//    composited to 2.2-3.2:1 and failed contrast outright.
for (const [file, src] of uiFiles) {
  for (const m of src.matchAll(/text-(?:chalk|ash)\/\d+/g)) {
    fail(file, `Alpha text colour ${m[0]}.`,
         "Use chalk / body / ash / faint. Alpha on text was the contrast bug.");
  }
}

// 5. A DECLARED ARIA PATTERN KEEPS ITS KEYBOARD CONTRACT. `role="tablist"` and
//    `role="radiogroup"` both promise arrow keys and a single tab stop. v1
//    declared four of them and implemented none — a screen reader announcing
//    "tab, 2 of 7" where arrow keys do nothing is worse than a plain button,
//    because the announcement teaches an interaction that is not there.
for (const [file, src] of uiFiles) {
  if (!/role="(tablist|radiogroup)"/.test(src)) continue;
  if (!/onKeyDown/.test(src)) {
    fail(file, "Declares `tablist`/`radiogroup` with no `onKeyDown`.",
         "Those roles promise arrow-key navigation. Implement it or use plain buttons.");
  }
  if (!/tabIndex/.test(src)) {
    fail(file, "Declares `tablist`/`radiogroup` with no roving `tabIndex`.",
         "The group is one tab stop, not one per option.");
  }
}

// 6. NO COLOURED SIDE STRIPE. A 2px accent border down one edge of a card is the
//    most recognisable tell of a generated interface, and on a rounded corner it
//    reads as trim rather than as status. A dot says the same thing.
for (const [file, src] of uiFiles) {
  if (/border-[lr]-(?:2|4|8)\b/.test(src)) {
    fail(file, "Coloured side stripe (`border-l-2` or similar).",
         "Use a status dot; the tone still comes from `explain.tone`.");
  }
}

// 7. SIGN-BASED TONE IS A FIXED BUDGET, NOT A HABIT. Colour is decided once, in
//    Python, from `explain.tone`. Six sites legitimately colour from a number's
//    sign because the server has no interpretation to offer there — a day's
//    price change, the seasonality grid — and RESEARCH_ROADMAP §14 documents
//    them. This does not ban the pattern; it stops the list growing quietly.
const SIGN_TONE_BUDGET = {
  "components/AnomalyPanel.tsx": 2,     // a day's price change, twice
  // Two, and the second was invisible to the old pattern for the same reason
  // LongTermPanel's were: it colours a Card accent from a constant pair rather
  // than a Tailwind class. Both are gated on significance BEFORE they take a
  // direction — see `carTone` — so an insignificant result stays grey however
  // it is signed, which is the whole reason these two are allowed.
  "components/EventStudyPanel.tsx": 2,
  // Three, not one, and the number changed because the CHECK changed rather
  // than the code. The seasonality grid colours twice — an inline background
  // and the figure under it — and the calendar-returns bars colour a third
  // time, but only the Tailwind one was visible to the old pattern. The budget
  // read 1 while three sites existed, which is precisely the quiet growth this
  // rule is here to stop. All three are the exceptions RESEARCH_ROADMAP §14
  // documents: Python has no interpretation to offer for whether a month's
  // average return being positive is good news.
  "components/LongTermPanel.tsx": 3,
  "components/TechnicalPanel.tsx": 2,   // the day's change, and change-since
};
//    WIDENED 1 SEP 2026. The rule only ever matched Tailwind class ternaries,
//    so `style={{ background: value < 0 ? DOWN : UP }}` walked straight past it.
//    That was theoretical until the exposure work added two components that draw
//    geometry from a beta and colour it from a constant — the next person to
//    touch either will reach for an inline style, and the check has to be there
//    when they do. Both forms count against the same budget.
const SIGN_TONE_PATTERNS = [
  /[<>]=?\s*0\s*\?\s*"text-(?:acc|dist)"/g,
  /[<>]=?\s*0\s*\?\s*[A-Z_]{2,}\s*:\s*[A-Z_]{2,}/g,
];
for (const [file, src] of uiFiles) {
  const hits = SIGN_TONE_PATTERNS
    .reduce((n, pattern) => n + [...src.matchAll(pattern)].length, 0);
  const allowed = SIGN_TONE_BUDGET[file] ?? 0;
  if (hits > allowed) {
    fail(file, `Colours from a number's sign ${hits} times, budget ${allowed}.`,
         "Direction is decided in api/_lib/explain.py. Read `explain.tone`, or add the "
         + "site to SIGN_TONE_BUDGET with the reason Python cannot judge it.");
  }
}

// 8. THE TEXT PALETTE CLEARS WCAG AA ON EVERY GROUND.
//
//    DESIGN.md asserted "Base palette clears AA" and quoted two ratios. Both
//    quoted numbers were wrong (understated), and the token it did NOT quote —
//    `faint` — cleared only 3.48 to 4.11 while being used for every `.eyebrow`
//    field label and the footer disclaimer. Twenty-one sites of real text below
//    the 4.5 threshold, asserted as compliant in the design doc and checked by
//    nothing.
//
//    Contrast is arithmetic on the config, so it does not need a browser. This
//    reads the palette out of tailwind.config.ts and recomputes it, which means
//    the claim can never drift from the tokens again.
const CONFIG = readFileSync(join(ROOT, "tailwind.config.ts"), "utf8");
const hexOf = (name) => {
  const m = CONFIG.match(new RegExp(`\\b${name}:\\s*"(#[0-9A-Fa-f]{6})"`));
  return m ? m[1] : null;
};
const srgb = (v) => (v / 255 <= 0.03928 ? v / 255 / 12.92
                                        : Math.pow((v / 255 + 0.055) / 1.055, 2.4));
const luminance = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return 0.2126 * srgb((n >> 16) & 255) + 0.7152 * srgb((n >> 8) & 255)
       + 0.0722 * srgb(n & 255);
};
const contrast = (a, b) => {
  const [x, y] = [luminance(a), luminance(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
};
const TEXT_TOKENS = ["chalk", "body", "ash", "faint"];
const GROUNDS = ["ink", "panel", "raised", "sunken"];
const AA = 4.5;
for (const token of TEXT_TOKENS) {
  const fg = hexOf(token);
  if (!fg) { fail("tailwind.config.ts", `Text token \`${token}\` not found.`,
                  "The palette check reads it out of the config by name."); continue; }
  for (const ground of GROUNDS) {
    const bg = hexOf(ground);
    if (!bg) continue;
    const ratio = contrast(fg, bg);
    if (ratio < AA) {
      fail("tailwind.config.ts",
           `${token} on ${ground} is ${ratio.toFixed(2)}:1, below WCAG AA ${AA}.`,
           "Every token in the text ladder is used for text somewhere. Lighten it, "
           + "or stop using it for text and remove it from TEXT_TOKENS with the reason.");
    }
  }
}

if (designFailures.length) {
  console.error("\nDesign-system rules broken (see DESIGN.md):\n");
  console.error(designFailures.join("\n\n"));
  console.error("\nEach of these was a real bug found by measuring the rendered page.");
  process.exit(1);
}
console.log(`  design rules: 8 checked across ${uiFiles.length} UI files`);

const work = mkdtempSync(join(tmpdir(), "quantdesk-frontend-"));
process.on("exit", () => rmSync(work, { recursive: true, force: true }));

const config = join(work, "tsconfig.json");
writeFileSync(config, JSON.stringify({
  compilerOptions: {
    target: "ES2020", module: "CommonJS", moduleResolution: "node",
    jsx: "react-jsx", esModuleInterop: true, skipLibCheck: true,
    outDir: work, baseUrl: ROOT, paths: { "@/*": ["./*"] },
  },
  include: SOURCES.map((f) => join(ROOT, f)),
}, null, 2));

const compiled = spawnSync("npx", ["tsc", "-p", config], { encoding: "utf8" });
if (compiled.status !== 0) {
  console.error("TypeScript failed to compile the modules under test:\n");
  console.error(compiled.stdout || compiled.stderr);
  process.exit(1);
}

// CommonJS: the compiled components import through `@/...`, which tsc emits
// verbatim and which resolves only via the node_modules/@ link below.
writeFileSync(join(work, "package.json"), JSON.stringify({ type: "commonjs" }));
const modules = join(work, "node_modules");
spawnSync("mkdir", ["-p", modules]);
for (const pkg of PACKAGES) {
  try { symlinkSync(join(ROOT, "node_modules", pkg), join(modules, pkg)); } catch { /* already linked */ }
}
try { symlinkSync(work, join(modules, "@")); } catch { /* already linked */ }

cpSync(join(ROOT, "tests/frontend/assertions.cjs"), join(work, "assertions.cjs"));

const result = spawnSync(process.execPath, [join(work, "assertions.cjs")],
                         { encoding: "utf8", stdio: "inherit" });
if (result.status !== 0) {
  console.error("\nFrontend checks FAILED.");
  process.exit(result.status ?? 1);
}
