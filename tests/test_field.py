"""What the business does, and where it stands among the names doing the same.

WHY THESE TESTS EXIST

The first run of this ranking crowned RIGS.JK — a small tug and barge operator —
with 99.4% of Indonesian marine shipping and 456 times the runner-up's revenue.
Yahoo labels its statements USD while serving them in rupiah, so converting at
the boundary multiplied a correct figure by about 16,300. The output was not a
crash or an obviously silly number. It was a confident market leader.

That is the shape of every failure worth guarding here: bad units and missing
peers do not break a ranking, they produce a plausible wrong one.

WHAT THESE TESTS PROTECT

1. A MISLABELLED CURRENCY LEAVES A NAME UNPLACED, never merely low. Placing it
   at zero would hand its field's lead to whoever is next, which is the same
   error one rank down.
2. THE UNITS TEST ONLY RUNS ON A CONVERTED FIGURE. An earlier version ran it on
   everything and refused 71 names, nearly all of them companies that are simply
   expensive — a tiny price-to-sales ratio is what the market loving something
   looks like.
3. A THIN FIELD NAMES NO LEADER. Being the largest of two is not a position.
4. A NARROW LEAD NAMES NO LEADER. Under LEAD_MARGIN one disposal reverses it.
5. "NOT FETCHED" AND "NONE PUBLISHED" STAY DIFFERENT. The first is a gap a
   refetch fills; the second is a fact about the data. Collapsing them sends a
   reader to re-run a scan that cannot change the answer.
6. THE CAVEAT TRAVELS IN THE PAYLOAD. A rank rendered without `basis` reads as
   market share, which nothing here measures.
7. "NO LISTED RIVAL" ACCOUNTS FOR THE RIVALS THAT DID NOT RETURN. A field of one
   whose other members merely failed to file is a thin measurement, not a
   monopoly, and it is the strongest claim this module makes.
"""

from __future__ import annotations

import pandas as pd
import pytest

from _lib import field as F


def income(revenue: float, label: str = "2025-12-31") -> pd.DataFrame:
    return pd.DataFrame({pd.Timestamp(label): {"Total Revenue": revenue}})


def record(revenue=1_000.0, *, currency="IDR", financial=None, fx=None,
           cap=2_000.0, **extra):
    out = {"income": income(revenue), "currency": currency,
           "financial_currency": financial, "fx_rate": fx, "market_cap": cap}
    out.update(extra)
    return out


# --------------------------------------------------------------------------- #
# profile: description, and the two ways a description can be missing
# --------------------------------------------------------------------------- #
def test_summary_is_repeated_not_judged():
    out = F.profile({"sector": "Energy", "industry": "Thermal Coal",
                     "business_summary": "Mines and sells thermal coal.",
                     "employees": 4200.0, "country": "Indonesia"})
    assert out["industry"] == "Thermal Coal"
    assert out["summary"] == "Mines and sells thermal coal."
    assert out["employees"] == 4200
    assert "Thermal Coal" in out["reading"]


def test_absent_key_is_a_gap_and_empty_key_is_a_fact():
    # No key at all: the record predates the app asking for a description.
    stale = F.profile({"industry": "Steel"})
    assert stale["summaryState"] == "not fetched"
    assert "refetch" in stale["reading"]

    # Key present and empty: the provider has none, and refetching cannot help.
    empty = F.profile({"industry": "Steel", "business_summary": ""})
    assert empty["summaryState"] == "none published"
    assert "refetch" not in empty["reading"]


def test_profile_of_nothing_says_so_rather_than_inventing_fields():
    out = F.profile(None)
    assert out["industry"] is None and out["summary"] is None
    assert out["summaryState"] == "not fetched"


def test_summary_is_trimmed_at_a_sentence_where_one_is_near():
    body = ("A. " * 3) + "B" * 400
    trimmed = F._trim(body, limit=60)
    assert len(trimmed) <= 60
    # A full stop deep enough into the budget beats the budget.
    long_first = "First sentence runs on for a good while and then stops. " + "x" * 300
    assert F._trim(long_first, limit=80).endswith(".")


# --------------------------------------------------------------------------- #
# revenue: the units guard
# --------------------------------------------------------------------------- #
def test_revenue_reads_the_top_line_in_the_trading_currency():
    out = F.revenue_of(record(5_000.0, cap=10_000.0))
    assert out["usable"] is True
    assert out["value"] == 5_000.0
    assert out["currency"] == "IDR"


def test_unconverted_foreign_statements_are_refused_not_compared():
    # Statements in USD, shares in IDR, no rate applied: the figure is real but
    # on a different scale from every name it would be ranked against.
    out = F.revenue_of(record(5_000.0, currency="IDR", financial="USD", fx=None))
    assert out["usable"] is False
    assert "no exchange rate was applied" in out["reason"]


def test_a_mislabelled_currency_is_refused_rather_than_crowned():
    # The RIGS.JK case, to scale: statements already in rupiah, labelled USD,
    # so the boundary multiplied them by 16,300.
    out = F.revenue_of(record(366_000.0 * 16_300, currency="IDR", financial="USD",
                              fx=16_300.0, cap=423_000.0))
    assert out["usable"] is False
    assert "label looks wrong" in out["reason"]
    assert out["value"] is None            # not placed low — not placed at all


def test_a_correct_conversion_survives_the_units_test():
    # An ADR reporting in won and trading in dollars: huge raw figure, sane once
    # converted, which is the opposite verdict on the same shape of input.
    out = F.revenue_of(record(25_000.0, currency="USD", financial="KRW",
                              fx=0.00072, cap=4_400.0))
    assert out["usable"] is True


def test_an_expensive_company_is_not_mistaken_for_a_units_error():
    # MSTR's shape: $477m of revenue against $52bn of market value. A real
    # price-to-sales ratio of 0.009, and no conversion involved.
    out = F.revenue_of(record(477_233_000.0, currency="USD", financial="USD",
                              cap=52_031_979_520.0))
    assert out["usable"] is True


def test_no_revenue_line_is_stated_not_guessed():
    out = F.revenue_of({"income": pd.DataFrame(), "currency": "USD"})
    assert out["usable"] is False
    assert "no revenue line" in out["reason"]


# --------------------------------------------------------------------------- #
# standings
# --------------------------------------------------------------------------- #
def entries(*pairs, industry="Thermal Coal"):
    return [{"ticker": t, "name": t, "industry": industry, "revenue": r}
            for t, r in pairs]


def test_a_clear_leader_is_named():
    out = F.standings(entries(("A", 100.0), ("B", 20.0), ("C", 10.0)))
    assert out["fields"]["Thermal Coal"]["leader"] == "A"
    assert out["positions"]["A"]["leads"] is True
    assert out["positions"]["A"]["rank"] == 1
    assert out["positions"]["B"]["leads"] is False
    assert out["positions"]["B"]["rank"] == 2


def test_a_field_too_thin_to_rank_names_nobody():
    out = F.standings(entries(("A", 100.0), ("B", 1.0)))
    assert out["fields"]["Thermal Coal"]["leader"] is None
    assert out["positions"]["A"]["leads"] is False
    assert "not a position" in out["positions"]["A"]["reading"]


def test_a_narrow_lead_names_nobody():
    out = F.standings(entries(("A", 100.0), ("B", 90.0), ("C", 10.0)))
    assert out["fields"]["Thermal Coal"]["leader"] is None
    assert out["positions"]["A"]["leads"] is False
    assert "no leader is named" in out["positions"]["A"]["reading"]


def test_unplaced_names_are_counted_rather_than_dropped():
    rows = [
        *entries(("A", 100.0), ("B", 20.0), ("C", 10.0)),
        {"ticker": "D", "industry": "", "revenue": 500.0},
        {"ticker": "E", "industry": "Thermal Coal", "revenue": None},
    ]
    out = F.standings(rows)
    assert out["measured"] == 3
    assert out["unplaced"] == 2
    assert {d["ticker"] for d in out["unplacedDetail"]} == {"D", "E"}
    # The missing names are not in anyone's peer count.
    assert out["positions"]["A"]["peers"] == 3


def test_a_missing_peer_can_hand_over_the_lead_and_the_count_says_so():
    """The failure this instrument exists for, stated as a test.

    The same field with and without its largest member produces two different
    leaders, and nothing about the second is visibly wrong. `unplaced` is the
    only thing standing between a reader and that.
    """
    full = F.standings(entries(("BIG", 900.0), ("A", 100.0), ("B", 20.0), ("C", 5.0)))
    partial = F.standings([
        *entries(("A", 100.0), ("B", 20.0), ("C", 5.0)),
        {"ticker": "BIG", "industry": "Thermal Coal", "revenue": None},
    ])
    assert full["fields"]["Thermal Coal"]["leader"] == "BIG"
    assert partial["fields"]["Thermal Coal"]["leader"] == "A"
    assert partial["unplaced"] == 1


def test_the_basis_caveat_travels_with_every_position():
    out = F.standings(entries(("A", 100.0), ("B", 20.0), ("C", 10.0)))
    assert "not a market share" in out["basis"]
    assert out["positions"]["A"]["basis"] == out["basis"]
    assert "Private and overseas" in out["positions"]["A"]["reading"]


def test_runners_up_are_told_how_far_behind_rather_than_how_far_ahead():
    out = F.standings(entries(("A", 100.0), ("B", 25.0), ("C", 10.0)))
    assert out["positions"]["A"]["margin"] == pytest.approx(4.0)
    assert out["positions"]["A"]["behindLeader"] is None
    assert out["positions"]["B"]["margin"] is None
    assert out["positions"]["B"]["behindLeader"] == pytest.approx(0.25)


def test_fields_do_not_leak_into_each_other():
    rows = [*entries(("A", 100.0), ("B", 20.0), ("C", 10.0)),
            *entries(("X", 50.0), ("Y", 5.0), ("Z", 2.0), industry="Gold")]
    out = F.standings(rows)
    assert out["positions"]["A"]["peers"] == 3
    assert out["positions"]["X"]["industry"] == "Gold"
    assert set(out["leaders"]) == {"Thermal Coal", "Gold"}
    # Field share is of the whole scanned population, not of one field.
    assert out["positions"]["A"]["fieldShareOfMarket"] == pytest.approx(130 / 187)


def test_no_niche_flag_ships():
    """Measured and rejected; see the module docstring.

    Field share does not measure narrowness — the median field holds 1/97th of
    scanned revenue because there are 97 labels. A flag built on it would sort
    fields by how finely the provider subdivides them.
    """
    out = F.standings(entries(("A", 100.0), ("B", 20.0), ("C", 10.0)))
    assert "niche" not in out["positions"]["A"]
    assert "niche" not in out["fields"]["Thermal Coal"]


def test_standings_of_nothing_is_empty_rather_than_an_error():
    out = F.standings([])
    assert out["fields"] == {} and out["positions"] == {}
    assert out["measured"] == 0 and out["unplaced"] == 0


# --------------------------------------------------------------------------- #
# no listed rival, which is a stronger claim than being the only ranked name
# --------------------------------------------------------------------------- #
def test_a_field_of_one_with_no_other_listing_is_a_sole_listing():
    out = F.standings(entries(("A", 100.0)))
    place = out["positions"]["A"]
    assert place["soleListing"] is True
    assert place["unranked"] == 0
    assert "is not listed on this exchange" in place["reading"]


def test_an_unrankable_peer_cancels_the_sole_listing_claim():
    """The rival that did not return its filings is still a rival.

    Without this the claim reads as "nobody else does this", when what happened
    is "nobody else could be measured" — the difference between a niche and a
    thin scan, on the one flag the specialist shortlist selects with.
    """
    out = F.standings([
        {"ticker": "A", "name": "A", "industry": "Thermal Coal", "revenue": 100.0},
        {"ticker": "B", "name": "B", "industry": "Thermal Coal", "revenue": None},
    ])
    place = out["positions"]["A"]
    assert place["peers"] == 1              # still the only one ranked
    assert place["unranked"] == 1
    assert place["soleListing"] is False    # but not alone in its field
    assert "only one that could be measured" in place["reading"]
    assert out["fields"]["Thermal Coal"]["unranked"] == 1
    assert out["fields"]["Thermal Coal"]["unrankedTickers"] == ["B"]


def test_a_named_leader_says_how_many_of_its_field_went_unmeasured():
    out = F.standings([
        *entries(("A", 100.0), ("B", 20.0), ("C", 10.0)),
        {"ticker": "D", "industry": "Thermal Coal", "revenue": None},
    ])
    place = out["positions"]["A"]
    assert place["leads"] is True
    assert place["unranked"] == 1
    assert "lead is over the measured group only" in place["reading"]


def test_a_name_with_no_industry_at_all_counts_against_no_field():
    out = F.standings([
        *entries(("A", 100.0), ("B", 20.0), ("C", 10.0)),
        {"ticker": "X", "industry": "", "revenue": None},
    ])
    assert out["fields"]["Thermal Coal"]["unranked"] == 0
    assert out["unplaced"] == 1


def test_a_conversion_the_app_declined_is_still_comparable():
    """`market_data` now refuses to scale statements whose label it can show is
    wrong — RIGS.JK's rupiah figures labelled USD. Those figures are ALREADY in
    the trading currency, which is the scale this ranking needs, so treating the
    absent rate as "not converted" would drop the one name the guard rescued.
    """
    out = F.revenue_of({
        **record(365_897_785_357.0, currency="IDR", financial="USD", fx=None,
                 cap=423_345_324_032.0),
        "fx_skipped": {"reportingCurrency": "USD", "tradingCurrency": "IDR",
                       "rateRefused": 16_300.0, "reason": "wrong label at the source"},
    })
    assert out["usable"] is True
    assert out["value"] == 365_897_785_357.0
    assert out["labelOverridden"] is True


def test_a_genuinely_missing_rate_is_still_refused():
    out = F.revenue_of(record(5_000.0, currency="IDR", financial="USD", fx=None))
    assert out["usable"] is False
    assert "no exchange rate was applied" in out["reason"]
