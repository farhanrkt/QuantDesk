"use client";

import { Check, Minus, X } from "lucide-react";
import { Card, CardBody, CardHeader, CardTitle, Stat } from "@/components/ui/card";
import type { QualityResponse } from "@/lib/types";
import { num } from "@/lib/utils";

const GOOD = "#35C4A8";
const BAD = "#FF6B6B";
const WARN = "#F2C14E";
const ASH = "#7A8CA0";

const BAND_COLOR: Record<string, string> = {
  strong: GOOD, solid: GOOD, safe: GOOD, clean: GOOD,
  mixed: ASH, grey: WARN, borderline: WARN,
  weak: BAD, distress: BAD, flagged: BAD,
  unknown: ASH,
};

/**
 * Engine 4 — the lens that opens the filings.
 *
 * The other three read the company from the outside: price, volume, cash flow
 * projections. None of them asks whether the business is solvent or whether the
 * earnings are real. A DCF on a company sliding toward insolvency is arithmetic,
 * and this is the panel that says so before the reader acts on it.
 */
export function QualityPanel({ data }: { data: QualityResponse }) {
  if (!data.applicable) {
    return (
      <Card className="animate-rise">
        <CardHeader><CardTitle>Accounting quality</CardTitle></CardHeader>
        <CardBody>
          <p className="text-sm leading-relaxed text-ash">{data.reason}</p>
          {data.sector && (
            <p className="mt-3 font-mono text-[0.65rem] uppercase tracking-[0.1em] text-ash">
              {data.sector}{data.industry ? ` · ${data.industry}` : ""}
            </p>
          )}
        </CardBody>
      </Card>
    );
  }

  const { piotroski, altman, beneish } = data;
  const verdictColor =
    data.verdict === "SOUND" ? GOOD : data.verdict === "CONCERNS" ? BAD : ASH;

  return (
    <div className="space-y-4 animate-rise">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Verdict" value={data.verdict ?? "—"}
              tone={data.verdict === "SOUND" ? "text-acc"
                    : data.verdict === "CONCERNS" ? "text-dist" : "text-ash"}
              sub={data.headline} />
        {piotroski && (
          <Stat label="Piotroski F-Score" value={`${piotroski.score}/${piotroski.maxScore}`}
                sub={piotroski.band}
                tone={piotroski.band === "weak" ? "text-dist"
                      : piotroski.band === "mixed" ? "text-ash" : "text-acc"} />
        )}
        {altman && (
          <Stat label="Altman Z''-score (EM)"
                value={altman.score === null ? "—" : num(altman.score)}
                sub={altman.band}
                tone={altman.band === "distress" ? "text-dist"
                      : altman.band === "grey" ? "text-warn" : "text-acc"} />
        )}
        {beneish && (
          <Stat label="Beneish M-Score"
                value={beneish.score === null ? "—" : num(beneish.score)}
                sub={`${beneish.band} · ${beneish.indicesAvailable}/${beneish.indicesTotal} indices`}
                tone={beneish.band === "flagged" ? "text-dist"
                      : beneish.band === "borderline" ? "text-warn" : "text-acc"} />
        )}
      </div>

      {piotroski && piotroski.signals.length > 0 && (
        <Card accent={verdictColor}>
          <CardHeader>
            <CardTitle>Piotroski signals</CardTitle>
            <span className="font-mono text-[0.65rem] text-ash">
              {piotroski.signalsAvailable} of {piotroski.signalsTotal} computable
            </span>
          </CardHeader>
          <CardBody className="px-0">
            <ul>
              {piotroski.signals.map((signal) => (
                <li key={signal.name}
                    className="flex items-baseline gap-3 border-b border-rule/60 px-5 py-2 last:border-0">
                  <span className="mt-0.5 shrink-0">
                    {signal.passed === null
                      ? <Minus aria-label="not computable" className="h-3.5 w-3.5 text-ash" />
                      : signal.passed
                        ? <Check aria-label="pass" className="h-3.5 w-3.5 text-acc" />
                        : <X aria-label="fail" className="h-3.5 w-3.5 text-dist" />}
                  </span>
                  <span className="flex-1 text-xs text-chalk/90">{signal.name}</span>
                  <span className="num shrink-0 text-[0.7rem] text-ash">{signal.detail}</span>
                </li>
              ))}
            </ul>
            <p className="px-5 pt-3 text-[0.7rem] leading-relaxed text-ash">
              A signal that could not be computed scores nothing — it is never counted as a
              pass, which is why the denominator moves with data coverage.
            </p>
          </CardBody>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {altman && (
          <Card accent={BAND_COLOR[altman.band] ?? ASH}>
            <CardHeader><CardTitle>Distress risk</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              <p className="text-sm leading-relaxed text-chalk/80">{altman.reading}</p>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[0.7rem]">
                {Object.entries(altman.components).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-2">
                    <dt className="text-ash">{LABELS[key] ?? key}</dt>
                    <dd className="num text-chalk/80">{value === null ? "—" : num(value)}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-[0.68rem] leading-relaxed text-ash">
                Altman&apos;s Z&apos;&apos; with the emerging-market constant, so the scale is
                the same for an IDX listing and a US one. Safe above 5.85, distress below 4.35.
              </p>
            </CardBody>
          </Card>
        )}

        {beneish && (
          <Card accent={BAND_COLOR[beneish.band] ?? ASH}>
            <CardHeader><CardTitle>Earnings manipulation screen</CardTitle></CardHeader>
            <CardBody className="space-y-3">
              <p className="text-sm leading-relaxed text-chalk/80">{beneish.reading}</p>
              <dl className="grid grid-cols-4 gap-x-3 gap-y-1 text-[0.7rem]">
                {Object.entries(beneish.indices).map(([key, value]) => (
                  <div key={key} className="flex flex-col">
                    <dt className="font-mono text-[0.6rem] uppercase text-ash">{key}</dt>
                    <dd className="num text-chalk/80">{value === null ? "—" : num(value)}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-[0.68rem] leading-relaxed text-ash">
                A screen, not a finding. Beneish classified roughly three-quarters of known
                manipulators correctly — which on a population where manipulation is rare also
                means most flags are false positives.
              </p>
            </CardBody>
          </Card>
        )}
      </div>

      <p className="text-xs leading-relaxed text-ash">
        Piotroski (2000) scores nine fundamental trends; Altman&apos;s Z&apos;&apos;-score (2005
        emerging-market variant) estimates distance from distress; Beneish (1999) screens accrual
        patterns. All three were built on non-financial firms and are not reported for banks or
        insurers. Educational and research use only.
      </p>
    </div>
  );
}

const LABELS: Record<string, string> = {
  workingCapitalToAssets: "Working capital / assets",
  retainedToAssets: "Retained earnings / assets",
  ebitToAssets: "EBIT / assets",
  equityToLiabilities: "Equity / liabilities",
};
