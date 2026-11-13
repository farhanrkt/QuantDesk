"use client";

import { Card, CardBody, CardHeader, CardTitle, Note } from "@/components/ui/card";
import { HeadlineList } from "@/components/ui/headlines";
import type { Engine, NewsResponse } from "@/lib/types";
import { StateCard } from "@/components/ui/state";
import { useT } from "@/lib/i18n";

/**
 * Contextual catalyst — the headline panel from the Whale Tracker app.
 *
 * Everything here is third-party text fetched from a public feed, and it is
 * rendered by `HeadlineList`, the one place this app draws a headline.
 */
export function NewsPanel({ state }: { state: Engine<NewsResponse> }) {
  const t = useT();
  // A FAILED FEED AND A QUIET COMPANY USED TO LOOK IDENTICAL: both rendered
  // nothing. They are different facts, and only one of them is about the
  // company, so each now says which it is.
  if (state.status === "idle" || state.status === "loading") return null;
  if (state.status === "error") {
    return (
      <StateCard kind="error" title={t("Headlines did not load")}>
        {t("{message} Nothing else on this page reads the news, so every other figure is unaffected.", { message: state.failure.message })}
      </StateCard>
    );
  }
  if (state.data.items.length === 0) {
    return (
      <StateCard kind="empty" title={t("No recent headlines")}>
        {t("The feed returned nothing for {ticker}. That is common for smaller listings and says nothing about the company either way.", { ticker: state.data.ticker })}
      </StateCard>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Contextual catalyst")}</CardTitle>
        <span className="font-mono text-micro text-ash">{t("Google News · {ticker}", { ticker: state.data.ticker })}</span>
      </CardHeader>
      <CardBody className="px-0">
        <HeadlineList items={state.data.items} />
        <div className="px-5 pt-3">
          <Note>
            {t("Headlines from Google News, unverified and matched by best effort. Context for the signals above, never confirmation of them — nothing in this app reads them back as data.")}
          </Note>
        </div>
      </CardBody>
    </Card>
  );
}
