"""
quality.py
==========
Engine 4 — accounting quality, financial strength and solvency.

WHY A FOURTH LENS
-----------------
Flow, trend and value all read the same company from the outside. None of them
opens the filings and asks whether the business is sound. That gap matters most
exactly where the other three are loudest: a discounted cash flow on a company
sliding toward insolvency is arithmetic, not a valuation, and the DCF will
happily return a large "undervalued" number for a firm whose equity is about to
be worth nothing.

Three published scores, each answering a different question:

  Piotroski F-Score   Is the fundamental trend improving?      0-9, higher better
  Altman Z''-EM       How far from financial distress?         higher better
  Beneish M-Score     Do the accruals look manipulated?        lower better

APPLICABILITY IS ENFORCED, NOT ASSUMED
--------------------------------------
None of the three applies to banks or insurers, and this module refuses rather
than returning a number that looks fine. Piotroski (2000) explicitly excluded
financial firms; Altman built Z on manufacturers, and the working-capital and
current-ratio terms are meaningless for an institution with no operating cycle;
Beneish's indices assume a receivables-and-inventory revenue model. Silence is
the correct output for BBCA. The bank instead gets the residual income engine
(see `valuation.py`), which is built for exactly that balance sheet.

References
----------
Piotroski, J. D. (2000). "Value Investing: The Use of Historical Financial
    Statement Information to Separate Winners from Losers." Journal of
    Accounting Research 38, 1-41.
Altman, E. I. (1968). "Financial Ratios, Discriminant Analysis and the
    Prediction of Corporate Bankruptcy." Journal of Finance 23(4), 589-609.
Altman, E. I. (2005). "An emerging market credit scoring system for corporates."
    Emerging Markets Review 6(4), 311-323.
Beneish, M. D. (1999). "The Detection of Earnings Manipulation." Financial
    Analysts Journal 55(5), 24-36.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from . import market_data
from . import posterior as posterior_lib
from . import screendomain
from .valuation import _get_row, _safe_float
from .lang import tr

# Sectors and industry keywords the three models were never fitted on.
_FINANCIAL_SECTORS = {"financial services", "financials"}
_FINANCIAL_KEYWORDS = ("bank", "insurance", "insurer", "capital markets",
                       "asset management", "credit services", "reinsurance")

# Beneish combines eight indices; a score assembled from half of them is not a
# Beneish score. Below this many, the module declines to report one.
_MIN_BENEISH_INDICES = 6

# THE PIOTROSKI BANDS, AS SHARES OF THE CHECKS THAT COULD BE COMPUTED. The
# lower edge of mixed, solid and strong. On a full nine they are exactly the
# counts the bands always used — 4, 6 and 8 — and on eight computable checks
# they band every score as the counts did, so nothing scored on complete or
# nearly complete filings moves. `explain._piotroski` reads the same three edges,
# so the metric's sentence and the band that votes cannot disagree again.
PIOTROSKI_CUTS = (4 / 9, 6 / 9, 8 / 9)

# Fewer computable checks than this and no band is called. Six of the nine
# compare this year with last, so one year of statements leaves three level
# tests — profitable, cash-generating, cash above profit — which say nothing
# about a TREND, and the F-score is a trend reading. Same floor, for the same
# reason, as Beneish's six of eight.
PIOTROSKI_MIN_SIGNALS = 6


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def is_financial(sector: str, industry: str) -> bool:
    """Same routing rule the valuation engine uses, applied for exclusion."""
    s = (sector or "").strip().lower()
    i = (industry or "").strip().lower()
    return s in _FINANCIAL_SECTORS or any(k in i for k in _FINANCIAL_KEYWORDS)


def _series(statement, key: str) -> Optional[pd.Series]:
    row = _get_row(statement, key)
    return row if row is not None else None


def _at(statement, key: str, period: int = 0) -> float:
    """One line item at `period` (0 = most recent fiscal year, 1 = prior)."""
    row = _series(statement, key)
    if row is None or period >= len(row):
        return np.nan
    return _safe_float(row.iloc[period])


def _ratio(numerator: float, denominator: float) -> float:
    if not np.isfinite(numerator) or not np.isfinite(denominator) or denominator == 0:
        return np.nan
    return numerator / denominator


def _nullable(value) -> Optional[float]:
    out = _safe_float(value)
    return float(out) if np.isfinite(out) else None


# --------------------------------------------------------------------------- #
# Piotroski F-Score
# --------------------------------------------------------------------------- #
def piotroski_band(score: int, computable: int) -> tuple[str, str]:
    """The band, and its sentence, for `score` passes out of `computable` checks."""
    if computable <= 0:
        return "unknown", tr("No usable statement history.",
                             "Tidak ada riwayat laporan keuangan yang bisa dipakai.")
    if computable < PIOTROSKI_MIN_SIGNALS:
        return "unknown", (tr(f"Only {computable} of the nine checks could be computed from these "
                              f"filings, too few to call a direction: most of them compare this "
                              f"year with last.",
                              f"Hanya {computable} dari sembilan pemeriksaan yang bisa dihitung dari "
                              "laporan keuangan ini, terlalu sedikit untuk menyimpulkan arah: sebagian "
                              "besar membandingkan tahun ini dengan tahun lalu."))
    share = score / computable
    mixed, solid, strong = PIOTROSKI_CUTS
    # The tolerance only absorbs float error at an exact edge such as 6/9.
    if share >= strong - 1e-9:
        return "strong", tr("Fundamentals improving on almost every axis.",
                            "Fundamental membaik di hampir setiap sumbu.")
    if share >= solid - 1e-9:
        return "solid", tr("More improving than deteriorating.",
                           "Lebih banyak yang membaik daripada yang memburuk.")
    if share >= mixed - 1e-9:
        return "mixed", tr("No clear fundamental direction.",
                           "Tidak ada arah fundamental yang jelas.")
    return "weak", tr("Deteriorating on most axes Piotroski measures.",
                      "Memburuk di sebagian besar sumbu yang diukur Piotroski.")


def piotroski_f_score(income, balance, cashflow) -> dict:
    """Nine binary fundamental signals, scored 0-9.

    Each signal is scored only if BOTH years it needs are available; an
    unavailable signal scores nothing and is reported as such, so a 5/9 built
    from nine tests reads differently from a 5/7 built from seven. Awarding a
    point for missing data would be the easy bug here and it inflates every
    thin-coverage listing.

    THE BAND READS THE SHARE OF COMPUTABLE CHECKS, NOT THE RAW COUNT. It used
    to band the count as if nine had always been computed, so the opposite bug
    shipped instead: a company with one year of statements, passing all three
    checks that year allows, banded "weak — deteriorating on most axes", the
    Quality lens voted bearish, and the pre-trade panel printed "3 of 3
    fundamental checks passed — deteriorating". Found in the November 2026
    analysis. Below PIOTROSKI_MIN_SIGNALS the band is `unknown`, which every
    reader already treats as "could not be assessed".
    """
    signals: list[dict] = []

    def record(name: str, passed, detail: str = "") -> None:
        signals.append({
            "name": name,
            "passed": None if passed is None else bool(passed),
            "detail": detail,
        })

    assets_now, assets_prior = _at(balance, "total_assets", 0), _at(balance, "total_assets", 1)
    income_now, income_prior = _at(income, "net_income", 0), _at(income, "net_income", 1)
    cfo_now = _at(cashflow, "ocf", 0)

    roa_now = _ratio(income_now, assets_now)
    roa_prior = _ratio(income_prior, assets_prior)

    # --- profitability ---
    record(tr("Return on assets positive", "Imbal hasil aset positif"), roa_now > 0 if np.isfinite(roa_now) else None,
           f"ROA {roa_now:.1%}" if np.isfinite(roa_now) else tr("unavailable", "tidak tersedia"))
    record(tr("Operating cash flow positive", "Arus kas operasional positif"), cfo_now > 0 if np.isfinite(cfo_now) else None,
           "" if np.isfinite(cfo_now) else tr("unavailable", "tidak tersedia"))
    record(tr("Return on assets improving", "Imbal hasil aset membaik"),
           roa_now > roa_prior if np.isfinite(roa_now) and np.isfinite(roa_prior) else None,
           f"{roa_prior:.1%} -> {roa_now:.1%}"
           if np.isfinite(roa_now) and np.isfinite(roa_prior) else tr("unavailable", "tidak tersedia"))

    # THE DETAIL REPORTS THE TWO FIGURES, not the conclusion. It used to read
    # "earnings backed by cash rather than accruals" whatever the test did, so a
    # company that failed — AAPL FY2025, cash flow 30.9% of assets against a
    # 31.2% ROA — rendered a red cross beside a sentence asserting the opposite.
    # Every other signal here prints what it measured; this one now does too.
    cfo_over_assets = _ratio(cfo_now, assets_now)
    record(tr("Cash flow exceeds accounting profit", "Arus kas melebihi laba akuntansi"),
           cfo_over_assets > roa_now
           if np.isfinite(cfo_over_assets) and np.isfinite(roa_now) else None,
           tr(f"cash {cfo_over_assets:.1%} vs profit {roa_now:.1%}",
              f"kas {cfo_over_assets:.1%} vs laba {roa_now:.1%}")
           if np.isfinite(cfo_over_assets) and np.isfinite(roa_now) else tr("unavailable", "tidak tersedia"))

    # --- leverage, liquidity, source of funds ---
    ltd_now, ltd_prior = _at(balance, "long_term_debt", 0), _at(balance, "long_term_debt", 1)
    leverage_now = _ratio(ltd_now, assets_now)
    leverage_prior = _ratio(ltd_prior, assets_prior)
    record(tr("Leverage falling", "Leverage menurun"),
           leverage_now < leverage_prior
           if np.isfinite(leverage_now) and np.isfinite(leverage_prior) else None,
           f"{leverage_prior:.1%} -> {leverage_now:.1%}"
           if np.isfinite(leverage_now) and np.isfinite(leverage_prior) else tr("unavailable", "tidak tersedia"))

    current_now = _ratio(_at(balance, "current_assets", 0), _at(balance, "current_liabilities", 0))
    current_prior = _ratio(_at(balance, "current_assets", 1), _at(balance, "current_liabilities", 1))
    record(tr("Current ratio improving", "Rasio lancar membaik"),
           current_now > current_prior
           if np.isfinite(current_now) and np.isfinite(current_prior) else None,
           f"{current_prior:.2f} -> {current_now:.2f}"
           if np.isfinite(current_now) and np.isfinite(current_prior) else tr("unavailable", "tidak tersedia"))

    shares_now, shares_prior = _at(balance, "shares_issued", 0), _at(balance, "shares_issued", 1)
    record(tr("No dilution", "Tanpa dilusi"),
           shares_now <= shares_prior * 1.001
           if np.isfinite(shares_now) and np.isfinite(shares_prior) else None,
           tr(f"{shares_prior / 1e6:,.0f}M -> {shares_now / 1e6:,.0f}M shares",
              f"{shares_prior / 1e6:,.0f}jt -> {shares_now / 1e6:,.0f}jt saham")
           if np.isfinite(shares_now) and np.isfinite(shares_prior) else tr("unavailable", "tidak tersedia"))

    # --- operating efficiency ---
    revenue_now, revenue_prior = _at(income, "revenue", 0), _at(income, "revenue", 1)
    cogs_now, cogs_prior = _at(income, "cogs", 0), _at(income, "cogs", 1)
    margin_now = _ratio(revenue_now - cogs_now, revenue_now)
    margin_prior = _ratio(revenue_prior - cogs_prior, revenue_prior)
    record(tr("Gross margin expanding", "Margin kotor melebar"),
           margin_now > margin_prior
           if np.isfinite(margin_now) and np.isfinite(margin_prior) else None,
           f"{margin_prior:.1%} -> {margin_now:.1%}"
           if np.isfinite(margin_now) and np.isfinite(margin_prior) else tr("unavailable", "tidak tersedia"))

    turnover_now = _ratio(revenue_now, assets_now)
    turnover_prior = _ratio(revenue_prior, assets_prior)
    record(tr("Asset turnover improving", "Perputaran aset membaik"),
           turnover_now > turnover_prior
           if np.isfinite(turnover_now) and np.isfinite(turnover_prior) else None,
           f"{turnover_prior:.2f}x -> {turnover_now:.2f}x"
           if np.isfinite(turnover_now) and np.isfinite(turnover_prior) else tr("unavailable", "tidak tersedia"))

    scored = [s for s in signals if s["passed"] is not None]
    score = sum(1 for s in scored if s["passed"])
    band, reading = piotroski_band(score, len(scored))

    return {
        "score": int(score),
        "maxScore": len(scored),
        "signalsAvailable": len(scored),
        "signalsTotal": len(signals),
        "band": band,
        "reading": reading,
        "signals": signals,
    }


# --------------------------------------------------------------------------- #
# Altman Z''-score, emerging-market variant
# --------------------------------------------------------------------------- #
def altman_z_em(income, balance) -> dict:
    """Altman's Z''-score with the emerging-market constant.

        Z'' = 3.25 + 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4

    X1 working capital / total assets      X3 EBIT / total assets
    X2 retained earnings / total assets    X4 book equity / total liabilities

    The Z'' form drops the sales/assets term of the original Z, which makes it
    comparable across industries with very different asset turnover. The +3.25
    constant is Altman's emerging-market adjustment, calibrated so the score maps
    onto US bond-equivalent ratings; it is the right variant for an IDX listing
    and harmless for a US one.
    """
    assets = _at(balance, "total_assets")
    if not np.isfinite(assets) or assets <= 0:
        return {"score": None, "band": "unknown",
                "reading": tr("Total assets unavailable, so no solvency score.",
                              "Total aset tidak tersedia, jadi tidak ada skor solvabilitas."),
                "components": {}}

    working_capital = _at(balance, "current_assets") - _at(balance, "current_liabilities")
    retained = _at(balance, "retained_earnings")
    ebit = _at(income, "ebit")
    equity = _at(balance, "equity")
    liabilities = _at(balance, "total_liabilities")

    x1 = _ratio(working_capital, assets)
    x2 = _ratio(retained, assets)
    x3 = _ratio(ebit, assets)
    x4 = _ratio(equity, liabilities)

    components = {"workingCapitalToAssets": _nullable(x1), "retainedToAssets": _nullable(x2),
                  "ebitToAssets": _nullable(x3), "equityToLiabilities": _nullable(x4)}

    if not all(np.isfinite(v) for v in (x1, x2, x3, x4)):
        missing = [name for name, value in
                   zip((tr("working capital", "modal kerja"), tr("retained earnings", "laba ditahan"), "EBIT", tr("total liabilities",
                                                                           "total kewajiban")),
                       (x1, x2, x3, x4), strict=True) if not np.isfinite(value)]
        return {"score": None, "band": "unknown",
                "reading": tr(f"Cannot score: {', '.join(missing)} unavailable.",
                              f"Tidak bisa diberi skor: {', '.join(missing)} tidak tersedia."),
                "components": components}

    score = 3.25 + 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4

    # Altman's Z'' zones (2.6 / 1.1) shifted by the +3.25 EM constant.
    if score > 5.85:
        band, reading = "safe", tr("Comfortably outside Altman's distress zone.",
                                   "Jauh di luar zona tertekan Altman.")
    elif score >= 4.35:
        band, reading = "grey", tr("Altman's grey zone — neither safe nor distressed.",
                                   "Zona abu-abu Altman — tidak aman, tidak pula tertekan.")
    else:
        band, reading = "distress", (tr("Inside Altman's distress zone. A going-concern "
                                        "question outranks any valuation.",
                                        "Di dalam zona tertekan Altman. Pertanyaan tentang kelangsungan usaha "
                                        "mengalahkan valuasi apa pun."))

    return {"score": float(score), "band": band, "reading": reading,
            "components": components}


# --------------------------------------------------------------------------- #
# Beneish M-Score
# --------------------------------------------------------------------------- #
def beneish_m_score(income, balance, cashflow) -> dict:
    """Eight-index earnings-manipulation model.

        M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
            + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI

    M above -1.78 flags a company with characteristics common among known
    manipulators. It is a SCREEN, not an accusation: Beneish reports it
    correctly classifying about three-quarters of manipulators, which also means
    a large false-positive rate on a population where manipulation is rare.

    Missing indices default to 1.0 (the "no change year over year" value) so a
    partial score stays on scale, but the module refuses to report at all below
    `_MIN_BENEISH_INDICES` — an M-Score assembled from three of eight indices is
    not evidence of anything.
    """
    def pair(statement, key):
        return _at(statement, key, 0), _at(statement, key, 1)

    revenue_now, revenue_prior = pair(income, "revenue")
    receivables_now, receivables_prior = pair(balance, "receivables")
    cogs_now, cogs_prior = pair(income, "cogs")
    assets_now, assets_prior = pair(balance, "total_assets")
    current_now, current_prior = pair(balance, "current_assets")
    ppe_now, ppe_prior = pair(balance, "ppe")
    depreciation_now, depreciation_prior = pair(cashflow, "depreciation")
    sga_now, sga_prior = pair(income, "sga")
    ltd_now, ltd_prior = pair(balance, "long_term_debt")
    curliab_now, curliab_prior = pair(balance, "current_liabilities")
    net_income_now = _at(income, "net_income", 0)
    cfo_now = _at(cashflow, "ocf", 0)

    indices: dict[str, Optional[float]] = {}

    def index_of(name: str, value: float) -> float:
        if np.isfinite(value) and value > 0:
            indices[name] = float(value)
            return float(value)
        indices[name] = None
        return 1.0

    dsri = index_of("DSRI", _ratio(_ratio(receivables_now, revenue_now),
                                   _ratio(receivables_prior, revenue_prior)))
    margin_now = _ratio(revenue_now - cogs_now, revenue_now)
    margin_prior = _ratio(revenue_prior - cogs_prior, revenue_prior)
    gmi = index_of("GMI", _ratio(margin_prior, margin_now))

    soft_now = _ratio(assets_now - current_now - ppe_now, assets_now)
    soft_prior = _ratio(assets_prior - current_prior - ppe_prior, assets_prior)
    aqi = index_of("AQI", _ratio(soft_now, soft_prior))

    sgi = index_of("SGI", _ratio(revenue_now, revenue_prior))

    rate_now = _ratio(depreciation_now, depreciation_now + ppe_now)
    rate_prior = _ratio(depreciation_prior, depreciation_prior + ppe_prior)
    depi = index_of("DEPI", _ratio(rate_prior, rate_now))

    sgai = index_of("SGAI", _ratio(_ratio(sga_now, revenue_now),
                                   _ratio(sga_prior, revenue_prior)))

    leverage_now = _ratio((curliab_now or 0) + (ltd_now or 0), assets_now)
    leverage_prior = _ratio((curliab_prior or 0) + (ltd_prior or 0), assets_prior)
    lvgi = index_of("LVGI", _ratio(leverage_now, leverage_prior))

    # TATA is a level, not a ratio of ratios, so it defaults to 0 not 1.
    tata_value = _ratio(net_income_now - cfo_now, assets_now)
    tata = float(tata_value) if np.isfinite(tata_value) else 0.0
    indices["TATA"] = _nullable(tata_value)

    available = sum(1 for v in indices.values() if v is not None)
    if available < _MIN_BENEISH_INDICES:
        return {
            "score": None, "band": "unknown", "indices": indices,
            "indicesAvailable": available, "indicesTotal": len(indices),
            "reading": (tr(f"Only {available} of {len(indices)} Beneish indices could be "
                           "computed from these filings — too few to report a score.",
                           f"Hanya {available} dari {len(indices)} indeks Beneish yang bisa dihitung "
                           "dari laporan keuangan ini — terlalu sedikit untuk melaporkan skor.")),
        }

    score = (-4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
             + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)

    if score > -1.78:
        band = "flagged"
        reading = (tr("Accrual and growth patterns resemble those Beneish found among "
                      "manipulators. A screen, not a finding — read the filings.",
                      "Pola akrual dan pertumbuhannya mirip dengan yang ditemukan Beneish pada "
                      "para manipulator. Ini penyaring, bukan temuan — bacalah laporan "
                      "keuangannya."))
    elif score > -2.22:
        band = "borderline"
        reading = tr("Close to Beneish's threshold; worth a look at the accruals.",
                     "Dekat ambang Beneish; layak melihat akrualnya.")
    else:
        band = "clean"
        reading = tr("No Beneish manipulation signature.", "Tidak ada jejak manipulasi Beneish.")

    return {"score": float(score), "band": band, "indices": indices,
            "indicesAvailable": available, "indicesTotal": len(indices),
            "reading": reading}


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def analyze(company: dict, symbol: Optional[str] = None,
            market_code: Optional[str] = None,
            manipulation_prior: Optional[float] = None) -> dict:
    """The whole quality lens for one company.

    `company` is the dict `valuation.fetch_company` already returns, so this
    costs no additional network calls — the statements have been fetched.

    `symbol` and `market_code` are used only by the validation-domain block,
    which reports whether THIS use sits inside the sample each screen was fitted
    on. Both are optional: without them the affected dimensions report "unknown"
    rather than guessing, which is the same contract every other missing input
    gets here.

    `manipulation_prior` selects which prevalence the Beneish posterior is
    computed at. It changes no score — only what a flag is reported to be worth.
    """
    sector = company.get("sector") or ""
    industry = company.get("industry") or ""
    income = company.get("income")
    balance = company.get("balance")
    cashflow = company.get("cashflow")

    # A COIN, A FUND OR AN INDEX IS NOT A COMPANY WITH A MISSING SECTOR. The
    # branch below told a reader of BTC-USD and SPY that "a repeat fetch will
    # usually resolve it", which no fetch ever will. Found in the November audit.
    kind = market_data.non_company(company, symbol)
    if kind:
        return {
            "applicable": False,
            "cause": "not-a-company",
            "reason": (tr(f"This listing is {kind}, not a company, so there are no "
                          f"financial statements for Piotroski, Altman or Beneish to "
                          f"read. That is what the listing is, not a gap in the data.",
                          f"Saham ini adalah {kind}, bukan perusahaan, jadi tidak ada laporan "
                          "keuangan untuk dibaca Piotroski, Altman, atau Beneish. Begitulah wujud "
                          "instrumen ini, bukan celah data.")),
            "sector": None, "industry": None,
            "piotroski": None, "altman": None, "beneish": None,
        }

    # AN UNKNOWN SECTOR IS NOT A NON-FINANCIAL SECTOR, and the difference is a
    # wrong answer rather than a missing one.
    #
    # Found on a whole-market IDX scan. Yahoo throttles the `.info` scrape long
    # before it throttles the statement endpoints, so a fetch can return complete
    # financial statements with an EMPTY sector and industry. `is_financial("",
    # "")` is False, so the refusal below never fires, and the lens goes on to
    # report a Piotroski F-score, an Altman band and a Beneish reading for a
    # bank — the exact arithmetic-without-meaning this whole branch exists to
    # decline. Observed on BBCA.JK, whose sector reads "Financial Services" on
    # any unthrottled fetch.
    #
    # There is no way to tell that outcome from a genuine non-financial firm by
    # looking at it, which is what makes it worth its own branch: the score looks
    # ordinary, and it is a score for a company the models cannot describe. IDX
    # is heavily weighted toward banks, so on this market it is not a rare case.
    if not sector and not industry:
        return {
            "applicable": False,
            "cause": "unknown-sector",
            "reason": (
                tr("No sector or industry came back for this listing, so there is no way "
                   "to tell whether Piotroski, Altman and Beneish apply to it. They were "
                   "built on non-financial firms and do not transfer to a bank or "
                   "insurer, and scoring first and asking afterwards is how a bank gets "
                   "an F-score. This is a refusal to guess, not a finding about the "
                   "company — a repeat fetch will usually resolve it.",
                   "Tidak ada sektor atau industri yang kembali untuk saham ini, jadi tidak "
                   "ada cara mengetahui apakah Piotroski, Altman, dan Beneish berlaku "
                   "untuknya. Ketiganya dibangun di atas perusahaan nonkeuangan dan tidak "
                   "berlaku untuk bank atau asuransi, dan memberi skor dulu lalu bertanya "
                   "kemudian adalah cara sebuah bank mendapat F-score. Ini penolakan untuk "
                   "menebak, bukan temuan tentang perusahaannya — pengambilan ulang "
                   "biasanya menyelesaikannya.")
            ),
            "sector": None, "industry": None,
            "piotroski": None, "altman": None, "beneish": None,
        }

    if is_financial(sector, industry):
        return {
            "applicable": False,
            # WHY the refusal, as a value rather than a sentence. There are two
            # ways this lens declines and they are not the same thing: one is a
            # designed refusal (the models do not transfer to a bank), the other
            # is missing data. Callers that need to say something specific about
            # one of them had to sniff the prose for a keyword, which breaks the
            # first time the prose is reworded.
            "cause": "financial",
            "reason": (
                tr("Piotroski, Altman and Beneish were all built on non-financial "
                   "firms and none of them transfers to a bank or insurer: there is "
                   "no operating cycle for working capital or a current ratio to "
                   "describe, and revenue is not a receivables-and-inventory "
                   "process. A score here would be arithmetic without meaning.",
                   "Piotroski, Altman, dan Beneish semuanya dibangun di atas perusahaan "
                   "nonkeuangan dan tidak ada yang berlaku untuk bank atau asuransi: tidak "
                   "ada siklus operasi untuk digambarkan modal kerja atau rasio lancar, dan "
                   "pendapatannya bukan proses piutang dan persediaan. Skor di sini "
                   "hanyalah aritmetika tanpa makna.")
            ),
            "sector": sector or None,
            "industry": industry or None,
            "piotroski": None, "altman": None, "beneish": None,
        }

    have_statements = any(
        isinstance(s, pd.DataFrame) and not s.empty for s in (income, balance, cashflow)
    )
    if not have_statements:
        return {
            "applicable": False,
            "cause": "no-statements",
            "reason": tr("No financial statements came back for this listing.",
                         "Tidak ada laporan keuangan yang kembali untuk saham ini."),
            "sector": sector or None, "industry": industry or None,
            "piotroski": None, "altman": None, "beneish": None,
        }

    piotroski = piotroski_f_score(income, balance, cashflow)
    altman = altman_z_em(income, balance)
    beneish = beneish_m_score(income, balance, cashflow)

    # One headline the confluence rail can vote with.
    concerns = []
    if altman["band"] == "distress":
        concerns.append(tr("solvency", "solvabilitas"))
    if beneish["band"] == "flagged":
        concerns.append(tr("accruals", "akrual"))
    if piotroski["band"] == "weak":
        concerns.append(tr("fundamental trend", "tren fundamental"))

    if concerns:
        verdict, tone = "CONCERNS", "bear"
        headline = (tr("Flagged on ", "Ditandai pada ") + tr(" and ", " dan ").join(concerns)
                    + ".")
    elif piotroski["band"] in {"strong", "solid"} and altman["band"] == "safe":
        verdict, tone = "SOUND", "bull"
        headline = tr("Improving fundamentals and no solvency or accrual flags.",
                      "Fundamental membaik dan tidak ada tanda solvabilitas atau akrual.")
    else:
        verdict, tone = "NEUTRAL", "neutral"
        headline = tr("Nothing alarming, nothing outstanding.",
                      "Tidak ada yang mengkhawatirkan, tidak ada yang menonjol.")

    return {
        "applicable": True,
        "sector": sector or None,
        "industry": industry or None,
        "verdict": verdict,
        "tone": tone,
        "headline": headline,
        "piotroski": piotroski,
        "altman": altman,
        "beneish": beneish,
        # WHAT A BENEISH FLAG IS ACTUALLY WORTH. The band decides the branch,
        # so this can never disagree with the score printed beside it. See
        # `_lib/posterior.py` for why the prior is the feature and why both the
        # flagged and clean branches are framed as a shift rather than a level.
        "manipulationPosterior": posterior_lib.for_beneish(
            beneish.get("band"), prior=manipulation_prior,
            indices_available=beneish.get("indicesAvailable"),
            indices_total=beneish.get("indicesTotal", 8)),
        # WHERE THESE NUMBERS CAME FROM, beside the numbers themselves.
        # Applicability is already enforced above and is a different question:
        # this one is whether a screen that DOES apply is being asked about a
        # company like the ones it was fitted on. It is never a colour and never
        # a verdict — see `_lib/screendomain.py`.
        "domains": screendomain.assess(company, symbol=symbol,
                                       market_code=market_code),
    }
