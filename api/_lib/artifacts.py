"""
artifacts.py
============
Writing one market's measurement without destroying another's.

THE BUG THIS EXISTS TO PREVENT, WHICH ALREADY HAPPENED
--------------------------------------------------------
Every stamped artifact in this app is keyed by market: `tape_calibration.json`,
`patterns_calibration.json`, `verdict_backtest.json`,
`volume_profile_calibration.json`. Each of their scripts takes `--market` as a
repeatable flag, builds a fresh `{"markets": {...}}` from whatever it was asked
to measure, and writes the file.

Which means running `backtest_verdict.py --market US` after a previous
`--market ID` run silently DELETES the Indonesian measurement. That is exactly
what happened on 11 September 2026: a ten-minute run over 120 US names replaced
a stamped result that had taken a comparable run over the Indonesian market, and
nothing said so — the script printed "written to ..." and exited zero. It was
noticed only because the next command happened to list the artifact's markets.

The loss is worse than it sounds. These artifacts are the only thing standing
between a feature and `PRODUCT.md` constraint 2: `patterns.py` scores nothing
without one, `tape.py` reports no direction without one, and the verdict panel's
null result gets LOUDER when one is missing. Quietly deleting one turns a
measured feature back into an unmeasured one, in the direction of showing less
and claiming the same.

WHAT MERGING DOES AND DOES NOT DO
-----------------------------------
A market measured in this run REPLACES its previous row — a re-measurement is
the point. A market absent from this run is CARRIED FORWARD unchanged, with its
own `measuredOn` intact, so a two-week-old Indonesian study stays two weeks old
rather than inheriting today's date from a US run that never looked at it.

It does not merge WITHIN a market. Two partial runs of the same market do not
combine into one better measurement; the later one wins whole. Half a study
stitched to half another study is not a study.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional


def merge_markets(path: Path, payload: dict,
                  today: Optional[str] = None) -> dict:
    """Merge `payload` into the artifact at `path`, preserving other markets.

    Returns the merged document with two extra keys describing what happened:
    `measuredNow` lists the markets this run wrote, `carriedForward` lists the
    ones it preserved. Callers print those, because a run that silently kept
    something is as surprising as one that silently dropped it.
    """
    stamp = today or dt.date.today().isoformat()

    existing: dict = {}
    try:
        loaded = json.loads(Path(path).read_text())
        if isinstance(loaded, dict):
            existing = loaded
    except (OSError, ValueError):
        # No artifact yet, or one this version cannot read. Either way the
        # measurement in hand is strictly better than nothing, and refusing to
        # write would strand it.
        existing = {}

    before = existing.get("markets") if isinstance(existing.get("markets"), dict) else {}
    fresh = payload.get("markets") if isinstance(payload.get("markets"), dict) else {}

    # EVERY ROW CARRIES ITS OWN DATE. Without this a market carried forward
    # inherits the top-level `measuredOn` of the run that did not measure it,
    # and a stale study starts reporting itself as current.
    stamped = {}
    for code, row in fresh.items():
        stamped[code] = ({**row, "measuredOn": row.get("measuredOn") or stamp}
                         if isinstance(row, dict) else row)

    carried = [code for code in before if code not in stamped]
    merged = {**existing, **payload,
              "markets": {**before, **stamped},
              "measuredOn": stamp}
    merged["measuredNow"] = sorted(stamped)
    merged["carriedForward"] = sorted(carried)
    return merged


def write_markets(path: Path, payload: dict,
                  today: Optional[str] = None) -> dict:
    """`merge_markets`, then write it. Returns the merged document."""
    merged = merge_markets(path, payload, today=today)
    Path(path).write_text(json.dumps(merged, indent=1))
    return merged


def note(merged: dict) -> str:
    """One line saying what was written and what was left alone."""
    now = merged.get("measuredNow") or []
    kept = merged.get("carriedForward") or []
    text = f"measured {', '.join(now) if now else 'nothing'}"
    if kept:
        text += (f"; kept the existing {', '.join(kept)} measurement"
                 f"{'' if len(kept) == 1 else 's'} untouched")
    return text
