// Walk a page by keyboard (every Tab stop: named? visible focus? at least 24px?)
// and then try to find companies by their everyday names in the command palette.
// Same setup as walk.mjs. usage: node scripts/audit/keys.mjs / 1440
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const [target = "/", width = "1440"] = process.argv.slice(2);
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: Number(width), height: 900 }, reducedMotion: "reduce" });
await context.route("**/api/**", async (route) => {
  const url = new URL(route.request().url());
  if (url.pathname === "/api/capabilities") return route.fulfill({ json: { privateTier: false } });
  try { return route.fulfill({ response: await route.fetch({ url: "http://127.0.0.1:8000" + url.pathname + url.search }) }); }
  catch { return route.abort(); }
});
const page = await context.newPage();
await page.goto("http://127.0.0.1:3001" + target, { waitUntil: "domcontentloaded" });
await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
await page.waitForTimeout(800);
const seen = []; let unnamed = 0, noFocusStyle = 0, small = 0;
for (let i = 0; i < 140; i++) {
  await page.keyboard.press("Tab");
  const info = await page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const name = el.getAttribute("aria-label") || el.innerText?.trim() || el.getAttribute("title") || el.getAttribute("placeholder") || (el.labels?.[0]?.innerText ?? "");
    const ring = cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0 || cs.boxShadow !== "none";
    return { tag: el.tagName.toLowerCase(), role: el.getAttribute("role"), name: name.slice(0, 40).replace(/\n/g, " "), ring, w: Math.round(r.width), h: Math.round(r.height), key: el.outerHTML.slice(0, 80) };
  });
  if (!info) continue;
  if (seen.length && seen[0].key === info.key && i > 3) break;
  seen.push(info);
  if (!info.name) unnamed++;
  if (!info.ring) noFocusStyle++;
  if (info.w < 24 || info.h < 24) small++;
}
console.log(JSON.stringify({ target, width, focusables: seen.length, unnamed, noFocusStyle, small,
  problems: seen.filter((s) => !s.name || !s.ring || s.w < 24 || s.h < 24).slice(0, 8) }, null, 1));
// Palette: find a company by its everyday name.
for (const q of ["telkom", "bca", "bank central asia", "apple", "astra"]) {
  await page.keyboard.press("Control+k");
  await page.waitForTimeout(300);
  await page.keyboard.type(q, { delay: 20 });
  await page.waitForTimeout(900);
  const options = await page.$$eval('[role="option"]', (els) => els.slice(0, 4).map((e) => e.innerText.replace(/\n/g, " ").slice(0, 60)));
  console.log(`palette "${q}":`, JSON.stringify(options));
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);
}
await browser.close();
