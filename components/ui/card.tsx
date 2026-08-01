import { cn } from "@/lib/utils";

/**
 * The panel surface every engine renders into. `accent` takes a raw hex rather
 * than a Tailwind class because the engine hues are chosen at runtime from the
 * data (flow bias, DCF vs DDM), not known at build time.
 */
export function Card({
  accent, className, children,
}: { accent?: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("relative rounded border border-rule bg-panel", className)}>
      {accent && (
        <span aria-hidden className="absolute inset-x-0 top-0 h-[2px] rounded-t"
              style={{ background: accent }} />
      )}
      {children}
    </div>
  );
}

export function CardHeader({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn(
      "flex flex-wrap items-center justify-between gap-3 border-b border-rule px-5 py-3",
      className,
    )}>
      {children}
    </div>
  );
}

export function CardTitle({ className, children }: { className?: string; children: React.ReactNode }) {
  return <h3 className={cn("text-sm font-semibold text-chalk", className)}>{children}</h3>;
}

/** Tables pass `px-0` so their rows can run the full width of the panel. */
export function CardBody({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("px-5 py-4", className)}>{children}</div>;
}

export function Stat({
  label, value, sub, tone,
}: { label: string; value: React.ReactNode; sub?: string; tone?: string }) {
  return (
    <div className="rounded border border-rule bg-panel px-4 py-3">
      <div className="eyebrow mb-1">{label}</div>
      <div className={cn("num text-lg font-semibold leading-tight", tone ?? "text-chalk")}>{value}</div>
      {sub && <div className="mt-0.5 text-[0.7rem] leading-snug text-ash">{sub}</div>}
    </div>
  );
}
