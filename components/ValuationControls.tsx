"use client";

import { useState } from "react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { useDetail } from "@/components/ui/explain";
import {
  ApplyButton, Disclosure, Field, NumberField, PercentField, SelectField, Toggle,
} from "@/components/ui/controls";
import type { ValuationOptions } from "@/lib/api";
import type { ManualInputs } from "@/lib/types";
import { useT } from "@/lib/i18n";
import { label as wordFor } from "@/lib/labels";

/**
 * Every assumption the valuation engine accepts, as a control.
 *
 * These all existed as sidebar widgets in the original Streamlit app and as
 * query parameters on the API, but nothing in the UI ever sent them — so every
 * valuation ran on the stock 10% / 2.5% defaults with no way to change them.
 *
 * `engineDefaults` mirrors api/_lib/valuation.py DEFAULTS so an unedited form
 * posts exactly what the engine would have chosen on its own.
 */

const ENGINE_DEFAULTS = {
  DCF: { growth: 0.10, terminal: 0.025, sdGrowth: 0.020, sdRate: 0.010, sdTerminal: 0.005 },
  DDM: { growth: 0.05, terminal: 0.025, sdGrowth: 0.015, sdRate: 0.010, sdTerminal: 0.005 },
  // Residual income: the "growth" slot carries the sustained ROE, and there is
  // no terminal growth — abnormal earnings fade at a fixed persistence instead.
  RI: { growth: 0.12, terminal: 0.0, sdGrowth: 0.030, sdRate: 0.010, sdTerminal: 0.0 },
} as const;

/**
 * The manual form on its own, for the failure case.
 *
 * When the engine returns `manualRequired` there is no valuation payload, so
 * the full Assumptions card cannot render — and telling the user to "open
 * Assumptions → Manual input mode" would point at a panel that is not on the
 * page. This puts the same fields directly in the error card, prefilled with
 * whatever the fetch did manage to return.
 *
 * Which fields to show is inferred from the shape of `suggested`: the DCF path
 * sends a `netDebt` key, the DDM path sends `payout`.
 */
export function ManualRescue({
  suggested, engine, busy, onApply,
}: {
  suggested: ManualInputs;
  /** Stated by the server. Never inferred from the shape of `suggested`. */
  engine?: "DCF" | "DDM" | "RI";
  busy: boolean;
  onApply: (o: ValuationOptions) => void;
}) {
  const t = useT();
  // Fall back to the old shape inference only for a failure that predates the
  // server sending `engine` — and never let it produce "RI", which it cannot
  // distinguish from DDM.
  const resolved: "DCF" | "DDM" | "RI" =
    engine ?? (suggested.payout !== undefined && suggested.netDebt == null ? "DDM" : "DCF");
  const isDcf = resolved === "DCF";
  const isRi = resolved === "RI";
  const [manual, setManual] = useState<ManualInputs>({
    // A negative base is what triggered the failure; do not prefill it back in.
    base: suggested.base != null && suggested.base > 0 ? suggested.base : null,
    netDebt: suggested.netDebt ?? null,
    shares: suggested.shares ?? null,
    price: suggested.price ?? null,
    payout: suggested.payout ?? null,
  });
  const set = (key: keyof ManualInputs) => (v: number | null) =>
    setManual((prev) => ({ ...prev, [key]: v }));

  return (
    <div className="mt-4 space-y-3 border-t border-ruleSoft pt-4">
      <div className="eyebrow">{t("Supply the missing figures")}</div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Field label={isRi ? t("Book value per share")
                      : isDcf ? t("Base free cash flow") : t("Annual dividend / share")}>
          <NumberField value={manual.base} onChange={set("base")} step={isDcf ? 1e8 : 0.01} />
        </Field>
        {isDcf && (
          <>
            <Field label={t("Net debt")} hint={t("Debt − cash.")}>
              <NumberField value={manual.netDebt} onChange={set("netDebt")} step={1e8} />
            </Field>
            <Field label={t("Shares outstanding")}>
              <NumberField value={manual.shares} onChange={set("shares")} step={1e6} min={1} />
            </Field>
          </>
        )}
        <Field label={t("Share price")}>
          <NumberField value={manual.price} onChange={set("price")} step={0.01} min={0} />
        </Field>
        {!isDcf && (
          <Field label={t("Payout ratio")}
                 hint={isRi ? t("Sets how fast book value compounds.") : t("Diagnostic only.")}>
            <PercentField value={manual.payout} onChange={set("payout")} step={1} min={0} max={1} />
          </Field>
        )}
      </div>
      <ApplyButton
        onClick={() => onApply({ engine: resolved.toLowerCase(), manual })}
        busy={busy}
      >
        {t("Value with these figures")}
      </ApplyButton>
    </div>
  );
}

export interface ValuationControlsProps {
  engine: "DCF" | "DDM" | "RI";
  rateName: string;
  currencySymbol: string;
  computedRate: number;
  basis: string;
  basisOptions: string[];
  manualDefaults: ManualInputs;
  manualApplied: Record<string, boolean>;
  /** Open the manual section straight away after a manualRequired failure. */
  manualFirst?: boolean;
  busy: boolean;
  onApply: (opts: ValuationOptions) => void;
}

export function ValuationControls({
  engine, rateName, currencySymbol, computedRate, basis, basisOptions,
  manualDefaults, manualApplied, manualFirst, busy, onApply,
}: ValuationControlsProps) {
  const t = useT();
  const d = ENGINE_DEFAULTS[engine];

  const [engineChoice, setEngineChoice] = useState("auto");
  const [growth, setGrowth] = useState<number | null>(d.growth);
  const [terminal, setTerminal] = useState<number | null>(d.terminal);
  const [overrideRate, setOverrideRate] = useState(false);
  const [rate, setRate] = useState<number | null>(computedRate);
  const [nSims, setNSims] = useState(10000);
  const [seed, setSeed] = useState(42);
  const [sdGrowth, setSdGrowth] = useState<number | null>(d.sdGrowth);
  const [sdRate, setSdRate] = useState<number | null>(d.sdRate);
  const [sdTerminal, setSdTerminal] = useState<number | null>(d.sdTerminal);
  const [basisChoice, setBasisChoice] = useState(basis);

  const [manual, setManual] = useState<ManualInputs>({
    base: manualDefaults.base ?? null,
    netDebt: manualDefaults.netDebt ?? null,
    shares: manualDefaults.shares ?? null,
    price: manualDefaults.price ?? null,
    payout: manualDefaults.payout ?? null,
  });
  const [useManual, setUseManual] = useState(
    Boolean(manualFirst) || Object.values(manualApplied ?? {}).some(Boolean)
  );
  const setManualField = (key: keyof ManualInputs) => (v: number | null) =>
    setManual((prev) => ({ ...prev, [key]: v }));

  const reset = () => {
    setEngineChoice("auto");
    setGrowth(d.growth); setTerminal(d.terminal);
    setOverrideRate(false); setRate(computedRate);
    setNSims(10000); setSeed(42);
    setSdGrowth(d.sdGrowth); setSdRate(d.sdRate); setSdTerminal(d.sdTerminal);
    setBasisChoice(basisOptions[0] ?? basis);
    setUseManual(false);
    onApply({});
  };

  const apply = () =>
    onApply({
      engine: engineChoice,
      growth: growth ?? undefined,
      terminal: terminal ?? undefined,
      rate: overrideRate ? rate ?? undefined : undefined,
      nSims,
      sdGrowth: sdGrowth ?? undefined,
      sdRate: sdRate ?? undefined,
      sdTerminal: sdTerminal ?? undefined,
      seed,
      basis: basisChoice,
      manual: useManual ? manual : undefined,
    });

  const streamLabel = engine === "DCF" ? t("free cash flow")
    : engine === "RI" ? t("book value per share") : t("dividend per share");
  const rateLabel = wordFor(rateName);

  // COLLAPSED IN GUIDED, NEVER REMOVED. This form is seventeen inputs deep and
  // it is the most powerful thing on the Value tab — the whole point of a DCF is
  // that you change the assumptions and watch the answer move. A beginner should
  // not meet it before they have read the verdict; they should absolutely meet
  // it afterwards, which is why the summary invites them in rather than hiding
  // the fact that it exists.
  const guided = useDetail() === "simple";

  const body = (
    <CardBody className="space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <Field label={t("Engine")} hint={t("Auto routes financials to the DDM.")}>
            <SelectField value={engineChoice} onChange={setEngineChoice}
                         options={[
                           { value: "auto", label: t("Auto (sector routing)") },
                           { value: "dcf", label: t("Force DCF") },
                           { value: "ddm", label: t("Force DDM") },
                           { value: "ri", label: t("Force residual income") },
                         ]} />
          </Field>
          <Field label={engine === "DCF" ? t("FCF growth Y1–Y5")
                        : engine === "RI" ? t("Sustained return on equity")
                        : t("Dividend growth Y1–Y5")}>
            <PercentField value={growth} onChange={setGrowth} step={0.5} min={-0.5} max={1} />
          </Field>
          {engine !== "RI" && (
            <Field label={t("Perpetual growth")} hint={t("At or below long-run nominal GDP.")}>
              <PercentField value={terminal} onChange={setTerminal} step={0.1} min={0} max={0.05} />
            </Field>
          )}
          <Field label={engine === "DCF" ? t("Base FCF anchor") : t("Base DPS anchor")}>
            <SelectField value={basisChoice} onChange={setBasisChoice}
                         options={(basisOptions.length ? basisOptions : [basis])
                           .map((option) => ({ value: option, label: wordFor(option) }))} />
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <Field label={rateLabel}
                 hint={overrideRate ? t("Manual.")
                   : t("Computed: {rate}%", { rate: (computedRate * 100).toFixed(2) })}>
            <PercentField value={overrideRate ? rate : computedRate} onChange={setRate}
                          step={0.25} min={0.0001} max={0.5} disabled={!overrideRate} />
          </Field>
          <div className="flex items-end pb-1">
            <Toggle checked={overrideRate} onChange={setOverrideRate}
                    label={t("Override {rate}", { rate: rateLabel })} />
          </div>
          <Field label={t("Iterations")}>
            <SelectField value={String(nSims)} onChange={(v) => setNSims(Number(v))}
                         options={["1000", "5000", "10000", "25000"]} />
          </Field>
          <Field label={t("Random seed")} hint={t("Fixed seed keeps runs reproducible.")}>
            <NumberField value={seed} onChange={(v) => setSeed(v ?? 42)} min={0} max={10000} />
          </Field>
        </div>

        <Disclosure summary={t("Monte Carlo dispersion (σ)")}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Field label={t("σ Growth")}>
              <PercentField value={sdGrowth} onChange={setSdGrowth} step={0.25} min={0} max={0.2} />
            </Field>
            <Field label={`σ ${rateLabel}`}>
              <PercentField value={sdRate} onChange={setSdRate} step={0.25} min={0} max={0.1} />
            </Field>
            <Field label={t("σ Terminal growth")}>
              <PercentField value={sdTerminal} onChange={setSdTerminal} step={0.1} min={0} max={0.05} />
            </Field>
          </div>
        </Disclosure>

        <Disclosure summary={t("Manual input mode")} defaultOpen={useManual}>
          <div className="space-y-3">
            <p className="text-meta leading-relaxed text-ash">
              {t("For when Yahoo has gaps in the filings — common on smaller IDX listings. Supply the figures yourself and they replace the fetched ones. Amounts are absolute, in")}{" "}
              <span className="font-mono text-body">{currencySymbol}</span>.
            </p>
            <Toggle checked={useManual} onChange={setUseManual}
                    label={t("Use the figures below instead of Yahoo's")} />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <Field label={t("Base {stream}", { stream: streamLabel })}>
                <NumberField value={manual.base} onChange={setManualField("base")}
                             disabled={!useManual} step={engine === "DCF" ? 1e8 : 0.01} />
              </Field>
              {engine === "DCF" && (
                <>
                  <Field label={t("Net debt")} hint={t("Debt − cash.")}>
                    <NumberField value={manual.netDebt} onChange={setManualField("netDebt")}
                                 disabled={!useManual} step={1e8} />
                  </Field>
                  <Field label={t("Shares outstanding")}>
                    <NumberField value={manual.shares} onChange={setManualField("shares")}
                                 disabled={!useManual} step={1e6} min={1} />
                  </Field>
                </>
              )}
              <Field label={t("Share price")}>
                <NumberField value={manual.price} onChange={setManualField("price")}
                             disabled={!useManual} step={0.01} min={0} />
              </Field>
              {engine !== "DCF" && (
                <Field label={t("Payout ratio")}
                       hint={engine === "RI" ? t("Sets how fast book value compounds.")
                                             : t("Diagnostic only — not the valuation.")}>
                  <PercentField value={manual.payout} onChange={setManualField("payout")}
                                disabled={!useManual} step={1} min={0} max={1} />
                </Field>
              )}
            </div>
          </div>
        </Disclosure>

        <div className="flex items-center gap-3 pt-1">
          <ApplyButton onClick={apply} busy={busy}>{t("Re-run valuation")}</ApplyButton>
          <span className="text-meta text-ash">
            {t("Only the valuation engine re-runs; the other two panels keep their results.")}
          </span>
        </div>
    </CardBody>
  );

  if (!guided) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("Assumptions")}</CardTitle>
          <button type="button" onClick={reset}
                  className="font-mono text-micro uppercase tracking-[0.12em] text-ash hover:text-chalk">
            {t("Reset to defaults")}
          </button>
        </CardHeader>
        {body}
      </Card>
    );
  }

  return (
    <Card>
      <details>
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3
                            px-5 py-3 text-ash transition-colors hover:text-chalk
                            focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-tech">
          <span className="eyebrow">{t("Change the assumptions")}</span>
          <span className="text-micro">
            {t("Growth, discount rate, terminal growth — every input is editable")}
          </span>
        </summary>
        <div className="border-t border-rule">{body}</div>
      </details>
    </Card>
  );
}
