/**
 * Placeholders shaped like what they stand in for.
 *
 * There was one: a 280px grey block, whatever was loading. A table that
 * arrived where a chart-shaped hole had been pushed everything below it, and a
 * row of four stats loading behind a chart silhouette told the reader to
 * expect the wrong thing. Each shape is the rough footprint of the content, so
 * the page moves less when the data lands.
 *
 * Decorative only: every caller pairs one with a sentence in a live region
 * (see `StateCard kind="loading"`), so the skeleton itself is `aria-hidden`.
 */
export type SkeletonShape = "chart" | "table" | "stats" | "lines";

const bar = "animate-pulseline rounded bg-rule";

export function Skeleton({ shape = "chart" }: { shape?: SkeletonShape }) {
  return (
    <div className="space-y-4 p-5" aria-hidden>
      {shape === "chart" && (
        <>
          <div className={`${bar} h-3 w-40`} />
          <div className="h-[260px] animate-pulseline rounded bg-raised" />
          <div className="flex gap-3">
            <div className={`${bar} h-3 flex-1`} />
            <div className={`${bar} h-3 w-24`} />
          </div>
        </>
      )}
      {shape === "table" && (
        <>
          <div className={`${bar} h-3 w-48`} />
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="flex gap-4">
              <div className={`${bar} h-3 w-16`} />
              <div className={`${bar} h-3 flex-1`} />
              <div className={`${bar} h-3 w-20`} />
            </div>
          ))}
        </>
      )}
      {shape === "stats" && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="space-y-2 rounded border border-ruleSoft bg-sunken p-3">
              <div className={`${bar} h-2.5 w-16`} />
              <div className={`${bar} h-5 w-20`} />
            </div>
          ))}
        </div>
      )}
      {shape === "lines" && (
        <>
          <div className={`${bar} h-3 w-3/4`} />
          <div className={`${bar} h-3 w-full`} />
          <div className={`${bar} h-3 w-5/6`} />
        </>
      )}
    </div>
  );
}

/** Placeholder shown while an engine is still running. */
export function PanelSkeleton({ shape = "chart" }: { shape?: SkeletonShape }) {
  return (
    <div aria-busy="true">
      <span className="sr-only">Running the engine…</span>
      <Skeleton shape={shape} />
    </div>
  );
}
