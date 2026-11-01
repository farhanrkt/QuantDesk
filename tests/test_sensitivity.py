"""The valuation sensitivity grid, against a closed form written here.

Every cell is checked against an independent scalar loop — the textbook sum of
discounted cash flows plus a Gordon terminal value — rather than against a
second call into the vectorised core, so a broadcasting mistake in the grid
cannot be agreed with by the code that made it.

WHAT THESE TESTS PROTECT

1. THE ASSUMED CELL IS THE BASE CASE. The grid and `baseCase.impliedPrice` are
   one calculation; two "centres" on one panel is a contradiction.
2. A CELL TOO CLOSE TO PERPETUAL GROWTH IS REFUSED. The core floors the spread
   silently, so a computed value there would not be the stated formula.
3. NOTHING HERE JUDGES THE PRICE. No aggregate keys, no tone, no "above", no
   counts — a grid of values coloured against price is a buy/sell heat map.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from _lib import valuation as V
from test_pretrade import AGGREGATE_KEYS
from test_residual_income import reference_ri
from test_synthesis import FORBIDDEN


def reference_dcf(base, g, r, gt, cash, debt, shares, years=V.PROJECTION_YEARS):
    """Value per share, by hand: explicit years, then Gordon on the last."""
    pv = 0.0
    flow = base
    for t in range(1, years + 1):
        flow = base * (1.0 + g) ** t
        pv += flow / (1.0 + r) ** t
    terminal = flow * (1.0 + gt) / (r - gt)
    return (pv + terminal / (1.0 + r) ** years + cash - debt) / shares


DCF = dict(engine="DCF", base=100.0, growth=0.10, rate=0.09, terminal_growth=0.025,
           cash=50.0, debt=200.0, shares=10.0, price=150.0)


def grid(**overrides):
    args = {**DCF, **overrides}
    return V.sensitivity_grid(args.pop("engine"), args.pop("base"), args.pop("growth"),
                              args.pop("rate"), args.pop("terminal_growth"), **args)


def test_every_valid_cell_matches_the_closed_form():
    out = grid()
    for i, g in enumerate(out["rowAxis"]["values"]):
        for j, r in enumerate(out["colAxis"]["values"]):
            cell = out["cells"][i][j]
            if cell["refused"]:
                continue
            expected = reference_dcf(100.0, g, r, 0.025, 50.0, 200.0, 10.0)
            assert cell["value"] == pytest.approx(expected, rel=1e-10), (g, r)


def test_the_assumed_cell_is_the_base_case():
    out = grid()
    i, j = out["assumed"]["row"], out["assumed"]["col"]
    _, summary = V.base_case_schedule("DCF", 100.0, 0.10, 0.09, 0.025,
                                      cash=50.0, debt=200.0, shares=10.0)
    assert out["rowAxis"]["values"][i] == 0.10
    assert out["colAxis"]["values"][j] == 0.09
    assert out["cells"][i][j]["value"] == pytest.approx(summary["implied_price"], rel=1e-12)


def test_a_cell_inside_the_spread_is_refused_never_clamped():
    # Terminal 2.5%, rates down to 7%: every column is >= 1.5 points clear. Push
    # terminal growth up to 6% and the 7% column is inside the spread.
    out = grid(terminal_growth=0.06, rate=0.09)
    cols = out["colAxis"]["values"]
    for i in range(len(out["rowAxis"]["values"])):
        for j, r in enumerate(cols):
            cell = out["cells"][i][j]
            inside = r - 0.06 < V.MIN_SPREAD - 1e-12
            assert (cell["refused"] == "spread") == inside, r
            if inside:
                assert cell["value"] is None and cell["label"] is None
    assert out["refusals"]["spread"]


def test_value_rises_with_growth_and_falls_with_the_discount_rate():
    out = grid()
    values = np.array([[c["value"] for c in row] for row in out["cells"]], dtype=float)
    assert np.all(np.diff(values, axis=0) > 0), "more growth is always worth more"
    assert np.all(np.diff(values, axis=1) < 0), "a higher discount rate is always worth less"


def test_the_implied_row_reproduces_the_price_at_each_rate():
    out = grid()
    for entry in out["impliedRow"]:
        if entry["impliedGrowth"] is None:
            continue
        value = reference_dcf(100.0, entry["impliedGrowth"], entry["rate"], 0.025, 50.0, 200.0, 10.0)
        assert value == pytest.approx(150.0, rel=1e-5)


def test_an_unreachable_price_says_so():
    out = grid(price=1e9)
    assert all(e["impliedGrowth"] is None and e["reason"] == "unreachable" for e in out["impliedRow"])


def test_axes_stay_inside_what_the_route_accepts():
    out = grid(growth=0.98, rate=0.012)
    assert max(out["rowAxis"]["values"]) <= V.SENS_GROWTH_BOUNDS[1]
    assert min(out["colAxis"]["values"]) >= V.SENS_RATE_BOUNDS[0]
    assert out["rowAxis"]["values"][out["assumed"]["row"]] == 0.98, "the assumption survives clipping"
    assert len(set(out["colAxis"]["values"])) == len(out["colAxis"]["values"]), "no duplicate columns"


def test_ddm_cells_match_the_closed_form_without_a_bridge():
    out = grid(engine="DDM", base=4.0, growth=0.05, rate=0.10, terminal_growth=0.03,
               cash=0.0, debt=0.0, shares=1.0, price=60.0)
    for i, g in enumerate(out["rowAxis"]["values"]):
        for j, r in enumerate(out["colAxis"]["values"]):
            cell = out["cells"][i][j]
            if not cell["refused"]:
                assert cell["value"] == pytest.approx(reference_dcf(4.0, g, r, 0.03, 0, 0, 1), rel=1e-10)
    assert out["colAxis"]["label"] == "Cost of equity"


def test_residual_income_grid_is_roe_by_cost_of_equity():
    out = V.sensitivity_grid("RI", 2500.0, 0.18, 0.11, 0.0, payout=0.4, price=9000.0)
    assert out["rowAxis"]["name"] == "roe"
    assert out["impliedRow"] is None and out["impliedRowReason"]
    lo, hi = V.RI_ROE_BOUNDS
    assert all(lo <= v <= hi for v in out["rowAxis"]["values"])
    for i, roe in enumerate(out["rowAxis"]["values"]):
        for j, r in enumerate(out["colAxis"]["values"]):
            assert out["cells"][i][j]["value"] == pytest.approx(
                reference_ri(2500.0, roe, r, 0.4), rel=1e-9)


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_nothing_in_the_block_judges_the_price():
    out = grid()
    keys = set(_keys(out))
    assert not keys & AGGREGATE_KEYS
    assert not keys & {"tone", "above", "below", "upside", "colour", "color", "band"}
    text = json.dumps(out).lower()
    for phrase in FORBIDDEN:
        assert phrase not in text
    assert "not a forecast" in out["reading"]


def _planted_analyze(monkeypatch, company):
    monkeypatch.setattr(V, "fetch_company", lambda ticker: company)
    monkeypatch.setattr(V, "fetch_risk_free_rate", lambda *a, **k: (0.042, "test"))
    monkeypatch.setattr(V.riskmodel, "estimate_beta_for_symbol",
                        lambda *a, **k: V.riskmodel.BetaEstimate(
                            raw=1.0, adjusted=1.0, stderr=0.1, r_squared=0.4,
                            observations=400, method="vasicek", index_symbol="^GSPC",
                            prior_weight=0.04))


def test_the_payload_grid_agrees_with_the_base_case(monkeypatch):
    """Wired in `analyze` from the inputs actually used — so the assumed cell and
    `baseCase.impliedPrice` agree in the payload a reader sees, refused cells
    included, and the price beside the grid is the one the panel quotes."""
    import pandas as pd

    years = [pd.Timestamp(f"{2025 - i}-12-31") for i in range(4)]
    company = {
        "ok": True, "name": "Planted", "sector": "Technology", "industry": "Software",
        "price": 40.0, "shares": 1_000.0, "beta": 1.0, "currency": "USD", "financial_currency": "USD",
        "market_cap": 40_000.0, "dividend_rate": np.nan, "trailing_dividend_rate": np.nan,
        "dividend_yield_raw": np.nan, "trailing_dividend_yield_raw": np.nan, "payout_ratio": np.nan,
        "roe_info": np.nan, "net_income_info": np.nan, "ttm_dividend": np.nan,
        "dividend_history": pd.DataFrame(), "price_source": "last daily close",
        "price_as_of": "2026-10-23", "fx_rate": None,
        "income": pd.DataFrame({y: {"Total Revenue": 900.0, "Net Income": 100.0} for y in years}),
        "cashflow": pd.DataFrame({y: {"Free Cash Flow": f, "Operating Cash Flow": f + 20}
                                  for y, f in zip(years, [120.0, 110.0, 100.0, 95.0], strict=True)}),
        "balance": pd.DataFrame({y: {"Cash And Cash Equivalents": 300.0, "Total Debt": 100.0,
                                     "Stockholders Equity": 800.0} for y in years}),
    }
    _planted_analyze(monkeypatch, company)
    payload = V.analyze("PLNT", market_code="US", engine_choice="dcf", n_sims=1000, seed=7)
    sens = payload["sensitivity"]
    i, j = sens["assumed"]["row"], sens["assumed"]["col"]
    assert payload["engine"] == "DCF"
    assert sens["cells"][i][j]["value"] == pytest.approx(payload["baseCase"]["impliedPrice"], rel=1e-12)
    assert sens["priceLabel"] == payload["priceLabel"]
    assert sens["terminalGrowth"] == payload["assumptions"]["terminalGrowth"]
    assert sens["colAxis"]["values"][j] == payload["discountRate"]
