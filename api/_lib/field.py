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
  * Only companies whose top line could be READ. For most of this module's
    life that excluded a quarter of the Indonesian exchange — 215 of 770 cached
    records carry no statements at all — and this paragraph called it a
    throttled fetch. It is not one; see "A QUARTER OF THE EXCHANGE FILES
    NOTHING THE PROVIDER CARRIES" below, and the summary figure that now stands
    in. Whatever is still missing is reported as `unplaced`, and a reader who
    sees a large one should distrust every thin field in it: a field's true
    leader can simply be absent, and the runner-up inherits the crown.
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

"NO LISTED RIVAL" AND "NOTHING ELSE WE COULD MEASURE" ARE DIFFERENT CLAIMS
---------------------------------------------------------------------------
A field holding one ranked name looks like a monopoly and is very often a thin
measurement, because a company's listed rivals can all be on the exchange and
absent from the ranking. On the 21 September Indonesian sweep as first ranked,
only 14 of the 29 fields with exactly one ranked name had no same-label listing
that failed to return revenue.

KETR.JK is the case that forced the distinction. It was the only Indonesian
listing under "Communication Equipment" whose revenue could be read, and TWO
others carried the label and filed nothing usable. Tightening the flag alone would
have dropped the one company this module was built to find; rendering the weak
state as the strong one would have told a reader it has no competition. So:

  `onlyRanked`   nothing else in the label could be measured. A fact about the
                 SCAN, and what a screen may select on — two tiny peers filing
                 nothing does not stop a company being the specialist.
  `soleListing`  nothing else carries the label at all. The claim, and the only
                 one to render as "no listed rival".
  `unranked`     how many same-label listings returned nothing, carried PER
                 FIELD as well as in the global `unplaced` total, because the
                 global figure cannot say whether THIS field is the thin one.
  `noCloseRival` no measured rival within LEAD_MARGIN of it: alone among the
                 measured, or that far ahead of the runner-up. What the
                 specialist screen selects on. It contains `onlyRanked` and
                 `leads` and adds one case, the larger of two by the margin,
                 which the screen could otherwise never select however far
                 ahead — so measuring a rival under half a company's size was
                 enough to remove it. See `standings`.

A named leader carries it too: its lead is over the measured group only, and the
reading says so whenever something in its field went unmeasured.

A QUARTER OF THE EXCHANGE FILES NOTHING THE PROVIDER CARRIES
--------------------------------------------------------------
215 of the 770 cached Indonesian records carry no income statement, balance
sheet or cash flow statement at all, and every one of them has a sector, so the
summary scrape did arrive. This module called that a throttled fetch for most of
its life. MEASURED ON 1 NOVEMBER, IT IS NOT ONE: re-asked unhurried, six weeks
after the sweep that cached them, 47 of 47 came back empty again, annual and
quarterly alike, while BBCA.JK, TLKM.JK, ASII.JK and UNVR.JK, asked in between,
returned complete statements. The provider carries none for these listings. They
are small — a median market value of about 300 billion rupiah — and no refetch
changes it.

The provider's SUMMARY does carry a trailing year's revenue for all 215, running
to June or September 2026 for 209 of them. Where both exist it agrees with the
filed year: on 104 Indonesian names that have both, 100 of them drawn at random,
trailing over filed is 1.04 at the median, within a quarter either way on 90 and within a half on 100, and
the two never disagree about the currency. The outliers are what a trailing year
does to a filed one — a stale filing (SFAN.JK's latest is 2024) and a broker's
volatile income (PADI.JK) — not units errors.

So `revenue_of` ranks a listing with no statements on the summary figure, and
never prefers it to a filed year. Re-ranking the 21 September sweep that way
places 725 names rather than 526, leaves unplaced only the 45 with no industry
label, and names 38 leaders rather than 32:

  gained  KETR.JK over CCSI.JK, a cable maker, and IOTF.JK — the two rivals it
          could not be measured against — and AKRA, PWON, ASSA, MPIX, PEVE, and
          INOV.JK in Waste Management, a recycler on 3.3x the revenue of
          MHKI.JK, which leaves the specialist shortlist it held only because
          INOV could not be read;
  lost    DIVA.JK in Software - Application, on the rule below.

Every field of one is now a sole listing: 20 of 20, where it was 14 of 29.

What the summary does NOT give these 215 is a history. One trailing year shows
no run of profits, no compounding and no borrowings, so `trackrecord` still has
nothing to read, and none of them can be a specialist itself. They can only now
be measured against one.

TWO KINDS OF FIGURE IN ONE FIELD, AND A LEAD THAT DEPENDS ON WHICH
-------------------------------------------------------------------
A filed year (here, usually to December 2025) and a trailing twelve months (to
June or September 2026) are both a year of sales, ending on different dates.
67 fields on that sweep mix the two, and every reading comparing them says so.
The one place it changes an answer is the lead: DIVA.JK led TOSK.JK by 2.05x on
DIVA's filed year against TOSK's trailing year, and by 1.85x on both companies'
trailing years. So where the top two are ranked on different kinds, the lead is
re-made on both trailing years, and a leader is named only if it clears
LEAD_MARGIN both ways — and not at all if one of them has no trailing figure to
re-make it with. KETR.JK passes, narrowly: 2.4x as ranked, 2.0x re-made.

A CLOSED-END FUND IS NOT A COMPANY, AND NOTHING HERE CAN TELL
--------------------------------------------------------------
On the US market the label "Asset Management" holds Brookfield, BlackRock, a row
of business development companies, and about three dozen closed-end trusts. A
trust's "Total Revenue" is investment income. Ranking it against an operating
manager's fee income is comparing two different quantities, and the peer count
for that field is inflated by entities that do not compete in it at all.

THREE SIGNALS WERE TESTED AND NONE SEPARATES THEM, measured on the 99 cached US
names carrying the label:

  `quoteType`   EQUITY for BlackRock Innovation and Growth Term Trust exactly as
                for Apple. It reads ETF only for actual exchange-traded funds.
  headcount     absent for the trusts, and absent for Ares Management and Main
                Street Capital too — 53 of the 62 names whose titles contain no
                fund word report no employees either.
  the name      "Trust" catches 36 trusts and also Northern Trust, a bank with
                23,600 staff.

A structural test comes closest and still does not close: `Gross Profit` and
`Cost Of Revenue` appear on 0 of 38 fund-named income statements, so their
PRESENCE rules a fund out — but they are also absent from 36 of the 62 others,
so their absence rules nothing in.

A FIFTH SIGNAL WAS NOT TESTED AT THE TIME, AND IT IS THE ONE THAT WORKS. The
names in question had all come back empty from a throttled fetch, so there was
no description to read. Once 216 of them were refetched the answer was in the
provider's own prose: BTX describes itself as "a mutual fund launched by
BlackRock". `describes_itself_as_a_fund` reads that, `standings` leaves those
entities UNPLACED with the reason, and the four failed signals above are left on
the record because the order in which they failed is the useful part — the
cheap structural tests were tried first and the text last, and the text won.

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

import collections
import math
import re
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


# The caveat travels WITH the number rather than beside it in a docstring,
# because a client that renders `rank: 1` without this is publishing a claim
# about market share that nothing here measured. See the module docstring.
BASIS = ("Ranked among the scanned listings carrying the same industry label. "
         "Private companies, companies listed elsewhere and divisions of larger "
         "groups are not in it, and names whose revenue could not be read are "
         "missing from it, so this is a standing among measured peers and not a "
         "market share. Each figure is the latest filed year, or the provider's "
         "trailing twelve months where it carries no statements.")


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

    The latest FILED year where an income statement arrived, and the provider's
    trailing twelve months only where no statement exists at all — `source`
    says which, and `trailing` carries the summary figure for every name that
    has one, so `standings` can re-make a lead between the two kinds on one. See
    the module docstring on the 215 Indonesian listings this is for.

    Returns a reading with `usable` false and a reason rather than a number it
    cannot stand behind, because the consumer is a ranking: a figure in the
    wrong units does not look wrong there, it looks like a market leader. See
    the docstring on RIGS.JK.
    """
    record = company if isinstance(company, dict) else {}
    income = record.get("income")
    filed = isinstance(income, pd.DataFrame) and not income.empty
    value = None
    as_of = None
    source = "statement"
    if filed:
        series = _get_row(income, "revenue")
        if series is not None:
            clean = pd.Series(series).dropna()
            if len(clean):
                value = _finite(clean.iloc[0])
                label = clean.index[0]
                as_of = str(getattr(label, "date", lambda: label)())
    else:
        # NO STATEMENTS AT ALL, WHICH ON THIS EXCHANGE IS NOT A THROTTLE. See the
        # module docstring: the provider carries none for these listings, and
        # its summary carries a trailing year's revenue for them. A STAND-IN,
        # NEVER A PREFERENCE — a record with an income statement is ranked on
        # its filed year even when the summary is fresher, so the names already
        # measured stay measured the way they were.
        value = _finite(record.get("revenue_ttm"))
        as_of = record.get("revenue_ttm_through")
        source = "summary"

    currency = (record.get("currency") or "").upper() or None
    reporting = (record.get("financial_currency") or "").upper() or None
    converted = _finite(record.get("fx_rate")) is not None
    figures = "statements" if source == "statement" else "summary figures"
    # The summary's trailing year for EVERY name that has one, filed or not, so a
    # comparison between the two kinds can be re-made on one kind. See
    # `standings` on DIVA.JK. Converted with the statements by `market_data`.
    trailing = _finite(record.get("revenue_ttm"))
    trailing = trailing if trailing is not None and trailing > 0 else None

    if value is None or value <= 0:
        return {"usable": False, "value": None, "currency": currency, "asOf": as_of,
                "source": None,
                "reason": ("no revenue line came back on the income statement" if filed
                           else "no statements came back, and the provider's summary "
                                "carries no revenue figure either")}

    # A CONVERSION DELIBERATELY DECLINED IS NOT A CONVERSION MISSING.
    # `market_data._apply_fx` refuses to scale statements whose currency label
    # it can show to be wrong — the figures are already in the trading currency,
    # which is exactly the scale this ranking needs. Treating that as "no rate
    # was applied" would drop the one case the guard exists to rescue.
    skipped = record.get("fx_skipped")

    # STATEMENTS IN ANOTHER CURRENCY THAT WERE NOT CONVERTED CANNOT BE COMPARED.
    # `market_data` converts at the boundary when it has a rate; when it does
    # not, the figure is real but on a different scale from its neighbours, and
    # a ranking is exactly where that does damage.
    if (reporting and currency and reporting != currency
            and not converted and not skipped):
        return {"usable": False, "value": None, "currency": currency, "asOf": as_of,
                "source": source,
                "reason": (f"the {figures} are written in {reporting} and the shares "
                           f"trade in {currency}, and no exchange rate was applied, so "
                           f"this figure is not on the same scale as its peers")}

    # THE UNITS SANITY TEST, AND IT ONLY RUNS ON A CONVERTED FIGURE.
    #
    # THE SECOND LINE OF DEFENCE, NOT THE FIRST. `market_data._apply_fx` now
    # runs the same comparison at the boundary and declines the conversion
    # outright, so in practice a record reaching here has already been cleared —
    # this fires only for a caller that built a record some other way. It is
    # kept because the cost is a comparison and the failure it guards is a
    # confident market leader; see the module docstring on RIGS.JK.
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
                    "source": source,
                    "reason": (f"the {figures} are labelled {reporting} and were "
                               f"converted at {rate:,.4g}, which puts revenue at "
                               f"{value:,.0f} against a market value of {cap:,.0f} — a "
                               f"price-to-sales ratio of {after:,.4g}, where the "
                               f"unconverted figure gives {before:,.4g}. The label "
                               f"looks wrong and the converted figure is not "
                               f"comparable with its peers")}

    return {"usable": True, "value": value, "currency": currency, "asOf": as_of,
            # "statement" for a filed year, "summary" for the provider's trailing
            # twelve months where it carries no statements. `standings` says so
            # in the reading wherever the two sit in one field.
            "source": source,
            "trailing": trailing,
            "converted": converted,
            "reportingCurrency": reporting if converted else None,
            # Carried so a reader can see that the app overrode the source's own
            # currency label on this name, rather than discovering it as an
            # unexplained difference from the filing.
            "labelOverridden": bool(skipped),
            "reason": None}


# Words that carry no information about WHAT a company does, either because
# every description uses them or because they are corporate furniture. This list
# is a judgement and is the weakest part of the function below: it was built by
# reading the output on a 726-name sweep and removing what was obviously noise,
# not by any test. The effect of getting it wrong is a bland term in a list of
# four, which is why it is allowed to be a judgement at all.
#
# THE PRONOUNS AND QUANTITY WORDS WERE ADDED FOR THE US CORPUS. The Indonesian
# descriptions are written in a flatter register and barely use them, so the
# first list had none — and on 1,767 US descriptions Highwoods Properties came
# back as "their, raleigh, they, experiences" and Pembina Pipeline as "barrels,
# capacity, basins, million". A word below four characters is already excluded
# by the tokeniser, which is why "we", "our" and "its" never needed listing.
_FURNITURE = frozenset("""
the a an and or of in to for with its it also as well is are was were by on at from
that this company companies operates operate through provides provide offers offer
products product services service indonesia indonesian tbk persero perseroan inc ltd
limited corporation corp plc founded headquartered based name names changed formerly
known subsidiary subsidiaries segments segment various other others addition engages
engaged business businesses group holding holdings sells sell sale sales trading trade
distributes distribution manufactures manufacturing production including include
includes under brand brands well customers market markets domestic international
activities activity operations operational related support supports solutions solution
consists systems system application applications process processes hour income prime
they them their theirs which these those such than then into over about
approximately primarily mainly certain approximately million billion thousand
percent primarily principally largely mostly
""".split())

_WORD = re.compile(r"[a-z][a-z-]{3,}")

# A term in more than this share of descriptions describes the market, not the
# company. 6% of a 726-name sweep is about 44 names.
COMMON_AT = 0.06

# And a term in only one description cannot be checked against anything — it is
# usually a proper noun the name filter missed.
MIN_DOCUMENTS = 2

# Below this many descriptions, "distinctive" has nothing to be distinctive
# AGAINST and the function returns nothing rather than a list of whatever a
# handful of companies happen to say.
#
# The ceiling is a SHARE of the corpus, and a share of a small number is a
# smaller number than the floor: at 45 descriptions, 6% is 2.7, so the only
# surviving terms were those in exactly two documents and a 45-name scan
# reported almost nothing while looking as though it had worked. Refusing
# outright is the honest version of that.
MIN_CORPUS = 50

# How many to report. Four is enough to recognise a business and few enough that
# a weak fourth does not crowd out a strong first.
TERMS_PER_NAME = 4


def distinctive_terms(entries: list[dict]) -> dict[str, list[str]]:
    """The words common in each description and rare in this market's.

    WHY, GIVEN THE INDUSTRY LABEL ALREADY EXISTS: because the label is far too
    coarse to say what a company does. KETR.JK is "Communication Equipment",
    which it shares with radio makers and handset distributors; the words that
    actually identify it are *cable*, *optic*, *fiber*. On a 726-name Indonesian
    sweep this returns *waste, treatment, utilization* for an industrial waste
    handler filed under Waste Management, *cargo, handling, aviation, catering*
    for a ground-handling company filed under Airports & Air Services, and
    *plantation, palm* — only two, correctly — for a palm grower.

    THIS IS WORD FREQUENCY AND NOTHING MORE. It is not a classification, nothing
    verified it, and a term can mislead: MAHA.JK returns *hauling, mover*
    because "prime mover trucks" tokenises into separate words. It is offered as
    a way INTO the descriptions — every term is searchable, and the search reads
    the full text — rather than as a statement about the company.

    A COMPANY'S OWN NAME IS EXCLUDED, which is most of the cleanup. Without it
    the list for Blue Bird is *blue, bird*, for Garuda Maintenance Facility
    *garuda, aero*, and for Telkom Indonesia *telekomunikasi* — the company
    repeating its own name back, which tells a reader nothing they did not get
    from the ticker.

    A CORPUS UNDER `MIN_CORPUS` RETURNS NOTHING. Distinctive is a comparison,
    and a handful of descriptions gives it nothing to compare against.
    """
    corpus: dict[str, list[str]] = {}
    for entry in entries or []:
        ticker = entry.get("ticker")
        summary = (entry.get("summary") or "").lower()
        if not ticker or not summary:
            continue
        own = set(_WORD.findall((entry.get("name") or "").lower()))
        corpus[ticker] = [word for word in _WORD.findall(summary)
                          if word not in _FURNITURE and word not in own]

    if len(corpus) < MIN_CORPUS:
        return {}

    documents = collections.Counter()
    for words in corpus.values():
        documents.update(set(words))
    total = len(corpus)
    # Never below the floor: the two bounds crossing is what silently emptied
    # small scans. See MIN_CORPUS.
    ceiling = max(MIN_DOCUMENTS, total * COMMON_AT)

    out: dict[str, list[str]] = {}
    for ticker, words in corpus.items():
        counts = collections.Counter(words)
        scored = [
            (count * math.log(total / documents[word]), word)
            for word, count in counts.items()
            if MIN_DOCUMENTS <= documents[word] <= ceiling
        ]
        # Ties broken alphabetically so two runs over the same corpus agree.
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        out[ticker] = [word for _, word in scored[:TERMS_PER_NAME]]
    return out


# A fund saying so in its own description. Deliberately narrow: the phrase has
# to be a statement about what this entity IS, not a mention of funds it deals
# with, which is why "is a mutual fund" matches and "manages mutual funds" does
# not. See `describes_itself_as_a_fund` for what it was measured against.
_FUND_PROSE = re.compile(
    r"\b(is an? [a-z\- ]*?(mutual fund|closed[\- ]end(ed)? fund|"
    r"exchange[\- ]traded fund)|launched and managed by|is a fund (launched|managed))",
    re.I)


def describes_itself_as_a_fund(summary: Optional[str]) -> bool:
    """Whether this entity's own description says it is a fund.

    THIS REVERSES AN EARLIER CONCLUSION, AND THE MEASUREMENT IS WHY. The module
    docstring recorded that nothing available separates a closed-end trust from
    an operating asset manager: `quoteType` reads EQUITY for a BlackRock term
    trust exactly as for Apple, headcount is absent for Ares Management and
    Main Street Capital as well as for the trusts, and a name test for "Trust"
    catches Northern Trust, a bank with 23,600 staff.

    All four of those were tested. The DESCRIPTION was not, because the names in
    question had come back empty from a throttled fetch and there was nothing to
    read. Once 216 of them were refetched, the answer was sitting in the prose:
    BTX describes itself as "a mutual fund launched by BlackRock".

    MEASURED ON 3,359 DESCRIBED US NAMES. Of the 138 labelled Asset Management,
    57 say they are a fund — Guggenheim, Brookfield, BlackRock, Eaton Vance,
    Gabelli, Nuveen, PIMCO — and the 81 that do not are operating firms: Ares
    Management, AllianceBernstein, Principal Financial, and the business
    development companies Main Street, Fidus, Horizon and Goldman Sachs BDC,
    which lend and are properly ranked on what they earn. It fires on ZERO of
    the other 3,221 names.

    IT IS STILL THE PROVIDER'S CLAIM, NOT A CLASSIFICATION THIS APP MAKES,
    which is the same epistemic footing as the industry label beside it.

    A SECOND PATTERN WAS TESTED AND REJECTED. Some closed-end funds never make
    the claim — CBRE Clarion Global Real Estate Income Fund opens "specializes
    in investments in various property types" and only refers to itself as "the
    fund" later — so matching that self-reference was tried. It catches 23 names
    and none outside Asset Management, which looks clean until you read them:
    Ares Capital, Goldman Sachs BDC, Fidus, FS KKR, Oaktree Specialty Lending,
    Carlyle Secured Lending. They are business development companies, they lend,
    and their interest income is an operating result properly compared with
    other lenders'. The pattern separates "entities that invest" from "operating
    companies", which is a real distinction and the wrong one here.

    SO IGR AND ITS KIND STAY RANKED, and that is the bounded cost of reading a
    claim rather than guessing a category. Of 147 US names labelled Asset
    Management, 61 are now unplaced; 14 with a fund-like NAME remain ranked, and
    6 of those have no description at all to test.
    """
    return bool(summary and _FUND_PROSE.search(summary))


def standings(entries: list[dict]) -> dict:
    """Rank every usable name inside its own industry label, by revenue.

    `entries` are dicts with `ticker`, `industry` and `revenue`; a name missing
    either is counted in `unplaced` rather than dropped silently, because the
    size of that count is what tells a reader how much to trust a thin field.
    """
    usable, unplaced = [], []
    # A NAME WITH A LABEL BUT NO REVENUE IS STILL IN THE FIELD, and losing that
    # fact is what would make "the only listed name in its field" a lie. It
    # cannot be RANKED — there is nothing to rank it by — but it is a listed
    # rival, and a claim of no rivals has to account for it. Kept per label
    # rather than only in the global `unplaced` total, because the global figure
    # cannot tell a reader whether THIS field is the thin one.
    unranked: dict[str, list[str]] = {}
    for entry in entries or []:
        industry = (entry.get("industry") or "").strip()
        revenue = _finite(entry.get("revenue"))
        # A FUND IS NOT A COMPANY COMPETING IN A FIELD. Its "revenue" is
        # investment income, which is not the quantity every other member of
        # its label is ranked on, and it inflates the peer count with entities
        # that do not compete. Left UNPLACED with a reason rather than dropped,
        # so the count of what could not be ranked still accounts for it.
        if describes_itself_as_a_fund(entry.get("summary")):
            unplaced.append({"ticker": entry.get("ticker"),
                             "why": "describes itself as a fund"})
            if industry:
                unranked.setdefault(industry, []).append(entry.get("ticker"))
            continue
        if not industry or revenue is None or revenue <= 0:
            unplaced.append({"ticker": entry.get("ticker"),
                             "why": "no industry" if not industry else "no usable revenue"})
            if industry:
                unranked.setdefault(industry, []).append(entry.get("ticker"))
            continue
        usable.append({"ticker": entry.get("ticker"), "name": entry.get("name"),
                       "industry": industry, "revenue": revenue,
                       # Absent on callers that predate the summary stand-in,
                       # which only ever passed filed years.
                       "source": entry.get("revenueSource") or "statement",
                       "trailing": _finite(entry.get("revenueTrailing"))})

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
        # A LEAD THAT DEPENDS ON WHICH KIND OF FIGURE WAS USED IS NOT A LEAD.
        # Where the leader is ranked on a filed year and the runner-up on the
        # summary's trailing twelve months, or the other way round, the margin
        # is re-made on both companies' trailing twelve months, and a leader is
        # named only if it clears LEAD_MARGIN both ways. Measured on the 21
        # September Indonesian sweep: DIVA.JK led TOSK.JK by 2.05x on its filed
        # year against TOSK's trailing year, and by 1.85x on both trailing
        # years. Where the second figure is missing nothing can be re-made, and
        # nothing is named on a comparison that could not be checked.
        mixed = bool(runner_up and leader["source"] != runner_up["source"])
        trailing_margin = None
        if mixed and leader.get("trailing") and runner_up.get("trailing"):
            trailing_margin = leader["trailing"] / runner_up["trailing"]
        clears = bool(margin is not None and margin >= LEAD_MARGIN
                      and (not mixed or (trailing_margin is not None
                                         and trailing_margin >= LEAD_MARGIN)))
        named = bool(len(members) >= MIN_PEERS and clears)

        missing = unranked.get(industry) or []
        summary = sum(1 for r in members if r["source"] == "summary")
        fields[industry] = {
            "industry": industry,
            "peers": len(members),
            # Listed under the same label, and not rankable. See `standings`.
            "unranked": len(missing),
            "unrankedTickers": missing,
            "revenue": pool,
            "shareOfMarket": (pool / total) if total else None,
            "leader": leader["ticker"] if named else None,
            "leaderMargin": margin if named else None,
            # The same lead on both companies' trailing twelve months, where the
            # top two are ranked on different kinds of figure; None otherwise.
            "leaderMarginTrailing": trailing_margin,
            # How many of the members are ranked on the provider's trailing
            # twelve months rather than a filed year. See `revenue_of`.
            "summaryFigures": summary,
            "members": [{"ticker": r["ticker"], "name": r.get("name"),
                         "revenue": r["revenue"], "source": r["source"]}
                        for r in members],
        }

        for rank, row in enumerate(members, start=1):
            positions[row["ticker"]] = {
                "industry": industry,
                "rank": rank,
                "peers": len(members),
                "revenue": row["revenue"],
                "revenueSource": row["source"],
                "share": (row["revenue"] / pool) if pool else None,
                "fieldShareOfMarket": (pool / total) if total else None,
                # The leader's lead, on the leader's row only; everyone else
                # gets how far behind the leader they are. Two different
                # questions, and one number cannot answer both.
                "margin": margin if rank == 1 else None,
                "marginTrailing": trailing_margin if rank == 1 else None,
                "behindLeader": (row["revenue"] / leader["revenue"]
                                 if rank > 1 and leader["revenue"] > 0 else None),
                "leads": bool(named and rank == 1),
                "unranked": len(missing),
                # TWO DIFFERENT STATEMENTS, AND CONFLATING THEM COSTS EITHER
                # HONESTY OR THE ANSWER.
                #
                # `onlyRanked` — nothing else in this label could be measured.
                # It is what a SCREEN can select on, because a specialist whose
                # two tiny listed peers filed nothing is still a specialist.
                #
                # `soleListing` — nothing else carries this label at all. The
                # stronger claim, and the only one a reader should be shown as
                # "no listed rival". KETR.JK, the name this was built for, is
                # the first and not the second: two other Indonesian listings
                # are filed under Communication Equipment and returned no usable
                # revenue. Selecting on the strong flag would have dropped it;
                # displaying the weak one as the strong one would have told a
                # reader it has no competition. It gets kept and qualified.
                "onlyRanked": len(members) == 1,
                "soleListing": bool(len(members) == 1 and not missing),
                # NO MEASURED RIVAL COMES WITHIN LEAD_MARGIN OF IT: alone among
                # the measured, or ahead of the runner-up by the margin a named
                # leader needs, re-made on one kind of figure where the top two
                # differ. What the specialist screen selects on, because without
                # it the screen was not monotone: a company with NO measured
                # rival qualified, and the same company became ineligible the
                # moment one rival could be read — however small. KETR.JK on 1
                # November is the case: CCSI.JK measurable at under half its
                # size, IOTF.JK at the exchange's 50-rupiah floor and out of the
                # scan, and a field of two. `leads` is unchanged and still needs
                # MIN_PEERS; this is a fact about the measurement, not a claim
                # to lead anything.
                "noCloseRival": bool(rank == 1 and (len(members) == 1 or clears)),
                "leader": leader["ticker"],
                "leaderName": leader.get("name"),
                "basis": BASIS,
                "reading": _position_reading(
                    industry, rank, len(members), row, leader, margin, named, pool,
                    len(missing), mixed, trailing_margin, clears)
                + _source_note(row, len(members), summary),
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


_KIND = {"statement": "filed year", "summary": "trailing twelve months"}


def _position_reading(industry: str, rank: int, peers: int, row: dict, leader: dict,
                      margin: Optional[float], named: bool, pool: float,
                      unranked: int = 0, mixed: bool = False,
                      trailing_margin: Optional[float] = None,
                      clears: bool = False) -> str:
    share = (row["revenue"] / pool * 100) if pool else None
    if peers == 1 and unranked:
        return (f"The only scanned name in {industry} whose revenue could be read, but "
                f"{unranked} other listing{'' if unranked == 1 else 's'} carr"
                f"{'ies' if unranked == 1 else 'y'} the same label and did not return "
                f"filings this scan could use. It is not alone in its field; it is the "
                f"only one that could be measured.")
    if peers == 1:
        return (f"The only scanned name carrying the {industry} label, so there is "
                f"nothing here to be largest of. Whoever it competes with is private, "
                f"listed elsewhere, or is not listed on this exchange.")
    if peers < MIN_PEERS and rank == 1 and clears:
        both = (f", {trailing_margin:.1f}x on both companies' trailing twelve months"
                if mixed and trailing_margin is not None else "")
        return (f"Only {peers} scanned names carry the {industry} label, too few to "
                f"name a leader, but the other is under half its size: it sells "
                f"{margin:.1f}x as much{both}. Private and overseas competitors are not "
                f"counted.")
    if peers < MIN_PEERS:
        return (f"Only {peers} scanned names carry the {industry} label, which is too "
                f"few for a rank in it to mean anything — being the largest of {peers} "
                f"is not a position.")
    if rank == 1 and named:
        both = (f" — {trailing_margin:.1f}x on both companies' trailing twelve months —"
                if mixed and trailing_margin is not None else "")
        text = (f"The largest of the {peers} scanned names in {industry}, on "
                f"{margin:.1f}x the revenue of the next one{both} and "
                f"{share:.0f}% of what the group sells between them. "
                f"Private and overseas competitors are not counted.")
        if unranked:
            text += (f" {unranked} further listing"
                     f"{'' if unranked == 1 else 's'} carr"
                     f"{'ies' if unranked == 1 else 'y'} this label and returned no "
                     f"usable revenue, so the lead is over the measured group only.")
        return text
    if rank == 1 and mixed and margin is not None and margin >= LEAD_MARGIN:
        mine = _KIND.get(leader.get("source"), "filed year")
        theirs = _KIND["summary" if leader.get("source") == "statement" else "statement"]
        remade = (f"on both companies' trailing twelve months it is "
                  f"{trailing_margin:.2f}x" if trailing_margin is not None else
                  "the comparison could not be re-made on one kind of figure for both")
        return (f"Nominally the largest of the {peers} scanned names in {industry}, on "
                f"{margin:.2f}x the next one, but that compares its {mine} with the "
                f"next one's {theirs}, and {remade} — so no leader is named for this "
                f"field.")
    if rank == 1:
        return (f"Nominally the largest of the {peers} scanned names in {industry}, "
                f"but only {margin:.2f}x the next one — inside the range one "
                f"disposal or one reporting change can reverse, so no leader is "
                f"named for this field.")
    return (f"{_ordinal(rank)} of the {peers} scanned names in {industry}, on "
            f"{share:.0f}% of the group's revenue. {leader['ticker']} is the "
            f"largest.")


def _source_note(row: dict, peers: int, summary: int) -> str:
    """Which figures in this field are the provider's trailing year, if any.

    A filed year and a trailing twelve months are both a year of sales, and they
    end on different dates — on this exchange the filed year is usually the one
    to December and the summary's the one to June or September. A lead of
    LEAD_MARGIN survives that; a rank between two near neighbours may not, so a
    reading comparing the two kinds says it is doing so. Nothing is said where
    there is no comparison: a field of one compares nothing.
    """
    if peers < 2 or not summary:
        return ""
    own = row.get("source") == "summary"
    if summary == peers:
        return (" Every figure here is the provider's trailing-twelve-month summary, "
                "because it carries no statements for any of these listings.")
    if own:
        others = summary - 1
        like = (f", like {others} other{'' if others == 1 else 's'} here," if others
                else "")
        return (f" Its figure{like} is the provider's trailing-twelve-month summary, "
                f"used because it carries no statements for this listing, so not "
                f"every figure in the comparison covers the same twelve months.")
    which = (f"The other {summary} figures here are" if summary == peers - 1 > 1 else
             "The other figure here is" if summary == peers - 1 else
             f"{summary} of the other figures here {'is' if summary == 1 else 'are'}")
    return (f" {which} the provider's trailing-twelve-month summary, used where it "
            f"carries no statements, so not every figure in the comparison covers the "
            f"same twelve months.")


_ORDINAL_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{_ORDINAL_SUFFIX.get(n % 10, 'th')}"
