"""A statement that came back a line short is asked for once more.

WHY THIS EXISTS

The provider does not always send the same statements twice. In the November
2026 audit, two passes over 122 US companies minutes apart read six of them
differently, five by a single line. NVDA's balance sheet came back with 79
lines where the other pass and five later fetches had 80, and with that line
gone its Altman score went from "safe" to "cannot score" — for the rest of the
day, because the record is cached as it arrived (docs/AUDIT.md, REL-7).

Nothing can tell a line that is missing from one that was never filed, so the
repair is narrow: when a screen that applies to the company cannot be scored,
the statements are fetched once more and each keeps the fuller copy. These
tests plant a provider whose first answer is short and whose second is whole.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import index
from _lib import market_data as MD

YEARS = pd.to_datetime(["2025-12-31", "2024-12-31"])


def statement(rows: dict) -> pd.DataFrame:
    return pd.DataFrame({YEARS[0]: [v[0] for v in rows.values()],
                         YEARS[1]: [v[1] for v in rows.values()]}, index=list(rows))


INCOME = {"Total Revenue": (1200.0, 1000.0), "Cost Of Revenue": (600.0, 550.0),
          "Net Income": (150.0, 100.0), "EBIT": (200.0, 150.0),
          "Selling General And Administration": (200.0, 180.0)}
BALANCE = {"Total Assets": (2000.0, 1900.0), "Current Assets": (800.0, 700.0),
           "Current Liabilities": (400.0, 420.0), "Retained Earnings": (600.0, 500.0),
           "Total Liabilities Net Minority Interest": (900.0, 950.0),
           "Stockholders Equity": (1100.0, 950.0), "Long Term Debt": (300.0, 400.0),
           "Accounts Receivable": (180.0, 160.0), "Net PPE": (900.0, 880.0),
           "Ordinary Shares Number": (100.0, 100.0)}
CASHFLOW = {"Operating Cash Flow": (250.0, 180.0),
            "Depreciation And Amortization": (90.0, 85.0)}


def record(balance: dict) -> dict:
    return {"ok": True, "name": "Planted", "sector": "Technology", "industry": "Semiconductors",
            "price": 100.0, "shares": 1e9, "market_cap": 1e11, "currency": "USD",
            "financial_currency": "USD", "income": statement(INCOME),
            "balance": statement(balance), "cashflow": statement(CASHFLOW)}


SHORT = {k: v for k, v in BALANCE.items() if k != "Retained Earnings"}


@pytest.fixture
def provider(monkeypatch):
    """First fetch a line short, every later one whole; counts the fetches."""
    calls = []

    def fetch(ticker, convert=True):
        calls.append(ticker)
        return record(SHORT if len(calls) == 1 else BALANCE)

    monkeypatch.setattr(MD, "_company_uncached", fetch)
    monkeypatch.setattr(MD, "_apply_fx", lambda data: data)
    monkeypatch.setattr(MD, "_refresh_price", lambda data, ticker: data)
    MD._COMPANY_CACHE.clear()
    MD._COMPANY_EXPIRES.clear()
    MD._COMPANY_LOCKS.clear()
    index._RATE_HITS.clear()
    yield calls
    MD._COMPANY_CACHE.clear()
    MD._COMPANY_EXPIRES.clear()


def test_a_score_lost_to_a_missing_line_is_recovered(provider):
    body = TestClient(index.app).get("/api/quality", params={"ticker": "NVDA"}).json()
    assert body["altman"]["band"] != "unknown", body["altman"]["reading"]
    assert provider == ["NVDA", "NVDA"], "exactly one more fetch"


def test_the_fuller_copy_is_kept_for_the_rest_of_the_day(provider):
    TestClient(index.app).get("/api/quality", params={"ticker": "NVDA"})
    held = MD.company("NVDA")
    assert "Retained Earnings" in held["balance"].index
    assert held["statements_rechecked"] is True


def test_it_is_asked_again_at_most_once_a_day(provider, monkeypatch):
    """A company that genuinely files no such line must not cost a second
    fetch on every request."""
    monkeypatch.setattr(MD, "_company_uncached",
                        lambda ticker, convert=True: provider.append(ticker) or record(SHORT))
    client = TestClient(index.app)
    for _ in range(3):
        body = client.get("/api/quality", params={"ticker": "NVDA"}).json()
    assert body["altman"]["band"] == "unknown"
    assert len(provider) == 2


def test_a_shorter_answer_never_replaces_a_fuller_one(monkeypatch):
    MD._COMPANY_CACHE.clear()
    MD._COMPANY_LOCKS.clear()
    first = record(BALANCE)
    monkeypatch.setattr(MD, "_company_uncached", lambda ticker, convert=True: first)
    monkeypatch.setattr(MD, "_apply_fx", lambda data: data)
    MD.company("NVDA")
    monkeypatch.setattr(MD, "_company_uncached", lambda ticker, convert=True: record(SHORT))
    again = MD.company_again("NVDA")
    assert "Retained Earnings" in again["balance"].index
    MD._COMPANY_CACHE.clear()


def test_a_record_this_cache_did_not_fetch_is_never_refetched():
    """A planted company in a test, or any caller that did not go through
    `company`, gets None — never a network call."""
    MD._COMPANY_CACHE.clear()
    assert MD.company_again("NEVER-FETCHED") is None
