import type { Metadata } from "next";
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
      <body className="min-h-screen font-sans">{children}</body>
    </html>
  );
}
