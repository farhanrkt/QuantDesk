"use client";

import { LANG_NAME, LANGS, useT, type Lang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * English or Bahasa Indonesia, as a two-option switch that behaves like one —
 * the same keyboard contract as the Guided / Full switch beside it: one tab
 * stop, arrow keys move, and each option announces its full name.
 */
export function LanguageToggle({
  value, onChange,
}: { value: Lang; onChange: (l: Lang) => void }) {
  const t = useT();
  const move = (event: React.KeyboardEvent) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    onChange(value === "en" ? "id" : "en");
  };
  return (
    <div role="radiogroup" aria-label={t("Language")}
         className="inline-flex rounded-lg border border-rule bg-raised p-1">
      {LANGS.map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={value === option}
          aria-label={LANG_NAME[option]}
          lang={option}
          tabIndex={value === option ? 0 : -1}
          onKeyDown={move}
          onClick={() => onChange(option)}
          className={cn(
            "rounded px-2.5 py-1.5 font-mono text-meta font-medium uppercase transition-colors",
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
            value === option ? "bg-tech/20 text-chalk shadow-sm" : "text-ash hover:text-chalk",
          )}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
