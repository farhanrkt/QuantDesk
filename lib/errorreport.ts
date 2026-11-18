/**
 * The browser's half of error reporting (the server's is api/_lib/reporting.py).
 *
 * OFF UNTIL THE SERVER SAYS OTHERWISE. `/api/capabilities` answers
 * `errorReporting: true` only when the deployment has an error service, and
 * nothing is sent before that answer; a deployment without one receives no
 * reports at all.
 *
 * SAME ORIGIN, ROUTE TEMPLATE ONLY. A report goes to `/api/client-error` on
 * this origin, so the content security policy stays `connect-src 'self'`. It
 * carries where it happened as a route template from `lib/redact.ts` — never
 * the path, which can hold a ticker or a compare list — and the server cuts any
 * query string out of the message and the stack again. Nothing a reader keeps
 * (watchlist, holdings, journal) is read here.
 *
 * BOUNDED. At most five reports per page load, and one per distinct message,
 * so a component that throws on every render costs one report, not a flood.
 */
import { redactPath } from "./redact";

export const REPORTS_PER_PAGE = 5;

let enabled = false;
const sent = new Set<string>();

export function setErrorReporting(on: boolean): void {
  enabled = on;
}

export interface ErrorReport {
  kind: "render" | "unhandled" | "rejection";
  message: string;
  stack: string;
  route: string;
}

/** The report for an error, or null when it should not be sent. Pure apart from `sent`. */
export function errorReport(kind: ErrorReport["kind"], error: unknown, pathname: string,
                            seen: Set<string> = sent): ErrorReport | null {
  const err = error instanceof Error ? error : new Error(String(error ?? "unknown"));
  const message = `${err.name}: ${err.message}`.slice(0, 500);
  if (seen.has(message) || seen.size >= REPORTS_PER_PAGE) return null;
  seen.add(message);
  return { kind, message, stack: (err.stack ?? "").slice(0, 4000), route: redactPath(pathname) };
}

/** Send one error, when reporting is on. Never throws, never waits for an answer. */
export function reportError(kind: ErrorReport["kind"], error: unknown): void {
  if (!enabled || typeof window === "undefined") return;
  const report = errorReport(kind, error, window.location.pathname);
  if (!report) return;
  try {
    void fetch("/api/client-error", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(report), keepalive: true,
    }).catch(() => {});
  } catch { /* reporting must never break the page */ }
}
