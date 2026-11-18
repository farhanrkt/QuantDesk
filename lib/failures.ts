import { t } from "./i18n";
import type { EngineFailure } from "./types";

/**
 * What a reader is told when a request does not come back with an answer.
 * =======================================================================
 *
 * Pure, so the frontend assertions can pin it: the request layer
 * (lib/api.ts) is a client module the assertions cannot load, and the four
 * cases below are exactly the ones that used to reach the reader as something
 * they could not read (docs/AUDIT.md, REL-5):
 *
 *   a status with no sentence      "Request failed (502)", in English, always
 *   a list of validation errors    cast to a failure with no message, so the
 *                                  card was blank
 *   no connection at all           "TypeError: Failed to fetch"
 *   no answer in time              nothing: the request waited forever
 *
 * A failure the server worded is passed through as it came; it is already in
 * the reader's language (api/_lib/lang.py).
 */

/** How long the browser waits for any one answer. The server answers in words
 * by 52 seconds and the platform stops it at 60; past that nothing is coming. */
export const REQUEST_DEADLINE_MS = 60_000;

/** The longest `Retry-After` worth waiting for once, in the background. */
export const RETRY_AFTER_CAP_MS = 8_000;

/** The failure for a response that was not ok, from its status and `detail`. */
export function failureFromResponse(status: number, detail: unknown): EngineFailure {
  if (typeof detail === "string" && detail.trim()) return { message: detail };
  if (detail && typeof detail === "object" && !Array.isArray(detail)
      && typeof (detail as EngineFailure).message === "string") {
    return detail as EngineFailure;
  }
  if (status === 429) {
    return { message: t("Too many requests from this connection in the last minute. Wait a moment and try again.") };
  }
  if (status === 422 || status === 400) {
    return { message: t("This request could not be read. Check the ticker: letters and digits, with an exchange suffix such as .JK where it has one.") };
  }
  if (status === 504 || status === 503 || status === 502) {
    return { message: t("The server did not answer in time. The data provider may be slow; trying again in a minute usually works.") };
  }
  return { message: t("The request failed (status {status}). Trying again usually works.", { status }) };
}

/** The failure for a request that never got a response at all. */
export function failureFromError(error: unknown): EngineFailure {
  const name = (error as { name?: string } | null)?.name;
  if (name === "TimeoutError") {
    return { message: t("This took too long and was stopped. The data provider may be slow; trying again in a minute usually works.") };
  }
  if (error instanceof TypeError) {
    return { message: t("QuantDesk's server could not be reached. Check the connection and try again.") };
  }
  if (error && typeof error === "object" && typeof (error as EngineFailure).message === "string") {
    return error as EngineFailure;
  }
  return { message: t("Something went wrong before an answer arrived. Trying again usually works.") };
}

/**
 * How long to wait before asking again after a 429, or null not to. Only a
 * short wait is worth taking on the reader's behalf; a longer one is theirs
 * to choose, so the refusal is shown instead.
 */
export function retryAfterMs(header: string | null): number | null {
  if (header === null) return null;
  const seconds = Number(header.trim());
  if (!Number.isFinite(seconds) || seconds < 0) return null;
  const ms = Math.ceil(seconds * 1000);
  return ms <= RETRY_AFTER_CAP_MS ? ms : null;
}
