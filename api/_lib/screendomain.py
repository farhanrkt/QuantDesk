"""
screendomain.py
===============
Whether a use of an accounting screen sits inside the sample it was validated on.

THE GAP THIS CLOSES
-------------------
`quality.py` already enforces APPLICABILITY: the three screens refuse to score a
bank, because none of them was built on one. That is a binary gate and it is the
right one. But applicability is not the same question as validation domain, and
the app has never answered the second.

Piotroski's nine tests were fitted on US filings from 1976 to 1996, on the
highest book-to-market quintile, and the paper reports the effect concentrated
in small and mid-caps with no analyst following. Altman's coefficients come from
sixty-six US manufacturers that went bankrupt or did not between 1946 and 1965.
Beneish was estimated on SEC enforcement actions from the 1980s. An Indonesian
large cap in 2026 is outside all three, on several axes at once.

THAT IS PROVENANCE, NOT A DEFECT, and the distinction is the whole design here.
A screen used outside its sample is not thereby wrong — every practical use of
all three is outside their samples, because the samples ended thirty years ago.
It is a fact a reader needs in order to weigh the number, in the same way the
constituent lists carry an as-of date and the Hurst band carries its sample size.

SO NOTHING HERE IS COLOURED
---------------------------
Every reading this module produces sits in the `context` band, which the tone
map renders neutral. Two reasons, and the second matters more.

Being OUTSIDE a validation sample is not a warning: it is the normal condition
of every use of every one of these models today, and a panel that painted it
amber would be crying wolf on all three scores for every company forever.

Being INSIDE one is not reassurance either — and that is the trap. A green tick
against "period: inside" would tell a reader the score can be trusted, which is
a claim about the model's accuracy on this company that nothing here measures.
Absence of a mismatch is not evidence of fit, which is the same rule the
pre-trade panel is built around.

WHAT IT DOES NOT DO
-------------------
It does not re-weight, discount or adjust any score. It reports where the number
came from and lets the reader decide what that is worth.

References for the sample descriptions below
--------------------------------------------
Piotroski, J. D. (2000). "Value Investing: The Use of Historical Financial
    Statement Information to Separate Winners from Losers." Journal of
    Accounting Research 38, 1-41. 14,043 firm-years, highest book-to-market
    quintile of US Compustat, 1976-1996; benefits concentrated in small and
    medium firms with low share turnover and no analyst following.
Altman, E. I. (1968). "Financial Ratios, Discriminant Analysis and the
    Prediction of Corporate Bankruptcy." Journal of Finance 23(4), 589-609.
    66 US manufacturers (33 bankrupt, 33 not), filings from before 1966.
Altman, E. I. (2005). "An emerging market credit scoring system for corporates."
    Emerging Markets Review 6(4), 311-323. The +3.25 constant and the
    bond-rating equivalence, developed on emerging-market corporates.
Beneish, M. D. (1999). "The Detection of Earnings Manipulation." Financial
    Analysts Journal 55(5), 24-36. Estimation sample 1982-1988: 50 manipulators
    identified through SEC enforcement actions against 1,708 industry-matched
    controls, US Compustat, non-financial.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd

from . import universes
from .valuation import _get_row, _safe_float
from .lang import tr

# The three fits, as data. Each `sample` string is what the paper's own sample
# was; each `thisUse` is computed from the company in front of the reader.
INSIDE, OUTSIDE, UNKNOWN = "inside", "outside", "unknown"

# Book-to-market below this is not the top quintile of anything. Published
# breakpoints for the highest book-to-market fifth move year to year and have
# sat roughly between 0.7 and 1.2 in US data; a company priced at more than
# three times its book value is outside any of them by a wide margin. The
# reverse call is NOT made: a high ratio does not put a name in the top quintile
# either, because a quintile is a position in a cross-section and placing one
# needs a universe scan this panel does not run.
NOT_VALUE_BM = 0.33


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _fiscal_year(*statements) -> Optional[int]:
    """The year of the most recent column across the statements.

    Yahoo labels statement columns with the period end date, so this is the
    fiscal year the scores were actually computed on rather than today's year —
    which matters, because a filing can be eighteen months stale.
    """
    years = []
    for frame in statements:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        for column in frame.columns:
            try:
                years.append(pd.Timestamp(column).year)
            except (TypeError, ValueError):
                continue
    return max(years) if years else None


def _dimension(key: str, name: str, sample: str, this_use: str,
               verdict: str, note: str) -> dict:
    return {"key": key, "name": name, "sample": sample, "thisUse": this_use,
            "verdict": verdict, "note": note}


def _period(key: str, name: str, sample: str, first: int, last: int,
            fiscal_year: Optional[int]) -> dict:
    if fiscal_year is None:
        return _dimension(
            key, name, sample, tr("no dated filing", "tidak ada laporan keuangan bertanggal"), UNKNOWN,
            tr("The statements carry no readable period, so the gap cannot be measured.",
               "Laporan keuangannya tidak memuat periode yang bisa dibaca, jadi "
               "selisihnya tidak bisa diukur."))
    inside = first <= fiscal_year <= last
    gap = fiscal_year - last
    return _dimension(
        key, name, sample, tr(f"{fiscal_year} filings", f"laporan keuangan {fiscal_year}"),
        INSIDE if inside else OUTSIDE,
        tr("Inside the years the model was fitted on.",
           "Di dalam rentang tahun tempat model ini dicocokkan.")
        if inside else
        tr(f"{gap} years after the sample ends. Accounting standards, disclosure rules "
           f"and the composition of listed markets have all moved since; the model has "
           f"not been refitted here.",
           f"{gap} tahun setelah sampelnya berakhir. Standar akuntansi, aturan "
           "pengungkapan, dan komposisi pasar saham semuanya sudah bergeser sejak "
           "itu; model ini belum dicocokkan ulang di sini."))


def _market(key: str, sample: str, market_code: Optional[str],
            emerging_recalibration: bool = False) -> dict:
    code = (market_code or "").upper()
    if code not in ("US", "ID"):
        return _dimension(key, tr("Market", "Pasar"), sample, tr("not stated", "tidak disebutkan"), UNKNOWN,
                          tr("The listing's market was not passed to this check.",
                             "Pasar saham ini tidak diteruskan ke pemeriksaan ini."))
    if emerging_recalibration:
        # THE ONE PLACE THE USUAL DIRECTION REVERSES, and it is worth saying out
        # loud. Altman's bands come from a recalibration built for emerging
        # markets, so an Indonesian listing is closer to the sample the ZONES
        # were drawn on than a US one is. The coefficients are a separate
        # dimension and go the other way.
        return _dimension(
            key, tr("Market", "Pasar"), sample,
            tr("US listing", "saham tercatat AS") if code == "US" else tr("Indonesian (IDX) listing",
                                                 "saham tercatat Indonesia (BEI)"),
            OUTSIDE if code == "US" else INSIDE,
            tr("The emerging-market recalibration was built for exactly this kind of "
               "listing, so the zone boundaries are on home ground here.",
               "Kalibrasi ulang pasar berkembang dibuat persis untuk jenis saham "
               "seperti ini, jadi batas zonanya berada di kandang sendiri di sini.")
            if code == "ID" else
            tr("The zone boundaries come from an emerging-market recalibration, "
               "benchmarked to US bond ratings. A US listing is not what that "
               "adjustment was made for, though the underlying ratios are unaffected.",
               "Batas zonanya berasal dari kalibrasi ulang pasar berkembang, yang "
               "dipatok pada peringkat obligasi AS. Saham AS bukan sasaran penyesuaian "
               "itu, meski rasio dasarnya tidak terpengaruh."))
    return _dimension(
        key, tr("Market", "Pasar"), sample,
        tr("US listing", "saham tercatat AS") if code == "US" else tr("Indonesian (IDX) listing",
                                             "saham tercatat Indonesia (BEI)"),
        INSIDE if code == "US" else OUTSIDE,
        tr("A US listing, which is the market the model was fitted on.",
           "Saham AS, pasar tempat model ini dicocokkan.")
        if code == "US" else
        tr("Fitted on US filings under US accounting standards. Indonesian filers "
           "report under IFRS-converged standards with different disclosure "
           "requirements, and no refit for this market is applied here.",
           "Dicocokkan pada laporan keuangan AS dengan standar akuntansi AS. Emiten "
           "Indonesia melapor dengan standar yang mengadopsi IFRS dan persyaratan "
           "pengungkapan yang berbeda, dan tidak ada pencocokan ulang untuk pasar "
           "ini yang diterapkan di sini."))


def _book_equity(company: dict) -> Optional[float]:
    """Shareholders' equity from the latest balance sheet.

    Read through `_get_row` rather than by column name for the same reason every
    other statement read in this codebase is: the aliases are where Yahoo's
    inconsistent row labels get resolved, and a direct lookup would silently
    return nothing for whichever label this filer happens to use.
    """
    row = _get_row(company.get("balance"), "equity")
    if row is None or not len(row):
        return None
    return _finite(_safe_float(row.iloc[0]))


def _book_to_market(company: dict) -> tuple[Optional[float], str]:
    """Book equity over market capitalisation, and how to say it.

    Both figures come from the same `fetch_company` payload the scores do, and
    the statements have already been converted to the trading currency at that
    boundary — so this ratio is not comparing a rupiah book value with a dollar
    market cap, which is the bug that boundary exists to prevent.
    """
    cap = _finite(company.get("market_cap"))
    equity = _book_equity(company)
    if cap is None or equity is None or cap <= 0:
        return None, tr("not computable", "tidak bisa dihitung")
    ratio = equity / cap
    return ratio, tr(f"book/market {ratio:.2f}", f"nilai buku/pasar {ratio:.2f}")


def _value_style(company: dict) -> dict:
    sample = tr("highest book-to-market fifth of the market (value stocks)",
                "seperlima pasar dengan rasio nilai buku terhadap pasar tertinggi (saham "
                "nilai)")
    ratio, text = _book_to_market(company)
    if ratio is None:
        return _dimension(
            "style", tr("Valuation style", "Gaya valuasi"), sample, text, UNKNOWN,
            tr("Book value or market capitalisation is missing, so this listing cannot be "
               "placed against the value screen the sample was drawn from.",
               "Nilai buku atau kapitalisasi pasar tidak ada, jadi saham ini tidak bisa "
               "ditempatkan terhadap penyaring nilai tempat sampelnya diambil."))
    if ratio < NOT_VALUE_BM:
        return _dimension(
            "style", tr("Valuation style", "Gaya valuasi"), sample, text, OUTSIDE,
            tr(f"Priced at more than three times book value. The F-Score's evidence comes "
               f"entirely from the cheapest fifth of the market on this measure, and no "
               f"published breakpoint for that fifth sits anywhere near {ratio:.2f}.",
               "Dihargai lebih dari tiga kali nilai bukunya. Bukti F-Score sepenuhnya "
               "berasal dari seperlima pasar yang termurah menurut ukuran ini, dan "
               f"tidak ada batas terbitan untuk seperlima itu yang mendekati {ratio:.2f}."))
    return _dimension(
        "style", tr("Valuation style", "Gaya valuasi"), sample, text, UNKNOWN,
        tr("Cheap enough to be in value territory, but the top fifth is a position in a "
           "cross-section and placing this name in one needs a universe-wide scan of book "
           "values, which does not batch and is not run here.",
           "Cukup murah untuk masuk wilayah nilai, tetapi seperlima teratas adalah "
           "posisi dalam penampang pasar, dan menempatkan saham ini di dalamnya "
           "butuh pemindaian nilai buku di seluruh semesta, yang tidak bisa "
           "dilakukan sekaligus dan tidak dijalankan di sini."))


def _size_and_coverage(symbol: Optional[str], company: dict) -> dict:
    """Where this name sits against "small and mid-cap, no analyst following".

    INDEX MEMBERSHIP RATHER THAN A CASH THRESHOLD, deliberately. A market-cap
    cutoff would need a number in dollars, an exchange rate for the rupiah, and
    a view on what "small" meant in 1976 against what it means now — three
    invented constants to answer one qualitative question. Membership of the Dow,
    the Nasdaq-100, IDX30 or LQ45 says the same thing without any of them, is
    already in this repo, and carries its own as-of date.
    """
    sample = (tr("small and mid-caps, thinly traded, with no analyst following — where "
                 "Piotroski reports the effect concentrated",
                 "saham berkapitalisasi kecil dan menengah, jarang diperdagangkan, tanpa "
                 "liputan analis — tempat Piotroski melaporkan efeknya terkonsentrasi"))
    groups = universes.containing(symbol) if symbol else []
    if groups:
        names = ", ".join(g["name"] for g in groups)
        return _dimension(
            "size", tr("Size and coverage", "Ukuran dan liputan"), sample, tr(f"a member of {names}", f"anggota {names}"), OUTSIDE,
            tr("A headline-index constituent is followed by many analysts and traded "
               "heavily, which is the opposite end of the market from where the paper "
               "found the effect. The nine tests still describe the filings; the return "
               "evidence behind them does not come from companies like this one.",
               "Anggota indeks utama diikuti banyak analis dan ramai diperdagangkan, "
               "ujung pasar yang berlawanan dengan tempat makalah itu menemukan "
               "efeknya. Sembilan uji itu tetap menggambarkan laporan keuangannya; "
               "bukti imbal hasil di baliknya tidak berasal dari perusahaan seperti ini."))
    cap = _finite(company.get("market_cap"))
    detail = tr("not in any predefined index", "tidak termasuk indeks yang sudah ditentukan")
    if cap is not None and cap > 0:
        detail += tr(f", market cap {cap:,.0f} {company.get('currency') or ''}",
                     f", kapitalisasi pasar {cap:,.0f} {company.get('currency') or ''}").rstrip()
    return _dimension(
        "size", tr("Size and coverage", "Ukuran dan liputan"), sample, detail, UNKNOWN,
        tr("Outside the predefined index lists, so this app cannot say how heavily it is "
           "followed. Analyst coverage and share turnover are the variables the paper "
           "conditions on, and neither is fetched here.",
           "Di luar daftar indeks yang sudah ditentukan, jadi aplikasi ini tidak "
           "bisa menilai seberapa banyak ia diikuti. Liputan analis dan perputaran "
           "saham adalah variabel yang dikendalikan makalah itu, dan keduanya tidak "
           "diambil di sini."))


def _industry(company: dict) -> dict:
    industry = (company.get("industry") or "").strip()
    sector = (company.get("sector") or "").strip()
    described = industry or sector or tr("not stated", "tidak disebutkan")
    manufacturing = any(word in (industry + " " + sector).lower() for word in (
        "manufactur", "industrial", "machinery", "auto", "aerospace", "chemical",
        "steel", "materials", "semiconductor equipment", "building products",
        "electrical equipment", "packaging"))
    if not (industry or sector):
        return _dimension(
            "industry", tr("Industry", "Industri"), tr("US manufacturers", "perusahaan manufaktur AS"), described, UNKNOWN,
            tr("No sector came back for this listing, so the fit cannot be judged.",
               "Tidak ada sektor yang kembali untuk saham ini, jadi kecocokannya tidak "
               "bisa dinilai."))
    return _dimension(
        "industry", tr("Industry", "Industri"), tr("US manufacturers", "perusahaan manufaktur AS"), described,
        INSIDE if manufacturing else OUTSIDE,
        tr("A manufacturer, which is what the discriminant analysis was fitted on.",
           "Perusahaan manufaktur, yang menjadi dasar pencocokan analisis "
           "diskriminan.")
        if manufacturing else
        tr("The Z'' form drops the sales-to-assets term precisely so the score travels "
           "across industries with different asset turnover, so this is the dimension the "
           "model itself was adapted to survive — but the coefficients were still "
           "estimated on manufacturers.",
           "Bentuk Z'' menghapus suku penjualan terhadap aset justru agar skornya "
           "berlaku lintas industri dengan perputaran aset yang berbeda, jadi "
           "inilah dimensi yang memang disesuaikan agar model bertahan — tetapi "
           "koefisiennya tetap diperkirakan dari perusahaan manufaktur."))


def _event_rate(company: dict) -> dict:
    return _dimension(
        "prevalence", tr("How common the event was in the sample",
                         "Seberapa umum peristiwa itu dalam sampel"),
        tr("50 manipulators against 1,708 controls, about 3% of the estimation sample",
           "50 manipulator dibandingkan 1,708 pembanding, sekitar 3% dari sampel "
           "estimasi"),
        tr("a listed company drawn from no sample at all",
           "perusahaan tercatat yang tidak diambil dari sampel mana pun"), OUTSIDE,
        tr("Manipulators were deliberately over-represented — about one firm in thirty-four, "
           "far commoner than in the wild. A screen tuned that way raises more false alarms "
           "here, so a flag is a reason to read the filings rather than a finding.",
           "Manipulator sengaja diwakili berlebihan — sekitar satu dari tiga puluh "
           "empat perusahaan, jauh lebih umum daripada di dunia nyata. Penyaring "
           "yang disetel seperti itu memunculkan lebih banyak alarm palsu di sini, "
           "jadi tanda adalah alasan untuk membaca laporan keuangan, bukan temuan."))


def assess(company: dict, symbol: Optional[str] = None,
           market_code: Optional[str] = None) -> dict:
    """Where each screen's use sits against the sample it was validated on.

    Returns one block per screen, each a list of dimensions with `inside`,
    `outside` or `unknown` — never a count and never a colour. See the module
    docstring for why a matching dimension is not reassurance.
    """
    fiscal_year = _fiscal_year(company.get("income"), company.get("balance"),
                               company.get("cashflow"))

    piotroski = [
        _period("period", tr("Period", "Periode"), tr("US filings, 1976-1996", "laporan keuangan AS, 1976-1996"), 1976, 1996, fiscal_year),
        _market("market", tr("US Compustat filers", "emiten AS di Compustat"), market_code),
        _value_style(company),
        _size_and_coverage(symbol, company),
    ]

    altman = [
        _period("period", tr("Period the coefficients come from", "Periode asal koefisien"),
                tr("US filings from before 1966", "laporan keuangan AS sebelum 1966"), 1946, 1965, fiscal_year),
        _market("market", tr("emerging-market corporates (2005 recalibration)",
                             "perusahaan pasar berkembang (kalibrasi ulang 2005)"),
                market_code, emerging_recalibration=True),
        _industry(company),
    ]

    beneish = [
        _period("period", tr("Period", "Periode"), tr("US filings, 1982-1988", "laporan keuangan AS, 1982-1988"), 1982, 1988, fiscal_year),
        _market("market", tr("US Compustat filers", "emiten AS di Compustat"), market_code),
        _event_rate(company),
    ]

    return {
        "asOf": dt.date.today().isoformat(),
        "fiscalYear": fiscal_year,
        "screens": {
            "piotroski": {
                "label": "Piotroski F-Score",
                "citation": "Piotroski (2000), Journal of Accounting Research 38",
                "sample": (tr("14,043 firm-years from the highest book-to-market fifth of "
                              "US Compustat, 1976-1996",
                              "14,043 tahun-perusahaan dari seperlima pasar Compustat AS dengan rasio "
                              "nilai buku terhadap pasar tertinggi, 1976-1996")),
                "dimensions": piotroski,
            },
            "altman": {
                "label": tr("Altman Z''-score (emerging-market variant)",
                            "Altman Z''-score (varian pasar berkembang)"),
                "citation": ("Altman (1968), Journal of Finance 23(4); Altman (2005), "
                             "Emerging Markets Review 6(4)"),
                "sample": (tr("66 US manufacturers, 33 of which went bankrupt, on filings "
                              "from before 1966; the zone boundaries recalibrated on "
                              "emerging-market corporates in 2005",
                              "66 perusahaan manufaktur AS, 33 di antaranya bangkrut, dari laporan "
                              "keuangan sebelum 1966; batas zonanya dikalibrasi ulang pada perusahaan "
                              "pasar berkembang pada 2005")),
                "dimensions": altman,
            },
            "beneish": {
                "label": "Beneish M-Score",
                "citation": "Beneish (1999), Financial Analysts Journal 55(5)",
                "sample": (tr("50 manipulators found through SEC enforcement actions "
                              "against 1,708 industry-matched controls, US Compustat, "
                              "1982-1988",
                              "50 manipulator yang ditemukan lewat tindakan penegakan hukum SEC "
                              "dibandingkan 1,708 pembanding yang dicocokkan per industri, Compustat "
                              "AS, 1982-1988")),
                "dimensions": beneish,
            },
        },
    }
