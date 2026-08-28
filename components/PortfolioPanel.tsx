"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Layers } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Explain, ExplainedRow, TONE_TEXT, useDetail } from "@/components/ui/explain";
import { ApplyButton } from "@/components/ui/controls";
import type { Engine, ExplainMap, PortfolioResponse } from "@/lib/types";
import { cn, num, pct } from "@/lib/utils";

/**
 * Where this candidate sits against what the reader already owns.
 *
 * THE HOLDINGS NEVER LEAVE THE BROWSER EXCEPT TO ANSWER THIS QUESTION. They are
 * kept in localStorage, exactly where the reading mode and the holding horizon
 * live, because this app has no database and wants none. They are sent on the
 * request that needs them, used, and forgotten — there is nowhere on the server
 * to keep them. Nothing about them reaches the analytics event, which has always
 * carried a market code and a lens count and never a ticker.
 *
 * IT IS THE ONE POST IN THIS APP, and the reason is the input rather than the
 * size. A company name in a URL is not a fact about anybody; a holdings list is,
 * and URLs are logged by every hop that handles them — the platform's access
 * log, any proxy, the browser's own history — none of which a response header
 * can reach. A body is not. The cost is that "everything the UI does is a plain
 * GET" is now "everything except this", plus one CORS preflight on this call.
 *
 * IT IS A BUTTON, NOT AN AUTOMATIC LEG. Firing this on every ticker run would
 * send somebody's portfolio to the server on the strength of them having typed
 * a symbol, and it costs a batch download most readers will not want.
 */

const STORAGE_KEY = "quantdesk.holdings";
const PORTFOLIO = "#6FD0C0";

function useHoldings(): [string, (v: string) => void] {
  const [raw, setRaw] = useState("");
  // Read on mount, not during render: the server renders this tree too.
  useEffect(() => {
    try {
      setRaw(window.localStorage.getItem(STORAGE_KEY) ?? "");
    } catch { /* private mode — an empty list is the right default */ }
  }, []);
  const update = (next: string) => {
    setRaw(next);
    try { window.localStorage.setItem(STORAGE_KEY, next); } catch { /* ignore */ }
  };
  return [raw, update];
}

/**
 * `AAPL, MSFT:2, NVDA` → symbols plus the optional weights, as a map.
 *
 * A MAP RATHER THAN A STRING because the request is a POST now: the body can
 * carry structure, so there is no reason to flatten a mapping into text and ask
 * the server to parse it back. The self-describing `TICKER:WEIGHT` shape stays
 * in the TEXTAREA, where a human types it.
 */
function parse(raw: string): { symbols: string[]; weights: Record<string, number> } {
  const symbols: string[] = [];
  const weights: Record<string, number> = {};
  for (const chunk of raw.split(/[\s,]+/)) {
    if (!chunk) continue;
    const [ticker, weight] = chunk.split(":");
    const symbol = ticker.trim().toUpperCase();
    if (!symbol) continue;
    symbols.push(symbol);
    if (weight && Number(weight) > 0) weights[symbol] = Number(weight);
  }
  return { symbols: [...new Set(symbols)], weights };
}

export function PortfolioPanel({
  state, ticker, onCompare,
}: {
  state: Engine<PortfolioResponse>;
  ticker: string;
  onCompare: (holdings: string[], weights: Record<string, number>) => void;
}) {
  const [raw, setRaw] = useHoldings();
  const guided = useDetail() === "simple";
  const { symbols, weights } = parse(raw);
  const others = symbols.filter((s) => s !== ticker.toUpperCase());

  return (
    <div className="space-y-4 animate-rise">
      <Card accent={PORTFOLIO}>
        <CardHeader>
          <CardTitle>What you already own</CardTitle>
          <span className="font-mono text-[0.65rem] text-ash">
            {others.length} holding{others.length === 1 ? "" : "s"}, stored in this browser
          </span>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-[0.82rem] leading-relaxed text-ash">
            Every other lens here reads one company on its own, which hides the most common
            way a portfolio goes wrong: the candidate is the fourth copy of a bet already
            held. Paste what you own — one symbol per line or comma separated, with{" "}
            <code className="font-mono text-chalk/80">TICKER:WEIGHT</code> if the sizes differ.
          </p>
          <textarea
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            rows={3}
            spellCheck={false}
            aria-label="Holdings"
            placeholder="AAPL, MSFT:2, BBCA.JK"
            className="w-full rounded border border-rule bg-ink px-3 py-2 font-mono text-xs
                       text-chalk placeholder:text-ash/60 focus:border-tech/60
                       focus:outline-none focus-visible:ring-1 focus-visible:ring-tech"
          />
          <div className="flex flex-wrap items-center gap-3">
            <ApplyButton onClick={() => onCompare(others, weights)}
                         busy={state.status === "loading"}
                         disabled={others.length === 0 || !ticker}>
              Compare with {ticker || "this ticker"}
            </ApplyButton>
            <span className="text-[0.68rem] leading-relaxed text-ash">
              Kept in this browser only — this app has no accounts and no database. The list
              is sent to answer this one question and forgotten. It travels in the request
              body rather than the address, which is the one route here that does: a URL is
              logged by every hop that handles it, and a portfolio has no business in a log.
            </span>
          </div>
        </CardBody>
      </Card>

      {state.status === "error" && (
        <Card className="border-dist/40 bg-dist/5">
          <CardBody>
            <div className="flex gap-3">
              <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-dist" />
              <p className="text-sm leading-relaxed text-chalk/80">{state.failure.message}</p>
            </div>
          </CardBody>
        </Card>
      )}

      {state.status === "ready" && <Result data={state.data} guided={guided} />}
    </div>
  );
}

function Result({ data, guided }: { data: PortfolioResponse; guided: boolean }) {
  const ex: ExplainMap = data.explain ?? {};

  if (!data.usable) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm leading-relaxed text-ash">{data.reason}</p>
        </CardBody>
      </Card>
    );
  }

  const independence = data.independence;
  const rows = data.contributions?.rows ?? [];

  return (
    <>
      <Card accent={TONE_HEXish(ex.effectiveHoldings?.tone)}>
        <CardHeader>
          <CardTitle>Is this a bet you already hold?</CardTitle>
          <span className="flex items-center gap-1.5 font-mono text-[0.65rem] text-ash">
            {data.observations} trading days
            <Explain explain={ex.effectiveHoldings} />
          </span>
        </CardHeader>
        <CardBody className="space-y-3">
          {independence && (
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="num text-2xl font-semibold text-chalk">
                {num(independence.after ?? 0, 1)}
              </span>
              <span className="text-[0.82rem] leading-relaxed text-ash">
                independent bets across {independence.withCandidate} positions — from{" "}
                {num(independence.before ?? 0, 1)} across {independence.holdings} before
                adding this one. An unrelated name would have added a full bet.
              </span>
            </div>
          )}
          {ex.effectiveHoldings && (
            <p className={cn("text-[0.82rem] leading-relaxed",
                             TONE_TEXT[ex.effectiveHoldings.tone] ?? "text-chalk/80")}>
              {ex.effectiveHoldings.reading}
            </p>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>How closely it tracks each holding</CardTitle>
          <span className="font-mono text-[0.65rem] text-ash">past year</span>
        </CardHeader>
        <CardBody className="space-y-1.5 text-xs">
          {(data.pairs ?? []).map((pair) => (
            <ExplainedRow key={pair.ticker}
                          label={pair.ticker}
                          value={num(pair.correlation)}
                          explain={ex[`holdingCorrelation.${pair.ticker}`]} />
          ))}
          {(data.missing ?? []).length > 0 && (
            <p className="pt-2 text-[0.7rem] leading-relaxed text-ash">
              Not compared: {(data.missing ?? []).join(", ")} — too few trading days in
              common to mean anything. Dropped rather than estimated.
            </p>
          )}
        </CardBody>
      </Card>

      {rows.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Where the risk actually sits</CardTitle>
            <span className="font-mono text-[0.65rem] text-ash">
              {data.equalWeighted ? "equal weights assumed" : "your weights"}
            </span>
          </CardHeader>
          <CardBody className="px-0">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                  <th>Position</th>
                  <th className="text-right">Share of money</th>
                  <th className="text-right">Share of risk</th>
                  {!guided && <th className="text-right">Volatility</th>}
                </tr>
              </thead>
              <tbody>
                {[...rows].sort((a, b) => b.riskShare - a.riskShare).map((row) => {
                  const explain = ex[`riskShare.${row.ticker}`];
                  return (
                    <tr key={row.ticker} className="border-b border-rule/60 last:border-0">
                      <td className="num px-5 py-2">
                        <span className="flex items-center gap-1.5">
                          {row.ticker}
                          <Explain explain={explain} />
                        </span>
                      </td>
                      <td className="num px-5 py-2 text-right text-ash">
                        {pct(row.weight, 0)}
                      </td>
                      <td className={cn("num px-5 py-2 text-right font-semibold",
                                        explain ? TONE_TEXT[explain.tone] : "text-chalk")}>
                        {pct(row.riskShare, 0)}
                      </td>
                      {!guided && (
                        <td className="num px-5 py-2 text-right text-ash">
                          {pct(row.volatility, 0)}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="px-5 pt-3 text-[0.7rem] leading-relaxed text-ash">
              The two columns are the point. A position holding a tenth of the money and a
              quarter of the risk is not diversified by being one of ten — it is the
              portfolio wearing a smaller name.
            </p>
          </CardBody>
        </Card>
      )}

      {data.stability && (
        <Card>
          <CardHeader>
            <CardTitle>Why this one is allowed to inform position size</CardTitle>
            <span className="font-mono text-[0.65rem] text-ash">
              measured {data.stability.measuredOn}
            </span>
          </CardHeader>
          <CardBody className="space-y-2">
            <p className="text-[0.82rem] leading-relaxed text-chalk/80">
              {data.stability.headline}
            </p>
            <ul className="space-y-1">
              {(data.stability.caveats ?? []).map((caveat) => (
                <li key={caveat} className="flex gap-2 text-[0.7rem] leading-relaxed text-ash">
                  <Layers aria-hidden className="mt-0.5 h-3 w-3 shrink-0" />
                  <span>{caveat}</span>
                </li>
              ))}
            </ul>
            <p className="text-[0.7rem] leading-relaxed text-ash">
              Everything above is price and volume only. The filings do not batch, so there
              is no quality or valuation dimension to this comparison — two companies can
              correlate at 0.9 and be entirely different businesses.
            </p>
          </CardBody>
        </Card>
      )}
    </>
  );
}

/** The accent for a card, from a tone that may be absent. */
function TONE_HEXish(tone?: string): string {
  return tone === "warn" ? "#F2C14E" : tone === "bad" ? "#FF6B6B" : PORTFOLIO;
}
