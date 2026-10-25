/**
 * What the analytics beacon may learn about where a reader is.
 * =============================================================
 *
 * ONE ROUTE TEMPLATE, NEVER THE PATH. The README promises that analytics never
 * see which company someone looked up, and for as long as the app was a single
 * page that held without trying: every page view was "/". Path routes break it
 * silently — `/stock/BBCA.JK` and `/compare?symbols=…` are a reader's research
 * list written into the one string every page view carries.
 *
 * AN ALLOWLIST, NOT A DENYLIST. Redacting `/stock/*` and forgetting the next
 * route is how this would leak again, so a path is reported only as one of the
 * templates below and anything else — a typo, a stale bookmark, a ticker typed
 * straight into the address bar — becomes "/other". The query string and the
 * fragment never survive: tab, compare list and run options all live there.
 *
 * Pure, so `tests/frontend/assertions.cjs` can pin it without a browser.
 */
export const ROUTE_TEMPLATES = ["/", "/stock/[symbol]", "/compare", "/markets", "/journal"] as const;

export function redactPath(pathname: string | null | undefined): string {
  if (!pathname) return "/";
  const path = pathname.split(/[?#]/)[0].replace(/\/+$/, "") || "/";
  if (/^\/stock\/[^/]+$/.test(path)) return "/stock/[symbol]";
  return (ROUTE_TEMPLATES as readonly string[]).includes(path) ? path : "/other";
}

export function redactUrl(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.origin}${redactPath(parsed.pathname)}`;
  } catch {
    return "/other";
  }
}
