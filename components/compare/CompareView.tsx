"use client";

import { StateCard } from "@/components/ui/state";

/** Replaced by the full compare view later in this series of commits. */
export function CompareView() {
  return (
    <div className="space-y-6">
      <h1>Compare</h1>
      <StateCard kind="empty" title="Compare is being built">
        Two to four companies, read lens by lens in parallel columns.
      </StateCard>
    </div>
  );
}
