"""
symbols.py
==========
Single source of truth for turning a user-typed ticker into a Yahoo symbol.

WHY THIS EXISTS
---------------
Each engine used to take the ticker string it was handed. Only the valuation
engine knew about the `.JK` suffix, so a request for "BBCA" on the IDX market
valued PT Bank Central Asia (BBCA.JK, IDR) while the technical and anomaly
engines silently analysed JPMorgan BetaBuilders Canada ETF (BBCA, USD) — three
panels, two different securities, one ticker in the header and no error.

Unsuffixed IDX codes are not safely inert on Yahoo: ASII resolves to Accredited
Solutions Inc., MAIN to Main Street Capital, LIFE to Ethos Technologies. The
failure mode is a plausible-looking wrong answer, which is the worst kind.

So resolution happens exactly once, at the edge, and every engine is handed the
resolved symbol. `resolve()` is idempotent, so calling it again downstream is
harmless.
"""

from __future__ import annotations

MARKET_SUFFIX = {
    "US": "",
    "ID": ".JK",
}

DEFAULT_MARKET = "US"


class SymbolError(ValueError):
    """Raised when a ticker cannot be turned into a Yahoo symbol."""


def resolve(ticker: str, market_code: str = DEFAULT_MARKET) -> str:
    """Normalise a user-typed ticker into the symbol Yahoo expects.

    Idempotent: `resolve(resolve(t, m), m) == resolve(t, m)`.

    An explicitly typed suffix always wins. "BBCA.JK" stays "BBCA.JK" whichever
    market is selected, because the user was more specific than the dropdown.
    Tickers that already carry a dot for another reason (BRK.B) are untouched on
    the US market, whose suffix is the empty string.
    """
    raw = (ticker or "").strip().upper()
    if not raw:
        raise SymbolError("Ticker symbol must be a non-empty string.")

    suffix = MARKET_SUFFIX.get((market_code or DEFAULT_MARKET).strip().upper(), "")
    if suffix and not raw.endswith(suffix):
        return f"{raw}{suffix}"
    return raw


def base_code(symbol: str) -> str:
    """The bare listing code, suffix stripped — for news search and display."""
    out = (symbol or "").strip().upper()
    for suffix in MARKET_SUFFIX.values():
        if suffix and out.endswith(suffix):
            return out[: -len(suffix)]
    return out


def market_of(symbol: str) -> str:
    """Infer the market from an already-resolved symbol."""
    out = (symbol or "").strip().upper()
    for code, suffix in MARKET_SUFFIX.items():
        if suffix and out.endswith(suffix):
            return code
    return DEFAULT_MARKET


def hint(symbol: str) -> str:
    """A specific next thing to try when a symbol returned no data.

    WHY THIS IS NOT JUST "CHECK THE SPELLING". A US class share is written
    BRK.B or BF.B everywhere a human reads one, and Yahoo spells it BRK-B. The
    dotted form passes this app's ticker validation — it looks exactly like an
    exchange suffix — so the request goes through, finds nothing, and comes back
    telling the reader to check a spelling that was never wrong. Verified live:
    BRK-B and BF-B both return data, BRK.B and BRK.A do not.

    The app does NOT rewrite the symbol on the reader's behalf. `symbols.py`
    exists because silently reinterpreting what someone typed is how this
    codebase once valued one company while charting another; suggesting a
    correction and letting them retype it keeps the resolution visible.
    """
    raw = (symbol or "").strip().upper()
    if not raw:
        return "Enter a ticker symbol."

    base, _, suffix = raw.rpartition(".")
    # A single trailing letter after a dot is a share class, not an exchange.
    # Real exchange suffixes are two or more letters (.JK, .L, .TO — .L being the
    # exception, which is why the class-share test also requires a short base).
    if base and len(suffix) == 1 and suffix.isalpha():
        return (f"US class shares use a hyphen on this data source: try "
                f"{base}-{suffix} rather than {raw}.")
    if "." not in raw and "-" not in raw:
        return ("Non-US listings need their exchange suffix — Indonesian tickers "
                "end in .JK. Crypto takes a pair, such as BTC-USD.")
    return "Check the symbol, or try a wider date range."
