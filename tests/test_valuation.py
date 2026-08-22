"""The valuation core, checked against independent arithmetic.

`pv_of_growing_stream` is the single function every DCF and DDM number in the
product flows through. It is vectorised over the Monte Carlo draws, which makes
it fast and makes an off-by-one in the exponent invisible — so it is verified
here against a plain Python loop of the textbook formula rather than against
itself.
"""

from __future__ import annotations

import threading
import time
from typing import ClassVar

import numpy as np
import pandas as pd
import pytest

from _lib import valuation as V


def reference_pv(base, g, r, gt, years=V.PROJECTION_YEARS):
    """The textbook calculation, written the slow obvious way."""
    projected = [base * (1.0 + g) ** t for t in range(1, years + 1)]
    pv_explicit = sum(p / (1.0 + r) ** t for t, p in enumerate(projected, start=1))
    spread = max(r - gt, V.MIN_SPREAD)
    terminal = projected[-1] * (1.0 + gt) / spread
    return projected, pv_explicit, terminal / (1.0 + r) ** years, terminal


@pytest.mark.parametrize(
    ("base", "g", "r", "gt"),
    [
        (1_000.0, 0.10, 0.09, 0.025),
        (5.5, 0.05, 0.11, 0.025),
        (1e9, 0.00, 0.08, 0.00),
        (250.0, -0.05, 0.12, 0.01),
        (100.0, 0.10, 0.03, 0.025),   # gt within MIN_SPREAD of r -> spread floor
        (100.0, 0.10, 0.02, 0.05),    # gt ABOVE r -> spread floor, must stay finite
    ],
)
def test_pv_matches_closed_form(base, g, r, gt):
    projected, pv_explicit, pv_terminal, terminal = V.pv_of_growing_stream(
        base, np.array([g]), np.array([r]), np.array([gt])
    )
    exp_projected, exp_explicit, exp_pv_terminal, exp_terminal = reference_pv(base, g, r, gt)

    np.testing.assert_allclose(projected[0], exp_projected, rtol=1e-12)
    np.testing.assert_allclose(pv_explicit[0, 0], exp_explicit, rtol=1e-12)
    np.testing.assert_allclose(pv_terminal[0, 0], exp_pv_terminal, rtol=1e-12)
    np.testing.assert_allclose(terminal[0, 0], exp_terminal, rtol=1e-12)


def test_terminal_value_never_diverges():
    """The Gordon denominator is floored, so gt >= r cannot produce inf/negative."""
    rates = np.full(200, 0.05)
    terminals = np.linspace(-0.02, 0.20, 200)   # deliberately runs past r
    _, _, pv_terminal, terminal = V.pv_of_growing_stream(100.0, np.full(200, 0.05),
                                                         rates, terminals)
    assert np.isfinite(terminal).all()
    assert np.isfinite(pv_terminal).all()
    assert (terminal > 0).all()


def test_dcf_equity_bridge():
    """Implied price = (EV + cash - debt) / shares, exactly."""
    base, g, r, gt = 1_000_000.0, 0.08, 0.09, 0.02
    cash, debt, shares = 500_000.0, 200_000.0, 1_000.0

    _, pv_explicit, pv_terminal, _ = V.pv_of_growing_stream(
        base, np.array([g]), np.array([r]), np.array([gt])
    )
    expected = ((pv_explicit + pv_terminal) + cash - debt) / shares
    got = V.dcf_implied_price(base, np.array([g]), np.array([r]), np.array([gt]),
                              cash, debt, shares)
    np.testing.assert_allclose(got, expected.ravel(), rtol=1e-12)


def test_ddm_price_is_per_share_pv():
    """A DDM values the dividend stream directly — no cash/debt bridge."""
    got = V.ddm_implied_price(5.0, np.array([0.05]), np.array([0.10]), np.array([0.025]))
    _, pv_explicit, pv_terminal, _ = V.pv_of_growing_stream(
        5.0, np.array([0.05]), np.array([0.10]), np.array([0.025])
    )
    np.testing.assert_allclose(got, (pv_explicit + pv_terminal).ravel(), rtol=1e-12)


# --------------------------------------------------------------------------- #
# Monte Carlo
# --------------------------------------------------------------------------- #
def test_monte_carlo_is_reproducible():
    """The CSV route promises the JSON route's exact distribution for one query."""
    kwargs = dict(engine="DCF", base=1e9, growth=0.10, rate=0.09, terminal_growth=0.025,
                  n_sims=5_000, sd_growth=0.02, sd_rate=0.01, sd_terminal=0.005,
                  cash=0.0, debt=0.0, shares=1e6)
    first = V.run_monte_carlo(seed=42, **kwargs)
    second = V.run_monte_carlo(seed=42, **kwargs)
    third = V.run_monte_carlo(seed=43, **kwargs)

    np.testing.assert_array_equal(first["Implied Price"], second["Implied Price"])
    assert not np.array_equal(first["Implied Price"], third["Implied Price"])


@pytest.mark.parametrize("engine", ["DCF", "DDM"])
def test_monte_carlo_keeps_terminal_growth_below_the_discount_rate(engine):
    """Every single draw, not just the mean — one bad draw is an infinite price."""
    sims = V.run_monte_carlo(
        engine=engine, base=1e6, growth=0.10, rate=0.06, terminal_growth=0.05,
        n_sims=20_000, sd_growth=0.05, sd_rate=0.04, sd_terminal=0.03, seed=7,
        cash=0.0, debt=0.0, shares=1e3,
    )
    rate_column = "WACC" if engine == "DCF" else "Cost of Equity"
    spread = sims[rate_column] - sims["Terminal Growth"]
    assert (spread >= V.MIN_SPREAD - 1e-12).all()
    assert np.isfinite(sims["Implied Price"]).all()


# --------------------------------------------------------------------------- #
# Guard-rails transcribed from the original app
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("raw", "expected"), [(0.5, 0.5), (3.0, 2.5), (0.1, 0.4),
                                              (None, 1.0), (float("nan"), 1.0)])
def test_beta_is_clipped(raw, expected):
    assert V.clip_beta(raw) == pytest.approx(expected)


def test_wacc_is_clipped_and_weights_sum_to_one():
    parts = V.compute_wacc(beta=1.2, risk_free=0.042, erp=0.055, equity_value=1e9,
                           total_debt=5e8, interest_expense=2.5e7, tax_rate=0.21)
    assert 0.02 <= parts["wacc"] <= 0.40
    assert parts["weight_equity"] + parts["weight_debt"] == pytest.approx(1.0)
    assert 0.01 <= parts["cost_debt"] <= 0.25


def test_wacc_falls_back_to_cost_of_equity_without_capital_structure():
    parts = V.compute_wacc(beta=1.0, risk_free=0.04, erp=0.05, equity_value=0.0,
                           total_debt=0.0, interest_expense=float("nan"), tax_rate=0.21)
    assert parts["weight_equity"] == 1.0
    assert parts["wacc"] == pytest.approx(parts["cost_equity"])


def test_effective_tax_rate_is_clipped(monkeypatch):
    import pandas as pd
    income = pd.DataFrame(
        {"2025": [1_000.0, 10_000.0]},
        index=["Tax Provision", "Pretax Income"],
    )
    assert V.effective_tax_rate(income, 0.21) == pytest.approx(0.10)

    extreme = pd.DataFrame({"2025": [9_500.0, 10_000.0]},
                           index=["Tax Provision", "Pretax Income"])
    assert V.effective_tax_rate(extreme, 0.21) == pytest.approx(0.40)   # clipped


def test_risk_free_rate_is_cached_per_day(monkeypatch):
    """Q7: one ^TNX fetch per day, not one per valuation. Failures are not cached."""
    calls = {"n": 0}

    class FakeTicker:
        def __init__(self, symbol):
            calls["n"] += 1

        def history(self, period):
            import pandas as pd
            return pd.DataFrame({"Close": [4.65]})

    monkeypatch.setattr(V.yf, "Ticker", FakeTicker)
    V._RISK_FREE_CACHE.clear()

    for _ in range(5):
        rate, source = V.fetch_risk_free_rate("US", 0.042)
        assert rate == pytest.approx(0.0465)
        assert "live" in source
    assert calls["n"] == 1

    # A non-US market never touches the network at all.
    before = calls["n"]
    V.fetch_risk_free_rate("ID", 0.065)
    assert calls["n"] == before


def test_risk_free_failure_is_not_cached(monkeypatch):
    class Exploding:
        def __init__(self, symbol):
            raise RuntimeError("network down")

    monkeypatch.setattr(V.yf, "Ticker", Exploding)
    V._RISK_FREE_CACHE.clear()

    rate, source = V.fetch_risk_free_rate("US", 0.042)
    assert rate == pytest.approx(0.042)
    assert "fallback" in source
    assert not V._RISK_FREE_CACHE, "a failed fetch must not pin the fallback all day"


def test_detect_engine_routes_financials_to_ddm():
    assert V.detect_engine("Financial Services", "Banks—Diversified")[0] == "DDM"
    assert V.detect_engine("Technology", "Consumer Electronics")[0] == "DCF"
    assert V.detect_engine("", "Regional Banking")[0] == "DDM"


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
    monkeypatch.setattr(V, "_fetch_company_uncached", fake)
    V._COMPANY_CACHE.clear()
    V._COMPANY_LOCKS.clear()


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

    first = V.fetch_company("TEST")
    first["price"] = 42.0                     # what analyze() does on manual_price

    second = V.fetch_company("TEST")
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
    threads = [threading.Thread(target=lambda: results.append(V.fetch_company("RACE")))
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

    threads = [threading.Thread(target=V.fetch_company, args=(f"SYM{i}",))
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

    monkeypatch.setattr(V.yf, "Ticker", FakeTicker)
    data = V._fetch_company_uncached("TEST")

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

    monkeypatch.setattr(V.yf, "Ticker", FakeTicker)
    data = V._fetch_company_uncached("TEST")

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
    bars = pd.DataFrame(
        {"Close": [311.30, 309.35]},
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

    monkeypatch.setattr(V.yf, "Ticker", FakeTicker)
    data = V._fetch_company_uncached("TEST")

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

    monkeypatch.setattr(V.yf, "Ticker", FakeTicker)
    data = V._fetch_company_uncached("TEST")

    assert data["price"] == pytest.approx(309.35)     # from fast_info
    assert data["price_source"] == "quote endpoint (fast_info)"
    assert data["price_as_of"] is None
