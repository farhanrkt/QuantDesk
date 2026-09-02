"""Validation domain — where each accounting screen's number came from.

WHAT THESE TESTS PROTECT

1. Nothing here is ever a colour. Every reading sits in the `context` band, in
   both directions. "Outside" is the normal condition of every use of these
   models today, so painting it amber would cry wolf on all three scores for
   every company forever; "inside" as a green tick would claim the score is
   therefore reliable, which nothing in this app measures. That second one is
   the trap, and it is the same rule the pre-trade panel is built around.

2. No tally. "3 of 4 dimensions match" is a fit score, and a fit score is a
   composite in the one field everybody reads.

3. The facts are the facts. The sample periods, markets and sample descriptions
   are checked against the published papers, so a later edit that rounds
   "1976-1996" into something tidier fails here rather than on the page.

4. Unknown stays unknown. A book-to-market ratio cannot place a company in a
   cross-sectional quintile, and the module has to say so rather than guessing —
   this is the dimension most likely to grow a made-up threshold later.
"""

from __future__ import annotations

import pandas as pd
import pytest

from _lib import explain as E
from _lib import screendomain as D


def balance(equity=4.0e10, year=2025):
    """A balance sheet whose only job is to carry equity and a period label."""
    columns = [pd.Timestamp(f"{year}-12-31"), pd.Timestamp(f"{year - 1}-12-31")]
    return pd.DataFrame({columns[0]: [equity], columns[1]: [equity * 0.95]},
                        index=["Stockholders Equity"])


def company(equity=4.0e10, year=2025, cap=1.0e11, sector="Technology",
            industry="Consumer Electronics", currency="USD"):
    frame = balance(equity, year)
    return {"balance": frame, "income": frame, "cashflow": frame,
            "market_cap": cap, "sector": sector, "industry": industry,
            "currency": currency}


def dims(result, screen):
    return {d["key"]: d for d in result["screens"][screen]["dimensions"]}


def verdicts(result):
    return {f"{screen}.{d['key']}": d["verdict"]
            for screen, block in result["screens"].items()
            for d in block["dimensions"]}


# --------------------------------------------------------------------------- #
# 1. Never a colour, in either direction
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("verdict", ["inside", "outside", "unknown"])
def test_no_verdict_is_ever_rendered_as_good_or_bad_news(verdict):
    result = E.explain("validationDomain", verdict, name="Period",
                       sample="US filings, 1976-1996", this_use="2025 filings",
                       note="A note.")
    assert result["band"] == "context"
    assert result["tone"] == "neutral"
    assert result["goodDirection"] == "none"


def test_matching_the_sample_is_not_described_as_reassurance():
    """The trap: a tick against 'inside' reads as 'so the score is reliable'."""
    inside = E.explain("validationDomain", "inside", name="Market",
                       sample="US Compustat filers", this_use="US listing", note="")
    assert "would not make the score" in inside["action"]
    assert "reliable" in inside["action"]


def test_the_module_explains_why_outside_is_not_a_defect():
    assert "not thereby wrong" in D.__doc__
    assert "provenance" in D.__doc__.lower()


# --------------------------------------------------------------------------- #
# 2. No tally
# --------------------------------------------------------------------------- #
FIT_SCORE_KEYS = {"score", "fit", "matches", "matched", "count", "total",
                  "passed", "grade", "rating", "confidence", "reliability"}


def test_no_screen_block_carries_a_fit_score():
    result = D.assess(company(), symbol="AAPL", market_code="US")
    assert not (set(result) & FIT_SCORE_KEYS)
    for block in result["screens"].values():
        assert not (set(block) & FIT_SCORE_KEYS), sorted(set(block) & FIT_SCORE_KEYS)
        for dimension in block["dimensions"]:
            assert not (set(dimension) & FIT_SCORE_KEYS)


# --------------------------------------------------------------------------- #
# 3. The published facts, as published
# --------------------------------------------------------------------------- #
def test_each_screen_names_its_paper_and_its_sample():
    result = D.assess(company(), symbol="AAPL", market_code="US")
    screens = result["screens"]
    assert set(screens) == {"piotroski", "altman", "beneish"}
    for block in screens.values():
        assert block["citation"] and block["sample"] and block["label"]
        assert block["dimensions"]


@pytest.mark.parametrize(("screen", "fragment"), [
    ("piotroski", "1976-1996"),
    ("piotroski", "14,043"),
    ("piotroski", "book-to-market"),
    ("altman", "66 US manufacturers"),
    ("altman", "before 1966"),
    ("altman", "emerging-market corporates"),
    ("beneish", "50 manipulators"),
    ("beneish", "1,708"),
    ("beneish", "1982-1988"),
])
def test_the_sample_descriptions_match_the_papers(screen, fragment):
    """Bibliographic facts, asserted so a later tidy-up cannot quietly reword
    them into something the papers do not say."""
    block = D.assess(company(), symbol="AAPL", market_code="US")["screens"][screen]
    haystack = block["sample"] + " " + " ".join(
        d["sample"] + " " + d["note"] for d in block["dimensions"])
    assert fragment in haystack, haystack


@pytest.mark.parametrize("screen", ["piotroski", "altman", "beneish"])
def test_a_2025_filing_is_outside_every_screens_period(screen):
    """The samples ended between 1965 and 1996. Nothing filed now is inside one,
    and the panel has to say so plainly rather than quietly omitting it."""
    result = D.assess(company(year=2025), symbol="AAPL", market_code="US")
    period = dims(result, screen)["period"]
    assert period["verdict"] == "outside"
    assert "2025" in period["thisUse"]


def test_a_filing_from_inside_the_sample_is_reported_as_inside():
    """The period test must be a real comparison, not a constant. A 1990 filing
    is inside Piotroski's window and outside Altman's."""
    result = D.assess(company(year=1990), symbol="XXXX", market_code="US")
    assert dims(result, "piotroski")["period"]["verdict"] == "inside"
    assert dims(result, "altman")["period"]["verdict"] == "outside"
    assert dims(result, "beneish")["period"]["verdict"] == "outside"


def test_the_fiscal_year_comes_from_the_filing_not_from_today():
    """A filing can be eighteen months stale, and dating the check to today
    would silently understate how far the number has travelled."""
    assert D.assess(company(year=2019))["fiscalYear"] == 2019


# --------------------------------------------------------------------------- #
# The market dimension, including the one place it reverses
# --------------------------------------------------------------------------- #
def test_an_idx_listing_is_outside_the_us_fitted_screens():
    result = D.assess(company(), symbol="BBCA.JK", market_code="ID")
    assert dims(result, "piotroski")["market"]["verdict"] == "outside"
    assert dims(result, "beneish")["market"]["verdict"] == "outside"


def test_altmans_emerging_market_bands_reverse_the_usual_direction():
    """The zone boundaries come from a recalibration built FOR emerging markets,
    so an Indonesian listing is on home ground where a US one is not. Getting
    this backwards would be the easy mistake, and it is the interesting fact."""
    idx = dims(D.assess(company(), symbol="BBCA.JK", market_code="ID"), "altman")
    us = dims(D.assess(company(), symbol="AAPL", market_code="US"), "altman")
    assert idx["market"]["verdict"] == "inside"
    assert us["market"]["verdict"] == "outside"
    assert "home ground" in idx["market"]["note"]
    # And the coefficients still go the other way, for both.
    assert idx["period"]["verdict"] == "outside"
    assert us["period"]["verdict"] == "outside"


def test_an_unstated_market_is_unknown_rather_than_assumed_us():
    result = D.assess(company(), symbol="AAPL")
    assert dims(result, "piotroski")["market"]["verdict"] == "unknown"


# --------------------------------------------------------------------------- #
# 4. Unknown stays unknown — the dimension most likely to grow a fake threshold
# --------------------------------------------------------------------------- #
def test_an_expensive_stock_is_outside_the_value_screen():
    """Book/market of 0.01 is not the cheapest fifth of any market in any year."""
    style = dims(D.assess(company(equity=1.0e9, cap=1.0e11)), "piotroski")["style"]
    assert style["verdict"] == "outside"
    assert "three times book" in style["note"]


def test_a_cheap_stock_is_not_claimed_to_be_in_the_top_quintile():
    """A quintile is a position in a cross-section. Book/market alone cannot
    place a name in one, and asserting otherwise would be inventing the
    breakpoint the module explicitly declines to invent."""
    style = dims(D.assess(company(equity=1.2e11, cap=1.0e11)), "piotroski")["style"]
    assert style["verdict"] == "unknown"
    assert "cross-section" in style["note"]


def test_a_missing_book_value_is_unknown_rather_than_outside():
    style = dims(D.assess(company(cap=float("nan"))), "piotroski")["style"]
    assert style["verdict"] == "unknown"


# --------------------------------------------------------------------------- #
# Size and coverage, via index membership rather than an invented cutoff
# --------------------------------------------------------------------------- #
def test_an_index_constituent_is_outside_where_the_effect_was_found():
    size = dims(D.assess(company(), symbol="AAPL"), "piotroski")["size"]
    assert size["verdict"] == "outside"
    assert "Nasdaq-100" in size["thisUse"] or "Dow" in size["thisUse"]
    assert "no analyst following" in size["sample"]


def test_a_name_outside_every_index_is_unknown_not_small():
    """Absence from the four lists is not evidence of being small — the lists
    cover a fraction of two markets. The module must not read one as the other."""
    size = dims(D.assess(company(), symbol="ZZZZ"), "piotroski")["size"]
    assert size["verdict"] == "unknown"
    assert "cannot say" in size["note"]


def test_no_symbol_at_all_is_unknown():
    assert dims(D.assess(company()), "piotroski")["size"]["verdict"] == "unknown"


# --------------------------------------------------------------------------- #
# Beneish's enriched sample — the setup for reading a flag correctly
# --------------------------------------------------------------------------- #
def test_beneish_states_that_manipulators_were_over_represented():
    prevalence = dims(D.assess(company()), "beneish")["prevalence"]
    assert prevalence["verdict"] == "outside"
    assert "over-represented" in prevalence["note"]
    assert "false alarms" in prevalence["note"]


# --------------------------------------------------------------------------- #
# Degradation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("payload", [
    {}, {"balance": None}, {"balance": pd.DataFrame()},
    {"balance": "not a frame", "market_cap": "nonsense"},
    {"sector": None, "industry": None, "market_cap": None},
])
def test_degenerate_companies_never_raise(payload):
    result = D.assess(payload, symbol=None, market_code=None)
    assert set(result["screens"]) == {"piotroski", "altman", "beneish"}
    for block in result["screens"].values():
        for dimension in block["dimensions"]:
            assert dimension["verdict"] in ("inside", "outside", "unknown")
            assert dimension["name"] and dimension["note"]


def test_every_dimension_reaches_the_explanation_layer():
    """A dimension the panel cannot render an info icon for is one the reader
    has to take on trust."""
    from _lib import quality as Q
    payload = {"domains": D.assess(company(), symbol="AAPL", market_code="US")}
    explained = E.for_quality(payload)
    expected = {f"domain.{screen}.{d['key']}"
                for screen, block in payload["domains"]["screens"].items()
                for d in block["dimensions"]}
    assert expected <= set(explained), sorted(expected - set(explained))
    assert all(explained[key]["tone"] == "neutral" for key in expected)
    assert Q.screendomain is D, "the lens must use this module, not a copy"
