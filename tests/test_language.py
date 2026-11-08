"""
The reading language: English unchanged, Indonesian complete, and the choice
scoped to one request.

Three properties matter and each has failed somewhere before in projects like
this one. The language must not leak between requests on a warm instance (a
module global would answer one reader in another's language). It must survive
the thread pools a route fans out through (a context variable does not cross a
bare ThreadPoolExecutor by itself). And a sentence switched to Indonesian must
not carry English fragments spliced in from somewhere else, which is the usual
way a half-translated product reads.
"""

from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor

import pytest

import index
from _lib import explain as E
from _lib import lang
from _lib.lang import Bilingual, tr


@pytest.fixture
def indonesian():
    token = lang.use("id")
    yield
    lang.reset(token)


# --------------------------------------------------------------------------- #
# The mechanism
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw, expected", [
    ("id", "id"), ("ID", "id"), ("id-ID", "id"), ("en", "en"), ("en-US", "en"),
    (None, "en"), ("", "en"), ("fr", "en"), ("javascript:", "en"),
])
def test_anything_unsupported_is_answered_in_english(raw, expected):
    assert lang.normalise(raw) == expected


def test_tr_answers_in_the_language_of_the_current_request(indonesian):
    assert tr("Volatility", "Volatilitas") == "Volatilitas"
    token = lang.use("en")
    try:
        assert tr("Volatility", "Volatilitas") == "Volatility"
    finally:
        lang.reset(token)
    assert lang.current() == "id"


def test_the_default_is_english():
    assert lang.current() == "en"
    assert tr("Volatility", "Volatilitas") == "Volatility"


def test_a_bare_thread_pool_does_not_inherit_the_language_but_carry_does(indonesian):
    # The reason `carry` exists: without it a pooled worker answers in English
    # whatever the reader asked for.
    with ThreadPoolExecutor(max_workers=2) as pool:
        bare = list(pool.map(lambda _: lang.current(), range(4)))
        carried = list(pool.map(lang.carry(lambda _: lang.current()), range(4)))
    assert set(bare) == {"en"}
    assert set(carried) == {"id"}


def test_carry_does_not_leave_the_worker_in_the_borrowed_language(indonesian):
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(lang.carry(lambda: None)).result()
        assert pool.submit(lang.current).result() == "en"


def test_the_middleware_scopes_the_language_to_one_request():
    seen = []

    class FakeRequest:
        def __init__(self, value):
            self.query_params = {"lang": value} if value is not None else {}

    async def call_next(_request):
        seen.append(lang.current())
        return "answered"

    for value in ("id", None, "xx", "id"):
        assert asyncio.run(index.language(FakeRequest(value), call_next)) == "answered"
        assert lang.current() == "en"
    assert seen == ["id", "en", "en", "id"]


def test_a_bilingual_table_answers_per_lookup_not_per_import(indonesian):
    table = Bilingual({"a": ("the index", "indeks")})
    assert table["a"] == "indeks"
    assert table.get("a") == "indeks"
    assert table.get("missing", "fallback") == "fallback"
    token = lang.use("en")
    try:
        assert table["a"] == "the index"
    finally:
        lang.reset(token)


def test_month_names_follow_the_language(indonesian):
    assert [lang.month_abbr(m) for m in (5, 8, 10, 12)] == ["Mei", "Agu", "Okt", "Des"]
    token = lang.use("en")
    try:
        assert [lang.month_abbr(m) for m in (5, 8, 10, 12)] == ["May", "Aug", "Oct", "Dec"]
    finally:
        lang.reset(token)


# --------------------------------------------------------------------------- #
# The explanation layer
# --------------------------------------------------------------------------- #
# Probe values chosen to walk every band of every interpreter, plus the context
# arguments the interpreters read. A metric that returns None for a probe is
# skipped for that probe, exactly as the glossary builder does.
PROBES = (1.0, 0.5, 50.0, 0.05, -0.2, 2.0, 25.0, 100.0, 8.0, -1.9, 0.004, 72.0,
          -0.5, 0.9, 0.15, 3.0, 0.3, -100.0, 120.0, 0.01, 6.0, 95.0, 15.0)
CONTEXTS = (
    {},
    {"price": 50.0, "plusDi": 30.0, "minusDi": 10.0, "aroonDown": 10.0, "stochD": 40.0,
     "macdSignal": 0.5, "squeezePercentile": 0.1, "atr": 2.5, "previous": -2.0,
     "maxScore": 7, "indicesAvailable": 6, "riskFree": 0.04, "var95": -0.03,
     "stderr": 0.03, "verdict": "indistinguishable", "low": 0.43, "high": 0.57,
     "observations": 400, "signal": "invested", "monthsInStance": 3, "rSquared": 0.2,
     "period": "12m", "benchmark": "^GSPC", "years": 3, "positiveShare": 0.8,
     "windows": 40, "totalDays": 900, "days": 30, "count": 4, "direction": "Accumulation",
     "avgRvol": 1.1, "ongoing": True, "currency": "IDR", "assumedGrowth": 0.05,
     "rate_name": None, "risk_free": 0.04, "beta": 1.1, "p25_label": "Rp 1,000",
     "p75_label": "Rp 2,000", "target_label": "Target 1", "atr_multiple": 1.0,
     "basis": "volatility", "risk_budget": 0.01, "uncapped": 1.5, "side": "resistance",
     "touches": 1, "price_text": "Rp 1,500", "fired": "up", "kind": "bearish",
     "size_atr": 1.5, "flagged": True, "prior_text": "3%", "partial": True,
     "market": "ID", "profitable": 4, "positive": 2, "of": 5, "events": 20, "p": 0.2,
     "ticker": "BBCA.JK", "overlap": 240, "names": 4, "before": 2.0, "gain": 0.1,
     "weight": 0.1, "market_share": 0.1, "holdings": 4, "loaded": 3, "scanned": 30,
     "weeks": 260, "check_label": "x", "universe_label": "the Nasdaq-100"},
)

# Words that appear in nearly every English sentence and in no Indonesian one.
ENGLISH = re.compile(r"\b(the|and|of|is|are|with|this|that|than|from|its|was|were|"
                     r"would|should|which|there|their|it)\b")

# Metrics whose label or definition is written by another module and passed in
# (the ranking signals' questions, the pre-trade checks' names). Those modules'
# own tests cover their prose.
BORROWED = {"signalRank"}


def _readings():
    for key, fn in sorted(E._REGISTRY.items()):
        if key in BORROWED:
            continue
        for context in CONTEXTS:
            for probe in PROBES:
                try:
                    result = fn(probe, **context)
                except (TypeError, ValueError, ZeroDivisionError, KeyError):
                    continue
                if result:
                    yield key, probe, result


def test_every_interpreter_runs_in_indonesian(indonesian):
    seen = {key for key, _, _ in _readings()}
    assert seen >= set(E._REGISTRY) - BORROWED - {"validationDomain"}


def test_no_interpreter_answers_an_indonesian_reader_in_english(indonesian):
    leaks = []
    for key, probe, result in _readings():
        for field in ("label", "what", "reading", "action", "valueText"):
            text = result.get(field) or ""
            # "Context, not a trigger" is a quoted label in some readings; the
            # passed-in names (BBCA.JK, Target 1) are data, not prose.
            words = ENGLISH.findall(text)
            if len(words) >= 2:
                leaks.append(f"{key}({probe}).{field}: {text[:90]}")
    assert not leaks, "\n".join(sorted(set(leaks))[:20])


def test_identifiers_do_not_change_with_the_language(indonesian):
    # Band, tone, direction and evidence are compared by the client and by the
    # tests; only prose moves.
    english, indonesian_ = {}, {}
    for key, probe, result in _readings():
        indonesian_[(key, probe)] = {k: result[k] for k in ("band", "tone", "goodDirection",
                                                            "evidence")}
    token = lang.use("en")
    try:
        for key, probe, result in _readings():
            english[(key, probe)] = {k: result[k] for k in ("band", "tone", "goodDirection",
                                                            "evidence")}
    finally:
        lang.reset(token)
    assert english == indonesian_


def test_the_reading_changes_language_but_not_its_numbers(indonesian):
    reading = E.explain("volatility", 0.32)["reading"]
    assert reading.startswith("Sekitar 32% per tahun")
    token = lang.use("en")
    try:
        assert E.explain("volatility", 0.32)["reading"].startswith("About 32% a year")
    finally:
        lang.reset(token)


def test_money_is_written_in_indonesian_units(indonesian):
    assert E._money(2.5e12, "IDR") == "Rp2.5 triliun"
    assert E._money(3.1e9, "USD") == "$3.1 miliar"
    token = lang.use("en")
    try:
        assert E._money(2.5e12, "IDR") == "Rp2.5tn"
    finally:
        lang.reset(token)


def test_the_board_names_months_in_indonesian(indonesian):
    assert E._board_date("2026-08-03", with_year=True) == "3 Agu 2026"


def test_the_calendar_names_its_sources_in_indonesian(indonesian):
    from _lib import econcalendar
    doc = econcalendar.load()
    named = econcalendar._sources(doc)
    assert named.keys() == doc["sources"].keys()
    for key, source in doc["sources"].items():
        assert named[key]["url"] == source["url"], "a translated citation still links the source"
        assert named[key]["name"] == econcalendar._SOURCES_ID[source["name"]], (
            f"{key}: every source in the file has its Indonesian name")


def test_the_calendar_sources_are_untouched_in_english():
    from _lib import econcalendar
    doc = econcalendar.load()
    assert econcalendar._sources(doc) == doc["sources"]


def test_the_jakarta_exchange_is_bei_to_an_indonesian_reader(indonesian):
    from _lib import econcalendar
    assert econcalendar._exchange_name("IDX") == "BEI"
    assert econcalendar._exchange_name("NYSE") == "NYSE"
    assert econcalendar.EXCHANGES["ID"]["name"] == "IDX", "the table itself is not changed"
