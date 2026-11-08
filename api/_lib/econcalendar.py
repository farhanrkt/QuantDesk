"""
econcalendar.py
===============
The dates that move markets — central bank decisions, the data releases they
are read against, and the days the exchanges are shut — from a committed file.

WHY A FILE AND NOT A FEED
-------------------------
Every source here publishes its schedule months ahead and changes it rarely:
the Fed lists its FOMC meetings a year out, BLS and BEA publish the whole next
year, Bank Indonesia publishes the next year's Board of Governors meetings each
December, and both exchanges announce their holidays a year ahead. Fetching them
on every request would put five government websites — two of which refuse
scripted requests — in the path of every page. So `calendar_events.json` is
transcribed from them, carries the URL each date came from and the day it was
checked, and `scripts/refresh_calendar.py` compares it against the sources again.

THE FILE SAYS WHAT IT DOES NOT KNOW
-----------------------------------
`pending` names what is not published yet or could not be read: Bank
Indonesia's 2027 meetings, BPS's inflation release dates, the Fed's upcoming
minutes. A calendar without Indonesian inflation reads as a calendar that
checked and found none, which is the absence-is-not-a-pass mistake PRODUCT.md
constraint 3 exists to prevent. `coverage` gives the last date each source
reaches, so a stale file announces itself on the page instead of going quiet.

SCHEDULED IS NOT CERTAIN
------------------------
Bank Indonesia published 15-16 July 2026 for its July meeting and decided on 22
July, and raised its rate between meetings on 9 June 2026. Past decisions in
the file are the dates it actually decided (from its BI-Rate table); upcoming
ones are the published schedule and are marked `scheduled`.

TIMES ARE CONVERTED HERE, FORMATTED THERE
-----------------------------------------
Each timed event carries its local time and IANA zone, and this module turns it
into a UTC instant with `zoneinfo`, which knows that 08:30 in New York is 13:30
UTC in summer and 12:30 in winter. The browser only formats that instant in the
reader's own zone, so a Jakarta reader sees a US CPI release at 20:30 or 19:30
without anybody's code doing daylight-saving arithmetic by hand.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from . import lang

PATH = Path(__file__).with_name("calendar_events.json")

MARKETS = ("US", "ID")

# What each kind of date is, said once, in words a newcomer can use. The panel
# shows it beside the event; the field manual does not, because these are
# events rather than metrics.
KINDS: dict[str, dict[str, str]] = {
    "fomc": {
        "label": "FOMC rate decision",
        "about": ("The Federal Reserve's rate-setting committee announces where it holds US "
                  "interest rates. Four of its eight meetings a year come with the Fed's own "
                  "projections for rates, growth and inflation."),
    },
    "cpi": {
        "label": "US consumer prices (CPI)",
        "about": ("The month's change in the prices US consumers pay — the inflation figure "
                  "most often set against the Fed's next decision."),
    },
    "jobs": {
        "label": "US jobs report",
        "about": ("How many jobs the US economy added last month and the unemployment rate, "
                  "from the Bureau of Labor Statistics, usually on the first Friday."),
    },
    "pce": {
        "label": "US PCE inflation",
        "about": ("Prices measured through what consumers actually spend. The Fed states its "
                  "2% inflation target in this measure rather than in CPI."),
    },
    "gdp": {
        "label": "US GDP",
        "about": ("The size of the US economy over a quarter, estimated three times as more "
                  "data arrives: advance, second and third."),
    },
    "bi-rate": {
        "label": "Bank Indonesia rate decision",
        "about": ("Bank Indonesia's Board of Governors sets the BI-Rate, Indonesia's policy "
                  "rate, over a two-day meeting, usually once a month."),
    },
    "holiday": {
        "label": "Exchange closed",
        "about": "No trading on this exchange for the whole day.",
    },
    "early-close": {
        "label": "Early close",
        "about": "The exchange stops trading early.",
    },
}

# Regular trading hours, in each exchange's own zone. The browser works out
# "open", "break" or "closed" from these and the holidays, every minute, so the
# status never waits on a request.
#
# IDX's hours are its own published sessions: Monday to Thursday 09:00-12:00 and
# 13:30-15:49:59, Friday 09:00-11:30 and 14:00-15:49:59, then the pre-closing
# auction to 16:00 — which is when the closing price is set, so the second
# session runs to 16:00 here.
EXCHANGES: dict[str, dict] = {
    "US": {"name": "NYSE", "tz": "America/New_York",
           "sessions": {"mon-thu": [["09:30", "16:00"]], "fri": [["09:30", "16:00"]]},
           "source": "https://www.nyse.com/markets/hours-calendars"},
    "ID": {"name": "IDX", "tz": "Asia/Jakarta",
           "sessions": {"mon-thu": [["09:00", "12:00"], ["13:30", "16:00"]],
                        "fri": [["09:00", "11:30"], ["14:00", "16:00"]]},
           "source": "https://www.idx.id/en/products-services/trading-hours-and-mechanism/"},
}

REQUIRED = ("kind", "date", "tz", "market", "source", "title")


class CalendarError(ValueError):
    """The committed file is malformed. Raised at load, never silently skipped."""


def _validate(doc: dict) -> dict:
    sources = doc.get("sources") or {}
    events = doc.get("events")
    if not isinstance(events, list) or not events:
        raise CalendarError("the calendar file holds no events")
    previous = ""
    for event in events:
        missing = [key for key in REQUIRED if not event.get(key)]
        if missing:
            raise CalendarError(f"event {event!r} lacks {missing}")
        if event["kind"] not in KINDS:
            raise CalendarError(f"unknown kind {event['kind']!r}")
        if event["market"] not in MARKETS:
            raise CalendarError(f"unknown market {event['market']!r}")
        if event["source"] not in sources:
            raise CalendarError(f"event on {event['date']} cites unknown source {event['source']!r}")
        dt.date.fromisoformat(event["date"])
        ZoneInfo(event["tz"])
        if event.get("time"):
            dt.time.fromisoformat(event["time"])
        if event["date"] < previous:
            raise CalendarError(f"events are out of order at {event['date']}")
        previous = event["date"]
    return doc


@lru_cache(maxsize=1)
def load(path: Path = PATH) -> dict:
    """The committed calendar, validated once per process."""
    return _validate(json.loads(path.read_text(encoding="utf-8")))


def instant(event: dict) -> Optional[str]:
    """The event's moment in UTC, or None for an all-day date."""
    if not event.get("time"):
        return None
    local = dt.datetime.combine(dt.date.fromisoformat(event["date"]),
                                dt.time.fromisoformat(event["time"]),
                                tzinfo=ZoneInfo(event["tz"]))
    return local.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def coverage(doc: Optional[dict] = None) -> dict[str, str]:
    """The last date each source's events reach."""
    doc = doc or load()
    out: dict[str, str] = {}
    for event in doc["events"]:
        out[event["source"]] = max(out.get(event["source"], ""), event["date"])
    return out


# The kinds in Bahasa Indonesia. The calendar file's own words — each event's
# detail, the pending notes — come from official English schedules and follow a
# handful of fixed shapes, so `_detail` restates those shapes rather than
# translating free text.
_KINDS_ID: dict[str, dict[str, str]] = {
    "fomc": {"label": "Keputusan suku bunga FOMC",
             "about": ("Komite penentu suku bunga Federal Reserve mengumumkan di mana ia menahan "
                       "suku bunga AS. Empat dari delapan rapatnya setahun disertai proyeksi The "
                       "Fed sendiri untuk suku bunga, pertumbuhan, dan inflasi.")},
    "cpi": {"label": "Harga konsumen AS (CPI)",
            "about": ("Perubahan bulanan harga yang dibayar konsumen AS — angka inflasi yang "
                      "paling sering disandingkan dengan keputusan The Fed berikutnya.")},
    "jobs": {"label": "Laporan ketenagakerjaan AS",
             "about": ("Berapa banyak lapangan kerja yang ditambahkan ekonomi AS bulan lalu dan "
                       "tingkat penganggurannya, dari Bureau of Labor Statistics, biasanya pada "
                       "Jumat pertama.")},
    "pce": {"label": "Inflasi PCE AS",
            "about": ("Harga yang diukur lewat apa yang benar-benar dibelanjakan konsumen. The "
                      "Fed menyatakan target inflasi 2%-nya dalam ukuran ini, bukan CPI.")},
    "gdp": {"label": "PDB AS",
            "about": ("Besarnya ekonomi AS dalam satu kuartal, diperkirakan tiga kali seiring "
                      "datangnya data: awal, kedua, dan ketiga.")},
    "bi-rate": {"label": "Keputusan suku bunga Bank Indonesia",
                "about": ("Dewan Gubernur Bank Indonesia menetapkan BI-Rate, suku bunga kebijakan "
                          "Indonesia, dalam rapat dua hari, biasanya sebulan sekali.")},
    "holiday": {"label": "Bursa tutup",
                "about": "Tidak ada perdagangan di bursa ini sepanjang hari."},
    "early-close": {"label": "Tutup lebih awal",
                    "about": "Bursa menghentikan perdagangan lebih awal."},
}


def kinds() -> dict[str, dict[str, str]]:
    """KINDS in the request's language."""
    if lang.current() != "id":
        return KINDS
    return {kind: {**text, **_KINDS_ID.get(kind, {})} for kind, text in KINDS.items()}


_MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December")
_MONTHS_ID = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
              "September", "Oktober", "November", "Desember")
_HOLIDAYS_ID = {
    "New Year's Day": "Tahun Baru", "Good Friday": "Jumat Agung",
    "Martin Luther King, Jr. Day": "Hari Martin Luther King, Jr.",
    "Washington's Birthday": "Hari Ulang Tahun Washington", "Memorial Day": "Memorial Day",
    "Labor Day": "Hari Buruh AS", "Thanksgiving Day": "Hari Thanksgiving",
    "The day after Thanksgiving": "Sehari setelah Thanksgiving",
    "Christmas Day": "Hari Natal", "Christmas Eve": "Malam Natal", "Christmas": "Natal",
    "Exchange holiday (libur bursa)": "Libur bursa", "Eid al-Fitr": "Idulfitri",
    "Eid al-Adha": "Iduladha", "Juneteenth": "Juneteenth", "Isra Mi'raj": "Isra Mikraj",
    "Nyepi": "Hari Raya Nyepi", "Ascension Day": "Kenaikan Isa Almasih", "Vesak": "Waisak",
    "Pancasila Day": "Hari Lahir Pancasila", "Chinese New Year": "Tahun Baru Imlek",
}
_PENDING_ID = {
    "BPS's release calendar could not be read, so Indonesian inflation dates are not shown. "
    "BPS usually publishes on the first working day of the month.":
        "Kalender rilis BPS tidak bisa dibaca, jadi tanggal inflasi Indonesia tidak ditampilkan. "
        "BPS biasanya merilis pada hari kerja pertama setiap bulan.",
    "The Fed lists each set of minutes once it is released, so upcoming minutes are not shown.":
        "The Fed mencantumkan setiap risalah setelah dirilis, jadi risalah yang akan datang "
        "tidak ditampilkan.",
}


def _months(text: str) -> str:
    for en, id_ in zip(_MONTHS_EN, _MONTHS_ID, strict=True):
        text = re.sub(rf"\b{en}\b", id_, text)
    return text.replace("Apr/May", "Apr/Mei")


def _detail(text: Optional[str], market: Optional[str] = None) -> Optional[str]:
    """An event's detail, or a pending note, in the request's language.

    The file's sentences come in a few fixed shapes, each restated here; any
    sentence that matches none of them is returned as written, in English,
    rather than guessed at.
    """
    if not text or lang.current() != "id":
        return text
    if text in _PENDING_ID:
        return _PENDING_ID[text]
    rules = (
        (r"Bank Indonesia has not yet published its (\d{4}) meeting schedule\.",
         lambda m: f"Bank Indonesia belum menerbitkan jadwal rapat {m[1]}."),
        (r"BI-Rate set at ([\d.]+)%\. Decided outside the published schedule\.",
         lambda m: f"BI-Rate ditetapkan {m[1]}%. Diputuskan di luar jadwal yang diterbitkan."),
        (r"BI-Rate set at ([\d.]+)%\.", lambda m: f"BI-Rate ditetapkan {m[1]}%."),
        (r"(\w+) (\d{4})\. Published late after the (\d{4}) shutdown\.",
         lambda m: f"{_months(m[1])} {m[2]}. Terbit terlambat setelah penutupan pemerintahan "
                   f"AS {m[3]}."),
        (r"(Advance|Second|Third) estimate, Q(\d) (\d{4})\.",
         lambda m: f"Estimasi {dict(Advance='awal', Second='kedua', Third='ketiga')[m[1]]}, "
                   f"kuartal {m[2]} {m[3]}."),
        (r"(With the Fed's economic projections\. )?Meeting (.+?); statement at ([\d:]+) ET, "
         r"press conference after\.",
         lambda m: ("Disertai proyeksi ekonomi The Fed. " if m[1] else "")
                   + f"Rapat {_months(m[2])}; pernyataan pukul {m[3]} ET, disusul konferensi "
                     "pers."),
        (r"Personal income and outlays, (\w+) (\d{4})\. The Fed's preferred inflation "
         r"measure\.",
         lambda m: f"Pendapatan dan belanja pribadi, {_months(m[1])} {m[2]}. Ukuran inflasi "
                   "pilihan The Fed."),
        (r"Board of Governors meeting, (.+)\. Scheduled: in (\d{4}) BI moved one meeting by a "
         r"week and decided once between meetings\.",
         lambda m: f"Rapat Dewan Gubernur, {_months(m[1])}. Terjadwal: pada {m[2]} BI menggeser "
                   "satu rapat sepekan dan sekali memutuskan di antara jadwal rapat."),
        (r"(\w+) (\d{4})\.", lambda m: f"{_months(m[1])} {m[2]}." if m[1] in _MONTHS_EN
         else None),
        (r"Cuti bersama, (.+)\.",
         lambda m: f"Cuti bersama {_HOLIDAYS_ID.get(m[1], m[1])}." if m[1] in _HOLIDAYS_ID
         else None),
        (r"Independence Day(, observed)?\.",
         lambda m: ("Hari Kemerdekaan RI" if (market or "").upper() == "ID"
                    else "Hari Kemerdekaan AS") + (" (pengganti)." if m[1] else ".")),
        (r"(.+?)(, observed)?\.",
         lambda m: (_HOLIDAYS_ID[m[1]] + (" (pengganti)." if m[2] else "."))
         if m[1] in _HOLIDAYS_ID else None),
    )
    for pattern, render in rules:
        match = re.fullmatch(pattern, text)
        if match:
            rendered = render(match)
            if rendered:
                return rendered
    return text


def between(first: dt.date, last: dt.date, doc: Optional[dict] = None) -> list[dict]:
    """Events dated `first` through `last`, each with its UTC instant and kind text."""
    doc = doc or load()
    out = []
    for event in doc["events"]:
        if first.isoformat() <= event["date"] <= last.isoformat():
            out.append({**event, "utc": instant(event), "allDay": not event.get("time"),
                        "label": kinds()[event["kind"]]["label"],
                        "detail": _detail(event.get("detail"), event.get("market"))})
    return out


def upcoming(today: dt.date, days: int = 90, doc: Optional[dict] = None) -> list[dict]:
    """Events from `today` through `days` ahead."""
    return between(today, today + dt.timedelta(days=days), doc)


def window(today: dt.date, days: int = 90) -> tuple[dt.date, dt.date]:
    """The dates the payload carries: this month so far, and `days` ahead.

    FROM THE START OF THE MONTH, NOT FROM TODAY, because the panel draws a month
    and a month whose first three weeks are blank reads as three quiet weeks.
    ONE DAY EARLIER STILL: a release on the last evening of the previous month in
    New York is the first morning of this one in Jakarta, and the browser files
    every timed event under the reader's own day. The lists show only what is
    still ahead; they filter by the reader's clock, not by this window.
    """
    return today.replace(day=1) - dt.timedelta(days=1), today + dt.timedelta(days=days)


def past_dates(kind: str, through: dt.date, doc: Optional[dict] = None) -> list[dt.date]:
    """Every date of one kind on or before `through`, oldest first. For the event history."""
    doc = doc or load()
    return [dt.date.fromisoformat(e["date"]) for e in doc["events"]
            if e["kind"] == kind and e["date"] <= through.isoformat()]


def payload(today: dt.date, days: int = 90) -> dict:
    """Everything the panel needs, none of it about the reader."""
    doc = load()
    first, last = window(today, days)
    return {
        "verifiedOn": doc.get("verifiedOn"),
        "events": between(first, last, doc),
        # Said, so the month view can mark a day past `through` as not loaded
        # rather than drawing it as a day with nothing on it.
        "window": {"from": first.isoformat(), "through": last.isoformat()},
        "kinds": kinds(),
        "exchanges": {code: {**info, "closures": [
            {"date": e["date"], "kind": e["kind"], "time": e.get("time"),
             "detail": _detail(e.get("detail"), code)}
            for e in doc["events"]
            if e["market"] == code and e["kind"] in ("holiday", "early-close")
            and e["date"] >= today.isoformat()]}
            for code, info in EXCHANGES.items()},
        "coverage": coverage(doc),
        "pending": [{**item, "note": _detail(item.get("note"))}
                    for item in doc.get("pending") or []],
        "sources": doc.get("sources") or {},
    }
