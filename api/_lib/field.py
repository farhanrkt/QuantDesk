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

"NO LISTED RIVAL" AND "NOTHING ELSE WE COULD MEASURE" ARE DIFFERENT CLAIMS
---------------------------------------------------------------------------
A field holding one ranked name looks like a monopoly and is very often a thin
measurement: 201 of the 722 cached Indonesian records carry no income statement,
so a company's listed rivals can all be present on the exchange and absent from
the ranking. Of the 28 Indonesian fields with exactly one ranked name, only 13
have no same-label listing that failed to return revenue.

KETR.JK is the case that forced the distinction. It is the only Indonesian
listing under "Communication Equipment" whose revenue could be read, and TWO
others carry the label and filed nothing usable. Tightening the flag alone would
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

A named leader carries it too: its lead is over the measured group only, and the
reading says so whenever something in its field went unmeasured.

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
         "groups are not in it, and names whose filings did not arrive are "
         "missing from it, so this is a standing among measured peers and not a "
         "market share.")


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
                "reason": (f"the statements are written in {reporting} and the shares "
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
                    "reason": (f"the statements are labelled {reporting} and were "
                               f"converted at {rate:,.4g}, which puts revenue at "
                               f"{value:,.0f} against a market value of {cap:,.0f} — a "
                               f"price-to-sales ratio of {after:,.4g}, where the "
                               f"unconverted figure gives {before:,.4g}. The label "
                               f"looks wrong and the converted figure is not "
                               f"comparable with its peers")}

    return {"usable": True, "value": value, "currency": currency, "asOf": as_of,
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

        missing = unranked.get(industry) or []
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
                "leader": leader["ticker"],
                "leaderName": leader.get("name"),
                "basis": BASIS,
                "reading": _position_reading(
                    industry, rank, len(members), row, leader, margin, named, pool,
                    len(missing)),
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


def _position_reading(industry: str, rank: int, peers: int, row: dict, leader: dict,
                      margin: Optional[float], named: bool, pool: float,
                      unranked: int = 0) -> str:
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
    if peers < MIN_PEERS:
        return (f"Only {peers} scanned names carry the {industry} label, which is too "
                f"few for a rank in it to mean anything — being the largest of {peers} "
                f"is not a position.")
    if rank == 1 and named:
        text = (f"The largest of the {peers} scanned names in {industry}, on "
                f"{margin:.1f}x the revenue of the next one and "
                f"{share:.0f}% of what the group sells between them. "
                f"Private and overseas competitors are not counted.")
        if unranked:
            text += (f" {unranked} further listing"
                     f"{'' if unranked == 1 else 's'} carr"
                     f"{'ies' if unranked == 1 else 'y'} this label and returned no "
                     f"usable revenue, so the lead is over the measured group only.")
        return text
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
