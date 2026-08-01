"use client";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      {...props}
      className={cn(
        "h-10 w-full rounded border border-rule bg-panel px-3",
        "font-mono text-sm text-chalk placeholder:font-sans placeholder:text-ash/70",
        "transition-colors hover:border-rule focus:border-tech/60",
        className,
      )}
    />
  );
}

export function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      {...props}
      className={cn(
        "h-10 shrink-0 rounded border border-rule bg-panel px-3",
        "text-xs text-chalk transition-colors hover:border-tech/40",
        className,
      )}
    >
      {children}
    </select>
  );
}
