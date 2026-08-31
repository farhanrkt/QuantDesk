"""Naming what a book has in common.

PLANTED GROUND TRUTH THROUGHOUT. Every test here builds returns whose driver is
known by construction — a factor the test itself created — and then asks the
module to find it. Nothing checks the answer against a second implementation of
the same arithmetic, which would only prove the formula was copied twice.

The cases that matter are the refusals. A panel that names a driver for a book
that has none is worse than no panel, because "your holdings are an energy bet"
is a sentence a reader will act on.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from _lib import exposure

DAYS = 500
INDEX = pd.bdate_range("2024-01-01", periods=DAYS)


def _noise(seed: float, scale: float = 0.012) -> pd.Series:
    rng = np.random.default_rng(int(seed))
    return pd.Series(rng.normal(0.0, scale, DAYS), index=INDEX)


def _references(**series) -> pd.DataFrame:
    """A reference frame keyed by the symbols `exposure` actually looks for."""
    blank = pd.Series(0.0, index=INDEX)
    frame = {"^JKSE": blank, "^GSPC": blank, "GC=F": blank,
             "CL=F": blank, "HG=F": blank, "DX-Y.NYB": blank}
    frame.update(series)
    return pd.DataFrame(frame)


def _book(factor: pd.Series, beta: float = 0.8, names: int = 4,
          idiosyncratic: float = 0.010) -> pd.DataFrame:
    """`names` holdings that are all the same bet plus their own noise."""
    return pd.DataFrame({
        f"H{i}": beta * factor + _noise(1000 + i, idiosyncratic)
        for i in range(names)
    })


# --------------------------------------------------------------------------- #
# It finds a driver that is really there
# --------------------------------------------------------------------------- #
def test_a_book_built_on_one_factor_is_named_after_it():
    """Four holdings that are the same bet on a planted factor, and that factor
    is one of the reference series. Anything less than naming it is a failure of
    the pipeline rather than of the data."""
    energy = _noise(1, 0.020)
    result = exposure.analyse(_book(energy), _references(**{"CL=F": energy}), "ID")

    assert result["usable"]
    assert [m["key"] for m in result["matches"]] == ["oil"]
    assert result["matches"][0]["correlation"] > 0.8
    assert result["varianceShare"] > 0.5, "one factor, so the first component is large"


def test_the_local_market_is_removed_before_anything_is_named():
    """THE WHOLE DESIGN, AS A TEST. Holdings driven purely by their own index
    must report a high market share and name nothing — otherwise the panel fires
    on every portfolio ever entered, which is the `screendomain.py` failure of
    colouring a condition that holds for everybody."""
    market = _noise(2, 0.014)
    result = exposure.analyse(_book(market), _references(**{"^JKSE": market}), "ID")

    assert result["usable"]
    assert result["marketShare"] > 0.8, "the shared direction IS the index"
    assert result["matches"] == [], "and nothing else should be claimed"


def test_a_driver_hiding_under_the_market_is_still_found():
    """The harder half: holdings carrying BOTH the index and a separate factor.

    A book can be 40% market and still be an energy bet, and the residual is
    where that shows. Reported market share must not swallow the second driver.
    """
    market, energy = _noise(3, 0.014), _noise(4, 0.020)
    holdings = pd.DataFrame({
        f"H{i}": 0.7 * market + 0.7 * energy + _noise(2000 + i, 0.008)
        for i in range(4)
    })
    result = exposure.analyse(
        holdings, _references(**{"^JKSE": market, "CL=F": energy}), "ID")

    assert result["marketShare"] > 0.2, "the index is genuinely in there"
    assert [m["key"] for m in result["matches"]] == ["oil"], "and so is the driver"


# --------------------------------------------------------------------------- #
# It refuses when it should
# --------------------------------------------------------------------------- #
def test_unrelated_holdings_are_not_given_a_driver():
    """Four independent random walks share nothing. Naming a driver here is the
    false positive that would make the panel unusable."""
    holdings = pd.DataFrame({f"H{i}": _noise(3000 + i) for i in range(4)})
    result = exposure.analyse(holdings, _references(**{"CL=F": _noise(9)}), "ID")

    assert result["usable"]
    assert result["matches"] == []
    assert result["hasSharedDirection"] is False, "no common direction to speak of"


def test_two_references_that_cannot_be_told_apart_name_neither():
    """AMBIGUITY IS A REFUSAL, NOT A TIE-BREAK.

    Two references that are near-copies of the driver both clear the threshold,
    and picking the larger would present a precision the sample does not have.
    """
    driver = _noise(5, 0.020)
    references = _references(**{"CL=F": driver + _noise(6, 0.001),
                                "GC=F": driver + _noise(7, 0.001)})
    result = exposure.analyse(_book(driver), references, "ID")

    assert result["ambiguous"] is True
    assert result["matches"] == [], "neither is named"


def test_two_holdings_are_refused():
    """The first component of two names is their average wearing a longer name."""
    driver = _noise(8, 0.020)
    result = exposure.analyse(_book(driver, names=2), _references(), "ID")
    assert result["usable"] is False
    assert "3 holdings" in result["reason"]


def test_a_short_history_is_refused():
    """Ten weeks is an anecdote. The floor is stated in the refusal so a reader
    knows what would fix it."""
    short = pd.bdate_range("2024-01-01", periods=50)
    holdings = pd.DataFrame(
        {f"H{i}": pd.Series(np.zeros(50), index=short) for i in range(4)})
    result = exposure.analyse(holdings, pd.DataFrame(), "ID")
    assert result["usable"] is False
    assert f"{exposure.MIN_WEEKS} weeks" in result["reason"]


def test_references_with_no_data_are_reported_as_untested_not_as_absent_drivers():
    """`tested` carries every reference and says which ones could be read.

    Constraint 3: a driver that could not be checked must not read as a driver
    that was checked and found absent, and the panel needs the difference in the
    payload to say so.
    """
    driver = _noise(10, 0.020)
    references = pd.DataFrame({"CL=F": driver}, index=INDEX)   # the others missing
    result = exposure.analyse(_book(driver), references, "ID")

    by_key = {t["key"]: t for t in result["tested"]}
    assert by_key["oil"]["available"] is True
    assert by_key["gold"]["available"] is False
    assert "correlation" not in by_key["gold"]


# --------------------------------------------------------------------------- #
# Contracts the rest of the app depends on
# --------------------------------------------------------------------------- #
def test_weekly_aggregation_is_exact_not_approximate():
    """Log returns ADD, so a week is the sum of its days.

    Checked against prices rather than against a second resample: build a price
    path, take its Friday-to-Friday log return directly, and require the summed
    daily returns to match. Averaging instead of summing would pass a
    same-formula test and be wrong by a factor of five.
    """
    rng = np.random.default_rng(11)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, DAYS))), index=INDEX)
    daily = np.log(prices / prices.shift(1)).to_frame("X")

    weekly = exposure.to_weekly(daily)
    fridays = prices.resample("W-FRI").last()
    direct = np.log(fridays / fridays.shift(1)).dropna()

    shared = weekly.index.intersection(direct.index)
    assert len(shared) > 50
    assert weekly.loc[shared, "X"].to_numpy() == pytest.approx(
        direct.loc[shared].to_numpy(), abs=1e-12)


def test_the_component_sign_is_fixed_so_it_cannot_flip_between_requests():
    """A principal component's sign is arbitrary. Left arbitrary it would flip as
    data arrived and turn every correlation downstream inside out, which reads as
    the driver reversing when nothing has changed."""
    driver = _noise(12, 0.020)
    for beta in (0.8, -0.8):
        direction = exposure.shared_direction(
            exposure.to_weekly(_book(driver, beta=beta)))
        assert sum(direction["loadings"].values()) > 0


def test_matches_come_back_in_declaration_order_not_strength_order():
    """`PRODUCT.md` constraint 1 forbids a strength ranking as squarely as it
    forbids a composite. Gold is declared before oil, so a book matching both
    must list gold first even when oil correlates more strongly."""
    driver = _noise(13, 0.020)
    # Gold is deliberately the WEAKER of the two — 0.58 against oil's 0.96 — and
    # far enough below it to clear the ambiguity guard, so this exercises the
    # ordering rather than skipping past it.
    references = _references(**{"GC=F": driver + _noise(14, 0.030),
                                "CL=F": driver + _noise(15, 0.001)})
    result = exposure.analyse(_book(driver), references, "ID")

    assert len(result["matches"]) == 2, "both must clear, or this proves nothing"
    keys = [m["key"] for m in result["matches"]]
    assert keys == ["gold", "oil"], "declaration order"
    assert abs(result["matches"][0]["correlation"]) < abs(
        result["matches"][1]["correlation"]), "and it is NOT strength order"


def test_reference_symbols_cover_every_series_the_analysis_reads():
    """The fetch list and the analysis must not drift apart: a reference the
    analysis looks for and the batch never requested is silently 'unavailable'
    forever, which is the quiet failure this module exists to avoid."""
    for market in ("US", "ID"):
        needed = set(exposure.reference_symbols(market))
        assert exposure.LOCAL_INDEX[market] in needed
        for reference in exposure.REFERENCES:
            if market in reference.markets:
                assert reference.symbol in needed
