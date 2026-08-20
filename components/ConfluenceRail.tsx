"use client";

import type {
  AnomalyResponse, Engine, QualityResponse, TechnicalResponse, ValuationResponse,
} from "@/lib/types";
import { pct, signedPct } from "@/lib/utils";

const ACC = "#35C4A8";
const DIST = "#FF6B6B";
const TECH = "#5B8DEF";
const DCF = "#E8B44C";
const DDM = "#A78BFA";
const QUAL = "#E8B44C";
const ASH = "#7A8CA0";

interface Reading {
  lens: string;
  verdict: string;
  detail: string;
  color: string;
  /** -1 bearish, 0 neutral, +1 bullish. Used only for the agreement count. */
  vote: number;
}

/**
 * Votes with the RECENT flow bias, not the all-time one.
 *
 * `netFlowBias` sums flow across every anomaly in the look-back — on the default
 * 2y period that is a two-year verdict. Setting it beside a live trend reading
 * and a current valuation implied the three lenses were describing the same
 * moment, when one of them was averaging over two years. The all-time figure is
 * still shown in the anomaly panel, labelled with its horizon.
 */
function readAnomaly(state: Engine<AnomalyResponse>): Reading {
  if (state.status !== "ready")
    return { lens: "Flow", verdict: "—", detail: "no reading", color: ASH, vote: 0 };
  const { stats } = state.data;
  const bias = stats.recentFlowBias;
  const color = bias === "Accumulation" ? ACC : bias === "Distribution" ? DIST : ASH;
  const drift =
    stats.netFlowBias !== bias ? ` · ${stats.netFlowBias.toLowerCase()} over the full window` : "";
  return {
    lens: "Flow",
    verdict: stats.recentCount === 0 ? "Quiet" : bias,
    detail:
      stats.recentCount === 0
        ? `no anomalies in the last ${stats.recentDays} days · ${stats.anomalyCount} across the window`
        : `${stats.recentCount} event${stats.recentCount === 1 ? "" : "s"} in the last ${stats.recentDays} days · peak strength ${stats.maxStrength}${drift}`,
    color: stats.recentCount === 0 ? ASH : color,
    vote:
      stats.recentCount === 0 ? 0 : bias === "Accumulation" ? 1 : bias === "Distribution" ? -1 : 0,
  };
}

function readTechnical(state: Engine<TechnicalResponse>): Reading {
  if (state.status !== "ready")
    return { lens: "Trend", verdict: "—", detail: "no reading", color: ASH, vote: 0 };
  const { summary, latest } = state.data;
  const tone = summary.trend_tone;
  const color = tone === "bull" ? ACC : tone === "bear" ? DIST : TECH;
  const momentum = summary.chips.find((c) => c.label === "Momentum (RSI)")?.value ?? "—";
  return {
    lens: "Trend",
    verdict: summary.trend,
    detail: `${momentum} · last close ${latest.close.toFixed(2)} (${latest.changePct >= 0 ? "+" : ""}${latest.changePct.toFixed(2)}%)`,
    color,
    vote: tone === "bull" ? 1 : tone === "bear" ? -1 : 0,
  };
}

function readValuation(state: Engine<ValuationResponse>): Reading {
  if (state.status !== "ready")
    return { lens: "Value", verdict: "—", detail: "no reading", color: ASH, vote: 0 };
  const d = state.data;
  const color =
    d.verdict === "UNDERVALUED" ? ACC : d.verdict === "OVERVALUED" ? DIST
      : d.engine === "DDM" ? DDM : DCF;
  return {
    lens: "Value",
    verdict: d.verdict.charAt(0) + d.verdict.slice(1).toLowerCase(),
    detail: `${d.engine} median ${d.monteCarlo.p50Label} · ${signedPct(d.monteCarlo.upside)} vs market · P(under) ${pct(d.monteCarlo.probUndervalued, 0)}`,
    color,
    vote: d.verdict === "UNDERVALUED" ? 1 : d.verdict === "OVERVALUED" ? -1 : 0,
  };
}

function readQuality(state: Engine<QualityResponse>): Reading {
  if (state.status !== "ready")
    return { lens: "Quality", verdict: "—", detail: "no reading", color: ASH, vote: 0 };
  const d = state.data;
  if (!d.applicable)
    return {
      lens: "Quality", verdict: "n/a",
      detail: "the three accounting models do not apply to financials",
      color: ASH, vote: 0,
    };

  const parts: string[] = [];
  if (d.piotroski) parts.push(`F-Score ${d.piotroski.score}/${d.piotroski.maxScore}`);
  if (d.altman?.score != null) parts.push(`Z'' ${d.altman.score.toFixed(1)} (${d.altman.band})`);
  if (d.beneish?.score != null) parts.push(`M ${d.beneish.score.toFixed(2)}`);

  return {
    lens: "Quality",
    verdict: d.verdict === "SOUND" ? "Sound"
      : d.verdict === "CONCERNS" ? "Concerns" : "Neutral",
    detail: parts.join(" · ") || (d.headline ?? ""),
    color: d.verdict === "SOUND" ? ACC : d.verdict === "CONCERNS" ? DIST : QUAL,
    vote: d.verdict === "SOUND" ? 1 : d.verdict === "CONCERNS" ? -1 : 0,
  };
}

/**
 * The one view none of the three source apps could produce: what the flow model,
 * the trend model and the valuation model each conclude, side by side, and
 * whether they agree. Agreement is the finding — three independent methods
 * landing in the same place is worth more than any one of them alone.
 */
export function ConfluenceRail({
  ticker, anomaly, technical, valuation, quality,
}: {
  ticker: string;
  anomaly: Engine<AnomalyResponse>;
  technical: Engine<TechnicalResponse>;
  valuation: Engine<ValuationResponse>;
  quality: Engine<QualityResponse>;
}) {
  const readings = [readAnomaly(anomaly), readTechnical(technical),
                    readValuation(valuation), readQuality(quality)];
  const live = readings.filter((r) => r.verdict !== "—" && r.verdict !== "n/a");
  const votes = live.map((r) => r.vote);
  const bulls = votes.filter((v) => v > 0).length;
  const bears = votes.filter((v) => v < 0).length;

  let agreement = "Mixed signals";
  let agreementColor = ASH;
  if (live.length === 0) {
    agreement = "Awaiting data";
  } else if (bulls === live.length && bulls > 1) {
    agreement = `All ${bulls} lenses constructive`;
    agreementColor = ACC;
  } else if (bears === live.length && bears > 1) {
    agreement = `All ${bears} lenses negative`;
    agreementColor = DIST;
  } else if (bulls > bears) {
    agreement = `${bulls} of ${live.length} constructive`;
    agreementColor = ACC;
  } else if (bears > bulls) {
    agreement = `${bears} of ${live.length} negative`;
    agreementColor = DIST;
  }

  return (
    <section className="animate-rise rounded border border-rule bg-panel">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-rule px-5 py-3">
        <div className="flex items-baseline gap-3">
          <h2 className="font-mono text-lg font-semibold tracking-[0.14em]">{ticker}</h2>
          <span className="eyebrow">{live.length || "no"} lenses reading</span>
        </div>
        <span className="num text-xs font-semibold" style={{ color: agreementColor }}>
          {agreement}
        </span>
      </div>
      <div className="border-b border-rule px-5 py-2">
        {/* Agreement is the product's headline claim, so its main weakness
            belongs next to it rather than in a footnote. */}
        <p className="text-[0.68rem] leading-relaxed text-ash">
          These lenses are not fully independent: flow and trend are both functions of the same
          price and volume series, so they agree more often than four unrelated tests would.
          Value and quality read the filings instead and carry most of the independent
          information.
        </p>
      </div>

      <div className="grid divide-y divide-rule sm:grid-cols-2 sm:divide-x lg:grid-cols-4 lg:divide-y-0">
        {readings.map((r) => (
          <div key={r.lens} className="relative px-5 py-4">
            <span aria-hidden className="absolute left-0 top-4 h-[calc(100%-2rem)] w-[2px]"
                  style={{ background: r.color, opacity: r.verdict === "—" ? 0.25 : 1 }} />
            <div className="eyebrow mb-1">{r.lens}</div>
            <div className="num text-lg font-semibold leading-tight" style={{ color: r.color }}>
              {r.verdict}
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ash">{r.detail}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
