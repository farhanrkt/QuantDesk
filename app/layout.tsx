import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next";
import { IBM_Plex_Mono, Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const plex = IBM_Plex_Mono({
  subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex", display: "swap",
});

export const metadata: Metadata = {
  title: "QuantDesk - by @farhanrkt",
  description:
    "Isolation Forest anomaly detection, automated technical analysis and DCF/DDM intrinsic value for US and Indonesian equities.",
};

/**
 * The design direction this surface commits to. Rendered into the page so a
 * built artifact carries the reasoning it was made against; see DESIGN.md for
 * the system it produced.
 */
const DIRECTION = `<!--
  THESIS: a research desk that ranks EVIDENCE, not companies. It refuses the category
  default of a dashboard whose biggest element is a verdict; the biggest element here is
  the question being asked, and the reader's own eye does the combining.

  OWN-WORLD: near-black ink under panel, raised and sunken strata; one hue per lens
  (teal / azure / amber / gold) owning a tinted header field rather than a hairline of
  trim; tone (acc / dist / warn) reserved for the server's judgement and never spent on
  chrome; mono kept for measured numerals only. Recognizable with all content removed by
  its four coloured lens fields and its sentence-case headings.

  STORY: the reader sees five lenses land in different places, understands that the
  disagreement IS the finding, and goes to the tab that owns it.

  FIRST VIEWPORT: ticker at 28px, four lens chips in a row underneath, then the
  plain-English verdict at reading size, then what argues against acting on it.

  FORM: an extension of the incumbent terminal world. Hierarchy, density and target size
  rebuilt; identity inherited rather than replaced.

  FINISH: unreviewed and undocumented is unfinished; this build ends with the finish
  review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
-->`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${plex.variable}`}>
      <body className="min-h-screen font-sans">
        {/*
          The v2 direction, emitted as a REAL HTML comment rather than a JSX one.
          React strips `{/* … *\/}` before it reaches the markup, so a contract
          written that way is a contract nobody can audit in a deployed build —
          checked by grepping the built output for THESIS, which found nothing
          until this changed. `hidden` keeps the carrier out of the layout.
        */}
        <div hidden aria-hidden dangerouslySetInnerHTML={{ __html: DIRECTION }} />
        {children}
        {/*
          Visitor counts, and NOTHING that needed the privacy posture relaxed.
          Three properties made this the only analytics worth adding here:

          SAME ORIGIN. The script loads from `/_vercel/insights/script.js` and
          beacons to `/_vercel/insights/event` — both on this app's own domain,
          proxied by the platform. `script-src 'self'` and `connect-src 'self'`
          in next.config.mjs therefore already permit it, so the CSP is
          unchanged. Every third-party alternative would have meant adding an
          external host to both directives.

          NO COOKIES, NO STORAGE. The package contains zero references to
          document.cookie, localStorage or sessionStorage — verified in its
          source, not taken on trust. That is what keeps this app free of a
          consent banner, which is a genuine feature and not a convenience.

          PRODUCTION ONLY. In development the package fetches a debug script
          from an external host, which this CSP correctly refuses; rendering it
          only in production keeps the local console clean and means the numbers
          are not polluted by our own reloads.
        */}
        {process.env.NODE_ENV === "production" && <Analytics />}
      </body>
    </html>
  );
}
