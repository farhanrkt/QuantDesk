"use client";

import { BookOpen, Columns3, LayoutGrid, Menu, NotebookPen, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { usePreferences } from "@/components/shell/preferences";
import { DetailToggle } from "@/components/ui/explain";
import { Kbd } from "@/components/ui/kbd";
import { cn } from "@/lib/utils";

/**
 * The one piece of chrome on every page.
 *
 * WHAT IT REPLACED. The single page opened on an `h1` reading QUANTDESK and a
 * tagline, and once a ticker was loaded there was no way back: no link home, no
 * way to reach the market-wide tools except through a tab on a stock, no route
 * to the journal except through the company the entry was about. A reader who
 * wanted to rank the Nasdaq-100 after reading Apple had to know that the ranking
 * lived on Apple's eighth tab.
 *
 * WHAT IT DELIBERATELY IS NOT. The brand is a link, not a heading — every route
 * owns exactly one `h1` and on a stock page that is the ticker, which is the
 * biggest thing on the page by design. There is no ticker tape, no index
 * quotes, no "market today" strip: decoration that reports numbers nobody asked
 * about is the dashboard habit this app exists to refuse.
 */
const NAV = [
  { href: "/markets", label: "Markets", icon: LayoutGrid, match: "/markets" },
  { href: "/compare", label: "Compare", icon: Columns3, match: "/compare" },
  { href: "/journal", label: "Journal", icon: NotebookPen, match: "/journal" },
];

export function TopBar({ onSearch }: { onSearch: () => void }) {
  const pathname = usePathname() ?? "/";
  const { detail, setDetail } = usePreferences();
  const menu = useRef<HTMLDialogElement>(null);

  // A route change closes the phone menu; leaving it open over the page the
  // reader just asked for would hide the answer to their own click.
  useEffect(() => { menu.current?.close(); }, [pathname]);

  const link = (item: (typeof NAV)[number], extra?: string) => {
    const active = pathname.startsWith(item.match);
    const Icon = item.icon;
    return (
      <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}
            className={cn(
              "inline-flex min-h-[36px] items-center gap-2 rounded-lg px-3 text-meta font-medium",
              "transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-tech",
              active ? "bg-raised text-chalk" : "text-ash hover:bg-raised/60 hover:text-chalk",
              extra,
            )}>
        <Icon aria-hidden className="h-4 w-4" />
        {item.label}
      </Link>
    );
  };

  return (
    <header className="sticky top-0 z-40 border-b border-rule bg-ink/90 backdrop-blur
                       supports-[backdrop-filter]:bg-ink/75 print:hidden">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 sm:px-6 lg:px-8">
        <Link href="/" aria-label="QuantDesk home"
              className="mr-1 rounded font-mono text-meta font-semibold tracking-[0.16em] text-chalk
                         focus:outline-none focus-visible:ring-2 focus-visible:ring-tech">
          QUANTDESK
        </Link>

        <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
          {NAV.map((item) => link(item))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <button type="button" onClick={onSearch}
                  className="inline-flex h-9 items-center gap-2 rounded-lg border border-rule bg-sunken
                             px-3 text-meta text-ash transition-colors hover:border-ruleStrong
                             hover:text-chalk focus:outline-none focus-visible:ring-2
                             focus-visible:ring-tech sm:min-w-[13rem]">
            <Search aria-hidden className="h-4 w-4" />
            <span className="hidden sm:inline">Search or jump to…</span>
            <span className="sr-only sm:hidden">Search</span>
            <Kbd keys={["mod", "K"]} className="ml-auto hidden sm:inline-flex" />
          </button>
          <div className="hidden md:block">
            <DetailToggle level={detail} onChange={setDetail} />
          </div>
          <a href="/docs/field-manual.html"
             className="hidden h-9 items-center gap-1.5 rounded-lg px-2.5 text-meta text-ash
                        transition-colors hover:text-chalk focus:outline-none focus-visible:ring-2
                        focus-visible:ring-tech lg:inline-flex">
            <BookOpen aria-hidden className="h-4 w-4" />
            Field manual
          </a>
          <button type="button" aria-label="Open menu" onClick={() => menu.current?.showModal()}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-ash
                             hover:bg-raised hover:text-chalk focus:outline-none
                             focus-visible:ring-2 focus-visible:ring-tech md:hidden">
            <Menu aria-hidden className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* A native dialog: focus is trapped and returned, Escape closes it, and
          the page behind is inert — all for free, which a hand-rolled drawer
          would have had to re-implement and would have got wrong somewhere. */}
      <dialog ref={menu} aria-label="Menu"
              className="m-0 ml-auto h-full max-h-none w-[min(20rem,85vw)] border-l border-rule bg-panel
                         p-0 text-body backdrop:bg-ink/70 open:animate-rise">
        <div className="flex h-14 items-center justify-between border-b border-rule px-4">
          <span className="font-mono text-meta font-semibold tracking-[0.16em] text-chalk">QUANTDESK</span>
          <button type="button" aria-label="Close menu" onClick={() => menu.current?.close()}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-ash
                             hover:text-chalk focus:outline-none focus-visible:ring-2 focus-visible:ring-tech">
            <X aria-hidden className="h-5 w-5" />
          </button>
        </div>
        <nav aria-label="Main" className="flex flex-col gap-1 p-3">
          {NAV.map((item) => link(item, "w-full"))}
          <a href="/docs/field-manual.html"
             className="inline-flex min-h-[36px] items-center gap-2 rounded-lg px-3 text-meta font-medium
                        text-ash hover:bg-raised/60 hover:text-chalk focus:outline-none
                        focus-visible:ring-2 focus-visible:ring-tech">
            <BookOpen aria-hidden className="h-4 w-4" />
            Field manual
          </a>
        </nav>
        <div className="border-t border-rule p-4">
          <div className="eyebrow mb-2">Reading mode</div>
          <DetailToggle level={detail} onChange={setDetail} />
        </div>
      </dialog>
    </header>
  );
}
