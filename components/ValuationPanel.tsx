"use client";

import {
  Bar, BarChart, CartesianGrid, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { CornerUpLeft } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle, Note, Stat } from "@/components/ui/card";
import { Explain, ExplainedStat, TONE_TEXT, useDetail } from "@/components/ui/explain";
import { DownloadButton } from "@/components/ui/controls";
import { ValuationControls } from "@/components/ValuationControls";
import type { ValuationOptions } from "@/lib/api";
import type { ExplainMap, ValuationResponse } from "@/lib/types";
import { downloadCsv, toCsv } from "@/lib/csv";
import { cn, num, pct, signedPct, verdictLabel } from "@/lib/utils";

const DCF = "#E8B44C";
const DDM = "#A78BFA";
const MARKET = "#5B8DEF";
const UP = "#35C4A8";
const DOWN = "#FF6B6B";

export function ValuationPanel({
  data, onApply, busy, csvUrl,
}: {
  data: ValuationResponse;
  onApply: (o: ValuationOptions) => void;
  busy: boolean;
  csvUrl: string;
}) {
  const detail = useDetail();
  const simple = detail === "simple";
  const ex: ExplainMap = data.explain ?? {};
  const accent = data.engine === "DDM" ? DDM : DCF;
  const mc = data.monteCarlo;
  const verdictColor =
    data.verdict === "UNDERVALUED" ? UP : data.verdict === "OVERVALUED" ? DOWN : DCF;

  const downloadSchedule = () =>
    downloadCsv(
      `${data.ticker}_${data.engine.toLowerCase()}_schedule.csv`,
      toCsv(
        data.schedule.map((r) => ({
          year: r.year, stream: r.streamRaw,
          discountFactor: r.discountFactor, presentValue: r.presentValueRaw,
        })),
        [
          { key: "year", label: "Year" },
          { key: "stream", label: data.streamLabel },
          { key: "discountFactor", label: "Discount Factor" },
          { key: "presentValue", label: "Present Value" },
        ]
      )
    );

  return (
    <div className="space-y-4 animate-rise">
      {/* Remount on a new company or a new routed engine. Every control below
          holds its value in useState, whose initialiser runs once — without
          this key, manual figures entered for one listing stay loaded and get
          applied to the next one on the first "Re-run valuation", and a DCF's
          10% growth default survives a route into the DDM's 5%. */}
      <ValuationControls
        key={`${data.ticker}:${data.engine}`}
        engine={data.engine}
        rateName={data.rateName}
        currencySymbol={data.market.symbol}
        computedRate={data.discountRate}
        basis={data.assumptions.basis}
        basisOptions={data.assumptions.basisOptions}
        manualDefaults={data.assumptions.manualDefaults}
        manualApplied={data.assumptions.manualApplied}
        busy={busy}
        onApply={onApply}
      />

      {data.notices.map((n, i) => (
        <div key={i}
             className="rounded border px-4 py-3 text-meta leading-relaxed"
             style={{
               borderColor: n.tone === "warn" ? "#F2C14E66" : `${accent}55`,
               background: n.tone === "warn" ? "#F2C14E14" : `${accent}14`,
               color: n.tone === "warn" ? "#F2C14E" : "#E7EEF5",
             }}>
          {n.text}
        </div>
      ))}

      {/* WHAT THIS PANEL IS AND IS NOT, said before the first number rather
          than in a footnote. A discounted cash flow is an opinion with
          arithmetic attached; leading with a single "fair value" invites it to
          be read as a price target, which is the one thing it cannot be. */}
      <Card accent={accent}>
        <CardHeader>
          <CardTitle>What this is worth, and how sure the model is</CardTitle>
          <span className="num text-meta font-semibold" style={{ color: verdictColor }}>
            {verdictLabel(data.verdict)}
          </span>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-base leading-relaxed text-body">
            Today the market prices {data.ticker} at {data.priceLabel}. Projecting the
            {data.engine === "DCF" ? " cash the business generates" :
             data.engine === "DDM" ? " dividends the business pays" :
             " profits earned above the cost of its capital"} forward and discounting them back
            at {pct(data.discountRate, 1)} a year puts it nearer {mc.p50Label} — a range of
            {" "}{mc.p25Label} to {mc.p75Label} once the assumptions are allowed to vary.
          </p>
          <Note tone="warn">
            This is not a price forecast. It is what the business is worth <em>if</em> the growth
            and discount rates below are right — and those are estimates. Which is why the answer
            is a range, and why every input is yours to change.
          </Note>
        </CardBody>
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Market price" value={data.priceLabel}
              sub={data.priceAsOf ? `close of ${data.priceAsOf}`
                                  : data.priceSource ?? undefined} />
        {/* NO `tone` OVERRIDE. Colouring by the sign of `upside` painted a 5%
            gap bright green while `_upside` — which knows that gap is inside
            the noise of a model whose P25-P75 can span 60% — calls it neutral.
            `ExplainedStat` falls back to `explain.tone`, which is the whole
            point of deciding direction once, in Python. */}
        <ExplainedStat label="Model's middle estimate" value={mc.p50Label}
                       explain={ex.upside}
                       sub={`${signedPct(mc.upside)} vs market`} />
        <ExplainedStat explain={ex.valuationSpread}
                       label="Pessimistic to optimistic"
                       value={`${mc.p25Label} – ${mc.p75Label}`} />
        <ExplainedStat explain={ex.probUndervalued} />
        <ExplainedStat explain={ex.terminalShare} />
      </div>

      {/* THE REVERSE DCF, AND IT SITS ABOVE THE FORWARD ONE ON PURPOSE.
          Run forwards the model says "this is worth X" — an answer whose whole
          width comes from assumptions the reader has no basis to judge, and
          which invites being read as a price target. Run backwards it says
          "the market is assuming Y% a year", which is a claim about the world
          a reader can agree or disagree with using things they know about the
          business and the model does not. That is the question worth putting
          first. */}
      {ex.impliedGrowth && (
        <Card accent={accent}>
          <CardBody className="py-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="eyebrow mb-1.5 flex items-center gap-1.5">
                  <CornerUpLeft aria-hidden className="h-3 w-3" />
                  Working the model backwards
                </div>
                <p className="prose-col text-base leading-relaxed text-body">
                  {ex.impliedGrowth.reading}
                </p>
                {/* `action` is 122 words and it is the longest single block on
                    this tab. It belongs where every other `action` lives — behind
                    the info icon — not printed twice the length of the reading it
                    follows. The affordance is right here on the figure. */}
              </div>
              <div className="shrink-0 text-right">
                <div className="eyebrow mb-1 flex items-center justify-end gap-1.5">
                  Implied growth
                  <Explain explain={ex.impliedGrowth} />
                </div>
                <div className={cn("num text-h2 font-semibold leading-none",
                                   TONE_TEXT[ex.impliedGrowth.tone])}>
                  {ex.impliedGrowth.valueText}
                </div>
                <div className="mt-1 text-meta text-ash">
                  a year, for five years
                </div>
                <div className="mt-2 border-t border-rule pt-2 text-micro text-ash">
                  you assumed{" "}
                  <span className="num text-body">{pct(data.baseCase.assumedGrowth)}</span>
                </div>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      <Card accent={accent}>
        <CardHeader>
          <CardTitle>Distribution of simulated fair value</CardTitle>
          <div className="flex items-center gap-2">
            <Badge color={accent}>{data.engine}</Badge>
            <Badge color={verdictColor}>{verdictLabel(data.verdict)}</Badge>
            {/* The full draw set never crosses the wire, so this one is a
                server round trip rather than a client-side export. */}
            <DownloadButton href={csvUrl}>Simulation CSV</DownloadButton>
          </div>
        </CardHeader>
        <CardBody>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={mc.histogram} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="value" type="number" domain={["dataMin", "dataMax"]}
                     tickFormatter={(v) => num(v, 0)} tickLine={false} axisLine={false} />
              <YAxis tickLine={false} axisLine={false} width={48} />
              <Tooltip
                cursor={{ fill: "rgba(255,255,255,0.04)" }}
                contentStyle={{ background: "#080C10", border: "1px solid #1E2A36",
                                borderRadius: 4, fontSize: 12 }}
                labelFormatter={(v) => `Fair value ${num(Number(v))}`}
                formatter={(v: number) => [`${v} iterations`, ""]} />
              <ReferenceArea x1={mc.p25} x2={mc.p75} fill={UP} fillOpacity={0.06} />
              <Bar dataKey="count" fill={accent} fillOpacity={0.55} isAnimationActive={false} />
              <ReferenceLine x={data.price} stroke={MARKET} strokeWidth={2}
                             label={{ value: "Market", fill: MARKET, fontSize: 11, position: "top" }} />
              <ReferenceLine x={mc.p50} stroke={UP} strokeWidth={2} strokeDasharray="5 4"
                             label={{ value: "Median", fill: UP, fontSize: 11, position: "top" }} />
            </BarChart>
          </ResponsiveContainer>
          <p className="mt-3 text-meta leading-relaxed text-ash">
            {data.assumptions.iterations.toLocaleString()} iterations.{" "}
            {data.engine === "DCF" ? "FCF growth" : "Dividend growth"} ~ N({pct(data.assumptions.growth)},{" "}
            {pct(data.assumptions.sdGrowth)}), {data.rateName} ~ N({pct(data.discountRate, 2)},{" "}
            {pct(data.assumptions.sdRate, 2)}), terminal growth ~ N({pct(data.assumptions.terminalGrowth, 2)},{" "}
            {pct(data.assumptions.sdTerminal, 2)}). Display trimmed at the 0.5th/99.5th percentiles;
            every statistic above uses the full sample.
          </p>
        </CardBody>
      </Card>

      {!simple && ex.discountRate && (
        <div className="grid grid-cols-1 gap-3">
          <ExplainedStat explain={ex.discountRate} />
        </div>
      )}

      {/* `minmax(0, …)` AND `min-w-0`, NOT `1.4fr_1fr`. A grid item's automatic minimum
          size is its min-content width, so the projection table below refused to shrink and
          stretched the track past the viewport instead of scrolling inside its own wrapper —
          the whole page scrolled sideways on a phone. The track cap fixes the two-column
          case and `min-w-0` on each child fixes the stacked one. */}
      <div className={simple ? "hidden"
                             : "grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]"}>
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>
              Base-case {data.engine === "DCF" ? "cash flow" : "dividend"} projection
            </CardTitle>
            <div className="flex items-center gap-2">
              <span className="font-mono text-micro text-ash">{data.assumptions.basis}</span>
              <DownloadButton onClick={downloadSchedule}>CSV</DownloadButton>
            </div>
          </CardHeader>
          <CardBody className="px-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-meta">
                <thead>
                  <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                    <th>Year</th>
                    <th className="text-right">{data.streamLabel}</th>
                    <th className="text-right">Discount factor</th>
                    <th className="text-right">Present value</th>
                  </tr>
                </thead>
                <tbody>
                  {data.schedule.map((row) => (
                    <tr key={row.year} className="border-b border-ruleSoft last:border-0">
                      <td className="num px-5 py-2 text-ash">{row.year}</td>
                      <td className="num px-5 py-2 text-right">{row.stream}</td>
                      <td className="num px-5 py-2 text-right text-ash">{row.discountFactor}</td>
                      <td className="num px-5 py-2 text-right">{row.presentValue}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {data.history.length > 0 && (
              <>
                <div className="eyebrow px-5 pb-2 pt-5">
                  {data.engine === "DCF" ? "Historical free cash flow" : "Declared dividend history"}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-meta">
                    <tbody>
                      {data.history.map((row, i) => (
                        <tr key={i} className="border-b border-ruleSoft last:border-0">
                          {Object.values(row).map((cell, j) => (
                            <td key={j} className={`num px-5 py-2 ${j === 0 ? "text-ash" : "text-right"}`}>
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </CardBody>
        </Card>

        <div className="min-w-0 space-y-4">
          <Card accent={accent}>
            <CardHeader>
              <CardTitle>
                {data.engine === "DCF" ? "Enterprise → equity bridge" : "Value composition"}
              </CardTitle>
            </CardHeader>
            <CardBody className="px-0">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-meta">
                  <tbody>
                    {data.bridge.map((row) => (
                      <tr key={row.component} className="border-b border-ruleSoft last:border-0">
                        <td className="px-5 py-2 text-ash">{row.component}</td>
                        <td className="num px-5 py-2 text-right">{row.amount}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle>Model diagnostics</CardTitle></CardHeader>
            <CardBody className="px-0">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-meta">
                  <tbody>
                    {data.diagnostics.map((row) => (
                      <tr key={row.metric} className="border-b border-ruleSoft last:border-0">
                        <td className="px-5 py-2 text-ash">{row.metric}</td>
                        <td className="num px-5 py-2 text-right">{row.value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardBody>
          </Card>
        </div>
      </div>

      <p className="text-meta leading-relaxed text-ash">
        Routed to the {data.engine} because {data.routeReason}. The KPI strip reports the Monte
        Carlo <b className="text-body">median</b>; the bridge reports the{" "}
        <b className="text-body">base case</b>. They differ because the price distribution is
        right-skewed in 1/(r − g). Data from Yahoo Finance, unaudited. A research tool, not
        investment advice.
      </p>
    </div>
  );
}
