"use client";

import { Analytics, type BeforeSendEvent } from "@vercel/analytics/react";
import { usePathname } from "next/navigation";
import { redactPath, redactUrl } from "@/lib/redact";

/**
 * Vercel Web Analytics, told only which kind of page this is.
 *
 * THE REACT ENTRY, NOT `@vercel/analytics/next`. The Next wrapper derives a
 * route template from the URL params — which would be fine — but it also sends
 * the raw `path` beside it, and on `/stock/AAPL` the raw path is the ticker.
 * Passing `route` and `path` ourselves switches the package's auto-tracking off
 * and leaves both fields under this file's control.
 *
 * `beforeSend` covers the other half: custom events (`track("analysis", …)` in
 * lib/api.ts) carry `location.href`, query string and all, and this is the one
 * hook every outgoing event passes through. Module-level so the package's own
 * effect does not re-register it on every render.
 */
const beforeSend = (event: BeforeSendEvent): BeforeSendEvent => ({
  ...event,
  url: redactUrl(event.url),
});

export function AnalyticsRedacted() {
  const route = redactPath(usePathname());
  return <Analytics framework="next" route={route} path={route} beforeSend={beforeSend} />;
}
