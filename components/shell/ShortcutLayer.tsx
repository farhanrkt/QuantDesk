"use client";

import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import { Kbd } from "@/components/ui/kbd";
import { matchShortcut, type ShortcutAction } from "@/lib/shortcuts";

/**
 * The app's keyboard shortcuts, and the one dialog that lists them.
 *
 * Page-specific actions — previous/next lens tab, star this ticker — are not
 * handled here: the shell does not know what page it is wrapping. They go out
 * as a `quantdesk:shortcut` event and the stock page answers them, so a `]` on
 * the compare view does nothing rather than something surprising.
 */
export const SHORTCUT_EVENT = "quantdesk:shortcut";

const LIST: { keys: string[]; what: string }[] = [
  { keys: ["mod", "K"], what: "Search companies, pages and settings" },
  { keys: ["/"], what: "The same, without the modifier" },
  { keys: ["["], what: "Previous tab on a stock page" },
  { keys: ["]"], what: "Next tab on a stock page" },
  { keys: ["w"], what: "Add or remove this stock from your watchlist" },
  { keys: ["?"], what: "This list" },
];

export function ShortcutLayer({
  onPalette, paletteOpen,
}: { onPalette: () => void; paletteOpen: boolean }) {
  const help = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // While a modal is open it owns the keyboard; the palette handles its own.
      if (paletteOpen || help.current?.open) return;
      if (document.querySelector("dialog[open]")) return;
      const action: ShortcutAction = matchShortcut(e, e.target as HTMLElement | null);
      if (!action) return;
      e.preventDefault();
      if (action === "palette") onPalette();
      else if (action === "help") help.current?.showModal();
      else window.dispatchEvent(new CustomEvent(SHORTCUT_EVENT, { detail: action }));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onPalette, paletteOpen]);

  return (
    <dialog ref={help} aria-labelledby="shortcut-help-title"
            onClick={(e) => { if (e.target === help.current) help.current?.close(); }}
            className="mt-[14vh] w-[min(28rem,calc(100vw-2rem))] rounded-xl border border-rule bg-panel
                       p-0 text-body shadow-pop backdrop:bg-ink/70 open:animate-rise print:hidden">
      <div className="flex items-center justify-between border-b border-rule px-5 py-3.5">
        <h2 id="shortcut-help-title" className="text-h3">Keyboard shortcuts</h2>
        <button type="button" aria-label="Close" onClick={() => help.current?.close()}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-ash
                           hover:text-chalk focus:outline-none focus-visible:ring-2 focus-visible:ring-tech">
          <X aria-hidden className="h-4 w-4" />
        </button>
      </div>
      <ul className="divide-y divide-ruleSoft px-5 py-2">
        {LIST.map((row) => (
          <li key={row.what} className="flex items-center justify-between gap-4 py-2.5 text-meta">
            <span>{row.what}</span>
            <Kbd keys={row.keys} />
          </li>
        ))}
      </ul>
      <p className="border-t border-rule px-5 py-3 text-micro text-faint">
        None of these fire while you are typing in a field.
      </p>
    </dialog>
  );
}
