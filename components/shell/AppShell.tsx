"use client";

import { usePathname } from "next/navigation";
import { useCallback, useState } from "react";
import { MarketBand } from "@/components/markets/MarketBand";
import { MarketRail } from "@/components/markets/MarketRail";
import { CommandPalette } from "@/components/palette/CommandPalette";
import { ErrorListener } from "@/components/shell/ErrorListener";
import { MarketBoardProvider } from "@/components/shell/marketboard";
import { PreferencesProvider } from "@/components/shell/preferences";
import { ShortcutLayer } from "@/components/shell/ShortcutLayer";
import { TopBar } from "@/components/shell/TopBar";
import { WorkspaceProvider } from "@/components/shell/workspace";
import { PartBoundary } from "@/components/ui/boundary";
import { ToastProvider } from "@/components/ui/toaster";
import { useT } from "@/lib/i18n";

/**
 * Everything that is the same on every page: the reader's stated preferences,
 * their watchlist and recent tickers, the board of what moved the markets,
 * confirmations, the top bar, the command palette, the keyboard layer, and the
 * line that says what this is not.
 *
 * Client-only state, all of it kept in this browser. Nothing the shell holds is
 * sent anywhere; the request layer cannot import it (check_frontend.mjs).
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const t = useT();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  // On a phone the band and the ticker form filled the whole first screen of a
  // stock page, and the company the reader asked for began below it. There the
  // stock workspace draws the band itself, under the company's summary.
  const onStock = usePathname()?.startsWith("/stock/") ?? false;

  return (
    <PreferencesProvider>
      <WorkspaceProvider>
        <MarketBoardProvider>
        <ToastProvider>
          <a href="#main"
             className="sr-only z-50 rounded-lg bg-tech px-4 py-2 font-semibold text-ink
                        focus:not-sr-only focus:fixed focus:left-4 focus:top-3">
            {t("Skip to content")}
          </a>
          <TopBar onSearch={openPalette} />
          {/* THE PAGE AND THE MARKETS PANEL SIDE BY SIDE from 1280px. The page
              keeps its own 1280px measure inside its column, so hiding the
              panel widens nothing; below 1280px the panel becomes the band at
              the top of the page. */}
          <div className="xl:flex">
            {/* AT LEAST A SCREEN TALL, so the footer starts below the fold.
                A page opens as a short placeholder and then fills; with 70vh the
                footer sat on the first screen and jumped off it when the page
                arrived, which was a third of the stock page's layout shift. */}
            <main id="main" tabIndex={-1}
                  className="min-h-[calc(100svh-3.5rem)] min-w-0 flex-1 px-4 pb-16 pt-6 focus:outline-none
                             sm:px-6 sm:pt-8 lg:px-8">
              <div className="mx-auto max-w-7xl">
                <PartBoundary>
                  <MarketBand className={onStock ? "mb-6 hidden sm:block xl:hidden" : "mb-6 xl:hidden"} />
                </PartBoundary>
                {children}
              </div>
            </main>
            <PartBoundary><MarketRail /></PartBoundary>
          </div>
          <footer className="border-t border-rule print:border-0">
            <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
              <p className="prose-col text-meta leading-relaxed text-faint">
                {t("Prices and filings from Yahoo Finance, unaudited and occasionally incomplete for IDX listings. Educational and research use only — not investment advice.")}
              </p>
            </div>
          </footer>
          <CommandPalette open={paletteOpen} onClose={closePalette} />
          <ShortcutLayer onPalette={openPalette} paletteOpen={paletteOpen} />
          <ErrorListener />
        </ToastProvider>
        </MarketBoardProvider>
      </WorkspaceProvider>
    </PreferencesProvider>
  );
}
