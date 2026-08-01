"use client";

import { Download } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Labelled controls for the engine assumption panels.
 *
 * Percent-valued fields show whole percents to the user and hold fractions
 * underneath, because that is the unit every engine takes. Doing the conversion
 * in one place keeps a "10" in the growth box from ever reaching the API as
 * 1000% growth.
 */

export function Field({
  label, hint, children,
}: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="eyebrow">{label}</span>
      {children}
      {hint && <span className="text-[0.65rem] leading-snug text-ash">{hint}</span>}
    </label>
  );
}

const inputClass =
  "h-9 w-full rounded border border-rule bg-raised px-2.5 font-mono text-xs text-chalk " +
  "transition-colors hover:border-rule focus:border-tech/60 disabled:opacity-40";

export function NumberField({
  value, onChange, step = 1, min, max, placeholder, disabled, suffix,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  step?: number; min?: number; max?: number;
  placeholder?: string; disabled?: boolean; suffix?: string;
}) {
  return (
    <span className="relative flex items-center">
      <input
        type="number"
        className={cn(inputClass, suffix && "pr-7")}
        value={value ?? ""}
        step={step}
        min={min}
        max={max}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => {
          const raw = e.target.value;
          onChange(raw === "" ? null : Number(raw));
        }}
      />
      {suffix && (
        <span className="pointer-events-none absolute right-2 font-mono text-[0.65rem] text-ash">
          {suffix}
        </span>
      )}
    </span>
  );
}

/** Displays whole percents, emits fractions. */
export function PercentField({
  value, onChange, step = 0.1, min, max, disabled, placeholder,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  step?: number; min?: number; max?: number; disabled?: boolean; placeholder?: string;
}) {
  const shown = value === null || value === undefined ? null
    : Math.round(value * 1000000) / 10000;
  return (
    <NumberField
      value={shown}
      onChange={(v) => onChange(v === null ? null : v / 100)}
      step={step}
      min={min === undefined ? undefined : min * 100}
      max={max === undefined ? undefined : max * 100}
      disabled={disabled}
      placeholder={placeholder}
      suffix="%"
    />
  );
}

export function SelectField({
  value, onChange, options, disabled,
}: {
  value: string; onChange: (v: string) => void;
  options: (string | { value: string; label: string })[]; disabled?: boolean;
}) {
  return (
    <select
      className={cn(inputClass, "px-2")}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((opt) => {
        const o = typeof opt === "string" ? { value: opt, label: opt } : opt;
        return <option key={o.value} value={o.value}>{o.label}</option>;
      })}
    </select>
  );
}

export function Toggle({
  checked, onChange, label,
}: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs text-ash">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5 accent-tech"
      />
      {label}
    </label>
  );
}

export function ApplyButton({
  onClick, busy, children = "Apply",
}: { onClick: () => void; busy?: boolean; children?: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className={cn(
        "h-9 shrink-0 rounded border border-tech/50 bg-tech/10 px-4",
        "font-mono text-[0.65rem] uppercase tracking-[0.14em] text-chalk",
        "transition-colors hover:bg-tech/20 disabled:cursor-not-allowed disabled:opacity-40",
      )}
    >
      {busy ? "Running" : children}
    </button>
  );
}

export function DownloadButton({
  onClick, href, children,
}: { onClick?: () => void; href?: string; children: React.ReactNode }) {
  const className =
    "inline-flex h-8 items-center gap-1.5 rounded border border-rule px-2.5 " +
    "font-mono text-[0.65rem] uppercase tracking-[0.12em] text-ash " +
    "transition-colors hover:border-tech/50 hover:text-chalk";
  const content = (
    <>
      <Download aria-hidden className="h-3 w-3" />
      {children}
    </>
  );
  return href ? (
    <a href={href} download className={className}>{content}</a>
  ) : (
    <button type="button" onClick={onClick} className={className}>{content}</button>
  );
}

/** Collapsible section for controls that most users will not touch. */
export function Disclosure({
  summary, defaultOpen, children,
}: { summary: string; defaultOpen?: boolean; children: React.ReactNode }) {
  return (
    <details open={defaultOpen} className="group">
      <summary className="eyebrow cursor-pointer list-none select-none py-1 hover:text-chalk">
        <span className="inline-block w-3 transition-transform group-open:rotate-90">›</span>
        {summary}
      </summary>
      <div className="pt-3">{children}</div>
    </details>
  );
}
