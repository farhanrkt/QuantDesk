"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ExposurePanel } from "@/components/ExposurePanel";
import { RankingPanel } from "@/components/RankingPanel";
import { ScanPanel } from "@/components/ScanPanel";
import { ScreenerPanel } from "@/components/ScreenerPanel";
import { useRegisterCommands } from "@/components/palette/registry";
import { Section } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { TabPanel, Tabs, type Tab } from "@/components/ui/tabs";
import { useExposureScan, useScan, useUniverses } from "@/lib/api";
import { palette } from "@/lib/palette";
import { useSessionState } from "@/lib/session";
import type { Market } from "@/lib/types";
import { marketsHref, parseMarketView, stockHref, type MarketView } from "@/lib/url";

/**
 * The tools that read a whole list of companies at once.
 *
 * MOVED, NOT CHANGED. Ranking and the anomaly screener used to be the eighth
 * tab of a stock page — reachable only after loading some company — and the
 * exposure scan was both a stock tab and a landing panel. They answer questions
 * about a MARKET, so they have a page of their own, reachable from the top bar
 * with no ticker at all. Every control and every caveat came with them; Full
 * mode loses nothing (PRODUCT.md: nothing removed or hidden).
 *
 * Each tool keeps its results for the session, so ranking the Nasdaq-100,
 * opening a row's stock page and coming back finds the ranking where it was.
 */
const VIEWS: (Tab & { id: MarketView })[] = [
  { id: "rank", label: "Rank a universe", accent: palette.trend },
  { id: "screener", label: "Unusual activity", accent: palette.flow },
  { id: "exposure", label: "What it moves with", accent: palette.drivers },
  { id: "scan", label: "Latest local scan", accent: palette.private, divider: "Private" },
];

export function MarketsView() {
  const router = useRouter();
  const search = useSearchParams();
  const parsed = parseMarketView(search?.get("view") ?? null);
  const [view, setViewState] = useState<MarketView>(parsed);
  useEffect(() => { setViewState(parsed); }, [parsed]);

  const setView = useCallback((next: string) => {
    setViewState(next as MarketView);
    window.history.replaceState(null, "", marketsHref(next as MarketView));
  }, []);

  const open = useCallback((ticker: string) => router.push(stockHref(ticker)), [router]);

  const { state: universes } = useUniverses();
  const { state: exposure, scan: scanExposure } = useExposureScan();
  const [exposureMarket, setExposureMarket] = useSessionState<Market>("exposure:market", "ID");
  const [scanMarket, setScanMarket] = useSessionState<Market>("scan:market", "ID");
  const { state: scan } = useScan(scanMarket);

  useRegisterCommands("markets", VIEWS.map((v) => ({
    id: `markets:${v.id}`, group: "Go to" as const, label: `Markets: ${v.label}`, run: () => setView(v.id),
  })));

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1>Markets</h1>
        <p className="prose-col text-ash">
          Tools that read a whole list of companies at once. Each one produces a shortlist to
          open in the four lenses — not a verdict on any name in it.
        </p>
      </header>

      <div className="sticky top-14 z-30 -mx-4 bg-ink/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-ink/80
                      sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
        <Tabs tabs={VIEWS} active={view} onChange={setView} idPrefix="markets" label="Market tools" />
      </div>

      <TabPanel id="rank" active={view} idPrefix="markets">
        <Section title="Rank a universe"
                 question="Of these hundred, which few are worth opening four lenses on?">
          <RankingPanel onSelect={open} />
        </Section>
      </TabPanel>

      <TabPanel id="screener" active={view} idPrefix="markets">
        {/* The screener answers what the ranking cannot: has anything UNUSUAL
            just happened here? A one-off event rather than a standing trait, with
            its own multiple-testing correction. */}
        <Section title="Scan for unusual activity"
                 question="Has anything just happened in these names that their own history says is rare?">
          <ScreenerPanel onSelect={open} />
        </Section>
      </TabPanel>

      <TabPanel id="exposure" active={view} idPrefix="markets">
        <Section title="What a market moves with"
                 question="Which shared forces drive this list — and which of those were measured to persist?">
          <ExposurePanel universeState={universes} market={exposureMarket}
                         onMarketChange={setExposureMarket} state={exposure}
                         onScan={scanExposure} highlight={null} />
        </Section>
      </TabPanel>

      <TabPanel id="scan" active={view} idPrefix="markets">
        <Section
          title="Latest local scan"
          question="The private whole-market sweep, as last run on this machine."
          aside={(
            <label className="flex items-center gap-2 text-meta text-ash">
              <span className="eyebrow">Market</span>
              <Select value={scanMarket} onChange={(e) => setScanMarket(e.target.value as Market)}
                      aria-label="Scan market" className="h-9">
                <option value="ID">Indonesia (IDX)</option>
                <option value="US">United States</option>
              </Select>
            </label>
          )}
        >
          <ScanPanel state={scan} market={scanMarket} onSelect={open} />
        </Section>
      </TabPanel>
    </div>
  );
}
