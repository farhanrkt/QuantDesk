// Which elements move as a page loads, and by how much: every layout-shift
// entry the browser records, with the nodes it names. A layout-shift score
// says that a page jumps; this says what jumped. Same setup as walk.mjs.
// usage: node scripts/audit/shifts.mjs "/stock/AAPL" 375
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const [target = "/", width = "375"] = process.argv.slice(2);
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: Number(width), height: 812 } });
await context.route("**/api/**", async (route) => {
  const url = new URL(route.request().url());
  if (url.pathname === "/api/capabilities") return route.fulfill({ json: { privateTier: false } });
  try { return route.fulfill({ response: await route.fetch({ url: "http://127.0.0.1:8000" + url.pathname + url.search }) }); }
  catch { return route.abort(); }
});
const page = await context.newPage();
await page.addInitScript(() => {
  window.__shifts = [];
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (e.hadRecentInput) continue;
      window.__shifts.push({
        t: Math.round(e.startTime), value: +e.value.toFixed(4),
        sources: (e.sources || []).map((s) => {
          const n = s.node;
          const label = !n ? "(gone)" : n.nodeType === 1
            ? `${n.tagName.toLowerCase()}${n.getAttribute("aria-label") ? `[${n.getAttribute("aria-label")}]` : ""}.${String(n.className?.baseVal ?? n.className ?? "").slice(0, 60)} «${(n.innerText || "").replace(/\s+/g, " ").slice(0, 50)}» in ${n.parentElement?.tagName.toLowerCase()}.${String(n.parentElement?.className ?? "").slice(0, 50)}`
            : `#text "${(n.textContent || "").slice(0, 30)}"`;
          return `${label} y${Math.round(s.previousRect.y)}→${Math.round(s.currentRect.y)} h${Math.round(s.previousRect.height)}→${Math.round(s.currentRect.height)}`;
        }).slice(0, 3),
      });
    }
  }).observe({ type: "layout-shift", buffered: true });
});
await page.goto("http://127.0.0.1:3001" + target, { waitUntil: "domcontentloaded" });
await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
await page.waitForTimeout(1500);
const shifts = await page.evaluate(() => window.__shifts);
const total = shifts.reduce((a, s) => a + s.value, 0);
console.log(`${target} at ${width}px: ${shifts.length} shifts, sum ${total.toFixed(3)}`);
for (const s of shifts.sort((a, b) => b.value - a.value).slice(0, 8)) {
  console.log(`  ${s.value.toFixed(3)} at ${s.t}ms`);
  for (const src of s.sources) console.log(`      ${src}`);
}
await browser.close();
