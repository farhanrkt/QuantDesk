"use client";

import { Download, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle, Note } from "@/components/ui/card";
import { BACKUP_MAX_BYTES, makeBackup, planRestore, readBackup, type RestorePlan } from "@/lib/backup";
import { useT } from "@/lib/i18n";

const read = (key: string): string | null => {
  try { return window.localStorage.getItem(key); } catch { return null; }
};

/**
 * Save what this browser holds to a file, and read one back.
 *
 * Everything happens on the page: the file is built here and downloaded, and a
 * restored file is read here. A restore shows what it would add and writes
 * nothing until the reader confirms; it merges and never removes (lib/backup.ts).
 */
export function BrowserBackup() {
  const t = useT();
  const input = useRef<HTMLInputElement>(null);
  const [plan, setPlan] = useState<RestorePlan | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const save = () => {
    const backup = makeBackup(read, new Date());
    const blob = new Blob([JSON.stringify(backup, null, 2)], { type: "application/json;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `quantdesk-backup-${backup.savedAt.slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const choose = async (file: File | undefined) => {
    setPlan(null); setProblem(null); setDone(false);
    if (!file) return;
    if (file.size > BACKUP_MAX_BYTES) { setProblem(t("That file is too large to be a QuantDesk backup.")); return; }
    const backup = readBackup(await file.text());
    if (!backup) { setProblem(t("That file is not a QuantDesk backup, so nothing was read from it.")); return; }
    setPlan(planRestore(read, backup));
  };

  const restore = () => {
    if (!plan) return;
    try {
      for (const [key, value] of Object.entries(plan.writes)) window.localStorage.setItem(key, value);
    } catch {
      setProblem(t("This browser would not store the data (a private window, or storage turned off)."));
      return;
    }
    setDone(true);
    // Every store reads on load, so a reload is how the page shows what was added.
    window.setTimeout(() => window.location.reload(), 900);
  };

  const nothing = plan && Object.keys(plan.writes).length === 0;
  return (
    <Card id="backup">
      <CardHeader>
        <CardTitle>{t("Your data in this browser")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <p className="prose-col text-meta leading-relaxed text-ash">
          {t("Your watchlist, this journal, your holdings and your settings are kept in this browser and nowhere else. A new device or cleared site data starts empty. Save them to a file to keep a copy, and restore it anywhere. The file never leaves this page unless you move it.")}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="quiet" size="sm" onClick={save}>
            <Download aria-hidden className="h-3.5 w-3.5" />{" "}{t("Save a backup file")}
          </Button>
          <Button variant="quiet" size="sm" onClick={() => input.current?.click()}>
            <Upload aria-hidden className="h-3.5 w-3.5" />{" "}{t("Restore from a file")}
          </Button>
          <input ref={input} type="file" accept="application/json,.json" className="sr-only"
                 aria-label={t("Choose a backup file")} tabIndex={-1}
                 onChange={(e) => { void choose(e.target.files?.[0]); e.target.value = ""; }} />
        </div>

        {problem && <Note tone="warn">{problem}</Note>}

        {plan && !done && (
          <div className="space-y-3 rounded-lg border border-ruleSoft bg-sunken px-4 py-3.5" role="status">
            {nothing ? (
              <p className="text-meta text-body">{t("Everything in that file is already here. Nothing to add.")}</p>
            ) : (
              <>
                <p className="text-meta text-body">{t("Restoring adds to what is here and removes nothing:")}</p>
                <ul className="list-disc space-y-1 pl-5 text-meta text-body">
                  {plan.added.journal > 0 && <li>{plan.added.journal === 1 ? t("1 journal entry")
                    : t("{count} journal entries", { count: plan.added.journal })}</li>}
                  {plan.added.watchlist > 0 && <li>{plan.added.watchlist === 1 ? t("1 symbol on the watchlist")
                    : t("{count} symbols on the watchlist", { count: plan.added.watchlist })}</li>}
                  {plan.added.holdings && <li>{t("your holdings (this browser has none)")}</li>}
                  {plan.added.preferences > 0 && <li>{plan.added.preferences === 1 ? t("1 setting this browser has not set")
                    : t("{count} settings this browser has not set", { count: plan.added.preferences })}</li>}
                </ul>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" onClick={restore}>{t("Add to this browser")}</Button>
                  <Button variant="quiet" size="sm" onClick={() => setPlan(null)}>{t("Cancel")}</Button>
                </div>
              </>
            )}
          </div>
        )}
        {done && <p className="text-meta text-body" role="status">{t("Added. Reloading the page to show it…")}</p>}
      </CardBody>
    </Card>
  );
}
