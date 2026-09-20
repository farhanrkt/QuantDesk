"""
field.py
========
What the business actually does, and where it sits among the listed names doing
the same thing.

WHY THIS EXISTS
---------------
`neglect.py` finds companies that are cheap, solid and unattended. It cannot say
whether any of them is a *good business*, because every input it reads is a
number off a filing. The owner's worked example was a company that "is the
biggest player on their field, its financial report solid, and they are needed"
— three claims, of which the scanner could previously check exactly one.

This module adds the second: it reports what the company sells, and whether it
is the largest of the listed names selling the same thing. The third claim —
whether the world *needs* the product — is not computable from anything here and
no proxy for it is invented below.

TWO HALVES, AND ONLY ONE OF THEM IS A CLAIM
--------------------------------------------
`profile()` is DESCRIPTION. Industry, sector, the provider's own business
summary, headcount, country. It asserts nothing; it repeats what the data source
says, and marks the difference between "the source had no description" and "this
record was written before the app asked for one".

`standings()` is a MEASUREMENT, and a narrow one. Inside each industry label it
ranks the scanned names by annual revenue and reports the rank, the number of
measured peers, the leader's share of their combined revenue, and the leader's
margin over the runner-up.

REVENUE, NOT MARKET CAPITALISATION, AND THE REASON IS THE SAME ONE `neglect.py`
IS BUILT ON. Market cap measures what the market thinks a company is worth,
which is precisely the quantity this whole screen suspects of being wrong. Rank
a cheap champion by market cap and its cheapness demotes it: the more underrated
it is, the smaller it looks. Revenue is what it sells, and the market has no
vote on it.

WHAT "LEADS ITS FIELD" MEANS HERE, EXACTLY
-------------------------------------------
Rank 1 by revenue, at least MIN_PEERS measured names in the field, and at least
LEAD_MARGIN times the runner-up's revenue.

The margin is not decoration. Measured on the 521 Indonesian listings with usable
statements in the local cache, a bare rank-1 test calls 97 of 97 fields won; at
1.5x it is 42, and at 2.0x it is 31. The US side, 2,203 names over 142 fields,
gives 60 at 1.5x and 32 at 2.0x. Twice the runner-up is a lead that one year's
accounting, one disposal or one change in where a conglomerate books a segment
cannot flip, and a word like "leads" should cost something to earn.

At 2.0x the US standings return AAPL for consumer electronics, AMZN for internet
retail, MSFT for infrastructure software, NVDA for semiconductors, PM for
tobacco, HCA for medical care facilities. That the method reproduces answers
already known is the only validation available for it, and it is weak evidence:
it says the arithmetic is not broken, not that the ranking predicts anything.

THIS IS A STANDING AMONG *SCANNED* NAMES, WHICH IS NOT MARKET SHARE
---------------------------------------------------------------------
Said plainly because the output is one short sentence away from sounding like
market share, and it is not that, on four counts:

  * Only LISTED companies are in it. A field's real leader is often private, and
    in Indonesia frequently is.
  * Only companies in THIS market. The US sweep places Apple first in consumer
    electronics on three measured peers, because Samsung and Sony are not US
    common stock. The figure is right and the impression it gives is wrong.
  * Only companies whose statements ARRIVED. 201 of the 722 cached Indonesian
    records carry no income statement at all — a throttled fetch, not a company
    without revenue — so a field's true leader can simply be missing and the
    runner-up inherits the crown. `standings()` therefore reports `unplaced`,
    and a reader who sees a large one should distrust every thin field in it.
  * Only companies the provider gave the SAME LABEL. These labels are coarse and
    occasionally wrong. "Conglomerates" is not a field anyone competes in.

So the wording everywhere below is "the largest of the N scanned names labelled
X", never "the market leader". The caveat travels in the payload as `basis` so a
client cannot render the standing without it.

A WRONG CURRENCY LABEL MANUFACTURES A CHAMPION, AND IT DID
------------------------------------------------------------
The first run of this ranking crowned RIGS.JK with 99.4% of Indonesian marine
shipping and 456 times the runner-up. RIGS is a small tug and barge operator.
Yahoo reports its statements as USD while serving them in rupiah, so converting
at the boundary multiplied a correct figure by about 16,300 — and the result was
not an obvious error. It was a confident, plausible-looking market leader.

That is the failure mode worth guarding, because it is silent: bad units do not
produce a crash, they produce a ranking. `revenue_of` therefore refuses a figure
whose implied price-to-sales ratio is outside PLAUSIBLE_PS, and a refused figure
leaves the name UNPLACED rather than placing it at zero — placing it low would
hand its field's lead to whoever is next, which is the same error one rank down.

Measured across all 388 cached records whose reporting and trading currencies
differ: 2 are demonstrably mislabelled (RIGS.JK, and YPF, which reports in
dollars while labelled pesos), 100 are correctly labelled, and 283 involve a
rate near 1 where this test cannot tell and does not pretend to. The two it
catches are the two that matter, because a near-1 rate cannot manufacture a
champion.

The test runs ONLY where a conversion actually happened. An earlier version ran
it on every name and refused 71, of which essentially none was a units error —
a very low price-to-sales ratio is what an expensive company looks like, not a
broken one. See `revenue_of`.

WHAT WAS TRIED AND IS NOT HERE: A "NICHE" TEST
-----------------------------------------------
The obvious companion to "leads its field" is "and the field is a small one",
and the obvious measure is the field's share of the scanned market's total
revenue. It was built and it does not discriminate. Across the fields with a
clear leader the median field holds 0.5% of scanned revenue, which is not a
finding about narrowness — it is 1/97 restated, an artifact of how many labels
the provider uses. A threshold on it would sort fields by how finely their
corner of the economy happens to be subdivided.

So no `niche` flag ships. The peer count and the field's revenue share are
reported as facts, and how narrow a business is stays a judgement the reader
makes from the description — which is the half of this module that exists for
exactly that purpose.

NO PREDICTIVE CLAIM, AND NO BACKTEST EITHER
---------------------------------------------
`PRODUCT.md` constraint 2 requires a measurement before any feature that implies
returns. Nothing here implies one: a standing is a description of today, and the
module scores nothing, gates nothing and changes no verdict.

A backtest is also unavailable, and for the same reason `neglect.py` publishes:
industry labels arrive as a current snapshot with no history, so "which names
were in this field in March" cannot be reconstructed, and the revenue behind the
ranking would be read as restated today. The honest route is `scanlog.py`
recording what the standing said on the day it said it.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .valuation import _get_row

# How many measured names a field needs before a rank in it means anything.
# Three is the smallest number for which "largest" beats more than one rival.
# Below it the field is reported with its members and no leader is named.
MIN_PEERS = 3

# How far ahead of the runner-up the leader must be. See the docstring: 2.0x is
# a lead one year's accounting cannot flip, and it cuts the Indonesian fields
# with a named leader from 97 to 31.
LEAD_MARGIN = 2.0

# The price-to-sales band a converted figure is checked against, and ONLY a
# converted one. Deliberately enormous — real ratios live between about 0.1 and
# 30 — because this is a units test, not a valuation screen, and the error it
# exists to catch is a factor of sixteen thousand. Applying it to every name
# instead refused 71, nearly all of them companies that are simply expensive;
# see `revenue_of`.
PLAUSIBLE_PS = (0.01, 100.0)

# How much of the provider's business summary to carry into a listing payload.
# The full text is kept in the local report; a table of 3,000 names carrying
# 2,000 characters each is a six-megabyte payload nobody reads.
SUMMARY_CHARS = 320


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def _trim(text: str, limit: int = SUMMARY_CHARS) -> str:
    """The opening of a description, cut at a sentence end where one is near.

    Cutting mid-clause reads as truncation damage rather than a summary, so a
    full stop anywhere in the last third of the budget wins over the budget.
    """
    body = " ".join((text or "").split())
    if len(body) <= limit:
        return body
    window = body[:limit]
    stop = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if stop >= int(limit * 0.66):
        return window[:stop + 1]
    cut = window.rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def profile(company: Optional[dict]) -> dict:
    """What this company does, as the data source states it.

    NOT A JUDGEMENT ABOUT THE BUSINESS. Every field is repeated from the
    provider, and the only thing this function decides is how to say that
    something is missing.

    A MISSING DESCRIPTION HAS TWO CAUSES AND THEY ARE NOT THE SAME. The key
    being absent means the record was written before this app asked for a
    summary — a cached record from an earlier version — and a refetch will fill
    it. The key being present and empty means the provider has no description
    for this listing, and refetching will not help. The first is a gap, the
    second is a fact about the data, and reporting both as "no description"
    would send a reader to re-run a scan that cannot change the answer.
    """
    record = company if isinstance(company, dict) else {}
    industry = (record.get("industry") or "").strip()
    sector = (record.get("sector") or "").strip()

    has_key = "business_summary" in record
    summary = (record.get("business_summary") or "").strip() if has_key else ""
    if summary:
        state = "described"
    elif not has_key:
        state = "not fetched"
    elif not industry and not sector:
        # NOTHING DESCRIPTIVE CAME BACK AT ALL, WHICH IS A THROTTLE SIGNATURE
        # RATHER THAN A SILENT COMPANY. `quality.py` already treats an empty
        # sector AND industry this way and refuses to score on it: Yahoo limits
        # the `.info` scrape long before the statement endpoints, so a fetch can
        # return complete filings with every descriptive field blank. Measured
        # there on eight US names, all eight returned a sector on an unhurried
        # refetch.
        #
        # Observed here on INDF.JK, which reads "Packaged Foods" on any
        # unthrottled fetch and came back with nothing on a two-worker sweep.
        # Calling that "the provider publishes no description" would be a
        # statement about Indofood rather than about the rate limit.
        state = "not returned"
    else:
        state = "none published"

    employees = _finite(record.get("employees"))
    return {
        "sector": sector or None,
        "industry": industry or None,
        "summary": summary or None,
        "summaryShort": _trim(summary) if summary else None,
        "summaryState": state,
        "employees": int(employees) if employees is not None and employees > 0 else None,
        "country": (record.get("country") or "").strip() or None,
        "website": (record.get("website") or "").strip() or None,
        "reading": _profile_reading(industry, sector, summary, state),
    }


def _profile_reading(industry: str, sector: str, summary: str, state: str) -> str:
    where = industry or sector
    if state == "described":
        return (f"Classified as {where}. " if where else "") + _trim(summary)
    if state == "none published":
        return (f"Classified as {where}, and the data source publishes no description "
                f"of what it does beyond that label.")
    if state == "not returned":
        return ("No sector, industry or description came back for this listing. That "
                "is the signature of a throttled fetch rather than a company nobody "
                "describes — the same one the accounting screens refuse to score on — "
                "so it says nothing about the business and an unhurried refetch will "
                "usually resolve it.")
    return ((f"Classified as {where}. No business description was fetched for this "
             f"record — it predates the app asking for one, and a refetch will "
             f"supply it.") if where else
            "No business description was fetched for this record, which predates the "
            "app asking for one. A refetch will supply it.")


def revenue_of(company: Optional[dict]) -> dict:
    """The most recent annual top line, in the currency the shares trade in.

    Returns a reading with `usable` false and a reason rather than a number it
    cannot stand behind, because the consumer is a ranking: a figure in the
    wrong units does not look wrong there, it looks like a market leader. See
    the docstring on RIGS.JK.
    """
    record = company if isinstance(company, dict) else {}
    series = _get_row(record.get("income"), "revenue")
    value = None
    as_of = None
    if series is not None:
        clean = pd.Series(series).dropna()
        if len(clean):
            value = _finite(clean.iloc[0])
            label = clean.index[0]
            as_of = str(getattr(label, "date", lambda: label)())

    currency = (record.get("currency") or "").upper() or None
    reporting = (record.get("financial_currency") or "").upper() or None
    converted = _finite(record.get("fx_rate")) is not None

    if value is None or value <= 0:
        return {"usable": False, "value": None, "currency": currency, "asOf": as_of,
                "reason": "no revenue line came back on the income statement"}

    # STATEMENTS IN ANOTHER CURRENCY THAT WERE NOT CONVERTED CANNOT BE COMPARED.
    # `market_data` converts at the boundary when it has a rate; when it does
    # not, the figure is real but on a different scale from its neighbours, and
    # a ranking is exactly where that does damage.
    if reporting and currency and reporting != currency and not converted:
        return {"usable": False, "value": None, "currency": currency, "asOf": as_of,
                "reason": (f"the statements are written in {reporting} and the shares "
                           f"trade in {currency}, and no exchange rate was applied, so "
                           f"this figure is not on the same scale as its peers")}

    # THE UNITS SANITY TEST, AND IT ONLY RUNS ON A CONVERTED FIGURE.
    #
    # The first version asked whether the price-to-sales ratio was plausible for
    # EVERY name, and refused 71 of them. Almost none was a units error: MSTR at
    # 0.009, DJT at 0.0015, a row of pre-revenue biotechs, and DCII.JK, the most
    # expensive listing on the Indonesian exchange. A tiny ratio is what a
    # company the market loves looks like, and it is indistinguishable from a
    # mis-scaled one by inspection.
    #
    # What IS distinguishable is a conversion that made things worse. A record
    # whose statements were never converted cannot have been mis-converted, so
    # the test has no business running on one. Where a conversion did happen,
    # both figures are available and the question becomes a comparison rather
    # than a threshold: if undoing the conversion lands the ratio inside the
    # plausible band and leaving it converted does not, the provider's currency
    # label is the thing that is wrong.
    rate = _finite(record.get("fx_rate"))
    cap = _finite(record.get("market_cap"))
    if converted and rate and rate > 0 and cap is not None and cap > 0:
        low, high = PLAUSIBLE_PS
        after = value / cap
        before = (value / rate) / cap
        if not (low <= after <= high) and low <= before <= high:
            return {"usable": False, "value": None, "currency": currency, "asOf": as_of,
                    "reason": (f"the statements are labelled {reporting} and were "
                               f"converted at {rate:,.4g}, which puts revenue at "
                               f"{value:,.0f} against a market value of {cap:,.0f} — a "
                               f"price-to-sales ratio of {after:,.4g}, where the "
                               f"unconverted figure gives {before:,.4g}. The label "
                               f"looks wrong and the converted figure is not "
                               f"comparable with its peers")}

    return {"usable": True, "value": value, "currency": currency, "asOf": as_of,
            "converted": converted, "reportingCurrency": reporting if converted else None,
            "reason": None}


def standings(entries: list[dict]) -> dict:
    """Rank every usable name inside its own industry label, by revenue.

    `entries` are dicts with `ticker`, `industry` and `revenue`; a name missing
    either is counted in `unplaced` rather than dropped silently, because the
    size of that count is what tells a reader how much to trust a thin field.
    """
    usable, unplaced = [], []
    for entry in entries or []:
        industry = (entry.get("industry") or "").strip()
        revenue = _finite(entry.get("revenue"))
        if not industry or revenue is None or revenue <= 0:
            unplaced.append({"ticker": entry.get("ticker"),
                             "why": "no industry" if not industry else "no usable revenue"})
            continue
        usable.append({"ticker": entry.get("ticker"), "name": entry.get("name"),
                       "industry": industry, "revenue": revenue})

    groups: dict[str, list[dict]] = {}
    for row in usable:
        groups.setdefault(row["industry"], []).append(row)

    total = sum(row["revenue"] for row in usable)
    fields, positions = {}, {}
    for industry, members in groups.items():
        members.sort(key=lambda r: -r["revenue"])
        pool = sum(r["revenue"] for r in members)
        leader = members[0]
        runner_up = members[1] if len(members) > 1 else None
        margin = (leader["revenue"] / runner_up["revenue"]
                  if runner_up and runner_up["revenue"] > 0 else None)
        named = bool(len(members) >= MIN_PEERS and margin is not None
                     and margin >= LEAD_MARGIN)

        fields[industry] = {
            "industry": industry,
            "peers": len(members),
            "revenue": pool,
            "shareOfMarket": (pool / total) if total else None,
            "leader": leader["ticker"] if named else None,
            "leaderMargin": margin if named else None,
            "members": [{"ticker": r["ticker"], "name": r.get("name"),
                         "revenue": r["revenue"]} for r in members],
        }

        for rank, row in enumerate(members, start=1):
            positions[row["ticker"]] = {
                "industry": industry,
                "rank": rank,
                "peers": len(members),
                "revenue": row["revenue"],
                "share": (row["revenue"] / pool) if pool else None,
                "fieldShareOfMarket": (pool / total) if total else None,
                # The leader's lead, on the leader's row only; everyone else
                # gets how far behind the leader they are. Two different
                # questions, and one number cannot answer both.
                "margin": margin if rank == 1 else None,
                "behindLeader": (row["revenue"] / leader["revenue"]
                                 if rank > 1 and leader["revenue"] > 0 else None),
                "leads": bool(named and rank == 1),
                "leader": leader["ticker"],
                "leaderName": leader.get("name"),
                "basis": BASIS,
                "reading": _position_reading(
                    industry, rank, len(members), row, leader, margin, named, pool),
            }

    return {
        "fields": fields,
        "positions": positions,
        "measured": len(usable),
        "unplaced": len(unplaced),
        "unplacedDetail": unplaced,
        "leaders": sorted((i for i, f in fields.items() if f["leader"]),
                          key=lambda i: -(fields[i]["revenue"] or 0)),
        "thresholds": {"minPeers": MIN_PEERS, "leadMargin": LEAD_MARGIN},
        "basis": BASIS,
    }


# The caveat travels WITH the number rather than beside it in a docstring,
# because a client that renders `rank: 1` without this is publishing a claim
# about market share that nothing here measured. See the module docstring.
BASIS = ("Ranked among the scanned listings carrying the same industry label. "
         "Private companies, companies listed elsewhere and divisions of larger "
         "groups are not in it, and names whose filings did not arrive are "
         "missing from it, so this is a standing among measured peers and not a "
         "market share.")


def _position_reading(industry: str, rank: int, peers: int, row: dict, leader: dict,
                      margin: Optional[float], named: bool, pool: float) -> str:
    share = (row["revenue"] / pool * 100) if pool else None
    if peers == 1:
        return (f"The only scanned name carrying the {industry} label, so there is "
                f"nothing here to be largest of. Whoever it competes with is private, "
                f"listed elsewhere, or did not come back from this scan.")
    if peers < MIN_PEERS:
        return (f"Only {peers} scanned names carry the {industry} label, which is too "
                f"few for a rank in it to mean anything — being the largest of {peers} "
                f"is not a position.")
    if rank == 1 and named:
        return (f"The largest of the {peers} scanned names in {industry}, on "
                f"{margin:.1f}x the revenue of the next one and "
                f"{share:.0f}% of what the group sells between them. "
                f"Private and overseas competitors are not counted.")
    if rank == 1:
        return (f"Nominally the largest of the {peers} scanned names in {industry}, "
                f"but only {margin:.2f}x the next one — inside the range one "
                f"disposal or one reporting change can reverse, so no leader is "
                f"named for this field.")
    return (f"{_ordinal(rank)} of the {peers} scanned names in {industry}, on "
            f"{share:.0f}% of the group's revenue. {leader['ticker']} is the "
            f"largest.")


_ORDINAL_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{_ORDINAL_SUFFIX.get(n % 10, 'th')}"
