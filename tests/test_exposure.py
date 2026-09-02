"""Naming what a book has in common.

PLANTED GROUND TRUTH THROUGHOUT. Every test here builds returns whose driver is
known by construction — a factor the test itself created — and then asks the
module to find it. Nothing checks the answer against a second implementation of
the same arithmetic, which would only prove the formula was copied twice.

The cases that matter are the refusals. A panel that names a driver for a book
that has none is worse than no panel, because "your holdings are an energy bet"
is a sentence a reader will act on.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

from _lib import explain as E
from _lib import exposure

DAYS = 500
INDEX = pd.bdate_range("2024-01-01", periods=DAYS)


def _noise(seed: float, scale: float = 0.012) -> pd.Series:
    rng = np.random.default_rng(int(seed))
    return pd.Series(rng.normal(0.0, scale, DAYS), index=INDEX)


def _references(**series) -> pd.DataFrame:
    """A reference frame keyed by the symbols `exposure` actually looks for."""
    blank = pd.Series(0.0, index=INDEX)
    frame = {"^JKSE": blank, "^GSPC": blank, "GC=F": blank,
             "CL=F": blank, "HG=F": blank, "DX-Y.NYB": blank}
    frame.update(series)
    return pd.DataFrame(frame)


def _book(factor: pd.Series, beta: float = 0.8, names: int = 4,
          idiosyncratic: float = 0.010) -> pd.DataFrame:
    """`names` holdings that are all the same bet plus their own noise."""
    return pd.DataFrame({
        f"H{i}": beta * factor + _noise(1000 + i, idiosyncratic)
        for i in range(names)
    })


# --------------------------------------------------------------------------- #
# It finds a driver that is really there
# --------------------------------------------------------------------------- #
def test_a_book_built_on_one_factor_is_named_after_it():
    """Four holdings that are the same bet on a planted factor, and that factor
    is one of the reference series. Anything less than naming it is a failure of
    the pipeline rather than of the data."""
    energy = _noise(1, 0.020)
    result = exposure.analyse(_book(energy), _references(**{"CL=F": energy}), "ID")

    assert result["usable"]
    assert [m["key"] for m in result["matches"]] == ["oil"]
    assert result["matches"][0]["correlation"] > 0.8
    assert result["varianceShare"] > 0.5, "one factor, so the first component is large"


def test_the_local_market_is_removed_before_anything_is_named():
    """THE WHOLE DESIGN, AS A TEST. Holdings driven purely by their own index
    must report a high market share and name nothing — otherwise the panel fires
    on every portfolio ever entered, which is the `screendomain.py` failure of
    colouring a condition that holds for everybody."""
    market = _noise(2, 0.014)
    result = exposure.analyse(_book(market), _references(**{"^JKSE": market}), "ID")

    assert result["usable"]
    assert result["marketShare"] > 0.8, "the shared direction IS the index"
    assert result["matches"] == [], "and nothing else should be claimed"


def test_a_driver_hiding_under_the_market_is_still_found():
    """The harder half: holdings carrying BOTH the index and a separate factor.

    A book can be 40% market and still be an energy bet, and the residual is
    where that shows. Reported market share must not swallow the second driver.
    """
    market, energy = _noise(3, 0.014), _noise(4, 0.020)
    holdings = pd.DataFrame({
        f"H{i}": 0.7 * market + 0.7 * energy + _noise(2000 + i, 0.008)
        for i in range(4)
    })
    result = exposure.analyse(
        holdings, _references(**{"^JKSE": market, "CL=F": energy}), "ID")

    assert result["marketShare"] > 0.2, "the index is genuinely in there"
    assert [m["key"] for m in result["matches"]] == ["oil"], "and so is the driver"


# --------------------------------------------------------------------------- #
# It refuses when it should
# --------------------------------------------------------------------------- #
def test_unrelated_holdings_are_not_given_a_driver():
    """Four independent random walks share nothing. Naming a driver here is the
    false positive that would make the panel unusable."""
    holdings = pd.DataFrame({f"H{i}": _noise(3000 + i) for i in range(4)})
    result = exposure.analyse(holdings, _references(**{"CL=F": _noise(9)}), "ID")

    assert result["usable"]
    assert result["matches"] == []
    assert result["hasSharedDirection"] is False, "no common direction to speak of"


def test_two_references_that_cannot_be_told_apart_name_neither():
    """AMBIGUITY IS A REFUSAL, NOT A TIE-BREAK.

    Two references that are near-copies of the driver both clear the threshold,
    and picking the larger would present a precision the sample does not have.
    """
    driver = _noise(5, 0.020)
    references = _references(**{"CL=F": driver + _noise(6, 0.001),
                                "GC=F": driver + _noise(7, 0.001)})
    result = exposure.analyse(_book(driver), references, "ID")

    assert result["ambiguous"] is True
    assert result["matches"] == [], "neither is named"


def test_two_holdings_are_refused():
    """The first component of two names is their average wearing a longer name."""
    driver = _noise(8, 0.020)
    result = exposure.analyse(_book(driver, names=2), _references(), "ID")
    assert result["usable"] is False
    assert "3 holdings" in result["reason"]


def test_a_short_history_is_refused():
    """Ten weeks is an anecdote. The floor is stated in the refusal so a reader
    knows what would fix it."""
    short = pd.bdate_range("2024-01-01", periods=50)
    holdings = pd.DataFrame(
        {f"H{i}": pd.Series(np.zeros(50), index=short) for i in range(4)})
    result = exposure.analyse(holdings, pd.DataFrame(), "ID")
    assert result["usable"] is False
    assert f"{exposure.MIN_WEEKS} weeks" in result["reason"]


def test_references_with_no_data_are_reported_as_untested_not_as_absent_drivers():
    """`tested` carries every reference and says which ones could be read.

    Constraint 3: a driver that could not be checked must not read as a driver
    that was checked and found absent, and the panel needs the difference in the
    payload to say so.
    """
    driver = _noise(10, 0.020)
    references = pd.DataFrame({"CL=F": driver}, index=INDEX)   # the others missing
    result = exposure.analyse(_book(driver), references, "ID")

    by_key = {t["key"]: t for t in result["tested"]}
    assert by_key["oil"]["available"] is True
    assert by_key["gold"]["available"] is False
    assert "correlation" not in by_key["gold"]


# --------------------------------------------------------------------------- #
# Contracts the rest of the app depends on
# --------------------------------------------------------------------------- #
def test_weekly_aggregation_is_exact_not_approximate():
    """Log returns ADD, so a week is the sum of its days.

    Checked against prices rather than against a second resample: build a price
    path, take its Friday-to-Friday log return directly, and require the summed
    daily returns to match. Averaging instead of summing would pass a
    same-formula test and be wrong by a factor of five.
    """
    rng = np.random.default_rng(11)
    prices = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, DAYS))), index=INDEX)
    daily = np.log(prices / prices.shift(1)).to_frame("X")

    weekly = exposure.to_weekly(daily)
    fridays = prices.resample("W-FRI").last()
    direct = np.log(fridays / fridays.shift(1)).dropna()

    shared = weekly.index.intersection(direct.index)
    assert len(shared) > 50
    assert weekly.loc[shared, "X"].to_numpy() == pytest.approx(
        direct.loc[shared].to_numpy(), abs=1e-12)


def test_the_component_sign_is_fixed_so_it_cannot_flip_between_requests():
    """A principal component's sign is arbitrary. Left arbitrary it would flip as
    data arrived and turn every correlation downstream inside out, which reads as
    the driver reversing when nothing has changed."""
    driver = _noise(12, 0.020)
    for beta in (0.8, -0.8):
        direction = exposure.shared_direction(
            exposure.to_weekly(_book(driver, beta=beta)))
        assert sum(direction["loadings"].values()) > 0


def test_matches_come_back_in_declaration_order_not_strength_order():
    """`PRODUCT.md` constraint 1 forbids a strength ranking as squarely as it
    forbids a composite. Gold is declared before oil, so a book matching both
    must list gold first even when oil correlates more strongly."""
    driver = _noise(13, 0.020)
    # Gold is deliberately the WEAKER of the two — 0.58 against oil's 0.96 — and
    # far enough below it to clear the ambiguity guard, so this exercises the
    # ordering rather than skipping past it.
    references = _references(**{"GC=F": driver + _noise(14, 0.030),
                                "CL=F": driver + _noise(15, 0.001)})
    result = exposure.analyse(_book(driver), references, "ID")

    assert len(result["matches"]) == 2, "both must clear, or this proves nothing"
    keys = [m["key"] for m in result["matches"]]
    assert keys == ["gold", "oil"], "declaration order"
    assert abs(result["matches"][0]["correlation"]) < abs(
        result["matches"][1]["correlation"]), "and it is NOT strength order"


def test_reference_symbols_cover_every_series_the_analysis_reads():
    """The fetch list and the analysis must not drift apart: a reference the
    analysis looks for and the batch never requested is silently 'unavailable'
    forever, which is the quiet failure this module exists to avoid."""
    for market in ("US", "ID"):
        needed = set(exposure.reference_symbols(market))
        assert exposure.LOCAL_INDEX[market] in needed
        for reference in exposure.REFERENCES:
            if market in reference.markets:
                assert reference.symbol in needed


# --------------------------------------------------------------------------- #
# One name, and the gate the stability study put in front of it
# --------------------------------------------------------------------------- #
def _stability(**rho) -> dict:
    """A planted stability artifact: factor id -> measured rank correlation."""
    return {"measuredOn": "2026-08-31", "killAt": 0.25,
            "factors": {key: {"all": {"persistenceWhereLoaded": {
                "usable": True, "meanRankCorrelation": value,
                "tStat": 3.0, "transitions": 8}}}
                for key, value in rho.items()}}


def test_persistence_is_reported_as_context_and_never_as_a_gate():
    """IT USED TO BE A GATE, AND THE GATE WAS MEASURING A DIFFERENT QUANTITY.

    Factors were filtered by measured persistence and gold was refused at +0.21
    against a 0.25 line. That held while the panel showed the same thing the
    study measured — raw one-year betas. It now shows a five-year beta with the
    market removed, whose persistence cannot be measured from nine years of
    history at all, so the study is reported as what it is rather than used to
    admit or refuse anything.
    """
    context = exposure.persistence_context(_stability(oil=0.42, gold=0.21))
    assert context["measured"] is True
    assert "gold" in context["rawOneYear"], "reported, not filtered"
    assert exposure.persistence_context(None) == {"measured": False}
    assert not hasattr(exposure, "printable"), "the gate must not come back"


def test_the_reading_says_it_is_history_rather_than_a_forecast():
    """The claim shrank when the quantity changed, and the words have to follow.
    Without this the panel prints a five-year beta in the tone of a prediction
    nothing measured."""
    reading = E.explain("factorExposure", 0.62, label="copper",
                        r_squared=0.21, weeks=260)["reading"]
    assert "not a forecast" in reading
    assert "could not be measured" in reading


def _planted(monkeypatch, beta: float, noise_scale: float = 0.004) -> None:
    """A factor, an INDEPENDENT market, and a stock built on the factor.

    THE MARKET HAS TO BE ITS OWN SERIES. An earlier fixture returned the factor
    for anything starting with `^`, so the index and the factor were the same
    thing — and once the engine started removing the market from both sides, that
    removed the entire planted relationship. The fixture was asserting against a
    world where "the market" and "the exposure" are indistinguishable, which is
    exactly the confusion the market removal exists to resolve.
    """
    rng = np.random.default_rng(77)
    factor = rng.normal(0.0, 0.02, 1400)
    market = rng.normal(0.0, 0.011, 1400)
    own = beta * factor + rng.normal(0.0, noise_scale, 1400)
    index = pd.bdate_range("2020-01-01", periods=1400)

    # KEYED ON THE ACTUAL SYMBOL SET, not on a substring. Testing for "=" looked
    # like it caught every factor and misses DX-Y.NYB, which has no equals sign —
    # so the dollar series silently became the stock itself and read as a perfect
    # loading. The fixture was manufacturing the finding it was meant to refute.
    factor_symbols = {r.symbol for r in exposure.REFERENCES}

    def fake(symbol, **_):
        source = (market if symbol.startswith("^")
                  else factor if symbol in factor_symbols else own)
        close = 100.0 * np.exp(np.cumsum(source))
        return pd.DataFrame({"Open": close, "High": close, "Low": close,
                             "Close": close, "Volume": 1e6}, index=index)

    monkeypatch.setattr(exposure.market_data, "ohlcv", fake)
    exposure._SERIES_CACHE.clear()


def test_the_beta_recovers_a_planted_one(monkeypatch):
    """Planted ground truth: a stock built as 0.60x a factor plus small noise
    must come back at 0.60, against arithmetic the test did not borrow from the
    module."""
    _planted(monkeypatch, beta=0.60)
    result = exposure.for_symbol("TEST", "US")

    assert result["usable"]
    by_key = {row["key"]: row for row in result["factors"]}
    assert by_key["oil"]["beta"] == pytest.approx(0.60, abs=0.05)
    # R-squared derived rather than eyeballed: with the factor at sigma 0.020 and
    # the idiosyncratic term at 0.004, the share of variance the factor accounts
    # for is b^2 s_f^2 / (b^2 s_f^2 + s_e^2) = 0.0144 / 0.0160 = 0.90.
    expected = (0.60 ** 2 * 0.020 ** 2) / (0.60 ** 2 * 0.020 ** 2 + 0.004 ** 2)
    assert by_key["oil"]["rSquared"] == pytest.approx(expected, abs=0.05)
    assert by_key["oil"]["marketRemoved"] is True, (
        "the market comes out of both sides before anything is reported")


def test_a_name_with_no_material_loading_is_refused_by_name(monkeypatch):
    """CONSTRAINT 3 AGAIN. A factor that was tested and found absent must be
    reported as refused with its reason, not dropped — an empty section reads as
    'no exposure' and this one has to say which question was asked."""
    _planted(monkeypatch, beta=0.0, noise_scale=0.02)
    result = exposure.for_symbol("TEST", "US")

    assert result["factors"] == []
    reasons = {row["key"]: row["reason"] for row in result["refused"]}
    assert reasons["oil"] == "no material loading on this name"
    assert set(reasons) == {"gold", "oil", "copper", "dollar"}, (
        "every factor tested and found absent is named, none silently dropped")


def test_the_estimation_window_is_five_years_not_one():
    """52 weeks sounded principled — it matched the study's block length — and
    produced betas too noisy to report: at 52 observations a loading needs
    R-squared above 0.15 to clear |t| = 3, and almost nothing in the IDX30 does.
    Measured on the day this changed, the old settings passed ten of thirty names
    on energy including a poultry producer and a pharmaceutical company.
    """
    assert exposure.ESTIMATION_WEEKS == 260
    stamped = exposure.load_stability()
    assert exposure.ESTIMATION_WEEKS > stamped["blockWeeks"], (
        "and it is deliberately longer than what the study could measure")


def test_the_screen_shares_a_t_statistic_and_not_an_r_squared():
    """THE BUG THIS REPLACED, PINNED. An earlier version shared `MATERIAL_R2`
    between the panel and the study so the two "could not drift" — but they
    measure over different window lengths, and a fixed R-squared is a different
    evidential bar at each. 0.05 is |t| = 5.0 over the study's 469 observations
    and |t| = 1.6 over the panel's 52, so the panel screened at p = 0.11 and
    called the survivors findings.

    A t-statistic is what transfers between sample sizes. Each window converts it
    to its own R-squared, and those numbers are SUPPOSED to differ.
    """
    assert exposure.material_r2(52) == pytest.approx(0.153, abs=0.005)
    assert exposure.material_r2(469) == pytest.approx(0.019, abs=0.005)
    assert exposure.material_r2(52) > exposure.material_r2(469), (
        "a shorter window must demand a LARGER R-squared for the same evidence")

    source = (pathlib.Path(__file__).resolve().parents[1]
              / "scripts" / "measure_exposure_stability.py").read_text()
    assert "exposure.material_r2(BLOCK_WEEKS)" in source
    # The comment above it is allowed to NAME the old constant while explaining
    # why it went; what must not come back is an assignment from it.
    assert "= exposure.MATERIAL_R2" not in source, "the fixed-R2 share must not return"
    assert not hasattr(exposure, "MATERIAL_R2"), "and the constant itself is gone"


# --------------------------------------------------------------------------- #
# The cross-section
# --------------------------------------------------------------------------- #
def _scan_frames(monkeypatch, exposed: list, flat: list) -> None:
    """A universe where `exposed` are built on the oil factor and `flat` are not."""
    rng = np.random.default_rng(404)
    factor = rng.normal(0.0, 0.02, 400)
    index = pd.bdate_range("2024-01-01", periods=400)

    def frame(source):
        close = 100.0 * np.exp(np.cumsum(source))
        return pd.DataFrame({"Open": close, "High": close, "Low": close,
                             "Close": close, "Volume": 1e6}, index=index)

    frames = {"CL=F": frame(factor), "HG=F": frame(rng.normal(0, 0.02, 400)),
              "GC=F": frame(rng.normal(0, 0.02, 400)),
              "DX-Y.NYB": frame(rng.normal(0, 0.02, 400)),
              # An independent market, for the same reason `_planted` needs one.
              "^GSPC": frame(rng.normal(0, 0.011, 400)),
              "^JKSE": frame(rng.normal(0, 0.011, 400))}
    for name in exposed:
        frames[name] = frame(0.9 * factor + rng.normal(0, 0.005, 400))
    for name in flat:
        frames[name] = frame(rng.normal(0, 0.02, 400))
    monkeypatch.setattr(exposure.market_data, "ohlcv_batch", lambda *a, **k: frames)
    monkeypatch.setattr(exposure, "load_stability",
                        lambda *a, **k: _stability(oil=0.42, copper=0.43, dollar=0.34))


def test_the_scan_separates_the_exposed_from_the_rest(monkeypatch):
    """Planted ground truth across a universe: two names built on the factor,
    three built on nothing. The material flag has to split them."""
    exposed, flat = ["AAA", "BBB"], ["CCC", "DDD", "EEE"]
    _scan_frames(monkeypatch, exposed, flat)
    result = exposure.scan(exposed + flat, "US")

    assert result["usable"]
    material = {r["ticker"] for r in result["rows"]
                if r["loadings"]["oil"]["material"]}
    assert material == set(exposed)
    for row in result["rows"]:
        if row["ticker"] in exposed:
            assert row["loadings"]["oil"]["beta"] == pytest.approx(0.9, abs=0.08)


def test_names_below_the_floor_stay_in_the_result(monkeypatch):
    """THEY ARE THE CONTROL GROUP. A scan returning only the names that loaded
    would make every universe look uniformly exposed — the reader could not see
    that two of five is unusual because there would be no five."""
    exposed, flat = ["AAA", "BBB"], ["CCC", "DDD", "EEE"]
    _scan_frames(monkeypatch, exposed, flat)
    result = exposure.scan(exposed + flat, "US")

    assert {r["ticker"] for r in result["rows"]} == set(exposed + flat)
    assert result["scanned"] == 5
    quiet = [r for r in result["rows"] if not r["loadings"]["oil"]["material"]]
    assert len(quiet) == 3, "and they are marked, not dropped"


def test_every_factor_is_offered_now_that_none_is_gated(monkeypatch):
    """The persistence gate is gone, so a factor is present unless its DATA is.

    Gold used to be refused for failing a study that measured raw one-year betas
    — a different quantity from the five-year market-removed one shown here. Over
    five years with the market out, gold picks out exactly the two Indonesian
    gold miners, which is the result that made keeping it out indefensible.
    """
    _scan_frames(monkeypatch, ["AAA"], ["BBB", "CCC"])
    result = exposure.scan(["AAA", "BBB", "CCC"], "US")

    assert {f["key"] for f in result["factors"]} == {"gold", "oil", "copper", "dollar"}
    assert result["refused"] == []
    assert result["persistence"]["measured"] is True, "reported, not used to filter"


def test_a_name_with_no_history_is_reported_missing_not_dropped(monkeypatch):
    """A symbol that fetched nothing and a symbol that loaded on nothing are
    different facts, and only the second belongs on the chart."""
    _scan_frames(monkeypatch, ["AAA"], ["BBB"])
    result = exposure.scan(["AAA", "BBB", "GHOST"], "US")

    assert result["missing"] == ["GHOST"]
    assert "GHOST" not in {r["ticker"] for r in result["rows"]}
    assert result["requested"] == 3 and result["scanned"] == 2


def test_the_scan_and_the_single_name_read_share_one_material_screen(monkeypatch):
    """A name the scan calls material must be one `for_symbol` will print, or the
    tab and the Trend line would disagree about the same stock on the same day."""
    _scan_frames(monkeypatch, ["AAA"], ["BBB"])
    batch = exposure.market_data.ohlcv_batch([], None, None)
    monkeypatch.setattr(exposure.market_data, "ohlcv", lambda symbol, **k: batch[symbol])
    exposure._SERIES_CACHE.clear()
    scanned = exposure.scan(["AAA", "BBB"], "US")
    by_ticker = {r["ticker"]: r for r in scanned["rows"]}
    single = exposure.for_symbol("AAA", "US")

    assert by_ticker["AAA"]["loadings"]["oil"]["material"] is True
    assert "oil" in {row["key"] for row in single["factors"]}
    assert single["factors"][0]["beta"] == pytest.approx(
        by_ticker["AAA"]["loadings"]["oil"]["beta"], abs=1e-9)
