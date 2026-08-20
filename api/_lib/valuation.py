"""
valuation.py
============
Engine 3 — INTRINSIC v2, extracted from the Streamlit app.

Every constant, clip, guard-rail and branch is transcribed unchanged:
MARKETS (Rf / ERP / tax / scale), ROW_ALIASES, the beta clip [0.4, 2.5], the
effective-tax clip [0.05, 0.40], the cost-of-debt clip [0.01, 0.25], the WACC
clip [0.02, 0.40], PROJECTION_YEARS = 5, MIN_SPREAD = 150bp, the Monte Carlo
draw ranges (DCF g in [-0.50, 1.00] / r in [0.02, 0.50]; DDM g in [-0.30, 0.50]
/ r in [0.03, 0.50]; gt in [-0.02, 0.06] then forced below r - MIN_SPREAD), and
the ±15% verdict bands.

What changed: `st.slider` / `st.number_input` / `st.checkbox` became function
arguments carrying the SAME default values the widgets had. Nothing else.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from . import symbols

# =============================================================================
# 1. MARKET CONVENTIONS
# =============================================================================

MARKETS = {
    "US": {
        "code": "US",
        "name": "US Market",
        "suffix": "",
        "symbol": "$",
        "risk_free_default": 0.042,
        "erp": 0.055,
        "tax_rate": 0.21,
        "example": "AAPL, JPM, NVDA",
        "scale": [(1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")],
    },
    "ID": {
        "code": "ID",
        "name": "Indonesian Market (IDX)",
        "suffix": ".JK",
        "symbol": "Rp",
        "risk_free_default": 0.065,
        "erp": 0.070,
        "tax_rate": 0.22,
        "example": "BBCA, TLKM, ASII",
        "scale": [(1e12, "T"), (1e9, "B"), (1e6, "M")],
    },
}


class ValuationError(Exception):
    """Raised when an engine cannot produce a defensible number.

    `manual_required` marks the subset of failures the user can actually fix by
    supplying figures themselves — a gap in Yahoo's filings rather than a
    business the model genuinely cannot value. `suggested` carries whatever the
    fetch DID return, so the client can prefill the manual form instead of
    presenting six empty boxes.
    """

    def __init__(self, message: str, manual_required: bool = False,
                 missing=(), suggested: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.manual_required = bool(manual_required)
        self.missing = list(missing)
        self.suggested = suggested or {}

    def as_detail(self) -> dict:
        return {
            "message": self.message,
            "manualRequired": self.manual_required,
            "missing": self.missing,
            "suggested": self.suggested,
        }


def fmt_big(value, market: dict) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    sign = "-" if value < 0 else ""
    gap = " " if market["code"] == "ID" else ""
    v = abs(float(value))
    for divisor, tag in market["scale"]:
        if v >= divisor:
            return f"{sign}{market['symbol']}{gap}{v / divisor:,.2f}{tag}"
    return f"{sign}{market['symbol']}{gap}{v:,.0f}"


def fmt_price(value, market: dict) -> str:
    if value is None or not np.isfinite(value):
        return "n/a"
    if market["code"] == "ID":
        return f"{market['symbol']} {value:,.0f}"
    return f"{market['symbol']}{value:,.2f}"


def fmt_dps(value, market: dict) -> str:
    """Dividends per share need more precision than prices — an IDX bank can
    pay Rp 172.50 per share, and rounding that to Rp 173 moves the valuation."""
    if value is None or not np.isfinite(value):
        return "n/a"
    if market["code"] == "ID":
        return f"{market['symbol']} {value:,.2f}"
    return f"{market['symbol']}{value:,.3f}"


# =============================================================================
# 2. DATA INGESTION
# =============================================================================

ROW_ALIASES = {
    "ocf": [
        "Operating Cash Flow",
        "Total Cash From Operating Activities",
        "Cash Flow From Continuing Operating Activities",
    ],
    "capex": [
        "Capital Expenditure", "Capital Expenditures",
        "Purchase Of PPE", "Net PPE Purchase And Sale",
    ],
    "fcf": ["Free Cash Flow"],
    "cash": [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Cash Equivalents At Carrying Value",
    ],
    "total_debt": ["Total Debt"],
    "long_term_debt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
    "short_term_debt": [
        "Current Debt", "Short Long Term Debt",
        "Current Debt And Capital Lease Obligation",
    ],
    "equity": [
        "Stockholders Equity", "Total Stockholder Equity",
        "Common Stock Equity", "Total Equity Gross Minority Interest",
    ],
    "revenue": ["Total Revenue", "Operating Revenue"],
    "net_income": ["Net Income Common Stockholders", "Net Income"],
    "pretax_income": ["Pretax Income", "Income Before Tax"],
    "tax_provision": ["Tax Provision", "Income Tax Expense"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "eps": ["Diluted EPS", "Basic EPS"],
}


def _get_row(df, key: str):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    lookup = {str(i).strip().lower(): i for i in df.index}
    for alias in ROW_ALIASES.get(key, []):
        hit = lookup.get(alias.strip().lower())
        if hit is not None:
            return df.loc[hit]
    for alias in ROW_ALIASES.get(key, []):
        for label_lc, original in lookup.items():
            if alias.strip().lower() in label_lc:
                return df.loc[original]
    return None


def _first_valid(series, default=np.nan):
    if series is None:
        return default
    s = pd.Series(series).dropna()
    return float(s.iloc[0]) if len(s) else default


def _safe_float(value, default=np.nan) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        return out if np.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _nullable(value):
    """float for the wire, or None when the figure is missing/non-finite."""
    out = _safe_float(value)
    return float(out) if np.isfinite(out) else None


# The 10Y yield moves once a day; this used to be refetched on EVERY valuation
# request, including all three legs of a confluence run. Keyed by date so it
# expires on its own, and only successful fetches are stored — caching a failure
# would pin the fallback for the rest of the day with no retry. Module scope
# survives warm serverless invocations and costs nothing when it does not.
_RISK_FREE_CACHE: dict[str, tuple[float, str]] = {}


def fetch_risk_free_rate(market_code: str, fallback: float):
    if market_code != "US":
        return fallback, "IndoGB 10Y proxy (static assumption)"

    today = dt.date.today().isoformat()
    cached = _RISK_FREE_CACHE.get(today)
    if cached is not None:
        return cached

    try:
        hist = yf.Ticker("^TNX").history(period="5d")
        if not hist.empty:
            close = hist["Close"].dropna()
            if len(close):
                result = (float(close.iloc[-1]) / 100.0, "US 10Y Treasury (^TNX, live)")
                _RISK_FREE_CACHE.clear()          # only ever hold the current day
                _RISK_FREE_CACHE[today] = result
                return result
    except Exception:
        pass
    return fallback, "US 10Y Treasury (fallback default)"


def fetch_company(ticker: str) -> dict:
    try:
        tk = yf.Ticker(ticker)
    except Exception:
        tk = None

    info = {}
    if tk is not None:
        try:
            info = tk.info or {}
        except Exception:
            info = {}

    price, shares, currency = np.nan, np.nan, None
    if tk is not None:
        try:
            fi = tk.fast_info
            price = _safe_float(fi.get("last_price"))
            shares = _safe_float(fi.get("shares"))
            currency = fi.get("currency")
        except Exception:
            pass

    if not np.isfinite(price):
        price = _safe_float(info.get("currentPrice"), _safe_float(info.get("regularMarketPrice")))
    if not np.isfinite(shares):
        shares = _safe_float(info.get("sharesOutstanding"))

    def _statement(attr):
        if tk is None:
            return pd.DataFrame()
        try:
            df = getattr(tk, attr)
            return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    ttm_dividend, div_history = np.nan, pd.DataFrame()
    if tk is not None:
        try:
            divs = tk.dividends
            if divs is not None and len(divs):
                divs = divs.copy()
                divs.index = pd.to_datetime(divs.index, utc=True).tz_localize(None)
                cutoff = divs.index.max() - pd.Timedelta(days=365)
                ttm_dividend = float(divs[divs.index > cutoff].sum())
                annual = divs.groupby(divs.index.year).sum().sort_index(ascending=False)
                div_history = pd.DataFrame(
                    {"Year": annual.index.astype(str), "Dividend / Share": annual.values}
                ).head(6)
        except Exception:
            pass

    return {
        "ok": bool(info) or np.isfinite(price),
        "name": info.get("longName") or info.get("shortName") or ticker,
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
        "price": price,
        "shares": shares,
        "beta": _safe_float(info.get("beta")),
        "currency": currency or info.get("currency") or "",
        "market_cap": _safe_float(info.get("marketCap")),
        "dividend_rate": _safe_float(info.get("dividendRate")),
        "trailing_dividend_rate": _safe_float(info.get("trailingAnnualDividendRate")),
        "dividend_yield_raw": _safe_float(info.get("dividendYield")),
        "trailing_dividend_yield_raw": _safe_float(info.get("trailingAnnualDividendYield")),
        "payout_ratio": _safe_float(info.get("payoutRatio")),
        "roe_info": _safe_float(info.get("returnOnEquity")),
        "net_income_info": _safe_float(info.get("netIncomeToCommon")),
        "ttm_dividend": ttm_dividend,
        "dividend_history": div_history,
        "income": _statement("income_stmt"),
        "balance": _statement("balance_sheet"),
        "cashflow": _statement("cashflow"),
    }


# =============================================================================
# 3. SECTOR ROUTING
# =============================================================================

def detect_engine(sector: str, industry: str):
    s = (sector or "").strip().lower()
    i = (industry or "").strip().lower()
    if s == "financial services" or "bank" in i:
        reason = "sector = Financial Services" if s == "financial services" else "industry mentions banking"
        return "DDM", reason
    return "DCF", "non-financial sector"


# =============================================================================
# 4. DERIVED FINANCIALS
# =============================================================================

def build_fcf_history(cashflow, years: int = 4) -> pd.DataFrame:
    if cashflow is None or not isinstance(cashflow, pd.DataFrame) or cashflow.empty:
        return pd.DataFrame()

    ocf = _get_row(cashflow, "ocf")
    capex = _get_row(cashflow, "capex")
    reported_fcf = _get_row(cashflow, "fcf")
    if ocf is None and reported_fcf is None:
        return pd.DataFrame()

    rows = []
    for col in list(cashflow.columns)[:years]:
        o = _safe_float(ocf.get(col)) if ocf is not None else np.nan
        c = _safe_float(capex.get(col)) if capex is not None else np.nan
        if np.isfinite(o) and np.isfinite(c):
            f = o - abs(c)
        elif reported_fcf is not None:
            f = _safe_float(reported_fcf.get(col))
        else:
            f = np.nan
        rows.append({
            "Fiscal Year": pd.Timestamp(col).strftime("%Y"),
            "Operating Cash Flow": o,
            "Capital Expenditure": -abs(c) if np.isfinite(c) else np.nan,
            "Free Cash Flow": f,
        })
    return pd.DataFrame(rows).dropna(subset=["Free Cash Flow"])


def extract_balance_items(balance):
    cash = _first_valid(_get_row(balance, "cash"), 0.0)
    total_debt = _first_valid(_get_row(balance, "total_debt"), np.nan)
    if not np.isfinite(total_debt):
        st_debt = _first_valid(_get_row(balance, "short_term_debt"), 0.0)
        lt_debt = _first_valid(_get_row(balance, "long_term_debt"), 0.0)
        total_debt = (st_debt or 0.0) + (lt_debt or 0.0)
    return float(cash or 0.0), float(total_debt or 0.0)


def effective_tax_rate(income, default: float) -> float:
    tax = _first_valid(_get_row(income, "tax_provision"))
    pretax = _first_valid(_get_row(income, "pretax_income"))
    if np.isfinite(tax) and np.isfinite(pretax) and pretax > 0:
        return float(np.clip(tax / pretax, 0.05, 0.40))
    return default


def clip_beta(beta) -> float:
    b = _safe_float(beta, 1.0)
    return float(np.clip(b if np.isfinite(b) else 1.0, 0.4, 2.5))


def cost_of_equity(beta: float, risk_free: float, erp: float) -> float:
    return float(risk_free + clip_beta(beta) * erp)


def compute_wacc(beta, risk_free, erp, equity_value, total_debt,
                 interest_expense, tax_rate) -> dict:
    ke = cost_of_equity(beta, risk_free, erp)

    if total_debt > 0 and np.isfinite(interest_expense) and interest_expense > 0:
        kd = float(np.clip(interest_expense / total_debt, 0.01, 0.25))
    else:
        kd = risk_free + 0.02

    e = max(equity_value, 0.0) if np.isfinite(equity_value) else 0.0
    d = max(total_debt, 0.0)
    v = e + d
    if v <= 0:
        wacc, we, wd = ke, 1.0, 0.0
    else:
        we, wd = e / v, d / v
        wacc = we * ke + wd * kd * (1 - tax_rate)

    return {
        "beta": clip_beta(beta), "cost_equity": ke, "cost_debt": kd,
        "weight_equity": we, "weight_debt": wd,
        "wacc": float(np.clip(wacc, 0.02, 0.40)),
    }


def normalize_yield(raw, price) -> float:
    v = _safe_float(raw)
    if not np.isfinite(v) or v <= 0:
        return np.nan
    return v / 100.0 if v > 1.0 else v


def resolve_dividend(data: dict, price: float):
    ttm = _safe_float(data.get("ttm_dividend"))
    if np.isfinite(ttm) and ttm > 0:
        return ttm, "trailing 12m payments (actual)"

    trailing = _safe_float(data.get("trailing_dividend_rate"))
    if np.isfinite(trailing) and trailing > 0:
        return trailing, "trailing annual rate (yfinance)"

    forward = _safe_float(data.get("dividend_rate"))
    if np.isfinite(forward) and forward > 0:
        return forward, "forward annual rate (yfinance)"

    for key in ("trailing_dividend_yield_raw", "dividend_yield_raw"):
        y = normalize_yield(data.get(key), price)
        if np.isfinite(y) and y > 0 and np.isfinite(price):
            return y * price, "derived from dividend yield"

    return np.nan, "unavailable"


def bank_diagnostics(data: dict, dps: float, price: float, shares: float) -> dict:
    net_income = _first_valid(_get_row(data["income"], "net_income"),
                              _safe_float(data.get("net_income_info")))
    equity = _first_valid(_get_row(data["balance"], "equity"), np.nan)

    roe = _safe_float(data.get("roe_info"))
    if not np.isfinite(roe) and np.isfinite(net_income) and np.isfinite(equity) and equity > 0:
        roe = net_income / equity

    payout = _safe_float(data.get("payout_ratio"))
    if (not np.isfinite(payout) or payout <= 0) and np.isfinite(net_income) and net_income > 0 \
            and np.isfinite(dps) and np.isfinite(shares) and shares > 0:
        payout = (dps * shares) / net_income

    payout_clean = float(np.clip(payout, 0.0, 1.0)) if np.isfinite(payout) else np.nan
    sustainable = roe * (1 - payout_clean) if np.isfinite(roe) and np.isfinite(payout_clean) else np.nan

    return {
        "net_income": net_income,
        "equity": equity,
        "roe": roe,
        "payout": payout,
        "payout_clean": payout_clean,
        "sustainable_growth": sustainable,
        "dividend_yield": dps / price if np.isfinite(dps) and np.isfinite(price) and price > 0 else np.nan,
        "eps": _first_valid(_get_row(data["income"], "eps"), np.nan),
    }


# =============================================================================
# 5. THE SHARED VALUATION CORE
# =============================================================================

PROJECTION_YEARS = 5
MIN_SPREAD = 0.015


def pv_of_growing_stream(base, growth, rate, terminal_growth, years=PROJECTION_YEARS):
    g = np.asarray(growth, dtype=float).reshape(-1, 1)
    r = np.asarray(rate, dtype=float).reshape(-1, 1)
    gt = np.asarray(terminal_growth, dtype=float).reshape(-1, 1)
    t = np.arange(1, years + 1).reshape(1, -1)

    projected = base * np.power(1.0 + g, t)
    discounted = projected / np.power(1.0 + r, t)

    spread = np.maximum(r - gt, MIN_SPREAD)
    terminal_value = projected[:, -1:] * (1.0 + gt) / spread
    pv_terminal = terminal_value / np.power(1.0 + r, years)

    return projected, discounted.sum(axis=1, keepdims=True), pv_terminal, terminal_value


def dcf_implied_price(base_fcf, growth, wacc, terminal_growth, cash, debt, shares):
    _, pv_explicit, pv_terminal, _ = pv_of_growing_stream(base_fcf, growth, wacc, terminal_growth)
    enterprise_value = pv_explicit + pv_terminal
    return ((enterprise_value + cash - debt) / shares).ravel()


def ddm_implied_price(base_dps, growth, cost_eq, terminal_growth):
    _, pv_explicit, pv_terminal, _ = pv_of_growing_stream(base_dps, growth, cost_eq, terminal_growth)
    return (pv_explicit + pv_terminal).ravel()


def base_case_schedule(engine, base, growth, rate, terminal_growth,
                       cash=0.0, debt=0.0, shares=1.0):
    projected, pv_explicit, pv_terminal, terminal_value = pv_of_growing_stream(
        base, np.array([growth]), np.array([rate]), np.array([terminal_growth])
    )
    projected = projected[0]
    pv_explicit = float(pv_explicit[0, 0])
    pv_terminal = float(pv_terminal[0, 0])
    terminal_value = float(terminal_value[0, 0])

    t = np.arange(1, PROJECTION_YEARS + 1)
    discount_factors = 1 / (1 + rate) ** t
    stream_label = "Projected FCF" if engine == "DCF" else "Projected DPS"

    schedule = pd.DataFrame({
        "Year": [f"Y{i}" for i in t],
        stream_label: projected,
        "Discount Factor": discount_factors,
        "Present Value": projected * discount_factors,
    })

    gross = pv_explicit + pv_terminal
    if engine == "DCF":
        equity_value = gross + cash - debt
        implied_price = equity_value / shares
    else:
        equity_value = gross
        implied_price = gross

    summary = {
        "pv_explicit": pv_explicit,
        "pv_terminal": pv_terminal,
        "terminal_value": terminal_value,
        "terminal_share": pv_terminal / gross if gross else np.nan,
        "gross": gross,
        "equity_value": equity_value,
        "implied_price": implied_price,
    }
    return schedule, summary


def run_monte_carlo(engine, base, growth, rate, terminal_growth,
                    n_sims, sd_growth, sd_rate, sd_terminal, seed,
                    cash=0.0, debt=0.0, shares=1.0) -> pd.DataFrame:
    rng = np.random.default_rng(int(seed))
    n = int(n_sims)

    if engine == "DCF":
        g = np.clip(rng.normal(growth, sd_growth, n), -0.50, 1.00)
        r = np.clip(rng.normal(rate, sd_rate, n), 0.02, 0.50)
    else:
        g = np.clip(rng.normal(growth, sd_growth, n), -0.30, 0.50)
        r = np.clip(rng.normal(rate, sd_rate, n), 0.03, 0.50)

    gt = np.clip(rng.normal(terminal_growth, sd_terminal, n), -0.02, 0.06)
    gt = np.minimum(gt, r - MIN_SPREAD)

    if engine == "DCF":
        prices = dcf_implied_price(base, g, r, gt, cash, debt, shares)
        rate_label = "WACC"
    else:
        prices = ddm_implied_price(base, g, r, gt)
        rate_label = "Cost of Equity"

    return pd.DataFrame({
        "Growth Rate": g,
        rate_label: r,
        "Terminal Growth": gt,
        "Implied Price": prices,
    })


# =============================================================================
# 6. ORCHESTRATION (replaces Streamlit sections 6-16)
# =============================================================================

DEFAULTS = {
    "DCF": {"growth": 0.10, "terminal": 0.025, "sd": (0.020, 0.010, 0.005)},
    "DDM": {"growth": 0.05, "terminal": 0.025, "sd": (0.015, 0.010, 0.005)},
}


def analyze(
    ticker: str,
    market_code: str = "US",
    engine_choice: str = "auto",
    growth: Optional[float] = None,
    terminal: Optional[float] = None,
    rate_override: Optional[float] = None,
    n_sims: int = 10000,
    sd_growth: Optional[float] = None,
    sd_rate: Optional[float] = None,
    sd_terminal: Optional[float] = None,
    seed: int = 42,
    fcf_basis: str = "Latest fiscal year",
    dps_basis: str = "Trailing 12 months",
    # --- manual input mode (Yahoo has gaps, especially on smaller IDX listings) ---
    manual_base: Optional[float] = None,       # base FCF (DCF) or annual DPS (DDM)
    manual_net_debt: Optional[float] = None,   # DCF only: debt - cash
    manual_shares: Optional[float] = None,     # DCF only
    manual_price: Optional[float] = None,      # both engines
    manual_payout: Optional[float] = None,     # DDM diagnostics only
    with_simulation: bool = False,             # attach raw sims under "_simulation"
) -> dict:
    market = MARKETS.get(market_code.upper(), MARKETS["US"])

    # One resolver for every engine — see _lib/symbols.py for why this matters.
    symbol = symbols.resolve(ticker, market["code"])

    data = fetch_company(symbol)
    rf_rate, rf_source = fetch_risk_free_rate(market["code"], market["risk_free_default"])

    auto_engine, route_reason = detect_engine(data.get("sector"), data.get("industry"))
    choice = (engine_choice or "auto").lower()
    if choice == "dcf":
        engine, route_reason = "DCF", "manual override"
    elif choice == "ddm":
        engine, route_reason = "DDM", "manual override"
    else:
        engine = auto_engine

    manual_price_f = _safe_float(manual_price)
    if np.isfinite(manual_price_f) and manual_price_f > 0:
        data["price"] = manual_price_f

    if not data["ok"] or not np.isfinite(data["price"]):
        raise ValuationError(
            f"No usable market data returned for '{symbol}'. Check the symbol, or supply "
            "the base figures yourself in manual input mode.",
            manual_required=True,
            missing=["price"],
            suggested={"price": None, "shares": _nullable(data.get("shares"))},
        )

    defaults = DEFAULTS[engine]
    growth_input = defaults["growth"] if growth is None else float(growth)
    terminal_input = defaults["terminal"] if terminal is None else float(terminal)
    sd_g = defaults["sd"][0] if sd_growth is None else float(sd_growth)
    sd_r = defaults["sd"][1] if sd_rate is None else float(sd_rate)
    sd_t = defaults["sd"][2] if sd_terminal is None else float(sd_terminal)

    price = data["price"]
    shares = data["shares"]
    tax_rate = effective_tax_rate(data["income"], market["tax_rate"])

    cash_used = debt_used = 0.0
    diagnostics_rows = []
    notices = []
    history_table = []
    bank = None

    RATE_NAME = "Cost of Equity" if engine == "DDM" else "WACC"

    if auto_engine == "DDM" and engine == "DDM":
        notices.append({"tone": "info", "text":
                        "Financial institution detected. Routed from DCF to Dividend Discount Model."})
    elif auto_engine == "DDM" and engine == "DCF":
        notices.append({"tone": "warn", "text":
                        "This is a financial institution, but DCF has been forced. Free cash flow is "
                        "not a meaningful measure for a bank."})
    elif auto_engine == "DCF" and engine == "DDM":
        notices.append({"tone": "info", "text":
                        "DDM has been forced on a non-financial company. This values only distributed "
                        "cash, so it will understate a business that reinvests."})

    # ---------------- ENGINE 1 — DCF ----------------
    if engine == "DCF":
        fcf_history = build_fcf_history(data["cashflow"])
        cash_auto, debt_auto = extract_balance_items(data["balance"])
        interest_expense = _first_valid(_get_row(data["income"], "interest_expense"), np.nan)

        vals = (fcf_history["Free Cash Flow"].astype(float).values
                if not fcf_history.empty else np.array([]))
        auto_base = float(vals[0]) if len(vals) else np.nan

        manual_base_f = _safe_float(manual_base)
        manual_shares_f = _safe_float(manual_shares)
        if np.isfinite(manual_shares_f) and manual_shares_f > 0:
            shares = manual_shares_f

        # A placeholder scaled to the company, not a flat 1e9: an IDX large cap
        # and a US small cap differ by six orders of magnitude, and a default
        # wrong by 1000x reads as a broken app.
        if np.isfinite(auto_base):
            suggested_base = float(auto_base)
        elif np.isfinite(price) and np.isfinite(shares) and price > 0 and shares > 0:
            suggested_base = round(price * shares * 0.05, 0)   # ~5% FCF yield
        else:
            suggested_base = None

        if np.isfinite(manual_base_f):
            # Manual mode mirrors the original: the user gives NET debt, so the
            # bridge carries it entirely on the debt side and cash is zero.
            base_value = float(manual_base_f)
            basis_label = "manual input"
            net_debt = _safe_float(manual_net_debt)
            if not np.isfinite(net_debt):
                net_debt = float(debt_auto - cash_auto)
            cash_used, debt_used = 0.0, float(net_debt)
            notices.append({"tone": "info", "text":
                            "Manual input mode: base free cash flow, net debt, shares and price "
                            "are the figures you supplied, not Yahoo's."})
        else:
            if fcf_history.empty:
                raise ValuationError(
                    "Yahoo returned no usable cash-flow statement for this ticker, so there is "
                    "no base free cash flow to grow. Enter a normalised free cash flow in manual "
                    "input mode, force the DDM engine, or try another symbol.",
                    manual_required=True,
                    missing=["base"],
                    suggested={"base": suggested_base,
                               "netDebt": float(debt_auto - cash_auto),
                               "shares": _nullable(shares), "price": _nullable(price)},
                )
            if fcf_basis == "3-year average" and len(vals) >= 3:
                base_value = float(np.mean(vals[:3]))
            elif fcf_basis == "3-year weighted (3/2/1)" and len(vals) >= 3:
                base_value = float(np.average(vals[:3], weights=[3, 2, 1]))
            elif fcf_basis == "2-year average" and len(vals) >= 2:
                base_value = float(np.mean(vals[:2]))
            else:
                base_value = float(vals[0])
                fcf_basis = "Latest fiscal year"
            basis_label = fcf_basis
            cash_used, debt_used = cash_auto, debt_auto

        if not np.isfinite(base_value) or base_value <= 0:
            raise ValuationError(
                "Base free cash flow is negative or zero. A growth-multiple DCF cannot value "
                "this — the model would simply scale a negative number. Enter a normalised free "
                "cash flow in manual input mode, or value the company on another basis.",
                manual_required=True,
                missing=["base"],
                suggested={"base": suggested_base,
                           "netDebt": float(debt_auto - cash_auto),
                           "shares": _nullable(shares), "price": _nullable(price)},
            )
        if not np.isfinite(shares) or shares <= 0:
            raise ValuationError(
                "Shares outstanding unavailable for this ticker. Enter it in manual input mode.",
                manual_required=True,
                missing=["shares"],
                suggested={"base": suggested_base,
                           "netDebt": float(debt_auto - cash_auto),
                           "shares": None, "price": _nullable(price)},
            )

        rate_parts = compute_wacc(
            beta=data["beta"], risk_free=rf_rate, erp=market["erp"],
            equity_value=price * shares, total_debt=max(debt_used, 0.0),
            interest_expense=interest_expense, tax_rate=tax_rate,
        )
        discount_rate = float(rate_override) if rate_override is not None else rate_parts["wacc"]

        diagnostics_rows = [
            ("Base FCF anchor", basis_label),
            ("Cost of equity (CAPM)", f"{rate_parts['cost_equity']:.2%}"),
            ("Cost of debt (pre-tax)", f"{rate_parts['cost_debt']:.2%}"),
            ("Effective tax rate", f"{tax_rate:.1%}"),
            ("Equity / debt weight", f"{rate_parts['weight_equity']:.0%} / {rate_parts['weight_debt']:.0%}"),
            ("Beta (clipped)", f"{rate_parts['beta']:.2f}"),
            ("Risk-free source", rf_source),
        ]

        history_table = [
            {
                "period": row["Fiscal Year"],
                "operatingCashFlow": fmt_big(row["Operating Cash Flow"], market),
                "capex": fmt_big(row["Capital Expenditure"], market),
                "freeCashFlow": fmt_big(row["Free Cash Flow"], market),
            }
            for _, row in fcf_history.iterrows()
        ]
        basis_options = ["Latest fiscal year"]
        if len(vals) >= 2:
            basis_options.append("2-year average")
        if len(vals) >= 3:
            basis_options += ["3-year average", "3-year weighted (3/2/1)"]

        manual_defaults = {
            "base": suggested_base,
            "netDebt": float(debt_auto - cash_auto),
            "shares": _nullable(shares),
            "price": _nullable(price),
            "payout": None,
        }

    # ---------------- ENGINE 2 — DDM ----------------
    else:
        auto_dps, dps_source = resolve_dividend(data, price)
        div_history = data.get("dividend_history", pd.DataFrame())

        manual_base_f = _safe_float(manual_base)
        suggested_dps = (float(auto_dps) if np.isfinite(auto_dps) and auto_dps > 0
                         else (round(float(price) * 0.03, 4)
                               if np.isfinite(price) and price > 0 else None))

        if np.isfinite(manual_base_f) and manual_base_f > 0:
            base_value = float(manual_base_f)
            dps_source = "manual input"
            basis_label = "manual input"
            notices.append({"tone": "info", "text":
                            "Manual input mode: the dividend per share is the figure you "
                            "supplied, not Yahoo's."})
        else:
            if not np.isfinite(auto_dps) or auto_dps <= 0:
                raise ValuationError(
                    "No usable dividend data returned, so a Dividend Discount Model has nothing "
                    "to discount. Bank dividend fields are frequently empty on Yahoo, especially "
                    "for IDX listings — enter the figure in manual input mode. If the company "
                    "genuinely pays no dividend, force the DCF engine instead.",
                    manual_required=True,
                    missing=["base"],
                    suggested={"base": suggested_dps, "price": _nullable(price),
                               "payout": 0.40},
                )
            if dps_basis == "Last full year" and len(div_history) >= 2:
                base_value = float(div_history["Dividend / Share"].iloc[1])
                dps_source = f"FY{div_history['Year'].iloc[1]} declared"
            elif dps_basis == "3-year average" and len(div_history) >= 3:
                base_value = float(div_history["Dividend / Share"].iloc[:3].mean())
                dps_source = "3-year average of declared dividends"
            else:
                base_value = float(auto_dps)
                dps_basis = "Trailing 12 months"
            basis_label = dps_basis

        bank = bank_diagnostics(data, base_value, price, shares)

        # A supplied payout ratio feeds the sustainable-growth diagnostic only;
        # it never touches the valuation itself.
        manual_payout_f = _safe_float(manual_payout)
        if np.isfinite(manual_payout_f):
            bank["payout"] = manual_payout_f
            bank["payout_clean"] = float(np.clip(manual_payout_f, 0.0, 1.0))
            if np.isfinite(bank["roe"]):
                bank["sustainable_growth"] = bank["roe"] * (1 - bank["payout_clean"])

        rate_parts = {
            "beta": clip_beta(data["beta"]),
            "cost_equity": cost_of_equity(data["beta"], rf_rate, market["erp"]),
        }
        discount_rate = float(rate_override) if rate_override is not None else rate_parts["cost_equity"]

        diagnostics_rows = [
            ("Base DPS source", dps_source),
            ("Current dividend yield",
             f"{bank['dividend_yield']:.2%}" if np.isfinite(bank["dividend_yield"]) else "n/a"),
            ("Payout ratio", f"{bank['payout']:.1%}" if np.isfinite(bank["payout"]) else "n/a"),
            ("Return on equity", f"{bank['roe']:.1%}" if np.isfinite(bank["roe"]) else "n/a"),
            ("Sustainable growth (ROE x retention)",
             f"{bank['sustainable_growth']:.1%}" if np.isfinite(bank["sustainable_growth"]) else "n/a"),
            ("Cost of equity (CAPM)", f"{rate_parts['cost_equity']:.2%}"),
            ("Beta (clipped)", f"{rate_parts['beta']:.2f}"),
            ("Risk-free source", rf_source),
        ]

        history_table = [
            {"period": row["Year"], "dividendPerShare": fmt_dps(row["Dividend / Share"], market)}
            for _, row in div_history.iterrows()
        ] if isinstance(div_history, pd.DataFrame) and not div_history.empty else []
        basis_options = ["Trailing 12 months"]
        if len(div_history) >= 2:
            basis_options.append("Last full year")
        if len(div_history) >= 3:
            basis_options.append("3-year average")

        manual_defaults = {
            "base": suggested_dps,
            "netDebt": None,
            "shares": _nullable(shares),
            "price": _nullable(price),
            "payout": _nullable(bank.get("payout_clean")),
        }

    # ---------------- Terminal growth guard-rail ----------------
    terminal_growth = min(terminal_input, discount_rate - MIN_SPREAD)
    if terminal_growth < terminal_input:
        notices.append({"tone": "warn", "text":
                        f"Perpetual growth capped at {terminal_growth:.2%} to hold 150bp below the "
                        f"{discount_rate:.2%} {RATE_NAME}. At or above it the Gordon Growth terminal "
                        f"value diverges to infinity."})

    # ---------------- Run ----------------
    schedule, summary = base_case_schedule(
        engine, base_value, growth_input, discount_rate, terminal_growth,
        cash=cash_used, debt=debt_used, shares=shares if engine == "DCF" else 1.0,
    )
    sims = run_monte_carlo(
        engine, base_value, growth_input, discount_rate, terminal_growth,
        n_sims=n_sims, sd_growth=sd_g, sd_rate=sd_r, sd_terminal=sd_t,
        seed=seed, cash=cash_used, debt=debt_used,
        shares=shares if engine == "DCF" else 1.0,
    )

    prices = sims["Implied Price"].values
    p05, p25, p50, p75, p95 = np.percentile(prices, [5, 25, 50, 75, 95])
    prob_undervalued = float((prices > price).mean())
    upside = (p50 - price) / price if price else np.nan

    verdict = ("UNDERVALUED" if upside > 0.15 else
               "OVERVALUED" if upside < -0.15 else "FAIRLY VALUED")

    # Histogram is built server-side so the wire carries 60 bins, not N floats.
    lo, hi = np.percentile(prices, [0.5, 99.5])
    display = prices[(prices >= lo) & (prices <= hi)]
    counts, edges = np.histogram(display, bins=60)
    histogram = [
        {"value": float((edges[i] + edges[i + 1]) / 2), "count": int(counts[i])}
        for i in range(len(counts))
    ]

    # ---------------- Post-run sanity checks ----------------
    if np.isfinite(summary["terminal_share"]) and summary["terminal_share"] > 0.80:
        notices.append({"tone": "warn", "text":
                        f"Terminal value is {summary['terminal_share']:.0%} of total value. The answer "
                        f"rests on the perpetuity assumption rather than the five-year forecast."})

    if engine == "DDM" and bank is not None:
        sustainable = _safe_float(bank.get("sustainable_growth"))
        if np.isfinite(sustainable) and growth_input > sustainable + 0.03:
            notices.append({"tone": "warn", "text":
                            f"Dividend growth of {growth_input:.1%} exceeds the sustainable rate of "
                            f"{sustainable:.1%} (ROE x retention). The bank would have to raise equity "
                            f"or run down its capital ratios to fund that path."})
        payout_check = _safe_float(bank.get("payout"))
        if np.isfinite(payout_check) and payout_check > 0.90:
            notices.append({"tone": "warn", "text":
                            f"Payout ratio is {payout_check:.0%}. There is little retained earnings "
                            f"cushion, so the dividend growth assumption is fragile."})

    diagnostics_rows += [
        ("Terminal value as % of total",
         f"{summary['terminal_share']:.0%}" if np.isfinite(summary["terminal_share"]) else "n/a"),
        ("P5 - P95 range", f"{fmt_price(p05, market)} - {fmt_price(p95, market)}"),
    ]

    stream_label = "Projected FCF" if engine == "DCF" else "Projected DPS"
    fmt_stream = fmt_big if engine == "DCF" else fmt_dps
    schedule_rows = [
        {
            "year": row["Year"],
            "stream": fmt_stream(row[stream_label], market),
            "streamRaw": float(row[stream_label]),
            "discountFactor": f"{row['Discount Factor']:.4f}",
            "presentValue": fmt_stream(row["Present Value"], market),
            "presentValueRaw": float(row["Present Value"]),
        }
        for _, row in schedule.iterrows()
    ]

    if engine == "DCF":
        bridge = [
            ("PV of Year 1-5 FCF", fmt_big(summary["pv_explicit"], market)),
            ("PV of terminal value", fmt_big(summary["pv_terminal"], market)),
            ("Enterprise value", fmt_big(summary["gross"], market)),
            ("+ Cash & equivalents", fmt_big(cash_used, market)),
            ("- Total debt", fmt_big(debt_used, market)),
            ("Equity value", fmt_big(summary["equity_value"], market)),
            ("/ Shares outstanding", f"{shares:,.0f}"),
            ("Implied price (base case)", fmt_price(summary["implied_price"], market)),
        ]
    else:
        bridge = [
            ("PV of Year 1-5 dividends", fmt_dps(summary["pv_explicit"], market)),
            ("PV of terminal value", fmt_dps(summary["pv_terminal"], market)),
            ("Implied price (base case)", fmt_price(summary["implied_price"], market)),
            ("Terminal value at Y5", fmt_dps(summary["terminal_value"], market)),
            ("Implied forward yield",
             f"{base_value * (1 + growth_input) / summary['implied_price']:.2%}"
             if summary["implied_price"] else "n/a"),
            ("Market price", fmt_price(price, market)),
        ]

    manual_applied = {
        "base": np.isfinite(_safe_float(manual_base)),
        "netDebt": np.isfinite(_safe_float(manual_net_debt)),
        "shares": np.isfinite(_safe_float(manual_shares)),
        "price": np.isfinite(_safe_float(manual_price)),
        "payout": np.isfinite(_safe_float(manual_payout)),
    }

    payload = {
        "ticker": symbol,
        "name": data["name"],
        "sector": data["sector"] or None,
        "industry": data["industry"] or None,
        "market": {"code": market["code"], "name": market["name"], "symbol": market["symbol"]},
        "engine": engine,
        "autoEngine": auto_engine,
        "routeReason": route_reason,
        "rateName": RATE_NAME,
        "price": float(price),
        "priceLabel": fmt_price(price, market),
        "discountRate": float(discount_rate),
        "riskFree": float(rf_rate),
        "riskFreeSource": rf_source,
        "erp": market["erp"],
        "beta": float(rate_parts["beta"]),
        "assumptions": {
            "growth": growth_input,
            "terminalGrowth": terminal_growth,
            "terminalRequested": terminal_input,
            "sdGrowth": sd_g,
            "sdRate": sd_r,
            "sdTerminal": sd_t,
            "iterations": int(n_sims),
            "seed": int(seed),
            "basis": basis_label,
            "basisOptions": basis_options,
            "rateOverridden": rate_override is not None,
            "manualApplied": {k: bool(v) for k, v in manual_applied.items()},
            "manualDefaults": manual_defaults,
        },
        "baseCase": {
            "impliedPrice": float(summary["implied_price"]),
            "impliedPriceLabel": fmt_price(summary["implied_price"], market),
            "terminalShare": float(summary["terminal_share"])
            if np.isfinite(summary["terminal_share"]) else None,
        },
        "monteCarlo": {
            "p05": float(p05), "p25": float(p25), "p50": float(p50),
            "p75": float(p75), "p95": float(p95),
            "p05Label": fmt_price(p05, market), "p25Label": fmt_price(p25, market),
            "p50Label": fmt_price(p50, market), "p75Label": fmt_price(p75, market),
            "p95Label": fmt_price(p95, market),
            "probUndervalued": prob_undervalued,
            "upside": float(upside) if np.isfinite(upside) else None,
            "histogram": histogram,
        },
        "verdict": verdict,
        "schedule": schedule_rows,
        "streamLabel": stream_label,
        "bridge": [{"component": k, "amount": v} for k, v in bridge],
        "diagnostics": [{"metric": k, "value": v} for k, v in diagnostics_rows],
        "history": history_table,
        "notices": notices,
    }

    if with_simulation:
        # A DataFrame, not JSON. The CSV route pops it before serialisation;
        # `clean()` never sees it.
        payload["_simulation"] = sims

    return payload
