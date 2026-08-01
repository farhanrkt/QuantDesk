import type { Config } from "tailwindcss";

/**
 * Palette note: each of the three engines owns a hue, and that hue is the only
 * way the interface signals "which model is speaking". Flow = teal/coral,
 * technicals = azure, valuation = amber (DCF) or violet (DDM). Nothing else in
 * the UI is allowed to use those five colours.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#080C10",
        panel: "#111820",
        raised: "#161F29",
        rule: "#1E2A36",
        ash: "#7A8CA0",
        chalk: "#E7EEF5",
        acc: "#35C4A8",   // accumulation / bull
        dist: "#FF6B6B",  // distribution / bear
        tech: "#5B8DEF",  // technical engine
        dcf: "#E8B44C",   // valuation — DCF
        ddm: "#A78BFA",   // valuation — DDM
        warn: "#F2C14E",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-plex)", "ui-monospace", "monospace"],
      },
      borderRadius: { DEFAULT: "4px", lg: "6px" },
      keyframes: {
        rise: { "0%": { opacity: "0", transform: "translateY(6px)" }, "100%": { opacity: "1", transform: "none" } },
        pulseline: { "0%,100%": { opacity: "0.25" }, "50%": { opacity: "1" } },
      },
      animation: {
        rise: "rise 220ms cubic-bezier(0.22,1,0.36,1) both",
        pulseline: "pulseline 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
