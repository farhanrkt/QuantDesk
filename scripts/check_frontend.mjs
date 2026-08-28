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
import { mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync, cpSync } from "node:fs";
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
