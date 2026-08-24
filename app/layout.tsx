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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${plex.variable}`}>
      <body className="min-h-screen font-sans">
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
