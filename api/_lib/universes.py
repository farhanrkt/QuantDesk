"""
universes.py
============
Predefined ticker lists for the ranking tier.

THE HONESTY PROBLEM WITH A HARDCODED CONSTITUENT LIST
-----------------------------------------------------
Index membership changes. A list baked into source is correct on the day it is
written and decays from then on: names get acquired, delisted, promoted and
dropped, and nothing in this file finds out. That decay is INVISIBLE at the
point of use — a dropped constituent still fetches happily, and a promoted one
is simply absent, so a scan quietly ranks a slightly wrong universe and reports
no error.

Three things follow, and all three are deliberate.

1. EVERY LIST CARRIES ITS AS-OF DATE, and the UI shows it. A reader can then
   judge for themselves whether a list of this age still means what it says.

2. THERE IS NO S&P 500 LIST HERE, and its absence is a decision rather than an
   oversight. Five hundred symbols is exactly the length at which reciting from
   memory goes wrong, and a wrong ticker is not inert: this codebase has already
   been bitten once by a symbol collision that valued the right company while
   charting a different one (see `symbols.py`). A misremembered constituent
   produces a plausible ranking row for a company nobody asked about. Shipping
   475 correct names and 25 wrong ones is worse than shipping none, because the
   error is undetectable from the output. The custom-list box takes a pasted
   universe from a source that maintains one.

3. THE LISTS THAT ARE HERE ARE THE ONES WHOSE MEMBERSHIP IS SMALL, STABLE AND
   WIDELY PUBLISHED — the Dow's thirty, the Nasdaq-100, and the two Indonesian
   headline indices. Even these will drift, which is what the as-of date is for.

AND ONE LIST THAT IS NOT AN INDEX AT ALL
----------------------------------------
`idxresources` breaks rule 3 deliberately and is the only entry that does. It is
a CURATED list — somebody's judgement about which Indonesian listings are
resource plays — and no exchange publishes it, so there is no authority to check
it against and no membership event to notice. That is a weaker footing than the
four index lists and it is marked as such in its own note.

It exists because a factor basket needs constituents and the index lists do not
carry them: not one of the four Indonesian palm-oil names is in the IDX30 or the
LQ45, so a CPO basket cannot be built from them at all.

WHY IT IS A SEPARATE LIST RATHER THAN ADDITIONS TO idx30/lq45. AALI is not in
the LQ45. Writing it into that list to make it reachable would make the list say
something false, and the failure would be undetectable from the output — which
is the exact argument point 2 above makes against shipping an S&P 500 list from
memory. A curated list that admits it is curated costs nothing; a corrupted
index list costs the file its point.

It also keeps the four stamped artifacts valid. `measure_lens_agreement.py`,
`calibrate_checks.py`, `measure_correlation_stability.py` and
`backtest_ranking.py` all hardcode ("dow30", "nasdaq100", "idx30", "lq45"), so
leaving those four lists untouched means every published measurement still
describes the population it was measured on.
"""

from __future__ import annotations

from typing import Optional

# The date these lists were last transcribed. Shown on the panel so a stale
# universe is visible rather than assumed. An entry may override it with its own
# `asOf` — the curated list below does, because "when the index was transcribed"
# and "when somebody last judged what counts as a coal name" are different facts
# and a single date would quietly assert the stronger one for both.
AS_OF = "2026-08-22"


UNIVERSES: dict[str, dict] = {
    "dow30": {
        "id": "dow30",
        "name": "Dow Jones Industrial Average",
        "market": "US",
        "note": "Thirty large US companies, chosen by a committee rather than by size.",
        "tickers": [
            "AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
            "GS", "HD", "HON", "IBM", "JNJ", "JPM", "KO", "MCD", "MMM", "MRK",
            "MSFT", "NKE", "NVDA", "PG", "SHW", "TRV", "UNH", "V", "VZ", "WMT",
        ],
    },
    "nasdaq100": {
        "id": "nasdaq100",
        "name": "Nasdaq-100",
        "market": "US",
        "note": ("The hundred largest non-financial companies on the Nasdaq. Heavily "
                 "weighted toward technology, which makes a scan of it less diversified "
                 "than the count suggests."),
        "tickers": [
            "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
            "AMZN", "ANSS", "APP", "ARM", "ASML", "AVGO", "AZN", "BIIB", "BKNG", "BKR",
            "CCEP", "CDNS", "CDW", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD", "CSCO",
            "CSGP", "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DXCM", "EA", "EXC", "FANG",
            "FAST", "FTNT", "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX", "INTC",
            "INTU", "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX", "LULU", "MAR", "MCHP",
            "MDB", "MDLZ", "MELI", "META", "MNST", "MRVL", "MSFT", "MU", "NFLX", "NVDA",
            "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PLTR",
            "PYPL", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SNPS", "TEAM", "TMUS", "TSLA",
            "TTD", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY", "XEL", "ZS",
        ],
    },
    "idx30": {
        "id": "idx30",
        "name": "IDX30",
        "market": "ID",
        "note": ("Thirty of the most liquid Indonesian listings. Fundamentals coverage on "
                 "Yahoo is patchier here than for US names, so the deepen step will have "
                 "more gaps."),
        "tickers": [
            "ADRO", "AMRT", "ANTM", "ARTO", "ASII", "BBCA", "BBNI", "BBRI", "BMRI", "BRIS",
            "BRPT", "BUKA", "CPIN", "EMTK", "ESSA", "EXCL", "GOTO", "ICBP", "INCO", "INDF",
            "INKP", "ITMG", "KLBF", "MDKA", "MEDC", "PGAS", "PTBA", "SMGR", "TLKM", "UNTR",
        ],
    },
    "lq45": {
        "id": "lq45",
        "name": "IDX LQ45",
        "market": "ID",
        "note": ("Forty-five Indonesian listings selected for liquidity and market value. "
                 "Reviewed twice a year, so membership drifts faster than the headline "
                 "US indices."),
        "tickers": [
            "ACES", "ADRO", "AKRA", "AMRT", "ANTM", "ARTO", "ASII", "BBCA", "BBNI", "BBRI",
            "BBTN", "BMRI", "BRIS", "BRPT", "BUKA", "CPIN", "CTRA", "ESSA", "EXCL", "GGRM",
            "GOTO", "HRUM", "ICBP", "INCO", "INDF", "INDY", "INKP", "INTP", "ISAT", "ITMG",
            "JPFA", "JSMR", "KLBF", "MAPI", "MBMA", "MDKA", "MEDC", "PGAS", "PGEO", "PTBA",
            "SIDO", "SMGR", "TLKM", "TOWR", "UNTR",
        ],
    },
    "idxresources": {
        "id": "idxresources",
        "name": "IDX resources (curated)",
        "market": "ID",
        "asOf": "2026-08-31",
        "note": ("Indonesian coal, nickel, palm oil and gold listings, grouped so a "
                 "factor basket has constituents. NOT AN INDEX — nobody publishes this "
                 "list and no exchange maintains it, so it carries the judgement of "
                 "whoever last edited it rather than an authority. Six of these names "
                 "are in neither the IDX30 nor the LQ45."),
        "tickers": [
            # Coal. ADRO, PTBA, ITMG, INDY and HRUM are index members; BUMI is not.
            "ADRO", "PTBA", "ITMG", "INDY", "HRUM", "BUMI",
            # Nickel. MBMA is already in the LQ45; NCKL is not.
            "INCO", "ANTM", "MBMA", "NCKL",
            # Palm oil. NONE of these four is in either index, which is the whole
            # reason this list exists — there was no way to build a CPO basket.
            "AALI", "LSIP", "DSNG", "TAPG",
            # Gold and copper. ANTM appears above and is deliberately not repeated.
            "MDKA",
        ],
    },
}

# DELIBERATELY ABSENT FROM `idxresources`: UNTR.
#
# United Tractors sells mining equipment and holds coal assets, and it reads a
# higher R-squared against the coal names than one of the coal miners reads
# against its own peers. That makes it the most interesting name in this file
# and the one that must stay OUT of the basket: a factor built to explain UNTR
# and then used to report that UNTR is coal-exposed explains nothing. Keeping it
# out is what makes its exposure measurable rather than circular.
#
# The same argument is why any name in this list needs leave-one-out when it is
# analysed against a basket it belongs to, and why UNTR does not.


def get(universe_id: str) -> Optional[dict]:
    """One universe by id, with its symbols resolved for its own market.

    Resolution happens here rather than at the call site so an IDX list arrives
    already suffixed. `symbols.resolve` is idempotent, so the route calling it
    again is harmless — see `symbols.py`.
    """
    entry = UNIVERSES.get((universe_id or "").strip().lower())
    if entry is None:
        return None
    from . import symbols
    return {
        **entry,
        "asOf": entry.get("asOf", AS_OF),
        "tickers": [symbols.resolve(t, entry["market"]) for t in entry["tickers"]],
        "count": len(entry["tickers"]),
    }


def containing(symbol: str) -> list[dict]:
    """Every predefined universe this symbol belongs to, largest first.

    Used to give a single-ticker view a peer group without asking the reader to
    choose one before they know what the choice means. Ordered by size because a
    percentile against ninety-nine names is better resolved than one against
    twenty-nine — the Dow places a stock in thirds, which is barely a comparison.

    The membership test runs against RESOLVED symbols so that "BBCA" typed on the
    IDX market matches the "BBCA.JK" stored in the list. Matching raw strings
    would silently find nothing for every Indonesian ticker.
    """
    from . import symbols as sym

    target = (symbol or "").strip().upper()
    if not target:
        return []

    found = []
    for entry in UNIVERSES.values():
        resolved = {sym.resolve(t, entry["market"]) for t in entry["tickers"]}
        if target in resolved:
            found.append({"id": entry["id"], "name": entry["name"],
                          "market": entry["market"], "note": entry["note"],
                          "count": len(entry["tickers"]),
                          "asOf": entry.get("asOf", AS_OF)})
    found.sort(key=lambda e: -e["count"])
    return found


def catalogue() -> list[dict]:
    """Every predefined universe, without the ticker lists, for the picker."""
    return [
        {"id": entry["id"], "name": entry["name"], "market": entry["market"],
         "note": entry["note"], "count": len(entry["tickers"]),
         "asOf": entry.get("asOf", AS_OF)}
        for entry in UNIVERSES.values()
    ]
