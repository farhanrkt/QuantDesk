"""What moved the markets: the board, its calibration and its refusals.

Offline, on planted frames. What is under test is the arithmetic that turns a
price history into "larger than 97% of its days" and the rules that keep the
board honest: declared order, neutral tone, each instrument on its own calendar,
and a missing quote named rather than dropped.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from helpers import _Stub

from _lib import explain, exposure, news
from _lib import market_data as MD
from _lib import marketboard as B

END = pd.Timestamp("2026-10-30")          # a Friday


def frame(closes, index) -> pd.DataFrame:
    closes = np.asarray(closes, dtype="float64")
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                         "Volume": np.full(len(closes), 1000.0)}, index=index)


def weekdays(n: int, end: pd.Timestamp = END) -> pd.DatetimeIndex:
    return pd.bdate_range(end=end, periods=n)


def walk(n: int, sigma: float = 0.01, seed: int = 7, start: float = 100.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return start * np.exp(np.cumsum(rng.normal(0.0, sigma, n)))


def with_last_move(closes: np.ndarray, move: float) -> np.ndarray:
    out = closes.copy()
    out[-1] = out[-2] * (1.0 + move)
    return out


def instrument(key: str) -> B.Instrument:
    return next(i for i in B.INSTRUMENTS if i.key == key)


# --------------------------------------------------------------------------- #
# The shape of the board
# --------------------------------------------------------------------------- #
def test_rows_come_back_in_declared_order_whatever_moved_most():
    frames = {i.symbol: frame(with_last_move(walk(500, seed=n), 0.001 * n), weekdays(500))
              for n, i in enumerate(B.INSTRUMENTS, start=1)}
    board = B.build(frames)
    assert [row["key"] for row in board["rows"]] == [i.key for i in B.INSTRUMENTS]
    moves = [abs(row["move"]) for row in board["rows"]]
    assert moves != sorted(moves, reverse=True), "the planted moves must not already be sorted"


def test_every_row_is_tone_neutral_including_unusual_ones():
    frames = {i.symbol: frame(with_last_move(walk(500, sigma=0.005), -0.08), weekdays(500))
              for i in B.INSTRUMENTS}
    board = B.build(frames)
    assert all(row["tone"] == "neutral" for row in board["rows"])
    assert any(row["unusual"] for row in board["rows"])
    readings = explain.for_market_board(board)["rows"].values()
    assert all(r["percentile"]["tone"] == "neutral" for r in readings if r["percentile"])


def test_the_exposure_references_are_read_from_exposure_not_retyped():
    """The stock page marks "moves with" by key; a symbol typed twice will differ one day."""
    by_key = {i.key: i for i in B.INSTRUMENTS}
    for reference in exposure.REFERENCES:
        assert by_key[reference.key].symbol == reference.symbol
        assert by_key[reference.key].exposure_key == reference.key


def test_each_strip_holds_at_most_eight_of_its_own_markets_rows():
    for code in B.MARKETS:
        strip = [i for i in B.INSTRUMENTS if code in i.strip]
        assert 1 <= len(strip) <= 8
        assert all(code in i.markets for i in strip)


def test_every_topic_has_a_declared_headline_feed():
    assert {i.topic for i in B.INSTRUMENTS} <= set(news.HEADLINE_TOPICS)


def test_what_the_source_cannot_supply_is_named_with_a_reason():
    board = B.build({})
    names = {item["key"] for item in board["missing"]}
    assert {"coal", "nickel", "palmoil", "idgb10"} <= names
    assert all(item["reason"] for item in board["missing"])


# --------------------------------------------------------------------------- #
# Units
# --------------------------------------------------------------------------- #
def test_a_yield_moves_in_basis_points_not_percent_of_itself():
    closes = np.r_[np.full(300, 4.80), 4.93]
    row, _ = B.read(instrument("t10y"), frame(closes, weekdays(301)))
    assert row["move"] == pytest.approx(13.0)
    assert explain.board_move_text(row) == "+13 bp"


def test_the_vix_moves_in_points():
    closes = np.r_[np.full(300, 17.2), 19.42]
    row, _ = B.read(instrument("vix"), frame(closes, weekdays(301)))
    assert row["move"] == pytest.approx(2.22)
    assert explain.board_move_text(row) == "+2.22 points"


def test_a_price_moves_in_percent_with_two_decimals():
    closes = np.r_[np.full(300, 515.28), 515.17]
    row, _ = B.read(instrument("lq45"), frame(closes, weekdays(301)))
    assert explain.board_move_text(row) == "-0.02%", "a broad index's hundredths are not -0.0%"


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #
def test_the_percentile_is_against_its_own_past_year_and_strictly_smaller():
    # A yield stepping between two levels moves by the same amount every day, so
    # the latest move ties the whole year: larger than none of it, not all of it.
    # (A percentage walk cannot plant a tie: up 1% and down 1% are not equal moves.)
    closes = np.r_[np.tile([4.80, 4.81], 150), 4.80, 4.81]
    row, _ = B.read(instrument("t10y"), frame(closes, weekdays(len(closes))))
    assert row["percentile"] == pytest.approx(0.0)
    assert row["unusual"] is False


def test_a_large_move_is_unusual_and_says_how_long_since_a_larger_one():
    closes = walk(500, sigma=0.008, seed=11)
    closes[300:] = closes[300:] * (0.93 * closes[299] / closes[300])   # an earlier, larger fall
    closes = with_last_move(closes, -0.05)
    row, _ = B.read(instrument("sp500"), frame(closes, weekdays(500)))
    assert row["unusual"] is True and row["percentile"] >= 95
    assert row["largestSince"] == weekdays(500)[300].date().isoformat()
    assert "its largest fall since" in explain.for_market_board(
        {"rows": [row], "markets": {}})["rows"]["sp500"]["reading"]


def test_the_largest_move_in_the_history_fetched_says_so():
    row, _ = B.read(instrument("gold"),
                    frame(with_last_move(walk(500, sigma=0.005), 0.09), weekdays(500)))
    assert row["largestSince"] is None and row["largestInHistory"] is True


def test_too_little_history_is_a_refusal_not_a_guess():
    row, _ = B.read(instrument("gold"),
                    frame(with_last_move(walk(60, sigma=0.005), 0.09), weekdays(60)))
    assert row["available"] is True
    assert row["percentile"] is None and row["unusual"] is None
    reading = explain.for_market_board({"rows": [row], "markets": {}})["rows"]["gold"]["reading"]
    assert "Too little history" in reading


def test_a_missing_quote_is_named_not_dropped():
    board = B.build({})
    assert len(board["rows"]) == len(B.INSTRUMENTS)
    assert all(row["available"] is False and row["reason"] for row in board["rows"])
    summary = explain.for_market_board(board)["markets"]["US"]["summary"]
    assert "left blank" in summary


# --------------------------------------------------------------------------- #
# Calendars
# --------------------------------------------------------------------------- #
def test_a_weekend_print_on_a_weekday_instrument_is_dropped():
    """USDIDR=X carried one flat Saturday bar on 31 October 2026 and read as +0.27%."""
    index = weekdays(300).append(pd.DatetimeIndex([END + pd.Timedelta(days=1)]))
    closes = np.r_[np.full(299, 18065.4), 18070.4, 18120.0]
    row, _ = B.read(instrument("usdidr"), frame(closes, index))
    assert row["asOf"] == END.date().isoformat()
    assert row["move"] == pytest.approx(18070.4 / 18065.4 - 1)


def test_bitcoin_keeps_its_weekends_and_its_year_is_365_sessions():
    index = pd.date_range(end=END + pd.Timedelta(days=1), periods=730, freq="D")
    row, history = B.read(instrument("bitcoin"),
                          frame(walk(730, sigma=0.03, seed=5), index))
    assert row["asOf"] == (END + pd.Timedelta(days=1)).date().isoformat()
    assert row["yearSessions"] == 364
    assert (history.index.dayofweek >= 5).any()


def test_the_base_rate_counts_weekdays_only():
    """Bitcoin's weekends once added 104 days only one instrument could flag."""
    daily = pd.date_range(end=END, periods=400, freq="D")
    rng = np.random.default_rng(3)
    histories = {
        "stocks": pd.Series(rng.normal(0, 0.01, 300), index=weekdays(300)),
        "coin": pd.Series(rng.normal(0, 0.03, 400), index=daily),
    }
    rate = B.base_rate(histories)
    assert rate is not None and rate["instruments"] == 2
    assert rate["days"] == len(pd.bdate_range(END - pd.Timedelta(days=B.YEAR_DAYS - 1), END))
    assert 0.05 <= rate["share"] <= 0.12, "two instruments at a 5% line each"


# --------------------------------------------------------------------------- #
# The summary
# --------------------------------------------------------------------------- #
def test_the_summary_names_only_unusual_moves_in_declared_order():
    frames = {i.symbol: frame(walk(500, sigma=0.01, seed=n), weekdays(500))
              for n, i in enumerate(B.INSTRUMENTS)}
    for key in ("gold", "sp500"):                  # planted out of declared order
        symbol = instrument(key).symbol
        frames[symbol] = frame(with_last_move(walk(500, sigma=0.004, seed=99), -0.06),
                               weekdays(500))
    board = B.build(frames)
    summary = explain.for_market_board(board)["markets"]["US"]["summary"]
    named = [row["name"] for row in board["rows"] if row["name"] in summary]
    assert "S&P 500" in named and "Gold" in named
    assert summary.index("S&P 500") < summary.index("Gold"), "declared order, not move order"
    by_key = {row["key"]: row for row in board["rows"]}
    assert all(by_key[key]["unusual"] for key in board["markets"]["US"]["unusual"])


def test_a_quiet_day_says_nothing_moved_unusually():
    frames = {i.symbol: frame(with_last_move(walk(500, sigma=0.01, seed=n), 0.0001),
                              weekdays(500))
              for n, i in enumerate(B.INSTRUMENTS)}
    summary = explain.for_market_board(B.build(frames))["markets"]["ID"]["summary"]
    assert summary.startswith("Nothing here moved more than it ordinarily does")


# --------------------------------------------------------------------------- #
# The data layer: one batch, many calendars
# --------------------------------------------------------------------------- #
def test_own_sessions_stops_a_shared_calendar_inventing_weekend_bars(monkeypatch):
    """Measured 1 November 2026: the S&P 500 came back with 208 weekend 0.00% days."""
    stocks = frame(walk(300), weekdays(300))
    coin = frame(walk(420, sigma=0.03, seed=2), pd.date_range(end=END, periods=420, freq="D"))
    monkeypatch.setattr(MD.yf, "download", _Stub({"^GSPC": stocks, "BTC-USD": coin}))

    shared = MD.ohlcv_batch(["^GSPC", "BTC-USD"], dt.date(2025, 1, 1), END.date())
    own = MD.ohlcv_batch(["^GSPC", "BTC-USD"], dt.date(2025, 1, 1), END.date(),
                         own_sessions=True)

    assert (shared["^GSPC"].index.dayofweek >= 5).any(), "the default keeps the shared calendar"
    assert not (own["^GSPC"].index.dayofweek >= 5).any()
    assert len(own["^GSPC"]) == 300
    assert (own["BTC-USD"].index.dayofweek >= 5).any(), "a coin keeps its own weekends"


def test_the_board_is_held_for_minutes_and_a_failure_is_not(monkeypatch):
    """The edge misses per region; a warm instance must not refetch 22 series each time."""
    calls = {"n": 0}

    def batch(symbols, start, end, **kwargs):
        calls["n"] += 1
        assert kwargs.get("own_sessions") is True, "the board reads each symbol's own sessions"
        return {}

    monkeypatch.setattr(B.market_data, "ohlcv_batch", batch)
    monkeypatch.setattr(B, "_CACHE", {})
    B.fetch()
    B.fetch()
    assert calls["n"] == 2, "an empty board is never held"

    frames = {i.symbol: frame(walk(300, seed=n), weekdays(300))
              for n, i in enumerate(B.INSTRUMENTS)}

    def full_batch(symbols, start, end, **kwargs):
        calls["n"] += 1
        return frames

    monkeypatch.setattr(B.market_data, "ohlcv_batch", full_batch)
    first = B.fetch()
    first["rows"].clear()                      # a caller mutating its copy...
    second = B.fetch()
    assert calls["n"] == 3, "held, not refetched"
    assert len(second["rows"]) == len(B.INSTRUMENTS), "...cannot damage what is held"
