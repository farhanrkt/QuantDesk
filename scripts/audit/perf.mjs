// What a mid-range phone on a slow connection pays to open a page of the local
// production build: first paint, layout shift, blocking time, bytes by type.
// Same setup as walk.mjs. usage: node scripts/audit/perf.mjs / /stock/AAPL /markets
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const targets = process.argv.slice(2);
const browser = await chromium.launch();
for (const target of targets) {
  const context = await browser.newContext({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 2 });
  await context.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/capabilities") return route.fulfill({ json: { privateTier: false } });
    try { return route.fulfill({ response: await route.fetch({ url: "http://127.0.0.1:8000" + url.pathname + url.search }) }); }
    catch { return route.abort(); }
  });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  // Roughly a mid 4G phone: 9 Mbit down, 170 ms round trip. /api goes through route(), unthrottled.
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 170, downloadThroughput: 9e6 / 8, uploadThroughput: 3e6 / 8 });
  const bytes = { script: 0, stylesheet: 0, font: 0, document: 0, image: 0, other: 0 };
  const types = new Map();
  cdp.on("Network.responseReceived", (e) => types.set(e.requestId, e.type.toLowerCase()));
  cdp.on("Network.loadingFinished", (e) => {
    const t = types.get(e.requestId) || "other";
    bytes[t in bytes ? t : "other"] += e.encodedDataLength;
  });
  await page.addInitScript(() => {
    window.__lcp = 0; window.__cls = 0; window.__long = 0;
    new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
    new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: "layout-shift", buffered: true });
    new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__long += Math.max(0, e.duration - 50); }).observe({ type: "longtask", buffered: true });
  });
  const t0 = Date.now();
  await page.goto("http://127.0.0.1:3001" + target, { waitUntil: "load", timeout: 90000 });
  const loadMs = Date.now() - t0;
  await page.waitForLoadState("networkidle", { timeout: 90000 }).catch(() => {});
  await page.waitForTimeout(1500);
  const m = await page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0];
    const fcp = performance.getEntriesByName("first-contentful-paint")[0];
    return { ttfb: Math.round(nav.responseStart), fcp: Math.round(fcp?.startTime ?? 0), lcp: Math.round(window.__lcp),
             cls: +window.__cls.toFixed(3), blocking: Math.round(window.__long), dom: document.querySelectorAll("*").length };
  });
  const kb = Object.fromEntries(Object.entries(bytes).map(([k, v]) => [k, Math.round(v / 1024)]));
  console.log(target, JSON.stringify({ loadMs, settledMs: Date.now() - t0, ...m, transferKB: kb }));
  await context.close();
}
await browser.close();
