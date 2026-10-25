"use client";

import { useCallback, useState } from "react";
import { CommandPalette } from "@/components/palette/CommandPalette";
import { PreferencesProvider } from "@/components/shell/preferences";
import { ShortcutLayer } from "@/components/shell/ShortcutLayer";
import { TopBar } from "@/components/shell/TopBar";
import { WorkspaceProvider } from "@/components/shell/workspace";
import { ToastProvider } from "@/components/ui/toaster";

/**
 * Everything that is the same on every page: the reader's stated preferences,
 * their watchlist and recent tickers, confirmations, the top bar, the command
 * palette, the keyboard layer, and the line that says what this is not.
 *
 * Client-only state, all of it kept in this browser. Nothing the shell holds is
 * sent anywhere; the request layer cannot import it (check_frontend.mjs).
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);

  return (
    <PreferencesProvider>
      <WorkspaceProvider>
        <ToastProvider>
          <a href="#main"
             className="sr-only z-50 rounded-lg bg-tech px-4 py-2 font-semibold text-ink
                        focus:not-sr-only focus:fixed focus:left-4 focus:top-3">
            Skip to content
          </a>
          <TopBar onSearch={openPalette} />
          <main id="main" tabIndex={-1}
                className="mx-auto min-h-[70vh] max-w-7xl px-4 pb-16 pt-6 focus:outline-none
                           sm:px-6 sm:pt-8 lg:px-8">
            {children}
          </main>
          <footer className="border-t border-rule print:border-0">
            <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
              <p className="prose-col text-meta leading-relaxed text-faint">
                Prices and filings from Yahoo Finance, unaudited and occasionally incomplete for IDX
                listings. Educational and research use only — not investment advice.
              </p>
            </div>
          </footer>
          <CommandPalette open={paletteOpen} onClose={closePalette} />
          <ShortcutLayer onPalette={openPalette} paletteOpen={paletteOpen} />
        </ToastProvider>
      </WorkspaceProvider>
    </PreferencesProvider>
  );
}
