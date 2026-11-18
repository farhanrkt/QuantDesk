"""A short history says why, when a longer range cannot fix it.

WHY THIS EXISTS

Three lenses answered a short price history with the same advice — "Widen the
date range", "Try a longer period", "Widen the chart range" — whatever had
made it short (docs/AUDIT.md, COR-5). On 14 November 2026 that sent two kinds
of reader looking for a control that cannot help:

  * Electronic Arts had not traded since 4 August 2026, and the provider sent
    one bar. The Trend lens said "too little history here … Widen the date
    range" and cast a neutral vote, so a delisted company counted as a lens
    that had read it.
  * SPRE.JK has traded for 569 sessions; the holding-period card told the
    reader to widen a five-year range that already held its whole life.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from _lib import explain, longterm, market_data, technical


def bars(start: str, end: str) -> pd.DataFrame:
    index = pd.bdate_range(start, end)
    close = 100.0 * np.exp(np.cumsum(np.random.default_rng(7).normal(0, 0.01, len(index))))
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                         "Close": close, "Volume": 1e6}, index=index)


TODAY = pd.Timestamp(dt.date.today())


def test_a_company_that_stopped_trading_is_named_with_its_last_date():
    frame = bars("2024-01-02", "2026-08-04")
    if TODAY - pd.Timestamp("2026-08-04") < pd.Timedelta(days=30):
        pytest.skip("the planted last trade is not yet stale on this date")
    sentence = market_data.why_short("EA", frame, dt.date(2021, 11, 1))
    assert "has not traded since 2026-08-04" in sentence
    assert "longer range will not" in sentence


def test_a_young_listing_is_named_with_its_first_date():
    first = (TODAY - pd.Timedelta(days=800)).date()
    frame = bars(str(first), str(TODAY.date()))
    sentence = market_data.why_short("SPRE.JK", frame, (TODAY - pd.Timedelta(days=1826)).date())
    assert sentence.startswith("SPRE.JK has only traded since")


def test_a_range_that_really_is_too_short_keeps_the_advice_to_widen():
    frame = bars(str((TODAY - pd.Timedelta(days=365)).date()), str(TODAY.date()))
    assert market_data.why_short("AAPL", frame, (TODAY - pd.Timedelta(days=366)).date()) is None
    rows = longterm.rolling_returns(frame["Close"], years=(5,))
    assert rows[0]["usable"] is False
    assert rows[0]["reason"].endswith("Widen the chart range.")
    assert rows[0]["widenable"] is True


def test_the_holding_table_passes_the_reason_on():
    frame = bars(str((TODAY - pd.Timedelta(days=800)).date()), str(TODAY.date()))
    because = "SPRE.JK has only traded since 2024-08-01, so a longer range will not add history."
    rows = longterm.rolling_returns(frame["Close"], years=(5,), short_because=because)
    assert rows[0]["reason"].endswith(because)
    assert "Widen" not in rows[0]["reason"]
    assert rows[0]["widenable"] is False


def test_the_sentence_is_in_the_readers_language():
    from _lib import lang
    first = (TODAY - pd.Timedelta(days=800)).date()
    token = lang.use("id")
    try:
        sentence = market_data.why_short("SPRE.JK", bars(str(first), str(TODAY.date())),
                                         (TODAY - pd.Timedelta(days=1826)).date())
    finally:
        lang.reset(token)
    assert sentence.startswith("SPRE.JK baru diperdagangkan sejak")


def test_too_little_history_to_read_a_trend_is_not_a_vote(monkeypatch):
    """One bar of a delisted name used to reach the synthesis as a neutral
    Trend reading. A lens that could not read does not vote."""
    one_bar = bars("2026-08-04", "2026-08-04")
    monkeypatch.setattr(technical, "fetch_data", lambda ticker, start, end: one_bar)
    monkeypatch.setattr(technical, "fetch_currency", lambda ticker: "USD")
    monkeypatch.setattr(market_data, "risk_free_rate", lambda code, fallback: (fallback, "test"))
    payload = technical.analyze("EA", range_key="5y", market_code="US")
    assert payload["summary"]["readable"] is False
    reading = explain._read_trend(payload)
    assert reading["tone"] == "none", "a Trend lens that could not read must not vote"
    synthesis = explain.for_synthesis({"technical": {"ok": True, "data": payload}},
                                      agreement_measurement=None)
    assert synthesis["agreement"]["lensesReading"] == 0
