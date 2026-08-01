"use client";

import { cn } from "@/lib/utils";

export interface Tab {
  id: string;
  label: string;
  /** Engine hue — the active tab is the only place this colour appears here. */
  accent: string;
}

export function Tabs({
  tabs, active, onChange,
}: { tabs: Tab[]; active: string; onChange: (id: string) => void }) {
  return (
    <div role="tablist" className="flex flex-wrap gap-1 border-b border-rule">
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.id)}
            className={cn(
              "-mb-px border-b-2 px-4 py-2.5 font-mono text-xs tracking-[0.1em]",
              "transition-colors",
              selected ? "text-chalk" : "border-transparent text-ash hover:text-chalk",
            )}
            style={selected ? { borderBottomColor: tab.accent, color: tab.accent } : undefined}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
