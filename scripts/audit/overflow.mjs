// Find the element that makes a page scroll sideways: hide one node at a time
// and descend into whichever one restores the width. Reading getBoundingClientRect
// is not enough, because the culprit is often a grid item wider than its track.
// Same setup as walk.mjs. usage: node scripts/audit/overflow.mjs "/stock/AAPL?tab=flow" 375 en
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const [target, width = "375", lang = "en"] = process.argv.slice(2);
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: Number(width), height: 812 } });
await context.addInitScript((l) => { try { localStorage.setItem("quantdesk.language", l); } catch {} }, lang);
await context.route("**/api/**", async (route) => {
  const url = new URL(route.request().url());
  if (url.pathname === "/api/capabilities") return route.fulfill({ json: { privateTier: false } });
  try { return route.fulfill({ response: await route.fetch({ url: "http://127.0.0.1:8000" + url.pathname + url.search }) }); }
  catch { return route.abort(); }
});
const page = await context.newPage();
await page.goto("http://127.0.0.1:3001" + target, { waitUntil: "domcontentloaded" });
await page.waitForLoadState("networkidle", { timeout: 75000 }).catch(() => {});
await page.waitForTimeout(1500);
const out = await page.evaluate(() => {
  const doc = document.documentElement;
  const base = doc.scrollWidth;
  const vw = window.innerWidth;
  if (base <= vw) return { base, vw, note: "no overflow" };
  // Descend: at each level find the child whose removal restores the width.
  let node = document.body, trail = [];
  for (let depth = 0; depth < 40; depth++) {
    let culprit = null;
    for (const child of node.children) {
      const prev = child.style.display;
      child.style.display = "none";
      const w = doc.scrollWidth;
      child.style.display = prev;
      if (w <= vw) { culprit = child; break; }
    }
    if (!culprit) break;
    const r = culprit.getBoundingClientRect();
    trail.push(`${culprit.tagName.toLowerCase()}.${String(culprit.className.baseVal ?? culprit.className).slice(0, 110)} [${Math.round(r.left)}..${Math.round(r.right)}] pos=${getComputedStyle(culprit).position} text=${(culprit.innerText || "").slice(0, 40).replace(/\n/g, " ")}`);
    node = culprit;
  }
  return { base, vw, trail };
});
console.log(JSON.stringify(out, null, 1));
await browser.close();
