"use client";

import { cn } from "@/lib/utils";

/**
 * The primary action, and it now looks like one.
 *
 * v1 drew it as a translucent tinted rectangle with 10px uppercase mono
 * lettering, which read as one more control in a row of controls rather than as
 * the thing a reader is meant to press. Solid fill, sentence case, 15px.
 */
export function Button({ className, ...props }: React.ComponentProps<"button">) {
  return (
    <button
      {...props}
      className={cn(
        "inline-flex h-11 shrink-0 items-center justify-center rounded-lg px-5",
        "bg-tech text-base font-semibold text-ink",
        "transition-colors hover:bg-tech/85",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
        "focus-visible:ring-offset-2 focus-visible:ring-offset-ink",
        "disabled:cursor-not-allowed disabled:bg-rule disabled:text-faint",
        className,
      )}
    />
  );
}
