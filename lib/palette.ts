/**
 * THE ONE PLACE A COLOUR IS WRITTEN DOWN.
 * =======================================
 *
 * Before this file the palette lived in tailwind.config.ts AND in some 140 hex
 * literals spread across 22 components — `const ACC = "#35C4A8"` redeclared in
 * six panels, the lens hues copied by hand between the page and the rail, and
 * five values that were in no palette at all (`#5B8DEF`, the old `tech`, in five
 * files; `#7A8CA0`, a grey between `ash` and `faint`, in ten; `#63748A`, the
 * `faint` that failed contrast, still drawing axis labels). A token that can be
 * redeclared locally is a suggestion. Tailwind reads this, Recharts props read
 * this, and `scripts/check_frontend.mjs` fails the build on a hex literal
 * anywhere else in components/ or app/.
 *
 * THE PALETTE HAS TWO JOBS AND THEY MUST NOT BLEND.
 *
 * IDENTITY says which model is speaking: flow teal, trend azure, value amber,
 * quality gold. It is structural, always on, and means nothing about the
 * company — a lens is that colour whether its reading is good or terrible.
 *
 * TONE says what the server concluded: `acc` good, `dist` bad, `warn` caution.
 * It arrives from `explain.tone` and from nowhere else. A component that picks
 * a tone colour from the sign of a number has re-litigated a judgement Python
 * already made, which is the bug class §14 spent an audit removing.
 *
 * Keeping them apart is why `tech` is not allowed to mean "good" and `acc` is
 * not allowed to mean "the flow lens". Before v2 both drifted: the flow lens's
 * teal and the accumulation tone were the same token doing two jobs, so a lens
 * heading and a verdict were the same colour and neither read as meaningful.
 *
 * NEUTRALS ARE A LADDER, NOT A PAIR. The v1 palette had exactly two text
 * colours — `chalk` and `ash` — and 54% of every screen was `ash`. When more
 * than half a page is in the de-emphasis colour, nothing is emphasised.
 *
 * The `name: "#RRGGBB"` spelling is load-bearing: rule 8 of check_frontend.mjs
 * reads the text ladder out of this file by that pattern and recomputes every
 * contrast ratio on every build.
 */
export const palette = {
  // --- strata -----------------------------------------------------------
  ink: "#080C10",       // page ground
  panel: "#111820",     // the standard surface
  raised: "#161F29",    // a surface on top of a surface
  sunken: "#0C1116",    // wells: tables, code, quoted figures
  rule: "#1E2A36",      // hairline
  ruleSoft: "#18222C",  // hairline INSIDE a group, so nesting reads
  ruleStrong: "#2A3846", // a hairline that has to survive on `raised`; scrollbar thumbs
  ruleHover: "#3A4C5E",  // the same hairline under a pointer

  // --- text ladder ------------------------------------------------------
  chalk: "#E7EEF5",     // headings and figures
  body: "#C3CFDC",      // running prose. NOT ash — this is the fix.
  ash: "#8496A9",       // genuinely secondary: units, counts, captions
  // LIGHTENED FROM #63748A, 1 September 2026, because it is not furniture.
  // `.eyebrow` uses it for every field label in the app and the footer
  // disclaimer is set in it. At #63748A it cleared 3.48 to 4.11 against the
  // four grounds and failed WCAG AA everywhere it was used. #7387A0 clears 4.52
  // to 5.33 while staying a clear step below `ash`.
  faint: "#7387A0",     // furniture AND small labels — must clear AA

  // --- tone: the server's judgement, never chrome -----------------------
  acc: "#35C4A8",
  dist: "#FF6B6B",
  warn: "#F2C14E",

  // --- identity: which lens is speaking, never a judgement --------------
  flow: "#2FBFA4",
  trend: "#6B9BFF",
  value: "#E8B44C",
  quality: "#C9A227",
  thesis: "#A78BFA",
  // The tabs that are not lenses. Each was an untokenised literal in one or two
  // files; naming them is what lets the tab bar and the panel that owns a tab
  // agree on its colour without copying a string.
  portfolio: "#6FD0C0",
  drivers: "#D4763A",   // "What drives it" — the exposure tab
  pretrade: "#F2A25C",
  // The private scanner tier. Deliberately outside the four lens hues: it is
  // not a lens, it is an aggregate OF the lenses, and colouring it like one
  // would imply it reads data of its own.
  private: "#7C8FA6",
  // "What it is". Orientation rather than a model, so it carries no hue of its
  // own — a coloured company tab would read as a fifth lens with an opinion.
  company: "#C3CFDC",

  // `tech` is the interactive accent (focus, links, controls) and `dcf`/`ddm`
  // are the valuation engine hues the charts key off.
  tech: "#6B9BFF",
  dcf: "#E8B44C",
  ddm: "#A78BFA",

  // --- chart furniture and series ---------------------------------------
  // Series hues say "this line is not that line" and nothing else. They are
  // never tones: a fast moving average drawn in `warn` yellow reads as a
  // caution it does not carry, which is how these came to be separate tokens.
  axis: "#7387A0",
  grid: "#1E2A36",
  seriesFast: "#F2C14E",
  seriesSlow: "#7FA8F5",
  seriesCyan: "#4DD0E1",
  seriesOrange: "#FFB74D",
  seriesViolet: "#A78BFA",
  // Levels drawn above and below the last close. Position, not judgement: a
  // ceiling is not bad news and a floor is not good news.
  levelAbove: "#EF9A9A",
  levelBelow: "#80CBC4",

  // --- print: the same ladder and tones, dark on white paper --------------
  // A printer does not draw dark backgrounds, so `chalk` text would print as
  // near-white on white. These are what each token becomes on paper, and the
  // tones keep their meaning at print contrast. Not a light theme: the screen
  // stays dark (DESIGN.md), and these exist for one media query.
  printText: "#0D1620",
  printBody: "#26313D",
  printMuted: "#4A5868",
  printRule: "#C9D2DC",
  printAcc: "#0B7A66",
  printDist: "#B42318",
  printWarn: "#8A6100",
} satisfies Record<string, string>;

export type PaletteToken = keyof typeof palette;

/**
 * The tab and chip hue for each lens. `ConfluenceRail` and the tab bar used to
 * hold separate hand-copied maps; both read this one now.
 */
export const LENS_HUE: Record<string, string> = {
  Flow: palette.flow, Trend: palette.trend, Value: palette.value, Quality: palette.quality,
};

/** `rgba()` from a palette hex, for washes and translucent chart fills. */
export function alpha(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
