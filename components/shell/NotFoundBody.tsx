"use client";

import { ButtonLink } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { useT } from "@/lib/i18n";

/**
 * The 404's words. A client component of its own because the page around it is
 * rendered on the server, which cannot know the reader's language; this part
 * redraws in it once the browser does.
 */
export function NotFoundBody() {
  const t = useT();
  return (
    <div className="mx-auto flex min-h-[50vh] max-w-2xl items-center">
      <div className="w-full rounded-xl border border-dashed border-rule px-6 py-14 text-center">
        <p className="eyebrow mb-3">404</p>
        <h1>{t("Nothing lives at this address")}</h1>
        <p className="mx-auto mt-3 max-w-md text-base leading-relaxed text-ash">
          {t("A company's page takes its ticker — /stock/AAPL, /stock/BBCA.JK — and anything that is not a ticker lands here. Search by name from the top bar, or press")}{" "}
          <Kbd keys={["mod", "K"]} className="align-middle" />.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <ButtonLink href="/" variant="primary" size="sm">{t("Go to the start")}</ButtonLink>
          <ButtonLink href="/markets" variant="quiet" size="sm">{t("Market tools")}</ButtonLink>
        </div>
      </div>
    </div>
  );
}
