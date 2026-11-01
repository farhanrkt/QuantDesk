#!/usr/bin/env python3
"""
refresh_calendar.py
===================
Compare `api/_lib/calendar_events.json` against the official schedules again.

    python scripts/refresh_calendar.py

WHAT IT CHECKS ITSELF, AND WHAT IT CANNOT
-----------------------------------------
Three sources answer a script:
- the Fed's FOMC calendar page;
- BEA's release calendar (an .ics feed);
- NYSE's holiday table.

This reads those and prints every date the file lacks or holds that the source
no longer lists.

The rest it can only name. BLS refuses scripted requests (HTTP 403), so its CPI
and jobs-report dates are read from its schedule pages in a browser. Bank
Indonesia's decision table pages by form post. IDX publishes its holiday notice
as a document the press reproduces, and BPS's release calendar could not be read
at all on 1 November 2026. For those it prints where to look.

It never writes the file. A transcription is checked by a person before it is
committed, because a wrong date here is shown as a fact on every page.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

# The certifi-backed context `news.py` uses: on a non-system Python the platform
# trust store has no usable issuer chain, and every fetch failed verification.
from _lib.news import _ssl_context  # noqa: E402

FILE = ROOT / "api" / "_lib" / "calendar_events.json"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
        return response.read(8_000_000).decode("utf-8", errors="replace")


def fomc_decisions(page: str) -> set[str]:
    """Each FOMC meeting's decision day, notation votes excluded."""
    out = set()
    for m in re.finditer(r"(\d{4}) FOMC Meetings", page):
        year = int(m.group(1))
        end = page.find("FOMC Meetings", m.end())
        block = page[m.end(): end if end > 0 else len(page)]
        months = re.findall(r"fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>", block)
        days = [d.strip() for d in re.findall(r"fomc-meeting__date[^>]*>([^<]+)<", block)]
        for month, day in zip(months, days, strict=False):
            if "notation" in day.lower():
                continue
            name = month.split("/")[-1]
            number = MONTHS.get(name) or MONTHS[next(k for k in MONTHS if k.startswith(name[:3]))]
            out.add(dt.date(year, number, int(day.rstrip("*").split("-")[-1])).isoformat())
    return out


def bea_releases(feed: str) -> set[tuple[str, str]]:
    """GDP estimates and Personal Income and Outlays, from BEA's iCalendar feed."""
    out = set()
    for block in feed.split("BEGIN:VEVENT")[1:]:
        summary = re.search(r"SUMMARY:(.*?)\r?\n(?! )", block, flags=re.S)
        start = re.search(r"DTSTART[^:]*:(\d{8})", block)
        if not summary or not start:
            continue
        text = re.sub(r"\r?\n ", "", summary.group(1)).replace("\\,", ",")
        date = dt.datetime.strptime(start.group(1), "%Y%m%d").date().isoformat()
        if text.startswith("Personal Income and Outlays"):
            out.add(("pce", date))
        # Older entries say "Gross Domestic Product, ... (Advance Estimate)", newer
        # ones "GDP (Advance Estimate), ...": both are the same release.
        elif re.match(r"(Gross Domestic Product|GDP)\b", text) and "Estimate" in text:
            out.add(("gdp", date))
    return out


def nyse_holidays(page: str) -> set[str]:
    """Full-day NYSE closures from the holiday table, for every year it lists."""
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.S)
    years: list[int] = []
    out = set()
    for row in rows:
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                 for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.S)]
        if cells and cells[0] == "Holiday":
            years = [int(c) for c in cells[1:] if c.isdigit()]
            continue
        for year, cell in zip(years, cells[1:], strict=False):
            m = re.search(r"([A-Z][a-z]+) (\d{1,2})", cell)
            if m and m.group(1) in MONTHS:
                out.add(dt.date(year, MONTHS[m.group(1)], int(m.group(2))).isoformat())
    return out


def compare(label: str, source: set, held: set, horizon: str) -> int:
    """Print what differs from today onward; return the number of differences."""
    today = dt.date.today().isoformat()
    missing = sorted(x for x in source - held if (x if isinstance(x, str) else x[1]) >= today)
    extra = sorted(x for x in held - source if (x if isinstance(x, str) else x[1]) >= today
                   and (x if isinstance(x, str) else x[1]) <= horizon)
    print(f"{label}: {len(source)} listed by the source, {len(held)} in the file")
    for item in missing:
        print(f"   missing from the file: {item}")
    for item in extra:
        print(f"   in the file, not listed by the source: {item}")
    return len(missing) + len(extra)


def main() -> int:
    doc = json.loads(FILE.read_text(encoding="utf-8"))
    events = doc["events"]
    print(f"calendar_events.json, verified {doc.get('verifiedOn')}, {len(events)} events\n")
    differences = 0

    fomc = fomc_decisions(fetch("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"))
    differences += compare("FOMC decisions", fomc,
                           {e["date"] for e in events if e["kind"] == "fomc"}, max(fomc))

    bea = bea_releases(fetch("https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics"))
    differences += compare("BEA (GDP, PCE)", bea,
                           {(e["kind"], e["date"]) for e in events if e["kind"] in ("gdp", "pce")},
                           max(d for _, d in bea))

    nyse = nyse_holidays(fetch("https://www.nyse.com/markets/hours-calendars"))
    differences += compare("NYSE closures", nyse,
                           {e["date"] for e in events if e["market"] == "US" and e["kind"] == "holiday"},
                           max(nyse))

    print("\nChecked by hand (these refuse scripts or publish documents):")
    print("   BLS CPI and jobs:   https://www.bls.gov/schedule/<year>/home.htm, in a browser")
    print("   Bank Indonesia:     https://www.bi.go.id/en/statistik/indikator/bi-rate.aspx (decisions)")
    print("                       https://www.bi.go.id/en/publikasi/kalender/default.aspx (schedule)")
    print("   IDX holidays:       the IDX holiday notice for the year (Peng-.../BEI.POP)")
    print("   BPS inflation:      still pending — see `pending` in the file")
    print("\nCoverage, the last date each source reaches:")
    cover: dict[str, str] = {}
    for e in events:
        cover[e["source"]] = max(cover.get(e["source"], ""), e["date"])
    for source, last in sorted(cover.items()):
        print(f"   {source:12s} {last}")
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main())
