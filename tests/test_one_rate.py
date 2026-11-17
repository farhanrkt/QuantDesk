"""Two lenses on one page use one risk-free rate.

WHY THIS EXISTS

The Value lens discounts from the live US ten-year yield, and the Trend lens
computed its Sortino ratio against a fixed 4.2% — under a comment saying the
two lenses agreed on what money costs, which stopped being true the day the
valuation engine went live. On 14 November 2026 the same page printed
"US 10Y 5.154 · Value tab's rate" in the markets band and "above a 4.2%
risk-free rate" on the Sortino tile (docs/AUDIT.md, COR-4).
"""

from __future__ import annotations

import pytest

from _lib import market_data, technical


@pytest.fixture
def planted(monkeypatch, ohlcv):
    """The Trend lens on two years of planted prices, with nothing fetched."""
    long = ohlcv.copy()
    monkeypatch.setattr(technical, "fetch_data", lambda ticker, start, end: long)
    monkeypatch.setattr(technical, "fetch_currency", lambda ticker: "USD")
    monkeypatch.setattr(market_data, "index_history", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(technical.exposure, "measure", lambda *a, **k: {"usable": False},
                        raising=False)


def test_the_sortino_uses_the_rate_the_value_lens_discounts_with(planted, monkeypatch):
    asked = []

    def live(market_code, fallback):
        asked.append(market_code)
        return 0.05154, "US 10Y Treasury (^TNX, live)"
    monkeypatch.setattr(market_data, "risk_free_rate", live)

    result = technical.analyze("AAPL", range_key="2y", market_code="US")
    risk = result["longTerm"]["risk"]
    assert risk["usable"], "two years of planted prices are enough for the risk block"
    assert risk["riskFree"] == pytest.approx(0.05154)
    assert asked == ["US"]


def test_the_idx_rate_is_the_stated_assumption(planted, monkeypatch):
    monkeypatch.setattr(market_data, "risk_free_rate",
                        lambda code, fallback: (fallback, "IndoGB 10Y proxy (static assumption)"))
    result = technical.analyze("BBCA.JK", range_key="2y", market_code="ID")
    assert result["longTerm"]["risk"]["riskFree"] == pytest.approx(0.065)
