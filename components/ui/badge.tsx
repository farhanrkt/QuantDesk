import { cn } from "@/lib/utils";

/**
 * `color` is a hex from the engine palette; the border and fill are derived from
 * it with alpha suffixes so a badge never introduces a colour of its own.
 */
export function Badge({
  color, className, children,
}: { color: string; className?: string; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "num inline-flex items-center rounded border px-2 py-0.5 text-[0.65rem] font-semibold tracking-[0.08em]",
        className,
      )}
      style={{ color, borderColor: `${color}66`, background: `${color}14` }}
    >
      {children}
    </span>
  );
}
