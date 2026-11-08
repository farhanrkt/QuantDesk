#!/usr/bin/env python3
"""
build_glossary.py
=================
Regenerate the field manual's glossary from the app's own explanation layer.

WHY THIS EXISTS
---------------
`docs/field-manual.html` documents every metric the app can explain. Those
definitions are NOT transcribed — they are the exact strings `_lib/explain.py`
puts on screen, injected here as a JS array. That is the whole point: a manual
whose glossary is typed by hand is wrong the first time a metric changes wording,
and wrong silently, because nothing compares the two.

So the definitions have one source. Add a metric to `explain.py`, run this, and
the manual carries the same sentence the info icon does.

WHAT IT ENFORCES, BEYOND COPYING
--------------------------------
1. EVERY REGISTERED METRIC IS CLASSIFIED. `LENS` below maps each key to the part
   of the app it belongs to, and a key that is registered but unclassified — or
   classified but no longer registered — fails the run. Adding a metric without
   deciding where it belongs is the exact mistake that would otherwise ship a
   glossary quietly missing an entry.

2. EVERY METRIC PRODUCES A READING. An interpreter that returns None for every
   probe value is either broken or takes context arguments this script does not
   supply; either way the manual cannot document it and should say so loudly.

3. THE FILE STAYS PURE ASCII. The published page is wrapped in a head this repo
   does not control, so it cannot rely on a charset declaration. Every non-ASCII
   character in the prose is an HTML entity and every one in the script is a
   `\\uXXXX` escape. A stray em dash pasted in later would render as mojibake on
   whichever host serves it without UTF-8; this check is what stops that.

THE INDONESIAN MANUAL IS BUILT, NOT WRITTEN
-------------------------------------------
`docs/field-manual.id.html` is generated from the English manual, never edited by
hand, for the same reason the glossary is: a translation kept as a second copy
of the page is wrong the first time someone edits the English, and wrong
silently. So the English stays the one source, and `docs/field-manual.id.json`
holds the Indonesian for each block of it, keyed by that block's English with
its whitespace collapsed — the way `lib/i18n-id.ts` holds the interface's. A
block is the text between two block-level tags, inline markup and all, so a
translation can reorder a sentence around its links and emphasis. The glossary
inside it is the app's own Indonesian, from `explain.py` run in Indonesian.

The build fails, and `--check` with it, when an English block has no Indonesian
(edit the English, and the Indonesian must follow), when an entry matches no
block any more, and when a translation's markup differs from its English — the
same tags, the same links, in any order. The metric count is `{{N}}` in the
catalog, so adding a metric does not orphan every sentence that mentions it.
`--missing` prints the blocks still to translate.

USAGE
-----
    python scripts/build_glossary.py            # rewrite both manuals
    python scripts/build_glossary.py --check    # fail if either is out of date (CI)
    python scripts/build_glossary.py --missing  # list English blocks with no Indonesian
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

MANUAL = ROOT / "docs" / "field-manual.html"
MANUAL_ID = ROOT / "docs" / "field-manual.id.html"
CATALOG_ID = ROOT / "docs" / "field-manual.id.json"

# Which part of the app each metric belongs to. The manual's filter chips read
# these keys, so a new group needs a chip in the HTML as well as an entry here.
LENS: dict[str, str] = {}


def _group(name: str, keys: str) -> None:
    for key in keys.split():
        if key in LENS:
            raise SystemExit(f"{key!r} is classified twice")
        LENS[key] = name


_group("trend-long", """
    cagr volatility downsideDeviation sharpe sortino calmar var95 cvar95 skew kurtosis
    positiveDays worstDay bestDay maxDrawdown currentDrawdown timeUnderWaterDays ulcerIndex
    maxDrawdownRecoveryDays hurst momentum12_1 roc252 roc63 faberDistance fromHigh52w
    fromAllTimeHigh rangePosition regressionSlope regressionR2 relativeExcess
    benchmarkCorrelation rollingWorst""")
_group("trend-ind", """
    sma200 sma100 sma50 adx aroon rsi stochastic williamsR cci macd bbPercentB
    bbBandwidth atrPct mfi cmf volumeTrend coppock""")
_group("trend-swing", """
    riskReward stopDistance positionShare distanceToLevel vwapDistance
    squeezePercentile volumeRatio divergenceState gapState""")
_group("quality", "piotroski altman beneish altmanComponent beneishIndex")
_group("flow", "spread moveVsSpread yangZhangVol amihud anomalyRate qValue cusumEpisode flowBias")
_group("value", "upside probUndervalued terminalShare discountRate valuationSpread impliedGrowth")
_group("rank", "compositeRank signalRank signalOverlap")
_group("pretrade", "checkFiringRate")
_group("provenance", "validationDomain manipulationPosterior")
_group("portfolio", "holdingCorrelation effectiveHoldings riskShare "
                    "sharedDirection sharedDriver")
# On the Trend tab rather than the portfolio one: it reads the price record,
# which is the family that lens owns.
_group("trend-ind", "factorExposure")
# The cross-sectional tier, beside the other scan metrics.
_group("rank", "factorBreadth")
# The company view: what the filings say the business has done. Description
# rather than a lens, so it gets its own chip rather than joining Quality.
_group("company", "yearsProfitable revenueCagr netDebtToEbitda freeCashFlowYears")
# The board of what moved the markets. Context rather than a lens, so its own chip.
_group("markets", "dailyMove eventDayMove")

# Values chosen to land inside SOME band of every ladder in the registry. An
# interpreter is asked in turn until one returns a reading; the specific value
# does not matter because only `label`, `what` and `goodDirection` are used, and
# those do not vary by band.
PROBES = (1.0, 0.5, 50.0, 0.05, -0.2, 2.0, 25.0, 100.0, 8.0, -1.9, 0.004, 72.0)


def collect() -> list[dict]:
    from _lib import explain as E

    registered = set(E._REGISTRY)
    unclassified = registered - set(LENS)
    stale = set(LENS) - registered
    if unclassified or stale:
        raise SystemExit(
            "The glossary classification is out of sync with _lib/explain.py.\n"
            + (f"  registered but unclassified: {sorted(unclassified)}\n" if unclassified else "")
            + (f"  classified but not registered: {sorted(stale)}\n" if stale else "")
            + "  Fix LENS in this script, and add a filter chip to the manual if the\n"
              "  metric belongs to a group that does not exist yet."
        )

    rows = []
    for key, fn in E._REGISTRY.items():
        result = None
        for probe in PROBES:
            try:
                result = fn(probe)
            except Exception:
                continue
            if result:
                break
        if not result:
            raise SystemExit(
                f"{key!r} produced no reading for any probe value, so it cannot be "
                f"documented. Either its interpreter is broken or it needs context "
                f"arguments this script does not supply."
            )
        rows.append({"k": key, "t": result["label"], "d": result["what"],
                     "g": result["goodDirection"], "l": LENS[key]})

    rows.sort(key=lambda r: r["t"].lower())
    return rows


def render(html: str, rows: list[dict]) -> str:
    html = render_rows(html, rows)

    # The count appears in the contents, the lede, the section intro and the
    # search placeholder. Leaving any of them stale is the kind of small lie that
    # makes a reader distrust the rest.
    n = len(rows)
    html = re.sub(r"\b\d+ terms\b", f"{n} terms", html)
    html = re.sub(r"\b\d+ metrics defined\b", f"{n} metrics defined", html)
    html = re.sub(r"\bAll \d+ metrics\b", f"All {n} metrics", html)
    return html


# --------------------------------------------------------------------------- #
# The Indonesian manual
# --------------------------------------------------------------------------- #
TOKEN = re.compile(r"<!--.*?-->|<(script|style)\b[^>]*>.*?</\1>|<[^>]+>|[^<]+", re.S | re.I)
# Tags that sit inside a sentence. Everything else ends one block and starts the next.
INLINE = frozenset("a abbr b br cite code em i kbd mark q s small span strong sub sup "
                   "time u var wbr".split())
ATTRIBUTES = ("aria-label", "title", "placeholder", "alt")
COUNT = "{{N}}"
COUNTED = ("{} terms", "{} metrics defined", "All {} metrics")
LANG_EN = '<div class="shell" lang="en">'
LINK_TO_ID = ('<a class="lang" href="field-manual.id.html" hreflang="id" lang="id" '
              'translate="no">Bahasa Indonesia</a>')
LINK_TO_EN = ('<a class="lang" href="field-manual.html" hreflang="en" lang="en" '
              'translate="no">English</a>')
GENERATED = ("<!-- GENERATED by scripts/build_glossary.py from docs/field-manual.html and "
             "docs/field-manual.id.json.\n     Edit those, then run the script; an edit "
             "here is lost on the next build. -->\n")
WIDTH = 96


def _key(text: str) -> str:
    return " ".join(text.split())


def _tags(text: str) -> list[str]:
    return sorted(_key(tag) for tag in re.findall(r"<[^>]+>", text))


def _name(token: str) -> str | None:
    match = re.match(r"<\s*/?\s*([A-Za-z][A-Za-z0-9-]*)", token)
    return match.group(1).lower() if match else None


def _inline(token: str) -> bool:
    return not token.startswith("<") or (not token.startswith("<!--") and _name(token) in INLINE)


def _says_something(core: str) -> bool:
    """Whether a block has words to translate, not just numbers, symbols or code."""
    text = re.sub(r"<(code|kbd)\b[^>]*>.*?</\1>", "", core, flags=re.S)
    text = re.sub(r"<[^>]+>|&#?\w+;", "", text)
    return bool(re.search(r"[A-Za-z]", text))


def _words(text: str) -> list[str]:
    """Split on spaces outside tags, so an attribute list never breaks a line."""
    words, current, inside = [], [], False
    for char in text:
        inside = True if char == "<" else False if char == ">" else inside
        if char == " " and not inside:
            if current:
                words.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        words.append("".join(current))
    return words


def _wrap(text: str, column: int, indent: str) -> str:
    lines, line, width = [], [], column
    for word in _words(text):
        if line and width + 1 + len(word) > WIDTH:
            lines.append(" ".join(line))
            line, width = [word], len(indent) + len(word)
        else:
            width += len(word) + (1 if line else 0)
            line.append(word)
    if line:
        lines.append(" ".join(line))
    return ("\n" + indent).join(lines)


class Translation:
    """One pass over the English manual, recording every way the catalog falls short."""

    def __init__(self, catalog: dict[str, str]):
        self.catalog = catalog
        self.used: set[str] = set()
        self.missing: list[str] = []
        self.mismatched: list[str] = []

    def look_up(self, english: str) -> str | None:
        key = _key(english)
        indonesian = self.catalog.get(key)
        if not indonesian:
            if key not in self.missing:
                self.missing.append(key)
            return None
        self.used.add(key)
        return indonesian

    def attributes(self, tag: str) -> str:
        def swap(match: re.Match) -> str:
            value = match.group(2)
            if not _says_something(value):
                return match.group(0)
            indonesian = self.look_up(value)
            if indonesian and '"' in indonesian:
                # A bare quote would end the attribute; write &ldquo; or &quot;.
                self.mismatched.append(_key(value))
                return match.group(0)
            return f'{match.group(1)}="{indonesian}"' if indonesian else match.group(0)
        names = "|".join(re.escape(name) for name in ATTRIBUTES)
        return re.sub(rf'\b({names})="([^"]*)"', swap, tag)

    def block(self, run: str, start: int, html: str) -> str:
        core = run.strip()
        if not core or not _says_something(core):
            return re.sub(r"<[^>]+>", lambda m: self.attributes(m.group(0)), run)
        indonesian = self.look_up(core)
        if indonesian is None:
            return run
        key = _key(core)
        if _tags(indonesian) != _tags(key) or (COUNT in indonesian) != (COUNT in key):
            self.mismatched.append(key)
            return run
        lead = run[: len(run) - len(run.lstrip())]
        trail = run[len(run.rstrip()):]
        if "\n" in core:
            begin = start + len(lead)
            column = begin - html.rfind("\n", 0, begin) - 1
            indent = re.match(r"[^\n]*\n([ \t]*)", core).group(1)
            indonesian = _wrap(indonesian, column, indent)
        indonesian = re.sub(r"<[^>]+>", lambda m: self.attributes(m.group(0)), indonesian)
        return lead + indonesian + trail

    def script(self, code: str, rows: list[dict]) -> str:
        def swap(match: re.Match) -> str:
            english = json.loads(f'"{match.group(3)}"')
            indonesian = self.look_up(english)
            if indonesian is None:
                return match.group(0)
            holes = lambda text: sorted(re.findall(r"\{\w+\}", text))  # noqa: E731
            if holes(indonesian) != holes(english):
                self.mismatched.append(_key(english))
                return match.group(0)
            literal = json.dumps(indonesian, ensure_ascii=True)
            return f"{match.group(1)}{match.group(2)}: {literal},"
        block = re.search(r"const TEXT = \{\n(.*?)\n\};", code, re.S)
        if not block:
            raise SystemExit("Could not find the manual script's `const TEXT = {...};` block.")
        body = re.sub(r'^(\s*)(\w+): "((?:[^"\\]|\\.)*)",$', swap, block.group(1), flags=re.M)
        code = code[: block.start(1)] + body + code[block.end(1):]
        return render_rows(code, rows)

    def problems(self) -> list[str]:
        unused = [key for key in self.catalog if key not in self.used]
        out = []
        if self.missing:
            out.append(f"{len(self.missing)} English block(s) have no Indonesian. Run "
                       "`python scripts/build_glossary.py --missing` to list them, and add "
                       "each to docs/field-manual.id.json.")
        if self.mismatched:
            out.append("These translations do not carry their English's markup (the same tags "
                       "and links, in any order) or its placeholders:\n  "
                       + "\n  ".join(key[:110] for key in self.mismatched))
        if unused:
            out.append("These entries match no block of the English manual any more — the "
                       "English was edited or removed. Update or delete each:\n  "
                       + "\n  ".join(key[:110] for key in unused))
        return out


def render_rows(html: str, rows: list[dict]) -> str:
    """Inject the glossary rows into the one `const GLOSSARY = ...` line."""
    # ensure_ascii keeps the data as \uXXXX escapes. HTML entities would be wrong
    # here — they are not interpreted inside a JS string literal, and the page
    # escapes what it renders, so "&mdash;" would appear literally on screen.
    data = json.dumps(rows, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")

    # The array sits on ONE line. Matching to end-of-line rather than to the first
    # semicolon matters: a non-greedy `.*?;` stops at a semicolon inside the data
    # and leaves the tail behind.
    html, count = re.subn(r"const GLOSSARY = .*\n",
                          lambda _: f"const GLOSSARY = {data};\n", html, count=1)
    if count != 1:
        raise SystemExit("Could not find the `const GLOSSARY = ...` line in the manual.")
    return html


def indonesian(english: str, rows: list[dict], catalog: dict[str, str]) -> tuple[str, Translation]:
    """The Indonesian manual, built from the up-to-date English one."""
    n = len(rows)
    for phrase in COUNTED:
        english = re.sub(r"\b" + re.escape(phrase.format(n)) + r"\b", phrase.format(COUNT), english)
    for marker in (LANG_EN, LINK_TO_ID):
        if english.count(marker) != 1:
            raise SystemExit(f"The English manual must contain {marker!r} exactly once.")
    english = english.replace(LANG_EN, LANG_EN.replace('"en"', '"id"'))
    english = english.replace(LINK_TO_ID, LINK_TO_EN)

    work = Translation(catalog)
    out, run, run_start = [], [], 0

    def flush() -> None:
        if run:
            out.append(work.block("".join(run), run_start, english))
            run.clear()

    matches = list(TOKEN.finditer(english))
    position = 0
    while position < len(matches):
        match = matches[position]
        token, kind = match.group(0), (match.group(1) or "").lower()
        position += 1
        if 'translate="no"' in token and _inline(token):
            # Kept whole and verbatim, and it ends the block around it: the
            # language link sits beside the rail's heading, not inside its text.
            flush()
            closing = f"</{_name(token)}>"
            out.append(token)
            while position < len(matches) and out[-1] != closing:
                out.append(matches[position].group(0))
                position += 1
            continue
        if _inline(token):
            if not run:
                run_start = match.start()
            run.append(token)
            continue
        flush()
        if token.startswith("<!--") or kind == "style":
            out.append(token)
        elif kind == "script":
            out.append(work.script(token, rows))
        else:
            out.append(work.attributes(token))
    flush()
    return GENERATED + "".join(out).replace(COUNT, str(n)), work


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if either manual is out of date")
    parser.add_argument("--missing", action="store_true",
                        help="print the English blocks that have no Indonesian yet")
    args = parser.parse_args()

    if not MANUAL.exists():
        raise SystemExit(f"{MANUAL} not found.")

    original = MANUAL.read_text(encoding="ascii")
    rows = collect()
    updated = render(original, rows)
    _ascii(updated, MANUAL)

    from _lib import lang
    token = lang.use("id")
    try:
        rows_id = collect()
    finally:
        lang.reset(token)
    catalog = json.loads(CATALOG_ID.read_text(encoding="utf-8")) if CATALOG_ID.exists() else {}
    built, work = indonesian(updated, rows_id, catalog)

    if args.missing:
        print(json.dumps({key: "" for key in work.missing}, indent=1, ensure_ascii=False))
        return 1 if work.missing else 0

    problems = work.problems()
    if problems:
        print("The Indonesian manual cannot be built:\n\n" + "\n\n".join(problems),
              file=sys.stderr)
        return 1
    _ascii(built, MANUAL_ID)

    current_id = MANUAL_ID.read_text(encoding="ascii") if MANUAL_ID.exists() else None
    if args.check:
        stale = [path.relative_to(ROOT).as_posix() for path, old, new in
                 ((MANUAL, original, updated), (MANUAL_ID, current_id, built)) if old != new]
        if stale:
            print(f"{' and '.join(stale)} out of date. Run:\n"
                  "    python scripts/build_glossary.py", file=sys.stderr)
            return 1
        print(f"Manuals are up to date ({len(rows)} metrics, English and Indonesian).")
        return 0

    for path, old, new in ((MANUAL, original, updated), (MANUAL_ID, current_id, built)):
        if old != new:
            path.write_text(new, encoding="ascii")
            print(f"Updated {path.relative_to(ROOT)} ({len(rows)} metrics).")
    if updated == original and built == current_id:
        print(f"No change ({len(rows)} metrics).")
    return 0


def _ascii(html: str, path: Path) -> None:
    non_ascii = sorted({c for c in html if ord(c) > 127})
    if non_ascii:
        raise SystemExit(
            f"Non-ASCII characters in {path.name}: {non_ascii}. Use an HTML entity in "
            f"the prose (&mdash;, &ldquo;) so the page does not depend on the host "
            f"declaring a charset.")


if __name__ == "__main__":
    raise SystemExit(main())
