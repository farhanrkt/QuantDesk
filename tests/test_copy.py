"""Sentences a reader sees, held to what they say.

Each of these read wrongly on the page in the November 2026 audit
(docs/AUDIT.md, COPY-1 to COPY-5). Guided mode shows only the first sentence of
a reading, so a first sentence that carries nothing leaves a figure unexplained,
which PRODUCT.md constraint 7 forbids.
"""

from __future__ import annotations

import re

import pytest

from _lib import explain, lang


def first_sentence(text: str) -> str:
    """The rule `components/ui/explain.tsx` applies in Guided mode."""
    if len(text.split()) <= 18:
        return text.strip()
    match = re.search(r"[.!?](?=\s+[A-Z\"“])", text)
    return text[:match.end()] if match else text


@pytest.mark.parametrize("value", [3.0, 8.0, 15.0, 25.0, 40.0])
def test_the_ulcer_index_explains_itself_in_its_first_sentence(value):
    first = first_sentence(explain.explain("ulcerIndex", value)["reading"])
    assert re.search(r"[a-z]{3}", first), f"first sentence is only a number: {first!r}"
    assert not re.fullmatch(r"[\d.,]+\.?", first.strip())


def test_a_loss_is_called_a_loss():
    reading = explain.explain("rollingWorst", -0.164, years=3, positiveShare=0.55)["reading"]
    assert "still returned" not in reading
    assert "lost 16.4% a year" in reading


def test_a_gain_still_reads_as_one():
    reading = explain.explain("rollingWorst", 0.002, years=3, positiveShare=1.0)["reading"]
    assert "still returned +0.2% a year" in reading


def test_a_negative_sortino_is_not_called_earnings():
    reading = explain.explain("sortino", -0.49, riskFree=0.065)["reading"]
    assert "earned -0.49" not in reading
    assert "fell short" in reading


def test_the_default_growth_is_the_models_not_the_readers():
    reading = explain.explain("impliedGrowth", 0.325, assumedGrowth=0.10)["reading"]
    assert "you assumed" not in reading and "MORE" not in reading
    assert "more growth than the model" in reading


def test_the_same_sentences_in_indonesian():
    token = lang.use("id")
    try:
        loss = explain.explain("rollingWorst", -0.164, years=3, positiveShare=0.55)["reading"]
        growth = explain.explain("impliedGrowth", 0.325, assumedGrowth=0.10)["reading"]
    finally:
        lang.reset(token)
    assert "merugi 16.4% per tahun" in loss
    assert "asumsi Anda" not in growth


def test_the_rate_limit_sentence_names_no_endpoint():
    import index
    from fastapi.testclient import TestClient

    index._RATE_HITS.clear()
    limits = dict(index.RATE_LIMITS)
    index.RATE_LIMITS["/api/health"] = (1, 60)
    exempt = set(index.RATE_EXEMPT)
    index.RATE_EXEMPT.discard("/api/health")
    try:
        client = TestClient(index.app)
        client.get("/api/health")
        detail = client.get("/api/health").json()["detail"]
    finally:
        index.RATE_LIMITS.clear()
        index.RATE_LIMITS.update(limits)
        index.RATE_EXEMPT.update(exempt)
        index._RATE_HITS.clear()
    assert "endpoint" not in detail
    assert "1 in 60 seconds" in detail


@pytest.mark.parametrize("period, english, indonesian", [
    ("36m", "Versus the index (36 months)", "Dibandingkan indeks (36 bulan)"),
    ("1m", "Versus the index (1 month)", "Dibandingkan indeks (1 bulan)"),
    ("12m", "Versus the index (12 months)", "Dibandingkan indeks (12 bulan)"),
])
def test_the_index_comparison_names_its_period_in_words(period, english, indonesian):
    # The period code reached the page as "(36M)" in both languages (UX-5).
    assert explain.explain("relativeExcess", 0.05, period=period)["label"] == english
    token = lang.use("id")
    try:
        assert explain.explain("relativeExcess", 0.05, period=period)["label"] == indonesian
    finally:
        lang.reset(token)
