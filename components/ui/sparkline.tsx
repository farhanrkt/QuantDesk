import { palette } from "@/lib/palette";

/**
 * Three months of a price as a line, and nothing else: no axis, no fill, no
 * colour. The shape is context for the figure beside it, which carries the
 * reading, so the drawing is hidden from assistive technology.
 *
 * Neutral on purpose. A sparkline drawn green when it ends higher is a verdict
 * picked from the sign of a number — the thing PRODUCT.md constraint 4 forbids.
 */
export function Sparkline({
  values, width = 96, height = 24, className,
}: { values?: number[] | null; width?: number; height?: number; className?: string }) {
  const finite = (values ?? []).filter((v) => Number.isFinite(v));
  if (finite.length < 2) return null;
  let low = finite[0];
  let high = finite[0];
  for (const v of finite) { if (v < low) low = v; if (v > high) high = v; }
  const span = high - low || 1;
  const pad = 2;
  const x = (i: number) => pad + (i / (finite.length - 1)) * (width - pad * 2);
  const y = (v: number) => pad + (1 - (v - low) / span) * (height - pad * 2);
  const points = finite.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = finite.length - 1;
  return (
    <svg aria-hidden width={width} height={height} viewBox={`0 0 ${width} ${height}`}
         className={className} focusable="false">
      <polyline points={points} fill="none" stroke={palette.ash} strokeWidth={1.25}
                strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(last)} cy={y(finite[last])} r={1.75} fill={palette.chalk} />
    </svg>
  );
}
