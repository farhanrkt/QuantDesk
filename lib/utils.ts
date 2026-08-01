import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function pct(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function signedPct(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
}

export function num(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function compact(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  const units: [number, string][] = [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]];
  for (const [div, tag] of units) {
    if (abs >= div) return `${(value / div).toFixed(2)}${tag}`;
  }
  return value.toFixed(0);
}

/** Renders **bold** spans from the engine's headline without dangerouslySetInnerHTML. */
export function splitEmphasis(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part) =>
    part.startsWith("**") && part.endsWith("**")
      ? { bold: true, text: part.slice(2, -2) }
      : { bold: false, text: part }
  );
}

export const TONE: Record<string, string> = {
  bull: "text-acc",
  bear: "text-dist",
  warn: "text-warn",
  neutral: "text-ash",
};
