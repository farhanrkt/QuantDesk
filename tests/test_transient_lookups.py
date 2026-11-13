"""A throttled moment is not a fact, and a dividend that stopped is not current.

WHY THIS EXISTS

Two lookups behind the published pages kept a throttled fetch as if it were the
answer: the share register, for the rest of the day in memory and for a WEEK on
disk in the scanner — where its emptiness turned off the free-float and
issuance gates — and the earnings calendar, until midnight, telling the company
tab there was no report coming. The company record had already been fixed for
exactly this in September (`_company_info_arrived`); these two had not.

And the trailing dividend was anchored on the last payment rather than on
today, so a dividend suspended in 2023 still read as "trailing 12m payments
(actual)" and was valued as current.
"""

from __future__ import annotations

import datetime as dt
import types

import numpy as np
import pandas as pd
import pytest

from _lib import market_data as MD


class YFRateLimitError(Exception):
    """Named like yfinance's own, which is all `_transient` reads of it."""


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setattr(MD, "FUNDAMENTALS_DIR", tmp_path)
    monkeypatch.setenv("QUANTDESK_FUNDAMENTALS_TTL_DAYS", "7")
    for store in (MD._REGISTER_CACHE, MD._REGISTER_EXPIRES,
                  MD._EARNINGS_CACHE, MD._EARNINGS_EXPIRES):
        store.clear()
    yield
    for store in (MD._REGISTER_CACHE, MD._REGISTER_EXPIRES,
                  MD._EARNINGS_CACHE, MD._EARNINGS_EXPIRES):
        store.clear()


# --------------------------------------------------------------------------- #
# What counts as a throttle
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("exc", [YFRateLimitError("429"), ConnectionError("reset"),
                                 TimeoutError("slow"), OSError("refused")])
def test_a_refusal_a_later_request_could_fix_is_transient(exc):
    assert MD._transient(exc) is True


@pytest.mark.parametrize("exc", [KeyError("insidersPercentHeld"), TypeError("NoneType"),
                                 ValueError("no tables found")])
def test_a_lookup_that_ran_and_found_nothing_is_not(exc):
    assert MD._transient(exc) is False


# --------------------------------------------------------------------------- #
# The share register
# --------------------------------------------------------------------------- #
def _ticker_whose_holders_raise(exc):
    class Ticker:
        def __init__(self, symbol):
            pass

        @property
        def major_holders(self):
            raise exc

        def get_shares_full(self, start=None):
            return None

        recommendations = None
        earnings_dates = None
    return Ticker


def test_a_throttled_register_is_marked_and_a_quiet_one_is_not(monkeypatch):
    monkeypatch.setattr(MD, "yf", types.SimpleNamespace(
        Ticker=_ticker_whose_holders_raise(YFRateLimitError("429"))))
    assert MD._register_uncached("TEST")["_throttled"] is True
    monkeypatch.setattr(MD, "yf", types.SimpleNamespace(
        Ticker=_ticker_whose_holders_raise(KeyError("no holders"))))
    assert "_throttled" not in MD._register_uncached("TEST")


def test_a_throttled_register_is_never_written_to_disk_and_kept_for_minutes(monkeypatch):
    calls = []

    def fetch(ticker):
        calls.append(ticker)
        return {"ok": False, "symbol": ticker, "insidersPercentHeld": None, "_throttled": True}

    monkeypatch.setattr(MD, "_register_uncached", fetch)
    first = MD.share_register("TEST")
    assert "_throttled" not in first, "the marker never leaves the boundary"
    assert MD._fundamentals_load("register", "TEST") is None, "a throttle was stored for a week"
    MD.share_register("TEST")
    assert calls == ["TEST"], "inside its minutes the record is shared, not refetched"

    key = ("TEST", dt.date.today().isoformat())
    MD._REGISTER_EXPIRES[key] = 0.0                 # its minutes are up
    MD.share_register("TEST")
    assert calls == ["TEST", "TEST"]


def test_a_register_that_arrived_is_still_kept_for_the_week(monkeypatch):
    monkeypatch.setattr(MD, "_register_uncached",
                        lambda ticker: {"ok": True, "symbol": ticker, "insidersPercentHeld": 0.4})
    MD.share_register("TEST")
    assert MD._fundamentals_load("register", "TEST")["insidersPercentHeld"] == 0.4


# --------------------------------------------------------------------------- #
# The earnings calendar
# --------------------------------------------------------------------------- #
def _calendar_ticker(exc, calls):
    class Ticker:
        def __init__(self, symbol):
            pass

        @property
        def earnings_dates(self):
            calls.append(1)
            raise exc

        calendar = None
    return Ticker


def test_a_throttled_earnings_table_is_kept_for_minutes_not_the_day(monkeypatch):
    calls: list = []
    monkeypatch.setattr(MD, "yf", types.SimpleNamespace(
        Ticker=_calendar_ticker(ConnectionError("reset"), calls)))
    assert MD.earnings_calendar("TEST")["next"] is None
    MD.earnings_calendar("TEST")
    assert len(calls) == 1
    MD._EARNINGS_EXPIRES[("TEST", dt.date.today().isoformat())] = 0.0
    MD.earnings_calendar("TEST")
    assert len(calls) == 2, "a throttled calendar was kept past its minutes"


def test_an_earnings_table_that_is_simply_absent_is_kept_for_the_day(monkeypatch):
    calls: list = []
    monkeypatch.setattr(MD, "yf", types.SimpleNamespace(
        Ticker=_calendar_ticker(ValueError("no tables found"), calls)))
    MD.earnings_calendar("TEST")
    assert ("TEST", dt.date.today().isoformat()) not in MD._EARNINGS_EXPIRES
    MD.earnings_calendar("TEST")
    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# The trailing dividend
# --------------------------------------------------------------------------- #
def _company_with_dividends(monkeypatch, paid: pd.Series):
    class FastInfo:
        def __getitem__(self, key):
            return {"last_price": 50.0, "shares": 1e6, "currency": "USD"}[key]

    class Ticker:
        def __init__(self, symbol):
            self.fast_info = FastInfo()
            self.info = {"longName": "Test", "sector": "Financial Services",
                         "industry": "Banks - Regional"}
            self.dividends = paid

        def __getattr__(self, name):
            return pd.DataFrame()

    monkeypatch.setattr(MD.yf, "Ticker", Ticker)
    monkeypatch.setattr(MD, "ohlcv", lambda *a, **k: None)
    return MD._company_uncached("TEST")


def test_a_dividend_suspended_years_ago_is_not_a_trailing_dividend(monkeypatch):
    today = pd.Timestamp(dt.date.today())
    paid = pd.Series([0.5, 0.5, 0.5, 0.5], index=[today - pd.Timedelta(days=d)
                                                 for d in (1400, 1220, 1035, 850)])
    data = _company_with_dividends(monkeypatch, paid)
    assert np.isnan(data["ttm_dividend"])
    assert not data["dividend_history"].empty, "the history itself is still shown"


@pytest.mark.parametrize("year_earlier", [364, 365, 366])
def test_a_semi_annual_payer_counts_exactly_two_instalments(monkeypatch, year_earlier):
    """Anchored on the last payment, which is what makes a semi-annual payer
    count both instalments whatever month it is — and NOT the one a year
    before, which a 365-day window took whenever dates drifted by a day."""
    today = pd.Timestamp(dt.date.today())
    last = 240
    paid = pd.Series([0.40, 0.45, 0.50], index=[today - pd.Timedelta(days=d) for d in
                                                (last + year_earlier, last + 182, last)])
    data = _company_with_dividends(monkeypatch, paid)
    assert data["ttm_dividend"] == pytest.approx(0.95)


def test_a_quarterly_payer_counts_four(monkeypatch):
    today = pd.Timestamp(dt.date.today())
    paid = pd.Series([0.2] * 6, index=[today - pd.Timedelta(days=30 + 91 * n)
                                      for n in range(6)])
    assert _company_with_dividends(monkeypatch, paid)["ttm_dividend"] == pytest.approx(0.8)
