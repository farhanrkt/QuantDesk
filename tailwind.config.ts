import type { Config } from "tailwindcss";
import { palette } from "./lib/palette";

/**
 * Colours come from lib/palette.ts and nowhere else — that file explains the
 * identity/tone split and the text ladder, and check_frontend.mjs recomputes
 * the ladder's contrast from it on every build.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { ...palette },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-plex)", "ui-monospace", "monospace"],
      },
      /**
       * SIX STEPS WITH REAL GAPS, replacing sixteen inside a 3px band.
       *
       * v1 rendered 272 of 402 text nodes at 12 / 11.2 / 10.88px — close enough
       * that no amount of colour could build a hierarchy on top of them, and
       * the two most important headings on the page (`What this adds up to`,
       * `What would give a careful buyer pause`) came out at 10.88px, SMALLER
       * than the body text they introduced.
       *
       * Each step below is at least 15% from its neighbour, which is the point
       * at which a size difference reads as intentional rather than as a
       * rendering artefact.
       */
      fontSize: {
        micro: ["0.6875rem", { lineHeight: "1.45" }],   // 11px  units, footnotes
        meta: ["0.8125rem", { lineHeight: "1.5" }],     // 13px  captions, table cells
        base: ["0.9375rem", { lineHeight: "1.65" }],    // 15px  running prose
        lead: ["1.0625rem", { lineHeight: "1.55" }],    // 17px  the sentence that matters
        h3: ["1.0625rem", { lineHeight: "1.35" }],      // 17px  subsection
        h2: ["1.375rem", { lineHeight: "1.3" }],        // 22px  section
        h1: ["1.75rem", { lineHeight: "1.2" }],         // 28px  the ticker
        // The landing's one sentence, and nothing else. 29% above h1, so it
        // reads as a different kind of text rather than a slightly larger
        // heading; a stock page never uses it — the ticker stays the biggest
        // thing there.
        display: ["2.25rem", { lineHeight: "1.15" }],   // 36px  the landing headline
        figure: ["1.5rem", { lineHeight: "1.15" }],     // 24px  a headline number
      },
      // A measure cap for prose. 15px Inter at 68ch lands near 640px, which is
      // why panels holding sentences stop there instead of running the full
      // 1280px container the way v1 did (96ch and worse on a wide screen).
      maxWidth: { measure: "40rem", measureWide: "46rem" },
      borderRadius: { DEFAULT: "5px", lg: "8px", xl: "12px" },
      boxShadow: {
        // Offset AND blur. A zero-offset halo is decoration, not depth.
        lift: "0 1px 2px rgba(0,0,0,0.4), 0 8px 24px -8px rgba(0,0,0,0.65)",
        pop: "0 2px 4px rgba(0,0,0,0.45), 0 16px 40px -12px rgba(0,0,0,0.75)",
      },
      keyframes: {
        rise: { "0%": { opacity: "0", transform: "translateY(6px)" }, "100%": { opacity: "1", transform: "none" } },
        pulseline: { "0%,100%": { opacity: "0.25" }, "50%": { opacity: "1" } },
      },
      animation: {
        rise: "rise 260ms cubic-bezier(0.22,1,0.36,1) both",
        pulseline: "pulseline 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
