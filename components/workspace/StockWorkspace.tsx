"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AnomalyPanel } from "@/components/AnomalyPanel";
import { CompanyHeader } from "@/components/company/CompanyHeader";
import { CompanyPanel } from "@/components/company/CompanyPanel";
import { ConfluenceRail } from "@/components/ConfluenceRail";
import { EventStudyPanel } from "@/components/EventStudyPanel";
import { ExposurePanel } from "@/components/ExposurePanel";
import { HoldingHorizonBar } from "@/components/HoldingHorizonBar";
import { NewsPanel } from "@/components/NewsPanel";
import { PeersPanel } from "@/components/PeersPanel";
import { PortfolioPanel } from "@/components/PortfolioPanel";
import { PreTradePanel } from "@/components/PreTradePanel";
import { QualityPanel } from "@/components/QualityPanel";
import { SynthesisPanel } from "@/components/SynthesisPanel";
import { TechnicalPanel } from "@/components/TechnicalPanel";
import { ThesisPanel } from "@/components/ThesisPanel";
import { TickerBar } from "@/components/TickerBar";
import { MarketStrip } from "@/components/markets/MarketStrip";
import { useBoardFocus } from "@/components/shell/marketboard";
import { ManualRescue } from "@/components/ValuationControls";
import { ValuationPanel } from "@/components/ValuationPanel";
import { VerdictPanel } from "@/components/VerdictPanel";
import { useRegisterCommands, type RunnableCommand } from "@/components/palette/registry";
import { SHORTCUT_EVENT } from "@/components/shell/ShortcutLayer";
import { usePreferences } from "@/components/shell/preferences";
import { useWorkspace } from "@/components/shell/workspace";
import { TabPanel, Tabs, type Tab } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toaster";
import { Panel, PortfolioSignpost, PrintHeader, RunStatus, StockActions } from "@/components/workspace/parts";
import {
  confluenceKey, simulationCsvUrl, useEngines, useEventStudy, useExposureScan, usePeers,
  usePortfolio, useUniverses, useVerdict, type RunOptions,
} from "@/lib/api";
import { palette } from "@/lib/palette";
import { readSession, useSessionState } from "@/lib/session";
import { marketOf, resolveSymbol } from "@/lib/symbols";
import type { Market } from "@/lib/types";
import {
  DEFAULT_TAB, compareHref, parseStockQuery, stockHref, type StockTab,
} from "@/lib/url";

/**
 * LABELLED BY THE QUESTION, NOT THE METHOD. "Flow · anomalies" and "Intrinsic
 * value" name the technique, which tells a newcomer nothing about whether the
 * tab is worth opening. The hues are the lens identity colours from
 * lib/palette, so a chip in the rail and the tab that owns it are one colour.
 */
const TABS: (Tab & { id: StockTab })[] = [
  // ORIENTATION FIRST IN THE ORDER, NOT THE DEFAULT. What the company is and
  // what its filings say it has done is the question a newcomer has before any
  // lens makes sense; Trend stays the tab a run lands on, for the reason in
  // lib/url.ts, and a one-line company header answers "who is this" on every tab.
  { id: "company", label: "What it is", accent: palette.company },
  { id: "flow", label: "Who is trading it", accent: palette.flow },
  { id: "trend", label: "What the price did", accent: palette.trend },
  { id: "value", label: "What it is worth", accent: palette.value },
  { id: "quality", label: "Are the numbers real", accent: palette.quality },
  // The fourth question this app can answer — how does it sit against what I
  // already own — and the only one that needs an input other than a ticker.
  { id: "portfolio", label: "Portfolio fit", accent: palette.portfolio },
  // The cross-sectional half of the same question: what a whole index moves
  // with. It needs no input beyond picking a list, and highlights this ticker.
  { id: "exposure", label: "What drives it", accent: palette.drivers },
  // Last of the published tabs: the only one that asks the reader for
  // something rather than telling them something.
  { id: "thesis", label: "Thesis", accent: palette.thesis },
  // THE PRIVATE TIER, AND LAST FOR A REASON THAT IS NOT MODESTY. This is the
  // one tab that returns a verdict rather than a description, and the page is
  // arranged so a reader meets the evidence before anything compresses it. Its
  // accent is outside the lens hues: it is an aggregate OF the lenses, not one.
  { id: "score", label: "Score it", accent: palette.private, divider: "Private" },
];

/** How old a loaded read may get before returning to the page fetches it again. */
const STALE_AFTER_MS = 15 * 60_000;

/**
 * One company, read through every lens — what the whole app used to be.
 *
 * THE URL IS THE SOURCE OF TRUTH. The path names the company and the query
 * names the tab and any tuning that differs from the defaults (lib/url.ts), so
 * a refresh, a bookmark, a shared link and the browser's back button all land
 * on the same page. Every on-demand request — event study, peers, portfolio,
 * score — runs for `symbol`, the company in the path. The old page ran three of
 * them for whatever was typed in the box at the moment of the click, so editing
 * the box without pressing Run sent the next company's request under this
 * company's header.
 *
 * Results are kept per symbol for the session (lib/session.ts): leaving for the
 * compare view and coming back restores the page rather than re-running it.
 */
export function StockWorkspace({ symbol }: { symbol: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const toast = useToast();
  const { horizon, setHorizon } = usePreferences();
  const { isWatched, toggleWatch, recordRecent } = useWorkspace();
  const market: Market = marketOf(symbol);

  const parsed = useMemo(() => parseStockQuery(search?.toString() ?? ""), [search]);
  const tuning = parsed.run;
  const opts: RunOptions = useMemo(() => ({ ticker: symbol, market, ...tuning }),
                                   [symbol, market, tuning]);

  // The tab follows the URL (back/forward), and a tab click updates the URL
  // without a navigation — `replaceState`, so tab-hopping does not fill the
  // history with entries the back button would have to wade through.
  const [tab, setTabState] = useState<StockTab>(parsed.tab);
  useEffect(() => { setTabState(parsed.tab); }, [parsed.tab]);
  const visible = TABS.some((t) => t.id === tab) ? tab : DEFAULT_TAB;
  const setTab = useCallback((next: string) => {
    const id = next as StockTab;
    setTabState(id);
    window.history.replaceState(null, "", stockHref(symbol, id, tuning));
  }, [symbol, tuning]);

  // A typed lowercase or encoded path is canonicalised in place, so the address
  // bar always says the symbol the engines were actually asked about.
  useEffect(() => {
    const segment = pathname?.split("/").pop() ?? "";
    let decoded = segment;
    try { decoded = decodeURIComponent(segment); } catch { /* leave it */ }
    if (decoded !== symbol) router.replace(stockHref(symbol, parsed.tab, tuning));
  }, [pathname, symbol, parsed.tab, tuning, router]);

  // --- data ---------------------------------------------------------------
  const engines = useEngines(symbol);
  const { anomaly, technical, valuation, quality, news, company, synthesis, preTrade } = engines;

  // The market board marks what this stock is related to. Only the stock's
  // market and the exposure the Trend tab MEASURED cross over, and only into
  // this browser: the board's request names nothing.
  useBoardFocus({
    symbol,
    market,
    factors: technical.status === "ready"
      ? (technical.data.exposure?.factors ?? []).map((f) => ({ key: f.key, label: f.label, weeks: f.weeks }))
      : null,
  });
  const { state: eventStudy, validate } = useEventStudy(symbol);
  const { state: peers, compare: comparePeers } = usePeers(symbol);
  const { state: portfolio, compare: comparePortfolio } = usePortfolio(symbol);
  const { state: verdict, score: scoreVerdict } = useVerdict(symbol);
  const { state: universes } = useUniverses();
  const { state: exposureScan, scan: scanExposure } = useExposureScan();
  // THE EXPOSURE PANEL OWNS ITS MARKET. It used to write the shared ticker-bar
  // market, so picking IDX30 to scan flipped the box a reader types tickers
  // into — a side effect with no visible cause.
  const [exposureMarket, setExposureMarket] = useSessionState<Market>("exposure:market", market);

  const runKey = confluenceKey(opts);
  const { run } = engines;
  useEffect(() => {
    const held = readSession<{ runKey: string | null; at: number | null }>(`engines:${symbol}`);
    const stale = !held?.at || Date.now() - held.at > STALE_AFTER_MS;
    if (held?.runKey !== runKey || (stale && held?.at)) run(opts);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runKey captures opts
  }, [runKey, run]);

  const lenses = [anomaly, technical, valuation, quality];
  const busy = lenses.some((s) => s.status === "loading");
  const failed = lenses.filter((s) => s.status === "error").length;

  // A ticker becomes "recent" once it has actually loaded — a typo that
  // returned nothing should not sit in the list as if it were a company.
  useEffect(() => {
    if (engines.at && lenses.some((s) => s.status === "ready")) recordRecent(symbol);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engines.at, symbol]);

  // --- the ticker bar -------------------------------------------------------
  const [draft, setDraft] = useState<RunOptions>(opts);
  useEffect(() => { setDraft(opts); }, [opts]);
  const submit = (next: RunOptions) => {
    const resolved = resolveSymbol(next.ticker, next.market);
    if (!resolved) return;
    const nextTuning = {
      period: next.period, range: next.range, mode: next.mode,
      contamination: next.contamination, madK: next.madK, scoreThreshold: next.scoreThreshold,
    };
    router.push(stockHref(resolved, resolved === symbol ? visible : DEFAULT_TAB, nextTuning));
  };

  // --- actions --------------------------------------------------------------
  const watched = isWatched(symbol);
  const onWatch = useCallback(() => {
    const wasWatched = isWatched(symbol);
    const ok = toggleWatch(symbol);
    if (!ok) toast({ message: "Your watchlist is full (50). Remove one to add another.", tone: "error" });
    else toast({ message: wasWatched ? `${symbol} removed from your watchlist` : `${symbol} added to your watchlist — kept in this browser only` });
  }, [isWatched, toggleWatch, symbol, toast]);
  const onCompare = useCallback(() => {
    const last = readSession<string[]>("compare:last") ?? [];
    router.push(compareHref([...last.filter((s) => s !== symbol), symbol].slice(-4)));
  }, [router, symbol]);
  const onCopy = useCallback(() => {
    const url = `${window.location.origin}${stockHref(symbol, visible, tuning)}`;
    navigator.clipboard?.writeText(url).then(
      () => toast({ message: "Link copied — it carries the ticker and tab, nothing else" }),
      () => toast({ message: "Could not reach the clipboard; copy the address bar instead", tone: "error" }),
    );
  }, [symbol, visible, tuning, toast]);
  const onPrint = useCallback(() => window.print(), []);

  // A printed page cannot open a disclosure, so every <details> on the page is
  // opened for the print and the ones the reader had closed are closed again
  // afterwards — their choice on screen is not the printer's to keep.
  useEffect(() => {
    let reopened: HTMLDetailsElement[] = [];
    const before = () => {
      reopened = [...document.querySelectorAll<HTMLDetailsElement>("main details:not([open])")];
      reopened.forEach((d) => { d.open = true; });
    };
    const after = () => { reopened.forEach((d) => { d.open = false; }); reopened = []; };
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);

  // Keyboard: [ ] move between tabs, w toggles the watchlist.
  useEffect(() => {
    const onShortcut = (e: Event) => {
      const action = (e as CustomEvent<string>).detail;
      const index = TABS.findIndex((t) => t.id === visible);
      if (action === "prevTab") setTab(TABS[(index - 1 + TABS.length) % TABS.length].id);
      else if (action === "nextTab") setTab(TABS[(index + 1) % TABS.length].id);
      else if (action === "watch") onWatch();
    };
    window.addEventListener(SHORTCUT_EVENT, onShortcut);
    return () => window.removeEventListener(SHORTCUT_EVENT, onShortcut);
  }, [visible, setTab, onWatch]);

  const commands: RunnableCommand[] = [
    ...TABS.map((t) => ({ id: `tab:${t.id}`, group: "Go to" as const,
                          label: `${symbol}: ${t.label}`, keywords: `tab ${t.id}`,
                          run: () => setTab(t.id) })),
    { id: "act:watch", group: "Actions", label: watched ? `Remove ${symbol} from watchlist` : `Add ${symbol} to watchlist`,
      detail: "w", run: onWatch },
    { id: "act:compare", group: "Actions", label: `Compare ${symbol} with…`, run: onCompare },
    { id: "act:copy", group: "Actions", label: "Copy link to this page", run: onCopy },
    { id: "act:print", group: "Actions", label: "Print this page", keywords: "pdf tearsheet", run: onPrint },
  ];
  useRegisterCommands("stock", commands);

  // What the engines actually resolved to — normally `symbol` itself, since the
  // path already carries the resolved form.
  const resolvedTicker =
    anomaly.status === "ready" ? anomaly.data.ticker
      : technical.status === "ready" ? technical.data.ticker
        : valuation.status === "ready" ? valuation.data.ticker
          : symbol;

  return (
    <div className="space-y-6">
      <PrintHeader symbol={symbol}
                   name={company.status === "ready" ? company.data.name : null}
                   priceAsOf={company.status === "ready" ? company.data.listing.priceAsOf : null} />
      <div className="space-y-3 print:hidden">
        <TickerBar opts={draft} onChange={setDraft} onRun={submit} busy={busy} />
        <RunStatus symbol={symbol} busy={busy} failed={failed} at={engines.at} />
      </div>

      {/* Phones only: a wider screen has the market bar at the foot of the page. */}
      <MarketStrip className="md:hidden" />

      <ConfluenceRail
        ticker={resolvedTicker} anomaly={anomaly} technical={technical}
        valuation={valuation} quality={quality}
        subtitle={<CompanyHeader state={company} />}
        actions={<StockActions watched={watched} onWatch={onWatch} onCompare={onCompare}
                               onCopy={onCopy} onPrint={onPrint} />}
      />

      {/* The frame everything below is read through: what this length of
          ownership has historically been like. Above the synthesis because it
          is neither a summary nor an objection. */}
      <HoldingHorizonBar state={technical} horizon={horizon} onHorizon={setHorizon} />

      {/* Reads the assembled payload, so it can only appear once every leg has
          settled — a summary of four lenses that renders before three of them
          have answered would describe a picture that does not exist yet. */}
      {synthesis && <SynthesisPanel data={synthesis} />}

      {/* AFTER the synthesis, deliberately: a reader meets the description
          before the objections to it. Above the tabs rather than inside a lens,
          because a condition that only appears once you open the panel that
          already worried you is not a veto — it is a footnote. */}
      {preTrade && <PreTradePanel data={preTrade} />}

      <div>
        {/* STICKY, under the top bar, because the tools were four thousand
            pixels down. ONE ROW that scrolls sideways on a phone, where it used
            to wrap into three sticky rows covering a third of the screen. */}
        <div className="sticky top-14 z-30 -mx-4 bg-ink/95 px-4 backdrop-blur
                        supports-[backdrop-filter]:bg-ink/80 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8
                        print:hidden">
          <Tabs tabs={TABS} active={visible} onChange={setTab} />
        </div>
        <div className="pt-6">
          <TabPanel id="company" active={visible}>
            <Panel state={company}>{(d) => <CompanyPanel data={d} />}</Panel>
          </TabPanel>
          <TabPanel id="flow" active={visible}>
            <div className="space-y-4">
              <Panel state={anomaly}>{(d) => <AnomalyPanel data={d} />}</Panel>
              <EventStudyPanel
                state={eventStudy}
                ticker={resolvedTicker}
                onValidate={() => validate({
                  ticker: symbol, market, mode: tuning.mode, scoreThreshold: tuning.scoreThreshold,
                })}
              />
              <NewsPanel state={news} />
            </div>
          </TabPanel>
          <TabPanel id="trend" active={visible}>
            <div className="space-y-4">
              <PortfolioSignpost onOpen={() => setTab("portfolio")} />
              <Panel state={technical}>
                {(d) => (
                  <TechnicalPanel data={d} busy={technical.status === "loading"}
                                  stateKey={symbol}
                                  onApply={(t) => engines.refineTechnical(opts, t)} />
                )}
              </Panel>
              {/* On the Trend tab because the seven signals it compares are
                  price and volume — the data this lens reads. */}
              <PeersPanel state={peers} ticker={resolvedTicker}
                          onCompare={(universe) => comparePeers({ ticker: symbol, market, universe })} />
            </div>
          </TabPanel>
          <TabPanel id="value" active={visible}>
            <Panel
              state={valuation}
              rescue={(failure) => (
                <ManualRescue suggested={failure.suggested ?? {}} engine={failure.engine}
                              busy={valuation.status === "loading"}
                              onApply={(v) => engines.refineValuation(opts, v)} />
              )}
            >
              {(d) => (
                <ValuationPanel data={d} busy={valuation.status === "loading"}
                                onApply={(v) => engines.refineValuation(opts, v)}
                                csvUrl={simulationCsvUrl(opts, engines.valuationOptions)} />
              )}
            </Panel>
          </TabPanel>
          <TabPanel id="quality" active={visible}>
            <Panel state={quality}>{(d) => <QualityPanel data={d} />}</Panel>
          </TabPanel>
          <TabPanel id="portfolio" active={visible}>
            <PortfolioPanel
              state={portfolio}
              ticker={resolvedTicker}
              onCompare={(holdings, weights) => comparePortfolio({
                candidate: symbol, market, holdings, weights,
              })}
            />
          </TabPanel>
          <TabPanel id="exposure" active={visible}>
            <ExposurePanel
              universeState={universes}
              market={exposureMarket}
              onMarketChange={setExposureMarket}
              state={exposureScan}
              onScan={scanExposure}
              highlight={resolvedTicker}
            />
          </TabPanel>
          {/* THE SNAPSHOT IS ASSEMBLED HERE, FROM WHAT IS ON SCREEN. A thesis is
              frozen against the numbers the reader was actually looking at, so
              these are read from the settled legs rather than re-fetched — a
              snapshot from a second request would record a page nobody saw. */}
          <TabPanel id="thesis" active={visible}>
            <ThesisPanel
              ticker={resolvedTicker}
              snapshot={{
                impliedGrowth: valuation.status === "ready"
                  ? valuation.data.baseCase?.impliedGrowth ?? null : null,
                assumedGrowth: valuation.status === "ready"
                  ? valuation.data.baseCase?.assumedGrowth ?? null : null,
                price: valuation.status === "ready" ? valuation.data.price : null,
                priceLabel: valuation.status === "ready" ? valuation.data.priceLabel : null,
                maxDrawdown: technical.status === "ready"
                  ? technical.data.longTerm?.drawdown?.maxDrawdown ?? null : null,
                worstAtHorizon: technical.status === "ready"
                  ? (technical.data.longTerm?.rollingReturns ?? [])
                      .find((r) => r.years === horizon && r.usable !== false)?.worst ?? null
                  : null,
                firedChecks: (preTrade?.flags ?? []).map((f) => f.explain.label),
              }}
            />
          </TabPanel>
          <TabPanel id="score" active={visible}>
            {/* THE PRIVATE SCORE NEVER LEAVES THE SCREEN. A printout travels
                without its context, and a number on paper is the easiest thing
                in this app to mistake for a recommendation. */}
            <div className="print:hidden">
              <VerdictPanel state={verdict} ticker={resolvedTicker}
                            onScore={() => scoreVerdict({ ticker: symbol, market })} />
            </div>
            <p className="hidden text-meta text-ash print:block">
              The private score is not printed.
            </p>
          </TabPanel>
        </div>
      </div>
    </div>
  );
}

