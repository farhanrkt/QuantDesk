"""The data-access boundary: the one module that talks to yfinance.

These tests used to live in test_valuation.py and test_ranking.py, patching each
engine's own `yf` import. They moved here with the code, which is the point of
the refactor — there is now ONE place a fetch can be intercepted, so there is one
place to test it.

Every test is offline. Nothing here reaches the network; the fakes reproduce the
shapes yfinance actually returns, including the `FastInfo` accessor whose real
semantics caused a live bug.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from typing import ClassVar

import numpy as np
import pandas as pd
import pytest

from helpers import _Stub, path, steady

from _lib import market_data as MD
from _lib import ranking as R

def test_risk_free_rate_is_cached_per_day(monkeypatch):
    """Q7: one ^TNX fetch per day, not one per valuation. Failures are not cached."""
    calls = {"n": 0}

    class FakeTicker:
        def __init__(self, symbol):
            calls["n"] += 1

        def history(self, period):
            import pandas as pd
            return pd.DataFrame({"Close": [4.65]})

    monkeypatch.setattr(MD.yf, "Ticker", FakeTicker)
    MD._RATE_CACHE.clear()

    for _ in range(5):
        rate, source = MD.risk_free_rate("US", 0.042)
        assert rate == pytest.approx(0.0465)
        assert "live" in source
    assert calls["n"] == 1

    # A non-US market never touches the network at all.
    before = calls["n"]
    MD.risk_free_rate("ID", 0.065)
    assert calls["n"] == before


def test_risk_free_failure_is_not_cached(monkeypatch):
    class Exploding:
        def __init__(self, symbol):
            raise RuntimeError("network down")

    monkeypatch.setattr(MD.yf, "Ticker", Exploding)
    MD._RATE_CACHE.clear()

    rate, source = MD.risk_free_rate("US", 0.042)
    assert rate == pytest.approx(0.042)
    assert "fallback" in source
    assert not MD._RATE_CACHE, "a failed fetch must not pin the fallback all day"




# --------------------------------------------------------------------------- #
# The company cache — two bugs that were invisible to a numerical audit
# --------------------------------------------------------------------------- #
def _stub_company(monkeypatch, calls: list, delay: float = 0.0) -> None:
    """Replace the network fetch with a counter, and clear the day's cache."""
    def fake(ticker: str) -> dict:
        calls.append(ticker)
        if delay:
            time.sleep(delay)
        return {
            "ok": True, "name": ticker, "sector": "Technology",
            "industry": "Software", "price": 100.0, "shares": 1e9,
            "income": pd.DataFrame({"a": [1.0]}),
            "balance": pd.DataFrame({"a": [1.0]}),
            "cashflow": pd.DataFrame({"a": [1.0]}),
        }
    monkeypatch.setattr(MD, "_company_uncached", fake)
    MD._COMPANY_CACHE.clear()
    MD._COMPANY_LOCKS.clear()


def test_mutating_a_fetched_company_cannot_poison_the_cache(monkeypatch):
    """`analyze` overwrites data["price"] for a manual override.

    While `fetch_company` returned the cached object itself, that assignment
    rewrote the day's cache: every later request for the symbol — including the
    quality lens, which never asked for an override — saw a price one user
    typed into the rescue form. The regression is asserted on the exact
    mutation `analyze` performs, not on a stand-in.
    """
    calls: list = []
    _stub_company(monkeypatch, calls)

    first = MD.company("TEST")
    first["price"] = 42.0                     # what analyze() does on manual_price

    second = MD.company("TEST")
    assert second["price"] == 100.0, "a caller's edit escaped into the shared cache"
    assert calls == ["TEST"], "the copy must not cost an extra upstream fetch"

    # The copy is deliberately SHALLOW: statements are read-only everywhere, so
    # they stay shared. Asserted so that boundary is a decision, not an accident.
    assert first is not second
    assert first["income"] is second["income"]


def test_concurrent_callers_for_one_symbol_fetch_it_once(monkeypatch):
    """/api/confluence runs the valuation and quality legs at the same instant.

    Both call `fetch_company` for the same symbol; without locking both saw an
    empty cache and both ran the full four-or-five-call fetch, doubling the
    heaviest leg's load on a rate-limited upstream. The delay is what makes the
    race deterministic — with an instant stub the first caller would finish
    before the second started and the bug would hide.
    """
    calls: list = []
    _stub_company(monkeypatch, calls, delay=0.2)

    results: list = []
    threads = [threading.Thread(target=lambda: results.append(MD.company("RACE")))
               for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == ["RACE"], f"one symbol, {len(calls)} upstream fetches"
    assert len(results) == 4
    assert all(r["price"] == 100.0 for r in results)
    # Every caller still owns its own dict, even the ones served from the cache.
    assert len({id(r) for r in results}) == 4


def test_distinct_symbols_are_not_serialised_by_the_lock(monkeypatch):
    """The lock is per key. A global one would make unrelated symbols queue.

    Four symbols at 0.2s each: concurrent finishes near 0.2s, serialised near
    0.8s. The 0.5s bound separates the two without being tight enough to flake.
    """
    calls: list = []
    _stub_company(monkeypatch, calls, delay=0.2)

    threads = [threading.Thread(target=MD.company, args=(f"SYM{i}",))
               for i in range(4)]
    started = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.monotonic() - started

    assert sorted(calls) == ["SYM0", "SYM1", "SYM2", "SYM3"]
    assert elapsed < 0.5, f"different symbols queued behind each other ({elapsed:.2f}s)"


class _FakeFastInfo:
    """yfinance's `FastInfo` semantics, reproduced exactly.

    `keys()` is camel case; `__getitem__` translates snake case; `get()` tests
    membership against `keys()` BEFORE translating, so it misses snake-case
    lookups and silently returns the default. Written from the real class's own
    source rather than from memory, because a fake that is merely dict-like
    would pass whatever the code does and prove nothing.
    """

    _CC: ClassVar[dict] = {"lastPrice": 309.35, "shares": 14_594_180_000,
                           "currency": "USD"}
    _SC_TO_CC: ClassVar[dict] = {"last_price": "lastPrice"}

    def keys(self):
        return list(self._CC)

    def __getitem__(self, key):
        return self._CC[self._SC_TO_CC.get(key, key)]

    def get(self, key, default=None):
        return self[key] if key in self.keys() else default


def test_fake_fast_info_reproduces_the_real_get_semantics():
    """Guards the fake itself: if this stops matching yfinance, the test below
    is measuring nothing."""
    fi = _FakeFastInfo()
    assert fi.get("last_price") is None      # the trap
    assert fi["last_price"] == 309.35        # the way through
    assert fi.get("shares") == 14_594_180_000   # unaffected: same spelling


def test_price_comes_from_fast_info_not_the_info_scrape(monkeypatch):
    """`fi.get("last_price")` returned None on every valuation.

    The engine then always fell through to `info["currentPrice"]`, so the
    primary source was dead code. `info` here deliberately carries NO quote
    field: with the bug, price is NaN and the caller is pushed to the manual
    rescue form for a figure fast_info was holding all along.
    """
    class FakeTicker:
        def __init__(self, symbol):
            self.fast_info = _FakeFastInfo()
            self.info = {"longName": "Test", "sector": "Technology",
                         "industry": "Software"}      # no currentPrice
            self.dividends = None

        def __getattr__(self, name):
            return pd.DataFrame()

    monkeypatch.setattr(MD.yf, "Ticker", FakeTicker)
    data = MD._company_uncached("TEST")

    assert data["price"] == pytest.approx(309.35), "price did not come from fast_info"
    assert data["shares"] == pytest.approx(14_594_180_000)
    assert data["currency"] == "USD"


def test_info_still_backfills_when_fast_info_has_no_price(monkeypatch):
    """The fallback stays. fast_info is the primary source, not the only one."""
    class Empty(_FakeFastInfo):
        _CC: ClassVar[dict] = {}
        def __getitem__(self, key):
            raise KeyError(key)

    class FakeTicker:
        def __init__(self, symbol):
            self.fast_info = Empty()
            self.info = {"currentPrice": 12.5, "sharesOutstanding": 1e6}
            self.dividends = None

        def __getattr__(self, name):
            return pd.DataFrame()

    monkeypatch.setattr(MD.yf, "Ticker", FakeTicker)
    data = MD._company_uncached("TEST")

    assert data["price"] == pytest.approx(12.5)
    assert data["shares"] == pytest.approx(1e6)


def test_the_daily_bar_close_beats_the_quote_endpoint(monkeypatch):
    """Yahoo's quote and chart endpoints do not always agree.

    Observed on a live AAPL request: the quote said 308.37 while the chart's
    last bar said 309.35, at rest, in the same request. Flow and Trend read the
    chart, so the valuation reading the quote put a price on the rail that no
    other panel displayed. The bar close is canonical; the planted gap here is
    the one that was actually measured.
    """
    # A FULL bar, because the price now arrives through the shared OHLCV
    # contract and that contract rejects a Close-only frame. The stricter
    # requirement is the point of routing every fetch through one place.
    bars = pd.DataFrame(
        {"Open": [310.0, 310.5], "High": [312.0, 311.0], "Low": [309.0, 308.0],
         "Close": [311.30, 309.35], "Volume": [1e6, 1.1e6]},
        index=pd.to_datetime(["2026-08-20", "2026-08-21"]),
    )

    class FakeTicker:
        def __init__(self, symbol):
            self.fast_info = _FakeFastInfo()          # lastPrice = 308.37 below
            self.fast_info._CC = dict(_FakeFastInfo._CC, lastPrice=308.37)
            self.info = {"currentPrice": 308.37}
            self.dividends = None

        def history(self, period, auto_adjust=True):
            return bars

        def __getattr__(self, name):
            return pd.DataFrame()

    monkeypatch.setattr(MD.yf, "Ticker", FakeTicker)
    data = MD._company_uncached("TEST")

    assert data["price"] == pytest.approx(309.35), "the quote endpoint won"
    assert data["price_source"] == "last daily close"
    assert data["price_as_of"] == "2026-08-21"


def test_the_quote_endpoint_still_backfills_when_there_are_no_bars(monkeypatch):
    """History is preferred, not required. A listing with no usable bars must
    still value rather than fall to the manual-rescue form."""
    class FakeTicker:
        def __init__(self, symbol):
            self.fast_info = _FakeFastInfo()
            self.info = {}
            self.dividends = None

        def history(self, period, auto_adjust=True):
            return pd.DataFrame()

        def __getattr__(self, name):
            return pd.DataFrame()

    monkeypatch.setattr(MD.yf, "Ticker", FakeTicker)
    data = MD._company_uncached("TEST")

    assert data["price"] == pytest.approx(309.35)     # from fast_info
    assert data["price_source"] == "quote endpoint (fast_info)"
    assert data["price_as_of"] is None


def test_batch_download_returns_one_frame_per_symbol(monkeypatch):
    frames = {"AAA": path(steady(n=300)), "BBB": path(steady(n=300, seed=9))}
    stub = _Stub(frames)
    monkeypatch.setattr(MD.yf, "download", stub)

    out = MD.ohlcv_batch(["AAA", "BBB"], dt.date(2023, 1, 1), dt.date(2024, 1, 1))
    assert set(out) == {"AAA", "BBB"}
    assert not out["AAA"].empty


def test_a_single_symbol_chunk_survives_the_multiindex_shape(monkeypatch):
    """The defect this file was written to catch.

    `group_by="ticker"` returns a TWO-LEVEL column index even for one symbol.
    The original code branched on `len(chunk) == 1` and handed the MultiIndex
    frame to the flat-column normaliser, which failed its check and dropped the
    symbol without a word — losing the benchmark index on every single scan.
    """
    stub = _Stub({"^GSPC": path(steady(n=300))})
    monkeypatch.setattr(MD.yf, "download", stub)

    out = MD.ohlcv_batch(["^GSPC"], dt.date(2023, 1, 1), dt.date(2024, 1, 1))
    assert "^GSPC" in out, "a one-symbol batch must not be silently dropped"
    assert len(out["^GSPC"]) > 200


def test_a_flat_single_symbol_response_still_works(monkeypatch):
    """The other shape, in case yfinance changes its mind again."""
    stub = _Stub({"AAA": path(steady(n=300))}, multiindex=False)
    monkeypatch.setattr(MD.yf, "download", stub)
    out = MD.ohlcv_batch(["AAA"], dt.date(2023, 1, 1), dt.date(2024, 1, 1))
    assert "AAA" in out


def test_the_universe_is_split_into_chunks(monkeypatch):
    frames = {f"S{i:03d}": path(steady(n=300, seed=i)) for i in range(120)}
    stub = _Stub(frames)
    monkeypatch.setattr(MD.yf, "download", stub)

    out = MD.ohlcv_batch(sorted(frames), dt.date(2023, 1, 1), dt.date(2024, 1, 1),
                           chunk_size=50)
    assert len(out) == 120
    assert [len(c) for c in stub.calls] == [50, 50, 20]


def test_the_last_chunk_of_a_51_symbol_universe_is_not_lost(monkeypatch):
    """The regression the single-symbol bug would also have caused.

    51 symbols at a chunk size of 50 leaves a final chunk of exactly one, which
    is the case that used to vanish.
    """
    frames = {f"S{i:03d}": path(steady(n=300, seed=i)) for i in range(51)}
    stub = _Stub(frames)
    monkeypatch.setattr(MD.yf, "download", stub)
    out = MD.ohlcv_batch(sorted(frames), dt.date(2023, 1, 1), dt.date(2024, 1, 1),
                           chunk_size=50)
    assert len(out) == 51


def test_a_failing_chunk_does_not_abort_the_whole_scan(monkeypatch):
    frames = {"AAA": path(steady(n=300)), "BBB": path(steady(n=300, seed=2))}

    def flaky(chunk, **kwargs):
        symbols = list(chunk) if isinstance(chunk, (list, tuple)) else [chunk]
        if "AAA" in symbols:
            raise RuntimeError("upstream is having a day")
        return pd.concat({s: frames[s] for s in symbols if s in frames}, axis=1)

    monkeypatch.setattr(MD.yf, "download", flaky)
    out = MD.ohlcv_batch(["AAA", "BBB"], dt.date(2023, 1, 1), dt.date(2024, 1, 1),
                           chunk_size=1)
    assert set(out) == {"BBB"}


def test_duplicate_symbols_are_requested_once(monkeypatch):
    stub = _Stub({"AAA": path(steady(n=300))})
    monkeypatch.setattr(MD.yf, "download", stub)
    MD.ohlcv_batch(["AAA", "aaa", "AAA"], dt.date(2023, 1, 1), dt.date(2024, 1, 1))
    assert stub.calls == [["AAA"]]




def test_scan_names_the_symbols_it_could_not_rank(monkeypatch):
    """A count is unactionable; a typo and a delisting look different."""
    frames = {"AAA": path(steady(n=400)), "BBB": path(steady(n=400, seed=2))}
    monkeypatch.setattr(MD.yf, "download", _Stub(frames))

    result = R.scan(["AAA", "BBB", "GHOST"], market_code="US")
    assert result["requested"] == 3
    assert result["ranked"] == 2
    assert result["missing"] == ["GHOST"]


# ============================================================================ #
# The common window — the bias that is invisible in the output
# ============================================================================ #

# ============================================================================ #
# The OHLCV contract
# ============================================================================ #
def _bar_frame(n=30):
    close = np.linspace(100.0, 110.0, n)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99,
         "Close": close, "Volume": np.full(n, 1e6)},
        index=pd.bdate_range("2024-01-02", periods=n),
    )


def test_normalise_accepts_every_column_shape_yfinance_returns():
    """yfinance nests columns TWO ways, and they are transposes of each other.

    `download(symbol)` returns (field, ticker); `download(list, group_by="ticker")`
    returns (ticker, field); `Ticker.history` returns them flat. Dropping a fixed
    level handles one and silently yields a frame of ticker-named columns for the
    other — which then fails the field check and drops the symbol without a word.

    That is not hypothetical: wiring this module in the first time broke every US
    ticker on the technical lens, and the stubbed tests did not catch it because
    they only ever produced one of the two shapes. Both are pinned here.
    """
    flat = _bar_frame()

    field_first = flat.copy()
    field_first.columns = pd.MultiIndex.from_product([flat.columns, ["AAPL"]])
    ticker_first = flat.copy()
    ticker_first.columns = pd.MultiIndex.from_product([["AAPL"], flat.columns])

    for name, frame in (("flat", flat), ("(field, ticker)", field_first),
                        ("(ticker, field)", ticker_first)):
        out = MD.normalise(frame)
        assert out is not None, f"{name} was rejected"
        assert list(out.columns) == list(MD.OHLCV), f"{name} produced {list(out.columns)}"
        assert len(out) == len(flat), name


def test_normalise_enforces_the_contract_every_engine_relies_on():
    frame = _bar_frame()
    frame.index = frame.index.tz_localize("America/New_York")
    frame = pd.concat([frame, frame.iloc[[-1]]])          # a repeated session
    frame.iloc[3, frame.columns.get_loc("Close")] = np.nan
    frame.iloc[5, frame.columns.get_loc("Volume")] = np.nan

    out = MD.normalise(frame)
    assert out.index.tz is None, "a tz-aware index compares unequal against a naive one"
    assert not out.index.duplicated().any(), "a repeated day double-counts in every window"
    assert out["Close"].notna().all(), "OHLC forward-fills"
    assert out["Volume"].iloc[5] == 0.0, "no trades IS zero volume"
    assert (out["Close"] > 0).all()
    assert out.index.is_monotonic_increasing


@pytest.mark.parametrize("frame", [
    None, pd.DataFrame(),
    pd.DataFrame({"Close": [1.0, 2.0]}),                  # no OHLC
    pd.DataFrame({"Open": [0.0], "High": [0.0], "Low": [0.0], "Close": [0.0]}),
])
def test_normalise_returns_none_rather_than_an_unusable_frame(frame):
    """One thing for callers to branch on."""
    assert MD.normalise(frame) is None


def test_last_close_does_not_demand_a_full_bar():
    """The risk-free rate wants one number from a yield series. Requiring four
    columns to obtain it would fail on a shape that is perfectly usable."""
    class FakeTicker:
        def __init__(self, symbol): pass
        def history(self, period, **_): return pd.DataFrame({"Close": [4.65, 4.73]})

    import unittest.mock as mock
    with mock.patch.object(MD, "yf") as fake:
        fake.Ticker = FakeTicker
        assert MD.last_close("^TNX") == pytest.approx(4.73)


def test_ok_means_the_symbol_resolved_to_something_real(monkeypatch):
    """`ok` used to be `bool(info) or isfinite(price)`.

    yfinance returns a non-empty `info` dict even for a symbol that does not
    exist, so that test was true whenever the scrape returned anything at all: a
    delisted ticker came back ok=True with a NaN price and three empty
    statements. The quality lens trusted the flag and told the reader "no
    financial statements came back for this listing" — which reads as "this
    company files nothing" rather than "this company was not found", and
    conflates a failed lookup with the DESIGNED refusal the lens gives banks.
    """
    class Ghost:
        """What a delisted symbol actually looks like: some info, nothing else."""
        def __init__(self, symbol):
            self.info = {"symbol": symbol, "quoteType": "NONE"}
            self.fast_info = _FakeFastInfo()
            self.fast_info._CC = {}
            self.dividends = None
        def history(self, *a, **k): return pd.DataFrame()
        def __getattr__(self, name): return pd.DataFrame()

    monkeypatch.setattr(MD, "yf", mock_module(Ghost))
    assert MD._company_uncached("ZZZZZZ")["ok"] is False

    class Real(Ghost):
        def __init__(self, symbol):
            super().__init__(symbol)
            self.info = {"symbol": symbol, "currentPrice": 100.0}

    monkeypatch.setattr(MD, "yf", mock_module(Real))
    assert MD._company_uncached("REAL")["ok"] is True, "a live price is enough"


def mock_module(ticker_cls):
    """A stand-in for the `yf` module exposing only what these paths touch."""
    class Module:
        Ticker = ticker_cls
        @staticmethod
        def download(*a, **k): return pd.DataFrame()
    return Module


# ============================================================================ #
# Currency: the accounts and the shares do not always agree
# ============================================================================ #
def _statement(values, index):
    return pd.DataFrame({"2025-12-31": values, "2024-12-31": values}, index=index)


def test_convert_scales_money_but_never_share_counts():
    """A share count multiplied by an exchange rate is meaningless.

    Every consumer happens to use counts only in ratios, where uniform scaling
    would cancel — but a statement whose share count has been multiplied by
    17,690 is wrong line by line even when the arithmetic downstream survives.
    """
    data = {
        "income": _statement([100.0, 50.0], ["Net Income", "Ordinary Shares Number"]),
        "balance": _statement([800.0, 12.0], ["Total Debt", "Share Issued"]),
        "cashflow": _statement([250.0], ["Free Cash Flow"]),
        "net_income_info": 100.0,
    }
    MD._convert_statements(data, 1_000.0)

    assert data["income"].loc["Net Income"].iloc[0] == 100_000.0
    assert data["income"].loc["Ordinary Shares Number"].iloc[0] == 50.0, "a count is not money"
    assert data["balance"].loc["Total Debt"].iloc[0] == 800_000.0
    assert data["balance"].loc["Share Issued"].iloc[0] == 12.0
    assert data["cashflow"].loc["Free Cash Flow"].iloc[0] == 250_000.0
    assert data["net_income_info"] == 100_000.0


def test_quality_scores_are_unchanged_by_the_conversion():
    """Piotroski, Altman and Beneish are built from ratios, so a uniform scaling
    must not move them. Asserted because the conversion runs at the boundary and
    the quality lens reads the same statements the valuation does."""
    from _lib import quality as Q

    index = ["Net Income", "Total Assets", "Total Debt", "Stockholders Equity",
             "Total Revenue", "Gross Profit", "Current Assets", "Current Liabilities",
             "Retained Earnings", "Operating Income"]
    raw = {"sector": "Energy", "industry": "Thermal Coal",
           "income": _statement([100.0, 900.0, 300.0, 500.0, 800.0, 300.0,
                                 400.0, 200.0, 250.0, 150.0], index),
           "balance": _statement([100.0, 900.0, 300.0, 500.0, 800.0, 300.0,
                                  400.0, 200.0, 250.0, 150.0], index),
           "cashflow": _statement([120.0] * 10, index),
           "net_income_info": 100.0}
    converted = {k: (v.copy() if isinstance(v, pd.DataFrame) else v) for k, v in raw.items()}
    MD._convert_statements(converted, 17_690.0)

    before, after = Q.analyze(raw), Q.analyze(converted)
    assert before["applicable"] == after["applicable"]
    assert (before.get("piotroski") or {}).get("score") == (after.get("piotroski") or {}).get("score")
    assert (before.get("altman") or {}).get("band") == (after.get("altman") or {}).get("band")
    assert (before.get("beneish") or {}).get("band") == (after.get("beneish") or {}).get("band")


@pytest.mark.parametrize(("base", "quote", "expected"), [
    ("USD", "USD", 1.0), ("idr", "IDR", 1.0), ("", "IDR", None), ("USD", "", None),
])
def test_fx_rate_handles_the_trivial_cases_without_a_fetch(base, quote, expected):
    assert MD.fx_rate(base, quote) == expected


def test_a_valuation_refuses_rather_than_mixing_currencies(monkeypatch):
    """Out by the exchange rate does not look like a rounding error — it looks
    like a confident answer, which is worse. Thirteen of the forty-six names in
    the IDX30 and LQ45 report in USD while trading in IDR."""
    from _lib import valuation as V

    company = {
        "ok": True, "price": 25_200.0, "shares": 1.1e9, "name": "Test",
        "sector": "Energy", "industry": "Thermal Coal",
        "currency": "IDR", "financial_currency": "USD", "fx_rate": None,
        "income": pd.DataFrame(), "balance": pd.DataFrame(),
        "cashflow": pd.DataFrame(), "dividend_history": pd.DataFrame(),
        "beta": 1.0, "market_cap": 2.8e13, "ttm_dividend": 1730.0,
        "dividend_rate": float("nan"), "trailing_dividend_rate": float("nan"),
        "dividend_yield_raw": float("nan"), "trailing_dividend_yield_raw": float("nan"),
        "payout_ratio": float("nan"), "roe_info": float("nan"),
        "net_income_info": float("nan"), "price_source": "x", "price_as_of": None,
    }
    monkeypatch.setattr(V, "fetch_company", lambda t: dict(company))

    with pytest.raises(V.ValuationError) as caught:
        V.analyze("TEST.JK", market_code="ID")
    detail = caught.value.as_detail()
    assert "USD" in detail["message"] and "IDR" in detail["message"]
    assert detail["manualRequired"] is True, "the rescue form is the way out"

    # With a rate present it must NOT refuse for this reason.
    with_rate = dict(company, fx_rate=17_690.0)
    monkeypatch.setattr(V, "fetch_company", lambda t: dict(with_rate))
    try:
        V.analyze("TEST.JK", market_code="ID")
    except V.ValuationError as exc:
        assert "exchange rate" not in exc.as_detail()["message"], exc.as_detail()["message"]
