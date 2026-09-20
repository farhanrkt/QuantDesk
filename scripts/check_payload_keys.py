#!/usr/bin/env python3
"""
check_payload_keys.py
=====================
Find reads of a key that no real payload carries.

    python scripts/check_payload_keys.py            # newest local scan
    python scripts/check_payload_keys.py --market US

WHY THIS EXISTS
---------------
`neglect.py` read `technical.longTerm.drawdown.current` for as long as it
existed. `longterm.py` has always written `currentDrawdown`. The first three
hops of that path resolved, the fourth never did, and Python returned None — so
the drawdown was always absent, the sentence reporting it never rendered once,
and the module's docstring went on promising a reader context it was not
delivering.

NOTHING CAUGHT IT. Not the type checker, because Python has none here. Not the
tests, because the fixture planted `current` too: the test agreed with the code,
the code agreed with the test, and neither agreed with the data. Not a reader,
because a missing key is indistinguishable from a company that genuinely has no
value for it — which is exactly the gap-versus-refusal confusion this codebase
keeps having to undo, arriving this time through a typo.

WHAT IT CHECKS, AND WHY ONLY THIS SHAPE
----------------------------------------
Only CHAINED reads — `(x.get("a") or {}).get("b")` — and only where the parent
key `a` is observed in real data while the leaf `b` never is. That is the one
case where a typo is invisible: the parent resolving proves the path is real, so
the leaf returning None reads as data rather than as a mistake.

A bare `.get("x")` is deliberately NOT flagged. Most of those read dicts built a
few lines above, and flagging them produced 121 hits of which none was a defect
— a check nobody trusts is worse than no check, which is the same conclusion
`check_frontend.mjs` reached about its deleted eleventh rule.

OUTSIDE CI, BECAUSE IT NEEDS REAL DATA. The offline suite plants its own ground
truth, and a key audit against planted data proves only that the fixture and the
code agree — which is the failure that let the original bug through. Run it
after a sweep, and after changing what any module puts in a payload.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SCAN_CACHE = ROOT / ".scan_cache"

# `(something.get("parent") or {}).get("leaf")` — the shape where a typo hides.
#
# THE LEAF IS A LOOKAHEAD, AND THAT IS NOT A STYLE CHOICE. `finditer` does not
# return overlapping matches, so consuming the leaf's `.get(` meant the scanner
# resumed past it — and in a three-deep chain like
# `technical.longTerm.drawdown.current` the middle hop swallowed the very call
# the next pair needed. The first version of this check therefore matched
# `longTerm -> drawdown`, never looked at `drawdown -> current`, and reported
# the file clean with the original bug reintroduced. Caught by putting the bug
# back and watching the check pass, which is the only test an instrument like
# this has.
CHAIN = re.compile(
    r'\.get\(\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\)\s*or\s*\{\}\s*\)'
    r'\s*(?=\.get\(\s*"([A-Za-z_][A-Za-z0-9_]*)")')

# Keys whose name is reused by unrelated structures, where "the parent exists"
# does not imply the two are the same thing. Each entry is a false positive that
# was checked by hand; add to this list WITH the reason rather than deleting the
# finding.
AMBIGUOUS = {
    # `lensagreement` reads the stamped artifact's populations, whose `families`
    # block is a kappa reading — nothing to do with a verdict's price/filings/
    # register families, which happen to share the key name.
    "families",
}


def observed(market: str) -> dict[str, list]:
    """Real payloads, keyed by the name a consumer would know them under."""
    roots: dict[str, list] = collections.defaultdict(list)

    days = sorted(p for p in SCAN_CACHE.glob("*") if p.is_dir())
    for path in list(days[-1].glob("*.json"))[:120] if days else []:
        try:
            legs = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for leg, block in legs.items():
            if isinstance(block, dict) and isinstance(block.get("data"), dict):
                roots[leg].append(block["data"])

    scans = sorted(REPORTS.glob(f"scan-{market}-*.json"))
    if scans:
        try:
            report = json.loads(scans[-1].read_text())
        except (OSError, ValueError):
            report = {}
        for entry in (report.get("verdicts") or [])[:120]:
            roots["verdict"].append(entry)
            for key, value in entry.items():
                if isinstance(value, dict):
                    roots[key].append(value)
    return roots


def children_of(roots: dict[str, list], parent: str) -> set[str]:
    """Every key seen directly under a dict named `parent`, anywhere."""
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == parent and isinstance(value, dict):
                    found.update(value.keys())
                walk(value)
        elif isinstance(node, list):
            for item in node[:30]:
                walk(item)

    for blocks in roots.values():
        for block in blocks:
            walk(block)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--market", default="ID", choices=["ID", "US"])
    args = parser.parse_args()

    roots = observed(args.market)
    if not roots:
        print(f"No local scan artifacts for {args.market}. This check reads what a "
              f"real sweep wrote — run scripts/scan_market.py first. Skipping.")
        return 0

    payloads = sum(len(v) for v in roots.values())
    print(f"Reading {payloads} real payloads across {len(roots)} blocks.")

    cache: dict[str, set[str]] = {}
    findings = []
    for src in sorted((ROOT / "api" / "_lib").glob("*.py")):
        text = src.read_text()
        for match in CHAIN.finditer(text):
            parent, leaf = match.group(1), match.group(2)
            if parent in AMBIGUOUS:
                continue
            if parent not in cache:
                cache[parent] = children_of(roots, parent)
            children = cache[parent]
            if not children or leaf in children:
                continue
            line = text[:match.start()].count("\n") + 1
            findings.append((src.name, line, parent, leaf, sorted(children)[:10]))

    if not findings:
        print("No chained read resolves its parent and misses its leaf.")
        return 0

    print(f"\n{len(findings)} chained read(s) whose parent exists and whose leaf "
          f"never does:\n")
    for name, line, parent, leaf, children in findings:
        print(f"  {name}:{line}  .{parent}.{leaf}")
        print(f"      {parent} actually holds: {children}")
    print("\nEach is either a typo or a key name two structures share. If it is "
          "the second, add it to AMBIGUOUS with the reason.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
