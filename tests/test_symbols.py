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
