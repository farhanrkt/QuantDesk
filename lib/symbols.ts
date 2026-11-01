/**
 * Ticker → Yahoo symbol, mirrored from api/_lib/symbols.py.
 * =========================================================
 *
 * WHY A BROWSER COPY OF A SERVER RULE. The page now has a URL per company, and
 * the URL has to name the symbol the server will actually fetch — otherwise
 * `/stock/BBCA` (a US ETF) and `/stock/BBCA.JK` (PT Bank Central Asia) are one
 * typo apart and the address bar says something the page does not. So the
 * symbol is resolved BEFORE navigation, exactly as the API would resolve it,
 * and the resolved form is what goes in the path.
 *
 * Two copies of one rule is the arrangement this codebase distrusts most, so
 * `scripts/check_frontend.mjs` compares this file's pattern and suffix map
 * against the Python ones on every build, the same way it guards the lens
 * families in the confluence rail.
 *
 * Pure: compiled into the frontend assertions and pinned there.
 */
import type { Market } from "./types";

/** Same characters, same length, as `TICKER_PATTERN` in api/index.py. */
export const TICKER_PATTERN = /^[A-Za-z0-9.\-^=]{1,20}$/;

/** Same map as `MARKET_SUFFIX` in api/_lib/symbols.py. */
export const MARKET_SUFFIX: Record<Market, string> = { US: "", ID: ".JK" };

export function isTicker(raw: string): boolean {
  return TICKER_PATTERN.test(raw.trim());
}

/** `symbols.resolve`: an explicit suffix wins over the market dropdown. */
export function resolveSymbol(ticker: string, market: Market = "US"): string {
  const raw = ticker.trim().toUpperCase();
  const suffix = MARKET_SUFFIX[market] ?? "";
  if (raw && suffix && !raw.endsWith(suffix)) return `${raw}${suffix}`;
  return raw;
}

/** `symbols.market_of`: the market an already-resolved symbol belongs to. */
export function marketOf(symbol: string): Market {
  return symbol.trim().toUpperCase().endsWith(MARKET_SUFFIX.ID) ? "ID" : "US";
}

/** `symbols.base_code`: the listing code without its exchange suffix. */
export function baseCode(symbol: string): string {
  const out = symbol.trim().toUpperCase();
  return out.endsWith(MARKET_SUFFIX.ID) ? out.slice(0, -MARKET_SUFFIX.ID.length) : out;
}
