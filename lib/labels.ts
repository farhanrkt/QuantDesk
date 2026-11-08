import { msg, t } from "./i18n";

/**
 * Words the server sends as identifiers and the page also shows.
 * ==============================================================
 * The valuation engine's basis options travel back to it as the reader's
 * choice, and the projection's stream label names a column; both stay English
 * on the wire in every language, so they are worded here, at the moment they
 * are drawn. Anything not listed is shown as it came.
 */
const LABELS: Record<string, string> = {
  "Latest fiscal year": msg("Latest fiscal year"),
  "2-year average": msg("2-year average"),
  "3-year average": msg("3-year average"),
  "3-year weighted (3/2/1)": msg("3-year weighted (3/2/1)"),
  "Trailing 12 months": msg("Trailing 12 months"),
  "Last full year": msg("Last full year"),
  "Cost of Equity": msg("Cost of Equity"),
  "Projected FCF": msg("Projected FCF"),
  "Projected DPS": msg("Projected DPS"),
  "Residual income / share": msg("Residual income / share"),
  structure: msg("structure"),
  volatility: msg("volatility"),
  "measured move": msg("measured move"),
};

/** `text` in the language the page is drawn in, when it is one of the words above. */
export function label(text: string | null | undefined): string {
  if (!text) return text ?? "";
  return LABELS[text] ? t(LABELS[text]) : text;
}
