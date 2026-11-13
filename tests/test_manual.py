"""The Indonesian field manual is built from the English one, and cannot drift from it.

`scripts/build_glossary.py` replaces each block of the English manual with its
Indonesian from `docs/field-manual.id.json`. These tests build a small manual
the same way, to pin the three ways the catalog can fall short — an English
block with no Indonesian, an entry no block uses, a translation that drops its
markup — and then check the committed pages are what the script would build.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from _lib import lang

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("build_glossary", ROOT / "scripts" / "build_glossary.py")
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

ENGLISH = """<title>A Manual</title>
<div class="shell" lang="en">
<nav class="rail" aria-label="Contents">
  <div class="rail-head"><span class="eyebrow">Field manual</span>
    <a class="lang" href="field-manual.id.html" hreflang="id" lang="id" translate="no">Bahasa Indonesia</a></div>
</nav>
<p>
  A <strong>percentile</strong> is a position, not a score. See
  <a href="#trend">section 05</a>.
</p>
<td><code>AAPL</code></td>
<input id="gsearch" placeholder="Search 3 terms&hellip;">
<script>
const TEXT = {
  allTerms: "{n} terms",
};
const GLOSSARY = [];
</script>
</div>
"""
PERCENTILE = ('A <strong>percentile</strong> is a position, not a score. See '
              '<a href="#trend">section 05</a>.')
CATALOG = {
    "A Manual": "Sebuah Panduan",
    "Contents": "Daftar isi",
    '<span class="eyebrow">Field manual</span>': '<span class="eyebrow">Panduan</span>',
    PERCENTILE: ('Lihat <a href="#trend">bagian 05</a>. <strong>Persentil</strong> adalah '
                 'posisi, bukan skor.'),
    "Search {{N}} terms&hellip;": "Cari {{N}} istilah&hellip;",
    "{n} terms": "{n} istilah",
}
ROWS = [{"k": f"m{i}", "t": f"M{i}", "d": "d", "g": "high", "l": "flow"} for i in range(3)]


def test_every_block_is_replaced_by_its_indonesian():
    html, work = B.indonesian(ENGLISH, ROWS, CATALOG)
    assert work.problems() == []
    assert "<title>Sebuah Panduan</title>" in html
    assert 'aria-label="Daftar isi"' in html, "attributes are translated too"
    assert "<strong>Persentil</strong>" in html and '<a href="#trend">bagian 05</a>' in html
    assert 'placeholder="Cari 3 istilah&hellip;"' in html, "the count is filled back in"
    assert 'allTerms: "{n} istilah",' in html, "the script's words are translated"
    assert "<td><code>AAPL</code></td>" in html, "code and tickers are left alone"
    assert html.startswith("<!-- GENERATED"), "the page says it must not be edited"


def test_the_page_names_its_language_and_links_back():
    html, _ = B.indonesian(ENGLISH, ROWS, CATALOG)
    assert '<div class="shell" lang="id">' in html
    assert ('<a class="lang" href="field-manual.html" hreflang="en" lang="en" '
            'translate="no">English</a>') in html
    assert "Bahasa Indonesia</a>" not in html


def test_an_english_edit_without_its_indonesian_fails():
    edited = ENGLISH.replace("not a score", "never a score")
    _, work = B.indonesian(edited, ROWS, CATALOG)
    problems = "\n".join(work.problems())
    assert "1 English block(s) have no Indonesian" in problems
    assert "match no block" in problems, "the old entry is reported, not left to rot"
    assert work.missing == [PERCENTILE.replace("not a score", "never a score")]


def test_a_translation_that_drops_a_link_fails():
    broken = {**CATALOG, PERCENTILE: "<strong>Persentil</strong> adalah posisi, bukan skor."}
    html, work = B.indonesian(ENGLISH, ROWS, broken)
    assert work.mismatched == [PERCENTILE]
    assert "do not carry their English's markup" in "\n".join(work.problems())
    assert PERCENTILE in " ".join(html.split()), "the block stays English, never half-linked"


@pytest.mark.parametrize("bad", ["{shown} istilah", "istilah"])
def test_a_script_string_must_keep_its_placeholders(bad):
    _, work = B.indonesian(ENGLISH, ROWS, {**CATALOG, "{n} terms": bad})
    assert work.mismatched == ["{n} terms"]


def test_an_attribute_translation_may_not_close_its_own_quotes():
    _, work = B.indonesian(ENGLISH, ROWS, {**CATALOG, "Contents": 'Isi "panduan"'})
    assert work.mismatched == ["Contents"]


def test_the_committed_manuals_are_what_the_script_builds():
    english = B.render(B.MANUAL.read_text(encoding="ascii"), B.collect())
    assert english == B.MANUAL.read_text(encoding="ascii")
    token = lang.use("id")
    try:
        rows = B.collect()
    finally:
        lang.reset(token)
    built, work = B.indonesian(english, rows, json.loads(B.CATALOG_ID.read_text(encoding="utf-8")))
    assert work.problems() == []
    assert built == B.MANUAL_ID.read_text(encoding="ascii"), "run scripts/build_glossary.py"
    assert all(row["t"] and row["d"] for row in rows)
