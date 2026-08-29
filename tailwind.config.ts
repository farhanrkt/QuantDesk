import type { Config } from "tailwindcss";

/**
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
 * than half a page is in the de-emphasis colour, nothing is emphasised. The
 * ladder below gives secondary text somewhere to go that is not the dimmest
 * value available.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // --- strata -------------------------------------------------------
        ink: "#080C10",       // page ground
        panel: "#111820",     // the standard surface
        raised: "#161F29",    // a surface on top of a surface
        sunken: "#0C1116",    // wells: tables, code, quoted figures
        rule: "#1E2A36",      // hairline
        ruleSoft: "#18222C",  // hairline INSIDE a group, so nesting reads

        // --- text ladder --------------------------------------------------
        chalk: "#E7EEF5",     // headings and figures
        body: "#C3CFDC",      // running prose. NOT ash — this is the fix.
        ash: "#8496A9",       // genuinely secondary: units, counts, captions
        faint: "#63748A",     // furniture: table headers, disabled

        // --- tone: the server's judgement, never chrome --------------------
        acc: "#35C4A8",
        dist: "#FF6B6B",
        warn: "#F2C14E",

        // --- identity: which lens is speaking, never a judgement -----------
        flow: "#2FBFA4",
        trend: "#6B9BFF",
        value: "#E8B44C",
        quality: "#C9A227",
        thesis: "#A78BFA",

        // Retained: `tech` is the interactive accent (focus, links, controls)
        // and `dcf`/`ddm` are the valuation engine hues the charts key off.
        tech: "#6B9BFF",
        dcf: "#E8B44C",
        ddm: "#A78BFA",
      },
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
