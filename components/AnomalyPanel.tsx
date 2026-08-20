"use client";

import {
  Area, AreaChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer,
  Scatter, Tooltip, XAxis, YAxis,
} from "recharts";
import type { TooltipProps } from "recharts";
import { Card, CardBody, CardHeader, CardTitle, Stat } from "@/components/ui/card";
import { DownloadButton } from "@/components/ui/controls";
import type { AnomalyPoint, AnomalyResponse } from "@/lib/types";
import { downloadCsv, toCsv } from "@/lib/csv";
import { cn, num, pct } from "@/lib/utils";

const ACC = "#35C4A8";
const DIST = "#FF6B6B";
const NEU = "#7A8CA0";

const flowColor = (flow?: string | null) =>
  flow === "Accumulation" ? ACC : flow === "Distribution" ? DIST : NEU;

/** A series row plus the per-flow columns the Scatter layers read. */
type ChartPoint = AnomalyPoint & {
  acc: number | null;
  dist: number | null;
  neu: number | null;
};

function AnomalyTooltip({ active, payload }: TooltipProps<number, string>) {
  // Recharts types `payload[n].payload` as the untyped source row; this is the
  // one place the cast belongs, and ChartPoint is exactly what we put in.
  const p = payload?.[0]?.payload as ChartPoint | undefined;
  if (!active || !p) return null;
  return (
    <div className="rounded border border-rule bg-ink/95 px-3 py-2 text-xs shadow-xl">
      <div className="num mb-1 text-ash">{p.date}</div>
      <div className="num">Close {num(p.close)}</div>
      {p.isAnomaly && (
        <>
          <div className="mt-1" style={{ color: flowColor(p.flow) }}>{p.flow}</div>
          <div className="num text-ash">Strength {p.strength}/100</div>
          <div className="num text-ash">RVOL {num(p.rvol)}x · MFI {num(p.mfi, 0)}</div>
        </>
      )}
    </div>
  );
}

export function AnomalyPanel({ data }: { data: AnomalyResponse }) {
  const { stats, series, anomalies, config } = data;

  // Recharts renders a Scatter by reading one key off every row, so each flow
  // class gets its own column that is null everywhere it does not apply.
  const chartData = series.map((p) => ({
    ...p,
    acc: p.flow === "Accumulation" ? p.close : null,
    dist: p.flow === "Distribution" ? p.close : null,
    neu: p.isAnomaly && p.flow === "Neutral" ? p.close : null,
  }));

  // The chart and the OBV fill follow the CURRENT reading, not the two-year one.
  const biasColor = flowColor(stats.recentFlowBias);
  const toneOf = (bias: string) =>
    bias === "Accumulation" ? "text-acc" : bias === "Distribution" ? "text-dist" : "text-ash";

  const downloadAnomalies = () =>
    downloadCsv(
      `${data.ticker}_anomaly_extract.csv`,
      toCsv(anomalies, [
        { key: "date", label: "Date" }, { key: "close", label: "Close" },
        { key: "rvol", label: "RVOL (x)" },
        { key: "priceChangePct", label: "Price change (%)" },
        { key: "mfi", label: "MFI" }, { key: "flow", label: "Flow" },
        { key: "tag", label: "Tag" }, { key: "strength", label: "Strength" },
        { key: "anomalyScore", label: "Anomaly Score" },
      ])
    );

  return (
    <div className="space-y-4 animate-rise">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Latest close" value={num(stats.latestClose)} />
        <Stat label="Anomalies found" value={stats.anomalyCount}
              sub={`${pct(stats.anomalyRate)} of ${stats.totalDays} days`} />
        {/* Two horizons, kept apart on purpose. The all-time figure summarises
            the whole look-back; only the recent one describes where flow is
            now, and that is what the confluence view votes with. */}
        <Stat label={`Flow bias · last ${stats.recentDays}d`} value={stats.recentFlowBias}
              tone={toneOf(stats.recentFlowBias)}
              sub={`${stats.recentCount} fresh event${stats.recentCount === 1 ? "" : "s"}`} />
        <Stat label={`Flow bias · full ${config.period}`} value={stats.netFlowBias}
              tone={toneOf(stats.netFlowBias)}
              sub="whole look-back" />
        <Stat label="Peak strength" value={`${stats.maxStrength}/100`} />
      </div>

      <Card accent={biasColor}>
        <CardHeader>
          <CardTitle>Price with detected anomalies</CardTitle>
          <div className="flex flex-wrap items-center gap-3 text-[0.68rem] text-ash">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rotate-45" style={{ background: ACC }} /> Accumulation
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rotate-45" style={{ background: DIST }} /> Distribution
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: NEU }} /> Neutral
            </span>
          </div>
        </CardHeader>
        <CardBody>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={48} />
              <YAxis domain={["auto", "auto"]} tickLine={false} axisLine={false} width={56} />
              <Tooltip content={<AnomalyTooltip />} />
              <Line type="monotone" dataKey="close" stroke="#5B8DEF" strokeWidth={1.4}
                    dot={false} isAnimationActive={false} />
              <Scatter dataKey="acc" fill={ACC} shape="triangle" isAnimationActive={false} />
              <Scatter dataKey="dist" fill={DIST} shape="triangle" isAnimationActive={false} />
              <Scatter dataKey="neu" fill={NEU} shape="circle" isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>

          <div className="eyebrow mt-4 mb-1">On-balance volume</div>
          <ResponsiveContainer width="100%" height={90}>
            <AreaChart data={chartData} margin={{ top: 2, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="obvFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={biasColor} stopOpacity={0.30} />
                  <stop offset="100%" stopColor={biasColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" hide />
              <YAxis hide domain={["auto", "auto"]} />
              <Area type="monotone" dataKey="obv" stroke={biasColor} strokeWidth={1}
                    fill="url(#obvFill)" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Event log · ranked by strength</CardTitle>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[0.65rem] text-ash">
              {config.mode} · {config.period}
              {config.mode === "threshold" && ` · cutoff ${config.scoreThreshold}`}
              {config.mode === "quota" && ` · ${pct(config.contamination)}`}
              {config.mode === "mad" && ` · ${config.madK} MAD`}
            </span>
            {anomalies.length > 0 && (
              <DownloadButton onClick={downloadAnomalies}>CSV</DownloadButton>
            )}
          </div>
        </CardHeader>
        <CardBody className="px-0">
          {anomalies.length === 0 ? (
            <p className="px-5 text-sm text-ash">
              No day in this window crossed the detection threshold. That is a result, not a
              failure — the cutoff is absolute, so a calm stock genuinely returns nothing.
            </p>
          ) : (
            <div className="max-h-[22rem] overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-panel">
                  <tr className="eyebrow border-b border-rule [&>th]:px-5 [&>th]:py-2 [&>th]:font-normal">
                    <th>Date</th><th>Flow</th><th>Tag</th>
                    <th className="text-right">RVOL</th>
                    <th className="text-right">Δ price</th>
                    <th className="text-right">MFI</th>
                    <th className="w-32">Strength</th>
                  </tr>
                </thead>
                <tbody>
                  {anomalies.map((a) => (
                    <tr key={a.date} className="border-b border-rule/60 last:border-0 hover:bg-raised/60">
                      <td className="num px-5 py-2 text-ash">{a.date}</td>
                      <td className="px-5 py-2" style={{ color: flowColor(a.flow) }}>{a.flow}</td>
                      <td className="px-5 py-2 text-ash">{a.tag}</td>
                      <td className="num px-5 py-2 text-right">{num(a.rvol)}x</td>
                      <td className={cn("num px-5 py-2 text-right",
                                        a.priceChangePct >= 0 ? "text-acc" : "text-dist")}>
                        {a.priceChangePct >= 0 ? "+" : ""}{num(a.priceChangePct)}%
                      </td>
                      <td className="num px-5 py-2 text-right">{num(a.mfi, 0)}</td>
                      <td className="px-5 py-2">
                        <div className="flex items-center gap-2">
                          <div className="h-1 flex-1 rounded bg-rule">
                            <div className="h-full rounded"
                                 style={{ width: `${a.strength}%`, background: flowColor(a.flow) }} />
                          </div>
                          <span className="num w-6 text-right text-[0.7rem] text-ash">{a.strength}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      <p className="text-xs leading-relaxed text-ash">
        Isolation Forest over six behavioural features (return, RVOL, |return|, MFI, OBV z-score,
        intraday range), 200 estimators, seed 42, fit with{" "}
        <span className="font-mono text-chalk/80">contamination=&quot;auto&quot;</span> so the
        decision score is an absolute scale and the anomaly count floats with the regime rather
        than being pinned to a fixed percentage. Flow is a four-way vote of OBV direction, A/D
        direction, MFI level and price direction. Anomalous activity has many benign causes —
        index rebalances, dividends, options expiry.
      </p>
    </div>
  );
}
