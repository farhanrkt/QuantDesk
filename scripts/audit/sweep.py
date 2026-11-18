#!/usr/bin/env python3
"""
sweep.py
========
Run the production payload builders over real companies and record what they
actually did: which statement line each lookup resolved to and how, the shape
of each statement, and every quality score.

WHY IT EXISTS
-------------
The offline suite plants its own ground truth, so it can only show that fixture
and code agree. Three questions in docs/AUDIT.md are about what the PROVIDER
sends, and no fixture answers them:

  * Does the substring fallback in `valuation._get_row` ever pick a line?
    (COR-1. On 14 November 2026: for seven of 198 companies, all Indonesian,
    and for six of them the wrong line.)
  * Is the balance-sheet share count restated for splits? (It is.)
  * Does the same request return the same statements twice? (REL-7. Not
    always: run this twice and `--compare` the outputs.)

It is a network script, outside CI, like every other measurement here.

    python scripts/audit/sweep.py out1.json                 # 198 names, ~15 minutes
    python scripts/audit/sweep.py out2.json --group US      # one group again
    python scripts/audit/sweep.py --compare out1.json out2.json

Set QUANTDESK_FUNDAMENTALS_TTL_DAYS to reuse statements between runs when the
question is about the code; leave it unset when the question is about what the
provider returns, or the second pass reads the first pass's cache.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

import index as api  # noqa: E402  — the production payload builders, deliberately

from _lib import (field, market_data, quality, screendomain, trackrecord,  # noqa: E402
                  universes, valuation)

INDEX_UNIVERSES = ("dow30", "nasdaq100", "idx30", "lq45")
SMALL_IDX_SEED = 20261114


def plan(extra_small: int, group: str | None) -> dict[str, str]:
    """Symbol -> group: the four index lists, then Indonesian names drawn from
    the rest of the exchange, because the index lists are the best-covered
    companies and the fragile data is everywhere else."""
    names: dict[str, str] = {}
    for universe_id in INDEX_UNIVERSES:
        entry = universes.get(universe_id)
        for symbol in entry["tickers"]:
            names.setdefault(symbol, entry["market"])
    listing = json.loads((ROOT / "api" / "_lib" / "listings_ID.json").read_text())
    pool = sorted({row["symbol"] for row in listing.get("rows", [])} - set(names))
    random.Random(SMALL_IDX_SEED).shuffle(pool)
    for symbol in pool[:extra_small]:
        names[symbol] = "ID-small"
    if group:
        names = {symbol: g for symbol, g in names.items() if g == group}
    return names


def trace_row_lookups(log: dict, current: dict) -> None:
    """Record every lookup that resolved to a row NOT named by an exact alias."""
    original = valuation._get_row

    def traced(frame, key):
        row = original(frame, key)
        if row is not None:
            label = str(row.name).strip()
            aliases = [alias.strip().lower() for alias in valuation.ROW_ALIASES.get(key, [])]
            if label.lower() not in aliases:
                log[f"{key}|{label}"].add(current["symbol"])
        return row

    for module in (valuation, quality, field, market_data, screendomain, trackrecord):
        if hasattr(module, "_get_row"):
            module._get_row = traced


def read_one(symbol: str, group: str) -> dict:
    market = "ID" if symbol.endswith(".JK") else "US"
    record: dict = {"symbol": symbol, "group": group}
    try:
        company = market_data.company(symbol)
    except Exception as exc:
        company = {"ok": False}
        record["companyError"] = repr(exc)[:120]
    record["ok"] = bool(company.get("ok"))
    record["sector"] = company.get("sector")
    record["shapes"] = {name: list(getattr(company.get(name), "shape", (0, 0)))
                        for name in ("income", "balance", "cashflow")}
    record["fiscal"] = [str(column)[:10]
                        for column in list(getattr(company.get("balance"), "columns", []))[:2]]
    record["price"], record["priceAsOf"] = company.get("price"), company.get("price_as_of")
    shares = quality._series(company.get("balance"), "shares_issued")
    record["shares"] = (None if shares is None else
                        [float(v) if np.isfinite(v) else None for v in list(shares.values)[:3]])
    for name, build in (("quality", lambda: api.quality_payload(symbol)),
                        ("valuation", lambda: api.valuation_payload(symbol, market_code=market)),
                        ("company", lambda: api.company_payload(symbol))):
        try:
            payload = build()
        except Exception as exc:
            record[name] = {"error": f"{type(exc).__name__}: "
                                     f"{str(getattr(exc, 'detail', exc))[:160]}"}
            continue
        if name == "quality":
            piotroski, beneish = payload.get("piotroski") or {}, payload.get("beneish") or {}
            record[name] = {
                "applicable": payload.get("applicable"), "cause": payload.get("cause"),
                "piotroski": {k: piotroski.get(k) for k in ("score", "maxScore", "band")},
                "altman": (payload.get("altman") or {}).get("band"),
                "beneish": {"band": beneish.get("band"),
                            "lvgi": (beneish.get("indices") or {}).get("LVGI"),
                            "available": beneish.get("indicesAvailable")}}
        elif name == "valuation":
            record[name] = {"engine": payload.get("engine"), "verdict": payload.get("verdict"),
                            "cause": payload.get("cause")}
    return record


def sweep(out: Path, extra_small: int, group: str | None) -> int:
    names = plan(extra_small, group)
    fallbacks: dict = defaultdict(set)
    current = {"symbol": None}
    trace_row_lookups(fallbacks, current)
    noise = io.StringIO()
    records = []

    def save() -> None:
        out.write_text(json.dumps(
            {"records": records,
             "fallbacks": {key: sorted(v) for key, v in fallbacks.items()}}, indent=1, default=str))

    for position, (symbol, name_group) in enumerate(names.items(), start=1):
        current["symbol"] = symbol
        started = time.monotonic()
        with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
            record = read_one(symbol, name_group)
        record["seconds"] = round(time.monotonic() - started, 1)
        records.append(record)
        if position % 10 == 0:
            print(f"{position}/{len(names)} {symbol} {record['seconds']}s", flush=True)
            save()
    save()

    print(f"\n{len(records)} companies. Lookups that resolved by substring:")
    for key, hit in sorted(fallbacks.items(), key=lambda item: -len(item[1])):
        print(f"  {key:66} {len(hit):3}  {', '.join(sorted(hit)[:6])}")
    if not fallbacks:
        print("  none")
    # A sweep that answers in no time is a network that has gone, and every
    # record from then on is a gap, not a company.
    instant = sum(1 for record in records if record["seconds"] == 0.0 and not record["ok"])
    if instant:
        print(f"\n{instant} companies answered instantly with nothing: the provider "
              f"stopped answering part-way. Run again.")
    return 0


def compare(first: Path, second: Path) -> int:
    a = {r["symbol"]: r for r in json.loads(first.read_text())["records"]}
    b = {r["symbol"]: r for r in json.loads(second.read_text())["records"]}
    shared = sorted(set(a) & set(b))
    differing = 0
    for symbol in shared:
        changed = [key for key in ("ok", "sector", "shapes", "fiscal", "shares", "quality",
                                   "valuation") if a[symbol].get(key) != b[symbol].get(key)]
        if changed:
            differing += 1
            print(f"{symbol}: {', '.join(changed)}")
            for key in changed:
                print(f"    {key}: {json.dumps(a[symbol].get(key))[:150]}")
                print(f"    {' ' * len(key)}  {json.dumps(b[symbol].get(key))[:150]}")
    print(f"\n{differing} of {len(shared)} companies read differently between the two passes.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--compare", action="store_true", help="diff two earlier outputs")
    parser.add_argument("--small", type=int, default=30,
                        help="Indonesian names drawn from outside the index lists")
    parser.add_argument("--group", choices=("US", "ID", "ID-small"))
    args = parser.parse_args()
    if args.compare:
        if len(args.paths) != 2:
            parser.error("--compare takes two files")
        return compare(*args.paths)
    return sweep(args.paths[0], args.small, args.group)


if __name__ == "__main__":
    raise SystemExit(main())
