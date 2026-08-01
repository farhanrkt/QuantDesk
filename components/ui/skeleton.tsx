/** Placeholder shown while an engine is still running. */
export function PanelSkeleton() {
  return (
    <div className="space-y-4 p-5" aria-busy="true">
      <span className="sr-only">Running the engine…</span>
      <div className="h-3 w-40 animate-pulseline rounded bg-rule" />
      <div className="h-[280px] animate-pulseline rounded bg-raised" />
      <div className="flex gap-3">
        <div className="h-3 flex-1 animate-pulseline rounded bg-rule" />
        <div className="h-3 w-24 animate-pulseline rounded bg-rule" />
      </div>
    </div>
  );
}
