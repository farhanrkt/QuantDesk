"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * A keyboard key, drawn as one.
 *
 * THE ONLY FILE ALLOWED A KEY GLYPH. DESIGN.md bans unicode glyphs as icons —
 * lucide, one stroke weight — and check_frontend.mjs enforces it. A keyboard
 * shortcut is the one place the glyph IS the thing being named: "⌘K" is what is
 * printed on the key. So the glyphs live here and nowhere else.
 *
 * `mod` renders as ⌘ on Apple platforms and Ctrl elsewhere, decided after mount
 * so the server render and the first client render agree.
 */
const GLYPH: Record<string, string> = {
  shift: "⇧", enter: "↵", up: "↑", down: "↓", left: "←", right: "→", esc: "Esc",
};

export function useIsApple() {
  const [apple, setApple] = useState(false);
  useEffect(() => {
    setApple(/Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent));
  }, []);
  return apple;
}

export function Kbd({ keys, className }: { keys: string[]; className?: string }) {
  const apple = useIsApple();
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {keys.map((k) => {
        const label = k === "mod" ? (apple ? "⌘" : "Ctrl") : GLYPH[k] ?? k;
        return (
          <kbd key={k}
               className="inline-flex h-5 min-w-[20px] items-center justify-center rounded border
                          border-rule bg-sunken px-1 font-mono text-micro text-ash">
            {label}
          </kbd>
        );
      })}
    </span>
  );
}
