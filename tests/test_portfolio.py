"""Portfolio context — the candidate against what is already owned.

WHAT THESE TESTS PROTECT

1. The fourth-copy detection actually works. A candidate that clones three
   existing holdings must show up as adding names without adding independence.
   That is the failure the whole feature exists to catch, and it is asserted
   against a PLANTED factor structure rather than against real prices, so the
   answer is known in advance.

2. The independence estimator is one implementation. `ranking.py` and this
   module ask the same question of different matrices, and two copies would
   eventually disagree about what redundancy means in an app whose whole
   argument is that correlated measures are worth less than they look.

3. Risk share and money share are compared, never conflated. A position holding
   a tenth of the money and a quarter of the risk is the finding.

4. Nothing is claimed without overlap. Correlation from thirty shared days is an
   anecdote, and the module has to refuse rather than print it.

5. The measured stability travels with the numbers. This is the one place in the
   app where a measurement informs position size, and it is only allowed to
   because the persistence was measured first — so the panel carries it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import exposure
from _lib import explain as E
from _lib import portfolio as P
from _lib import riskmodel


# --------------------------------------------------------------------------- #
# A planted factor structure: the answer is known before the code runs
# --------------------------------------------------------------------------- #
def _frames(spec: dict, n: int = 400, seed: int = 11) -> dict:
    """OHLCV frames built from `beta * market + idiosyncratic noise`.

    Two names sharing a beta of 1.0 with tiny idiosyncratic noise are near
    clones by construction; a name with beta 0.1 and large noise is genuinely
    separate. Nothing here is estimated from real prices, so every assertion
    below is against a structure that was planted.
    """
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2024-01-02", periods=n)
    market = rng.normal(0.0002, 0.011, n)
    out = {}
    for symbol, (beta, idio) in spec.items():
        returns = beta * market + rng.normal(0.0, idio, n)
        close = 100.0 * np.exp(np.cumsum(returns))
        out[symbol] = pd.DataFrame({
            "Open": close, "High": close * 1.01, "Low": close * 0.99,
            "Close": close, "Volume": np.full(n, 1_000_000.0),
        }, index=index)
    return out


CLONES = {"AAA": (1.0, 0.002), "BBB": (1.0, 0.002), "CCC": (1.0, 0.002),
          "ZZZ": (0.1, 0.020), "CAND": (1.0, 0.002), "INDEP": (0.05, 0.020)}


def analyse(candidate, holdings, frames=None, weights=None, monkeypatch=None, **kw):
    data = frames if frames is not None else _frames(CLONES)
    kept = {s: f for s, f in data.items() if s in {candidate, *holdings}}
    monkeypatch.setattr(P.market_data, "ohlcv_batch", lambda *a, **k: kept)
    return P.analyse(candidate, list(holdings), weights=weights, **kw)


@pytest.fixture()
def book(monkeypatch):
    def run(candidate="CAND", holdings=("AAA", "BBB", "CCC", "ZZZ"), **kw):
        return analyse(candidate, holdings, monkeypatch=monkeypatch, **kw)
    return run


# --------------------------------------------------------------------------- #
# 1. The fourth copy of a bet already held
# --------------------------------------------------------------------------- #
def test_a_clone_of_existing_holdings_adds_names_without_adding_independence():
    """The failure the feature exists to catch. Four names that move together
    are one position with four ticker symbols on it, and no single-ticker page
    can say so."""
    import _lib.portfolio as module
    frames = _frames(CLONES)
    original = module.market_data.ohlcv_batch
    try:
        module.market_data.ohlcv_batch = lambda *a, **k: {
            s: f for s, f in frames.items() if s in {"CAND", "AAA", "BBB", "CCC"}}
        result = module.analyse("CAND", ["AAA", "BBB", "CCC"])
    finally:
        module.market_data.ohlcv_batch = original

    assert result["usable"]
    independence = result["independence"]
    assert independence["withCandidate"] == 4
    # More names, no more independence: the participation ratio does not rise.
    assert independence["after"] <= independence["before"] + 0.05
    assert independence["after"] < 2.0, "four clones must not read as four bets"
    assert all(p["band"] == "high" for p in result["pairs"])


def test_a_genuinely_different_candidate_raises_the_independent_count(book):
    crowded = book(candidate="CAND", holdings=("AAA", "BBB", "CCC"))
    diversifier = book(candidate="INDEP", holdings=("AAA", "BBB", "CCC"))
    assert diversifier["independence"]["gain"] > crowded["independence"]["gain"]
    assert diversifier["independence"]["after"] > crowded["independence"]["after"]
    assert diversifier["pairs"][0]["band"] == "low"


def test_the_explanation_names_the_fourth_copy_shape(book):
    result = book(candidate="CAND", holdings=("AAA", "BBB", "CCC"))
    reading = E.for_portfolio(result)["effectiveHoldings"]["reading"]
    assert "next to no more" in reading
    assert "fourth copy" in reading
    assert E.for_portfolio(result)["effectiveHoldings"]["band"] == "caution"


def test_the_independence_scale_is_anchored_on_an_uncorrelated_addition(book):
    """`gain <= 0` was the obvious rule and it was wrong: the participation
    ratio creeps up with ANY extra name, so a fourth clone scored a small
    positive gain and read as progress. One unrelated name adds one bet, and
    that is what the bands are measured against."""
    clone = E.for_portfolio(book(candidate="CAND", holdings=("AAA", "BBB", "CCC")))
    fresh = E.for_portfolio(book(candidate="INDEP", holdings=("AAA", "BBB", "CCC")))
    assert clone["effectiveHoldings"]["band"] == "caution"
    assert fresh["effectiveHoldings"]["band"] == "context"
    assert "whole extra bet" in fresh["effectiveHoldings"]["reading"]


def test_pairs_are_ordered_most_correlated_first(book):
    pairs = book()["pairs"]
    assert [p["ticker"] for p in pairs][-1] == "ZZZ", "the diversifier sorts last"
    assert pairs == sorted(pairs, key=lambda p: -p["correlation"])


# --------------------------------------------------------------------------- #
# 2. One implementation of the independence estimator
# --------------------------------------------------------------------------- #
def test_the_participation_ratio_lives_in_one_place():
    """`ranking.py` asks the identical question of a signal matrix. A second
    copy would eventually disagree about what redundancy means."""
    from _lib import ranking
    assert ranking.riskmodel.effective_independent is riskmodel.effective_independent


def test_the_estimator_counts_independent_columns_and_collapses_redundant_ones():
    """Boundary anchors, so the number means what the prose claims."""
    identity = np.eye(4)
    assert riskmodel.effective_independent(identity) == pytest.approx(4.0)
    perfect = np.ones((4, 4))
    assert riskmodel.effective_independent(perfect) == pytest.approx(1.0)
    half = np.full((4, 4), 0.5) + np.eye(4) * 0.5
    value = riskmodel.effective_independent(half)
    assert 1.0 < value < 4.0


@pytest.mark.parametrize("bad", [None, "not a matrix", np.array([[np.nan, 1.0], [1.0, np.nan]])])
def test_the_estimator_returns_none_rather_than_raising(bad):
    assert riskmodel.effective_independent(bad) is None


# --------------------------------------------------------------------------- #
# 3. Risk share against money share
# --------------------------------------------------------------------------- #
def test_risk_shares_sum_to_one_and_the_volatile_name_carries_more_than_its_money(book):
    rows = book()["contributions"]["rows"]
    assert sum(r["riskShare"] for r in rows) == pytest.approx(1.0)
    assert sum(r["weight"] for r in rows) == pytest.approx(1.0)
    # ZZZ swings ten times harder than the clones, so at equal money it must
    # carry more than an equal share of the risk.
    volatile = next(r for r in rows if r["ticker"] == "ZZZ")
    assert volatile["excess"] > 0
    assert volatile["riskShare"] > volatile["weight"]


def test_supplied_weights_are_used_and_reported_as_not_equal(book):
    equal = book()
    assert equal["equalWeighted"] is True
    weighted = book(weights={"AAA": 5.0, "BBB": 1.0, "CCC": 1.0, "ZZZ": 1.0, "CAND": 1.0})
    assert weighted["equalWeighted"] is False
    heavy = next(r for r in weighted["contributions"]["rows"] if r["ticker"] == "AAA")
    assert heavy["weight"] == pytest.approx(5.0 / 9.0)
    assert heavy["riskShare"] > 0.4


def test_the_explanation_compares_risk_with_money_rather_than_quoting_one(book):
    reading = E.explain("riskShare", 0.25, ticker="NVDA", weight=0.10)["reading"]
    assert "25%" in reading and "10%" in reading
    assert E.explain("riskShare", 0.25, ticker="NVDA", weight=0.10)["band"] == "poor"
    # In line means no alarm.
    assert E.explain("riskShare", 0.21, ticker="X", weight=0.20)["band"] == "context"


def test_a_position_that_reduces_portfolio_risk_is_not_called_broadly_in_line():
    """Marginal risk contribution goes negative when a position moves against
    the book — it SUBTRACTS from total risk, which is diversification actually
    working. Putting that through the same ladder as everything else told a
    reader holding a real hedge that risk and money were 'broadly in line',
    which is the least useful thing that could be said about it. Found by
    running the panel against a book with a defensive name in it."""
    result = E.explain("riskShare", -0.02, ticker="KO", weight=0.167)
    assert "REDUCES" in result["reading"]
    assert "broadly in line" not in result["reading"]
    assert "diversification" in result["reading"]
    assert result["tone"] == "neutral", "a hedge is not a warning"


# --------------------------------------------------------------------------- #
# 4. Nothing claimed without overlap
# --------------------------------------------------------------------------- #
def test_a_holding_with_too_little_shared_history_is_dropped_not_correlated(monkeypatch):
    frames = _frames({"CAND": (1.0, 0.002), "AAA": (1.0, 0.002)}, n=400)
    frames["NEW"] = _frames({"NEW": (1.0, 0.002)}, n=40)["NEW"]
    result = analyse("CAND", ("AAA", "NEW"), frames=frames, monkeypatch=monkeypatch)
    assert [p["ticker"] for p in result["pairs"]] == ["AAA"]
    assert "NEW" in result["missing"]


def test_a_candidate_with_no_shared_history_refuses_rather_than_guessing(monkeypatch):
    frames = _frames({"AAA": (1.0, 0.002), "BBB": (1.0, 0.002)}, n=400)
    frames["CAND"] = _frames({"CAND": (1.0, 0.002)}, n=30)["CAND"]
    result = analyse("CAND", ("AAA", "BBB"), frames=frames, monkeypatch=monkeypatch)
    assert result["usable"] is False
    assert "no correlation against it means anything" in result["reason"]


def test_no_usable_holdings_says_so_rather_than_returning_an_empty_table(monkeypatch):
    frames = _frames({"CAND": (1.0, 0.002)}, n=400)
    frames["NEW"] = _frames({"NEW": (1.0, 0.002)}, n=20)["NEW"]
    result = analyse("CAND", ("NEW",), frames=frames, monkeypatch=monkeypatch)
    assert result["usable"] is False
    assert "exchange suffixes" in result["reason"]


def test_every_pair_reports_how_many_days_it_was_measured_over(book):
    for pair in book()["pairs"]:
        assert pair["overlapDays"] >= P.MIN_OVERLAP


# --------------------------------------------------------------------------- #
# 5. The measurement that licenses this feature travels with it
# --------------------------------------------------------------------------- #
def test_the_measured_persistence_is_shipped_and_attached(book):
    """This is the one place a measurement in this app informs position size,
    and it is only allowed to because the persistence was measured first. The
    panel has to carry that rather than assert it."""
    stability = P.load_stability()
    if stability is None:
        pytest.skip("run scripts/measure_correlation_stability.py")
    assert stability["measuredOn"]
    assert book()["stability"]["headline"] == stability["headline"]


def test_the_shipped_measurement_actually_supports_sizing_on_correlations():
    """If a re-measurement ever finds correlations do not persist, this fails
    and the feature has to be argued for again rather than quietly continuing."""
    stability = P.load_stability()
    if stability is None:
        pytest.skip("run scripts/measure_correlation_stability.py")
    yearly = stability["yearlyPersistence"]
    assert yearly["min"] is not None and yearly["min"] > 0.25, (
        "correlations no longer persist year to year; the panel must stop informing "
        "position size until this is re-argued")


def test_the_stress_caveat_is_carried_because_it_limits_the_feature():
    stability = P.load_stability()
    if stability is None:
        pytest.skip("run scripts/measure_correlation_stability.py")
    assert stability["stressRise"]["mean"] is not None
    assert any("Forbes" in c for c in stability["caveats"]), (
        "conditioning on returns biases any correlation measured inside the "
        "condition, and the file has to say so")


# --------------------------------------------------------------------------- #
# Degradation
# --------------------------------------------------------------------------- #
def test_a_correlation_with_no_value_is_never_coloured():
    result = E.explain("holdingCorrelation", None, ticker="AAA")
    assert result["band"] == "unavailable" and result["tone"] == "none"


def test_risk_contributions_refuse_rather_than_dividing_by_zero():
    matrix = pd.DataFrame(np.eye(2), index=["A", "B"], columns=["A", "B"])
    zero = pd.Series({"A": 0.0, "B": 0.0})
    weights = pd.Series({"A": 1.0, "B": 1.0})
    assert P.risk_contributions(matrix, zero, weights)["usable"] is False
    assert P.risk_contributions(matrix, pd.Series({"A": 0.2, "B": 0.2}),
                                pd.Series({"A": 0.0, "B": 0.0}))["usable"] is False


def test_for_portfolio_returns_nothing_for_an_unusable_result():
    assert E.for_portfolio({"usable": False, "reason": "x"}) == {}
    assert E.for_portfolio({}) == {}


# --------------------------------------------------------------------------- #
# What the book has in common — the driver label
# --------------------------------------------------------------------------- #
def test_the_reference_series_ride_along_and_are_kept_out_of_the_correlations(monkeypatch):
    """ONE FETCH, TWO PURPOSES, AND THE TWO MUST NOT MIX.

    `exposure` needs an index and four futures, and appending them to a download
    already being made is a chunk rather than a round trip. But a future is not
    a holding: if it survived into the correlation matrix the panel would report
    that the candidate tracks crude oil at 0.31 and count it toward how many
    independent bets the book is.
    """
    requested: list = []

    def spy(symbols_list, *a, **k):
        requested.extend(symbols_list)
        return _frames(CLONES)

    monkeypatch.setattr(P.market_data, "ohlcv_batch", spy)
    result = P.analyse("CAND", ["AAA", "BBB", "CCC"], market_code="ID")

    for symbol in exposure.reference_symbols("ID"):
        assert symbol in requested, "the references were asked for"
    assert "^JKSE" not in (result["holdings"] or []), "and kept out of the book"
    assert not any(p["ticker"].startswith("^") or "=" in p["ticker"]
                   for p in result["pairs"]), "and out of the pairwise correlations"


def test_a_failed_reference_fetch_reads_as_untested_not_as_no_driver(book):
    """CONSTRAINT 3, AT THE SEAM WHERE IT IS EASIEST TO LOSE.

    The stub supplies no reference series, which is the shape of a failed
    upstream fetch. The shared direction is still measurable — it needs only the
    holdings — so the panel keeps that figure. What it must NOT do is report
    "nothing explained these holdings", because nothing was asked: a reference
    that could not be read and a reference that was read and found absent are
    different facts, and only the second is a finding.
    """
    result = book()
    assert result["usable"] is True
    driver = result["driver"]
    assert driver["usable"] is True, "the shared direction needs no references"
    assert driver["varianceShare"] is not None
    assert driver["marketShare"] is None, "no index arrived, so no share is claimed"
    assert driver["matches"] == []
    assert all(t["available"] is False for t in driver["tested"])

    explanation = E.for_portfolio(result)["sharedDriver"]
    assert explanation["band"] == "unavailable", "not a finding — an unasked question"
    assert explanation["tone"] == "none"
    assert result["pairs"], "and the rest of the panel is unaffected"


def test_the_driver_uses_the_whole_fetched_window_not_the_correlation_window():
    """DIFFERENT QUESTIONS, DIFFERENT SAMPLES, and the reason is in `portfolio`.

    252 days is the window whose PERSISTENCE was measured, so it is the only one
    a correlation may be quoted from. Naming a shared direction makes no
    persistence claim, so it uses everything fetched — about seventy weeks rather
    than fifty-two, which is the difference between clearing `MIN_WEEKS` and not.
    """
    frames = _frames(CLONES, n=500)
    weekly = exposure.to_weekly(P.daily_returns(frames, window=10 ** 6))
    assert len(weekly) > 60, "the full window is well past the weekly floor"
    assert len(exposure.to_weekly(P.daily_returns(frames))) < 60, (
        "and the correlation window alone would be marginal")
