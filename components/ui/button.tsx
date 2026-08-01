"use client";

import { cn } from "@/lib/utils";

export function Button({ className, ...props }: React.ComponentProps<"button">) {
  return (
    <button
      {...props}
      className={cn(
        "h-10 shrink-0 rounded border border-tech/50 bg-tech/10 px-4",
        "font-mono text-xs uppercase tracking-[0.14em] text-chalk",
        "transition-colors hover:bg-tech/20",
        "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-tech/10",
        className,
      )}
    />
  );
}
