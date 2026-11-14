// Walk the locally running PRODUCTION build and record what a reader sees.
//
// Part of the November 2026 audit (docs/AUDIT.md) and of every UI change since:
// a green check battery does not mean the page renders (NEXT_SESSION_PROMPT),
// so the page is opened. For each width, language and page this saves a
// screenshot, the visible text, and one summary line: height, word count,
// whether the page scrolls sideways, the <html lang>, console errors, failed
// requests and, with --axe, every WCAG A/AA violation axe-core finds.
//
// It needs Playwright with Chromium, which is NOT a dependency of this project
// (it is 300 MB and CI does not open a browser): install it globally, or run
// this where it already is. Start the two halves first:
//
//   npm run build && npx next start -p 3001
//   .venv/bin/python -m uvicorn index:app --app-dir api --port 8000
//
// `next start` has no /api proxy (that rewrite is development-only), so this
// routes the page's /api calls to uvicorn itself.
//
// usage: node scripts/audit/walk.mjs <outDir> <label> [--widths 375,768,1440]
//        [--langs en,id] [--pages "/,/stock/AAPL?tab=value"] [--axe] [--fold]
//        [--scale 1] [--private 0|1] [--web URL] [--api URL]
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
import fs from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const outDir = args[0];
const label = args[1];
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i === -1 ? fallback : args[i + 1];
};
const widths = opt("widths", "375,768,1440").split(",").map(Number);
const langs = opt("langs", "en,id").split(",");
const pages = opt("pages", "/").split(",");
const runAxe = args.includes("--axe");
const scale = Number(opt("scale", "1"));
const privateTier = opt("private", "0") === "1";
const WEB = opt("web", "http://127.0.0.1:3001");
const API = opt("api", "http://127.0.0.1:8000");
const axeSource = runAxe
  ? fs.readFileSync(new URL("../../node_modules/axe-core/axe.min.js", import.meta.url), "utf8") : null;

fs.mkdirSync(outDir, { recursive: true });
const slug = (p) => p.replace(/^\//, "").replace(/[^A-Za-z0-9.]+/g, "-").replace(/-$/, "") || "home";

const browser = await chromium.launch();
const results = [];
for (const width of widths) {
  for (const lang of langs) {
    const context = await browser.newContext({
      viewport: { width, height: width < 500 ? 812 : 900 },
      deviceScaleFactor: scale,
      locale: lang === "id" ? "id-ID" : "en-US",
      bypassCSP: runAxe,
    });
    await context.addInitScript((l) => {
      try { window.localStorage.setItem("quantdesk.language", l); } catch {}
    }, lang);
    // The production build has no /api proxy; send API calls to uvicorn.
    await context.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      if (!privateTier && url.pathname === "/api/capabilities") {
        return route.fulfill({ json: { privateTier: false } });
      }
      const headers = { ...route.request().headers() };
      try {
        const response = await route.fetch({ url: API + url.pathname + url.search, headers });
        return route.fulfill({ response });
      } catch (err) {
        return route.abort();
      }
    });
    for (const target of pages) {
      const page = await context.newPage();
      const consoleErrors = [];
      const failedRequests = [];
      page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 300)); });
      page.on("pageerror", (e) => consoleErrors.push("pageerror: " + String(e).slice(0, 300)));
      page.on("response", (r) => {
        if (r.status() >= 400) failedRequests.push(`${r.status()} ${new URL(r.url()).pathname}`);
      });
      const started = Date.now();
      let navError = null;
      try {
        await page.goto(WEB + target, { waitUntil: "domcontentloaded", timeout: 60000 });
        // Lenses arrive by fetch; wait for the network to settle, bounded.
        await page.waitForLoadState("networkidle", { timeout: 75000 }).catch(() => {});
        await page.waitForTimeout(1200);
      } catch (err) { navError = String(err).slice(0, 200); }
      const metrics = await page.evaluate(() => {
        const doc = document.documentElement;
        const text = document.body.innerText || "";
        const offenders = [];
        if (doc.scrollWidth > window.innerWidth + 1) {
          for (const el of document.querySelectorAll("body *")) {
            const r = el.getBoundingClientRect();
            if (r.right > window.innerWidth + 1 && r.width > 0 && offenders.length < 5) {
              offenders.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 60)} right=${Math.round(r.right)}`);
            }
          }
        }
        return {
          title: document.title,
          htmlLang: doc.lang,
          scrollWidth: doc.scrollWidth,
          innerWidth: window.innerWidth,
          height: doc.scrollHeight,
          h1: [...document.querySelectorAll("h1")].map((h) => h.innerText.trim()).slice(0, 3),
          words: text.split(/\s+/).filter(Boolean).length,
          offenders,
          loadingLeft: document.querySelectorAll('[aria-busy="true"]').length,
        };
      }).catch((e) => ({ evalError: String(e).slice(0, 200) }));
      let axe = null;
      if (runAxe && !navError) {
        await page.addScriptTag({ content: axeSource });
        axe = await page.evaluate(async () => {
          const r = await window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] });
          return r.violations.map((v) => ({
            id: v.id, impact: v.impact, nodes: v.nodes.length,
            sample: v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ").slice(0, 200),
          }));
        }).catch((e) => [{ id: "axe-failed", impact: String(e).slice(0, 120), nodes: 0 }]);
      }
      const file = path.join(outDir, `${label}-${slug(target)}-${width}-${lang}.png`);
      // A full-page capture drops sticky and fixed chrome (the top bar, the markets
      // panel). Growing the viewport to the document instead keeps them in place.
      if (args.includes("--fold")) {
        await page.screenshot({ path: file }).catch(() => {});
      } else {
        const full = Math.min(metrics.height || 900, 15000);
        await page.setViewportSize({ width, height: full });
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.waitForTimeout(400);
        await page.screenshot({ path: file }).catch(() => {});
      }
      const textFile = path.join(outDir, `${label}-${slug(target)}-${width}-${lang}.txt`);
      fs.writeFileSync(textFile, await page.evaluate(() => document.body.innerText).catch(() => ""));
      results.push({
        target, width, lang, ms: Date.now() - started, navError, ...metrics,
        overflow: metrics.scrollWidth > metrics.innerWidth + 1,
        consoleErrors: [...new Set(consoleErrors)].slice(0, 6),
        failedRequests: [...new Set(failedRequests)].slice(0, 8), axe, file,
      });
      await page.close();
    }
    await context.close();
  }
}
await browser.close();
fs.writeFileSync(path.join(outDir, `${label}-summary.json`), JSON.stringify(results, null, 2));
for (const r of results) {
  console.log(`${r.target} ${r.width} ${r.lang} ${r.ms}ms h=${r.height} words=${r.words} overflow=${r.overflow}`
    + ` lang=${r.htmlLang} h1=${JSON.stringify(r.h1)} errs=${r.consoleErrors.length}`
    + ` failed=${JSON.stringify(r.failedRequests)}`
    + (r.axe ? ` axe=${JSON.stringify(r.axe.map((v) => `${v.id}:${v.nodes}`))}` : "")
    + (r.offenders?.length ? ` offenders=${JSON.stringify(r.offenders)}` : "")
    + (r.consoleErrors.length ? `\n   ${r.consoleErrors.join("\n   ")}` : ""));
}
