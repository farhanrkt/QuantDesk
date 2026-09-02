"""Locks the fix documented in _lib/symbols.py.

The bug: only the valuation engine knew about `.JK`, so a request for "BBCA" on
the IDX market valued PT Bank Central Asia while the technical and anomaly
panels analysed the BBCA US ETF — three panels, two securities, one ticker in
the header, no error. These tests pin the contract that prevents it.
"""

from __future__ import annotations

import pytest

from _lib import symbols


@pytest.mark.parametrize(
    ("ticker", "market", "expected"),
    [
        ("BBCA", "ID", "BBCA.JK"),      # the bare IDX code MUST gain its suffix
        ("bbca", "ID", "BBCA.JK"),      # case is normalised
        ("  BBCA  ", "ID", "BBCA.JK"),  # whitespace is stripped
        ("BBCA.JK", "ID", "BBCA.JK"),   # already suffixed, unchanged
        ("BBCA.JK", "US", "BBCA.JK"),   # an explicit suffix beats the dropdown
        ("AAPL", "US", "AAPL"),         # US suffix is empty
        ("BRK.B", "US", "BRK.B"),       # a dot for another reason is untouched
        ("BTC-USD", "US", "BTC-USD"),   # crypto pair
        ("^TNX", "US", "^TNX"),         # index
        ("AAPL", "", "AAPL"),           # blank market falls back to US
    ],
)
def test_resolve(ticker, market, expected):
    assert symbols.resolve(ticker, market) == expected


@pytest.mark.parametrize("market", ["US", "ID"])
@pytest.mark.parametrize("ticker", ["BBCA", "AAPL", "BRK.B", "BTC-USD"])
def test_resolve_is_idempotent(ticker, market):
    """resolve(resolve(t)) == resolve(t) — engines may call it again safely."""
    once = symbols.resolve(ticker, market)
    assert symbols.resolve(once, market) == once


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_resolve_rejects_empty(bad):
    with pytest.raises(symbols.SymbolError):
        symbols.resolve(bad, "US")


def test_base_code_and_market_round_trip():
    assert symbols.base_code("BBCA.JK") == "BBCA"
    assert symbols.base_code("AAPL") == "AAPL"
    assert symbols.market_of("BBCA.JK") == "ID"
    assert symbols.market_of("AAPL") == "US"


def test_bare_idx_codes_are_not_inert_on_yahoo():
    """The premise of the whole module, asserted so it cannot be argued away.

    ASII, MAIN and LIFE are all real US listings. Sending them unsuffixed
    returns a plausible wrong company rather than an error, which is why
    resolution has to happen at the edge and not per engine.
    """
    for code in ("ASII", "MAIN", "LIFE"):
        assert symbols.resolve(code, "ID") == f"{code}.JK"
        assert symbols.resolve(code, "US") == code


# --------------------------------------------------------------------------- #
# The conventions must follow the symbol, not the dropdown.
#
# `resolve` already let a typed suffix beat the dropdown, so "ITMG.JK" on the
# default US setting fetched the right Indonesian company — and then priced it
# as an American one, because the market code handed to the engines was still
# the dropdown's. Rupiah printed with a dollar sign, the cost of equity took the
# US 10-year and a 5.5% ERP, and beta was regressed against ^GSPC. Measured on
# ITMG.JK: fair value Rp 98,000 against the correct Rp 67,525.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("ticker", "dropdown", "expected"),
    [
        ("ITMG.JK", "US", "ID"),   # THE BUG: typed suffix, dropdown left alone
        ("BBCA.JK", "US", "ID"),   # the README's first documented IDX path
        ("bbca.jk", "us", "ID"),   # case-insensitive on both inputs
        ("BBCA", "ID", "ID"),      # the README's second path, still correct
        ("BBCA.JK", "ID", "ID"),   # agreeing inputs stay agreed
        ("AAPL", "US", "US"),      # the ordinary case is untouched
        ("BRK.B", "US", "US"),     # a class-share dot is not an exchange suffix
        ("BTC-USD", "US", "US"),   # crypto pair
        ("AAPL", "", "US"),        # blank dropdown falls back to US
    ],
)
def test_market_for_follows_the_typed_suffix(ticker, dropdown, expected):
    assert symbols.market_for(ticker, dropdown) == expected


def test_market_for_agrees_with_market_of_resolve():
    """It is defined as that composition; pin it so it cannot drift apart."""
    for ticker in ("ITMG.JK", "BBCA", "AAPL", "BRK.B", "BTC-USD"):
        for dropdown in ("US", "ID"):
            assert symbols.market_for(ticker, dropdown) == \
                symbols.market_of(symbols.resolve(ticker, dropdown))
