#!/usr/bin/env python3
"""
render_scan.py
==============
The scan report as one self-contained HTML file.

WHY HTML AND NOT A TERMINAL TABLE ALONE
---------------------------------------
The terminal summary answers "what came out on top". This answers "and why",
which is forty lines per name and does not fit in a column. The decomposition is
the point: a score with no decomposition cannot be argued with, which is the
exact property `technical.long_term_view` refuses to ship a score for. Every row
here opens into the five components, the two family scores, the agreement
branch, the shrinkage arithmetic, every penalty with its firing rate, and every
gate — so a reader can find the one number they disagree with.

WHAT THE LAYOUT IS ARGUING
--------------------------
The published measurement of whether this ranking predicts anything comes FIRST,
above the table, in the largest block on the page. That is not a disclaimer
position, it is the correct reading order: the table means something different
depending on that paragraph, so the paragraph cannot come after it. `PRODUCT.md`
constraint 2 says a feature implying prediction is measured and published
including nulls or does not ship. This is the null, published, at the top.

Self-contained by design — no CDN, no fetch, no build step. A report a year old
must still render, and a report is a record.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from _lib import chartsvg

PALETTE = """
:root{
  --ink:#080C10; --panel:#111820; --raised:#161F29; --sunken:#0C1116;
  --rule:#1E2A36; --ruleSoft:#18222C;
  --chalk:#E7EEF5; --body:#C3CFDC; --ash:#8496A9; --faint:#7387A0;
  --acc:#35C4A8; --dist:#FF6B6B; --warn:#F2C14E;
  --flow:#2FBFA4; --trend:#6B9BFF; --value:#E8B44C; --quality:#C9A227;
  --tech:#6B9BFF;
}
"""

CSS = PALETTE + """
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--body);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Inter,system-ui,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:34px 22px 90px}
h1{font-size:26px;line-height:1.2;color:var(--chalk);margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:18px;color:var(--chalk);margin:34px 0 12px;letter-spacing:-.005em}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.09em;color:var(--faint);
  margin:0 0 10px;font-weight:600}
p{margin:0 0 12px}
a{color:var(--tech)}
.sub{color:var(--ash);font-size:13.5px;margin-bottom:26px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-variant-numeric:tabular-nums}

/* --- the measurement, first and largest ------------------------------- */
.provenance{background:linear-gradient(180deg,rgba(242,193,78,.07),rgba(242,193,78,.02));
  border:1px solid rgba(242,193,78,.32);border-left:3px solid var(--warn);
  border-radius:10px;padding:20px 22px;margin:0 0 30px}
.provenance h3{color:var(--warn)}
.provenance p{color:var(--body);font-size:14.5px;max-width:82ch}
.provenance p:last-child{margin-bottom:0}
.provenance .stamp{color:var(--faint);font-size:12.5px;margin-top:12px}

/* --- funnel ------------------------------------------------------------ */
.funnel{display:flex;flex-wrap:wrap;gap:1px;background:var(--rule);
  border:1px solid var(--rule);border-radius:9px;overflow:hidden;margin-bottom:8px}
.funnel div{flex:1 1 150px;background:var(--panel);padding:13px 15px}
.funnel .n{font-size:23px;color:var(--chalk);font-weight:600;letter-spacing:-.02em}
.funnel .k{font-size:11.5px;text-transform:uppercase;letter-spacing:.07em;
  color:var(--faint);margin-top:3px}
.funnel .w{font-size:12px;color:var(--ash);margin-top:5px;line-height:1.4}
.note{font-size:12.5px;color:var(--ash);margin:8px 0 0}
.note.stale{color:var(--warn)}

/* --- table ------------------------------------------------------------- */
/* The table has eight columns and a company-name column that must stay
   readable. Below about 900px the name wraps to four lines and the row stops
   reading as a row, so the table keeps its own minimum and scrolls inside its
   wrapper rather than compressing. The page body never scrolls sideways. */
.tablewrap{overflow-x:auto;margin-top:6px;border-radius:9px}
table{width:100%;min-width:820px;border-collapse:collapse}
td:first-child{min-width:230px}
thead th{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--faint);
  text-align:left;padding:9px 10px;border-bottom:1px solid var(--rule);font-weight:600;
  background:var(--ink)}
thead th.num{text-align:right}
tbody tr.row{border-bottom:1px solid var(--ruleSoft);cursor:pointer}
tbody tr.row:hover{background:var(--raised)}
tbody td{padding:10px;vertical-align:middle;font-size:14px}
td.num{text-align:right}
.tick{color:var(--chalk);font-weight:600}
.nm{color:var(--ash);font-size:12.5px}
.held{color:var(--warn);font-size:11px;letter-spacing:.06em;margin-left:6px}
.score{font-size:17px;font-weight:600;color:var(--chalk)}
.pill{display:inline-block;padding:3px 9px;border-radius:999px;font-size:11.5px;
  font-weight:600;letter-spacing:.03em;white-space:nowrap;border:1px solid}
.t-good{color:var(--acc);border-color:rgba(53,196,168,.4);background:rgba(53,196,168,.1)}
.t-bad{color:var(--dist);border-color:rgba(255,107,107,.4);background:rgba(255,107,107,.1)}
.t-warn{color:var(--warn);border-color:rgba(242,193,78,.4);background:rgba(242,193,78,.1)}
.t-neutral{color:var(--ash);border-color:var(--rule);background:var(--raised)}
.t-none{color:var(--faint);border-color:var(--ruleSoft);background:transparent}
.conv{font-size:12px;color:var(--ash)}
.conv.high{color:var(--acc)} .conv.low{color:var(--warn)}
.entry{font-size:11.5px;font-family:ui-monospace,monospace;white-space:nowrap}
.entry.ok{color:var(--ash)} .entry.poor{color:var(--warn)} .entry.bad{color:var(--dist)}
.cross{font-size:11.5px;letter-spacing:.02em}
.cross.yes{color:var(--ash)}
.cross.no{color:var(--warn)}
.bar{height:5px;border-radius:3px;background:var(--sunken);overflow:hidden;
  min-width:56px;margin-top:5px}
.bar i{display:block;height:100%;border-radius:3px}

/* --- detail ------------------------------------------------------------ */
tr.detail{display:none}
tr.detail.open{display:table-row}
tr.detail>td{background:var(--sunken);padding:0;border-bottom:1px solid var(--rule)}
/* THE CHART SPANS THE FULL DETAIL WIDTH and sits above the two-column grid.
   Dropped into one of those columns it would render at half width, which on a
   180-session daily chart puts three sessions in a pixel. */
.chart{padding:18px 22px 4px;border-bottom:1px solid var(--ruleSoft)}
.chart svg{display:block;width:100%;height:auto;background:var(--sunken);
  border:1px solid var(--rule);border-radius:8px}
.chart-cap{margin:8px 0 0;font-size:12px;line-height:1.55;max-width:88ch}
.det{padding:20px 22px;display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);
  gap:26px}
@media(max-width:860px){.det{grid-template-columns:1fr}}
.comp{border-top:1px solid var(--ruleSoft);padding:11px 0}
.comp:first-of-type{border-top:0}
.comp .top{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.comp .lab{color:var(--chalk);font-size:13.5px;font-weight:500}
.comp .val{font-size:13.5px;color:var(--chalk)}
.comp .val.off{color:var(--faint);font-size:12px;font-style:italic}
.comp .meta{font-size:11.5px;color:var(--faint);margin-top:3px}
.comp .read{font-size:12.5px;color:var(--ash);margin-top:6px;line-height:1.5}
.fam-price i{background:var(--trend)} .fam-filings i{background:var(--value)}
.fam-register i{background:var(--thesis)}
.blk{background:var(--panel);border:1px solid var(--rule);border-radius:8px;
  padding:13px 15px;margin-bottom:12px}
.blk p{font-size:13px;color:var(--body);margin:0}
.blk p+p{margin-top:8px}
.blk .h{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--faint);
  font-weight:600;margin-bottom:7px}
.gate{border-color:rgba(255,107,107,.4);background:rgba(255,107,107,.06)}
.gate .h{color:var(--dist)}
.pen{display:flex;justify-content:space-between;gap:12px;font-size:12.5px;padding:5px 0}
.pen b{color:var(--dist);font-weight:600;font-family:ui-monospace,monospace}
.pen span{color:var(--ash)}
ul.why{margin:0;padding-left:17px}
ul.why li{font-size:12.5px;color:var(--ash);margin-bottom:7px;line-height:1.5}
.arith{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;
  color:var(--body);line-height:1.9}
.arith b{color:var(--chalk)}
.arith .op{color:var(--faint)}

details{margin-top:14px;border:1px solid var(--rule);border-radius:8px;
  background:var(--panel)}
details summary{padding:11px 15px;cursor:pointer;color:var(--ash);font-size:13px;
  list-style:none}
details summary::-webkit-details-marker{display:none}
details summary:before{content:"+ ";color:var(--faint)}
details[open] summary:before{content:"- "}
details .body{padding:0 15px 14px;font-size:12.5px;color:var(--ash)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{background:var(--sunken);border:1px solid var(--ruleSoft);border-radius:5px;
  padding:3px 7px;font-size:11.5px;color:var(--ash);
  font-family:ui-monospace,monospace}
footer{margin-top:46px;padding-top:18px;border-top:1px solid var(--rule);
  color:var(--faint);font-size:12.5px;max-width:80ch}
"""

JS = """
document.querySelectorAll('tr.row').forEach(function(row){
  row.addEventListener('click', function(){
    var detail = document.getElementById('d-' + row.dataset.i);
    if (detail) detail.classList.toggle('open');
  });
});
"""


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _tone_class(tone: Optional[str]) -> str:
    return f"t-{tone or 'none'}"


def _score_colour(score: Optional[float]) -> str:
    if score is None:
        return "var(--faint)"
    if score >= 60:
        return "var(--acc)"
    if score >= 45:
        return "var(--ash)"
    if score >= 33:
        return "var(--warn)"
    return "var(--dist)"


def _money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    for cut, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= cut:
            return f"{value / cut:,.1f}{suffix}"
    return f"{value:,.0f}"


def _component_block(component: dict) -> str:
    family = component["family"]
    if component["available"]:
        score = component["score"]
        value = f'<span class="val mono">{score:.0f}</span>'
        bar = (f'<div class="bar fam-{family}"><i style="width:{max(2, score):.0f}%">'
               f'</i></div>')
        reading = f'<div class="read">{_e(component.get("reading"))}</div>'
    else:
        word = "refused" if component["refused"] else "not read"
        value = f'<span class="val off">{word}</span>'
        bar = ""
        reading = f'<div class="read">{_e(component.get("reason"))}</div>'
    return f"""<div class="comp">
      <div class="top"><span class="lab">{_e(component['label'])}</span>{value}</div>
      <div class="meta">{_e(FAMILY_WORD[family])} &middot; {_e(component['evidence'])}
        evidence &middot; weight {component['baseWeight']:.1f}</div>
      {bar}{reading}
    </div>"""


FAMILY_WORD = {"price": "price and volume", "filings": "the filings",
               "register": "the share register"}
FAMILY_ORDER = ("price", "filings", "register")


def _chart_block(entry: dict) -> str:
    """The tape, drawn, for a row that says to do something.

    LEADS WITH THE CAPTION, NOT THE PICTURE. A chart with shaded bands on it is
    read as a recommendation by anybody who has seen one before, and the
    sentence saying which of those bands were measured and which are description
    has to arrive before the eye has finished making up its mind.
    """
    chart = entry.get("chart")
    drawn = chartsvg.render(chart, currency=(chart or {}).get("currency") or "")
    if not drawn:
        return ""
    caption = (chart or {}).get("caption") or ""
    profile = ((chart or {}).get("volumeProfile") or {}).get("reading") or ""
    return (f'<div class="chart">{drawn}'
            f'<p class="op chart-cap">{_e(caption)}</p>'
            + (f'<p class="op chart-cap">{_e(profile)}</p>' if profile else "")
            + "</div>")


def _specialists_section(report: dict) -> str:
    """The shortlist, above the ranked table because it is not near the top of it.

    Every name here is by construction unlikely to rank well: the blend shrinks
    toward 50 when its families disagree, and a company whose filings are strong
    and whose price family is weak is exactly that disagreement. Folding these
    into the ordering would hide them again, which is the same reasoning
    `neglect.py` is built on.

    GATED NAMES ARE LISTED WITH THEIR GATES. On the first full Indonesian sweep
    all seven were gated and six of those on turnover alone; printing only the
    ungated ones would have printed nothing.
    """
    block = report.get("specialists") or {}
    rows = list(block.get("tradeable") or []) + list(block.get("gated") or [])
    if not rows:
        return ""

    base = block.get("baseRates") or {}
    cards = []
    for row in rows:
        if row.get("soleListing"):
            where = "no listed rival in"
        elif row.get("onlyRanked"):
            where = f"only measurable of {(row.get('unrankedRivals') or 0) + 1} in"
        else:
            where = f"largest of {row.get('fieldPeers') or '?'} in"
        growth = ("&mdash;" if row.get("revenueCagr") is None
                  else f"{row['revenueCagr'] * 100:+.0f}%/yr")
        facts = [f"{_e(where)} {_e(row.get('industry') or 'an unstated field')}",
                 f"{row.get('yearsProfitable')}/{row.get('yearsAvailable')} yrs profitable"]
        if row.get("terms"):
            facts.append(_e(", ".join(row["terms"])))
        if row.get("netMargin") is not None:
            facts.append(f"{row['netMargin'] * 100:.1f}% net margin")
        if row.get("analysts") is not None:
            facts.append(f"{row['analysts']} analysts")
        price = ""
        if row.get("drawdown") is not None:
            at = (f"at {row['latestClose']:,.0f}, "
                  if row.get("latestClose") is not None else "")
            fall = (f"{abs(row['drawdown']) * 100:.0f}% below its own high"
                    if row["drawdown"] < -0.005 else "at its own high")
            price = (f'<p style="color:var(--faint);font-size:11.5px">{at}{fall} '
                     f'&mdash; this screen does not ask whether that is cheap</p>')
        gates = ""
        if row.get("gates"):
            gates = ('<p style="color:var(--faint);font-size:11.5px">Gated: '
                     + _e("; ".join(g["label"] for g in row["gates"])) + "</p>")
        cards.append(
            f'<div class="blk"><div class="h">{_e(row["ticker"])} '
            f'&mdash; {_e(row.get("name") or "")} <span class="op">{growth}</span></div>'
            f'<p style="color:var(--ash);font-size:11.5px">'
            f'{" &middot; ".join(facts)}</p>'
            f'{price}'
            f'<p>{_e(row.get("summary") or "")}</p>'
            f'{gates}</div>')

    return (
        f'<h2>Profitable specialists nobody is covering</h2>'
        f'<div class="blk" style="max-width:82ch">'
        f'<div class="h">What this list is, and what each part of it is worth</div>'
        f'<p>The largest &mdash; or the only measurable &mdash; scanned name in its '
        f'industry label, profitable in every year its filings cover with cash behind '
        f'the profit, growing revenue in this market\u2019s top quartile, and covered '
        f'by nobody.</p>'
        f'<p>Of the {base.get("scanned", 0)} names scanned, '
        f'{base.get("specialist", 0) * 100:.0f}% are the largest or only measurable '
        f'name in their field, {base.get("compounding", 0) * 100:.0f}% compound on all '
        f'three counts, and {base.get("unattended", 0) * 100:.0f}% are uncovered '
        f'&mdash; the loosest of the three by a distance, which is why each share is '
        f'printed rather than only the intersection.</p>'
        f'<p style="color:var(--ash)">{_e(block.get("note") or "")}</p>'
        f'</div>'
        + "".join(cards))


def _business_block(entry: dict) -> str:
    """What the company sells, where it stands, and what its filings have done.

    ON TOP OF THE ROW RATHER THAN INSIDE IT. Every other block in this detail
    pane is a reading about a company the report never names beyond its ticker,
    which is the gap `field.py` exists to close — and a static HTML file is the
    artifact that outlives a dev server, so it should not be the one surface
    that still cannot say what the business is.
    """
    profile = entry.get("profile") or {}
    place = entry.get("fieldPosition") or {}
    record = entry.get("trackRecord") or {}
    if not (profile or place or record):
        return ""

    parts = []
    summary = profile.get("summary")
    industry = profile.get("industry") or profile.get("sector")
    if summary:
        head = f'<b>{_e(industry)}.</b> ' if industry else ""
        parts.append(f"<p>{head}{_e(summary)}</p>")
    elif profile.get("reading"):
        parts.append(f'<p style="color:var(--ash)">{_e(profile["reading"])}</p>')

    # The words that identify this company and few others. In the written
    # report they are prose rather than controls — nothing here is clickable —
    # so they read as "and these are the words that make it unusual" beside the
    # description they were drawn from.
    terms = entry.get("terms") or []
    if terms:
        parts.append(f'<p style="color:var(--faint);font-size:11.5px">'
                     f'Distinctive in its description: '
                     f'<b>{_e(", ".join(terms))}</b>. Word frequency across this '
                     f'scan, not a classification.</p>')

    staff = profile.get("employees")
    where = profile.get("country")
    if staff or where:
        bits = []
        if staff:
            bits.append(f"{staff:,} employees")
        if where:
            bits.append(_e(where))
        parts.append(f'<p style="color:var(--faint);font-size:11.5px">'
                     f'{" &middot; ".join(bits)}</p>')

    if place.get("reading"):
        parts.append(f'<p style="color:var(--ash)">{_e(place["reading"])}</p>')
    if record.get("available") and record.get("reading"):
        parts.append(f'<p style="color:var(--ash)">{_e(record["reading"])}</p>')

    if not parts:
        return ""
    return ('<div class="blk"><div class="h">What this company does</div>'
            + "".join(parts) + "</div>")


def _detail(index: int, entry: dict) -> str:
    components = "".join(_component_block(c) for c in entry["components"])

    families = entry["families"]
    family_lines = []
    for key in FAMILY_ORDER:
        family = families.get(key)
        if family:
            # The vote is shown whenever it is not a whole one. A family
            # reporting on half its evidence casts half a vote, and a reader
            # checking the arithmetic below cannot reproduce the blend without
            # knowing that.
            vote = family.get("vote", 1.0)
            share = ("" if vote >= 0.999 else
                     f' <span class="op">&times; {vote:.2f} vote '
                     f'({family.get("coverage", 0) * 100:.0f}% of its evidence read)</span>')
            family_lines.append(
                f'<div>{_e(FAMILY_WORD[key]).capitalize()}: '
                f'<b>{family["score"]:.0f}</b> '
                f'<span class="op">from {", ".join(family["members"])}</span>{share}</div>')
        else:
            family_lines.append(
                f'<div class="op">{_e(FAMILY_WORD[key]).capitalize()}: never read</div>')

    raw = entry["rawScore"]
    shrunk = entry["shrunkScore"]
    final = entry["score"]
    arithmetic = "".join(family_lines)
    if raw is not None:
        voting = len([f for f in families.values() if f])
        arithmetic += (
            f'<div><span class="op">the {voting} '
            f'{"family" if voting == 1 else "families"} that read, one vote each</span> '
            f'&rarr; <b>{raw:.1f}</b></div>'
            f'<div><span class="op">&times; {entry["shrink"]["combined"]:.2f} '
            f'evidence shrinkage</span> &rarr; <b>{shrunk:.1f}</b></div>')
        if entry["penaltyTotal"]:
            arithmetic += (f'<div><span class="op">&minus; '
                           f'{entry["penaltyTotal"]:.1f} pre-trade flags</span> '
                           f'&rarr; <b>{final:.1f}</b></div>')

    gates = ""
    for gate in entry["gates"]:
        gates += (f'<div class="blk gate"><div class="h">Gate &mdash; '
                  f'{_e(gate["action"].replace("_", " ").lower())}</div>'
                  f'<p><b>{_e(gate["label"])}.</b> {_e(gate["detail"])}</p></div>')

    penalties = ""
    if entry["penalties"]:
        rows = "".join(
            f'<div class="pen"><span>{_e(p["label"])}<br>'
            f'<span style="color:var(--faint)">{_e(p["why"])}</span></span>'
            f'<b>-{p["points"]:.1f}</b></div>'
            for p in entry["penalties"])
        capped = ('<p style="color:var(--faint);font-size:11.5px;margin-top:8px">'
                  'Total capped: flags are correlated and an uncapped sum would '
                  'count one underlying fact several times.</p>'
                  if entry["penaltyCapped"] else "")
        penalties = (f'<div class="blk"><div class="h">Pre-trade flags that fired'
                     f'</div>{rows}{capped}</div>')

    site = entry.get("structure") or {}
    structure_html = ""
    if site.get("available"):
        structure_html = (
            f'<div class="blk"><div class="h">Where the trade is wrong</div>'
            f'<p>{_e(site.get("reading"))}</p></div>')
    elif site:
        structure_html = (
            f'<div class="blk"><div class="h">Where the trade is wrong</div>'
            f'<p style="color:var(--ash)">{_e(site.get("reason"))} Unmeasured is not '
            f'the same as clear.</p></div>')

    # WHAT TRADING IT COSTS, beside the effects it is being compared against.
    # The measured effects in this app are a few percent; a round trip on a thin
    # Indonesian listing can be more than that, and a gross number presented as
    # though it were net is the quietest way to mislead somebody.
    costs = entry.get("costs") or {}
    if costs.get("available"):
        costs_html = (
            f'<div class="blk"><div class="h">What a round trip costs</div>'
            f'<p>{_e(costs.get("reading"))}</p></div>')
    elif costs:
        costs_html = (
            f'<div class="blk"><div class="h">What a round trip costs</div>'
            f'<p style="color:var(--ash)">{_e(costs.get("reason"))}</p></div>')
    else:
        costs_html = ""

    sector = entry.get("sectorRank") or {}
    if sector.get("percentile") is not None:
        sector_html = (
            f'<div class="blk"><div class="h">Against its own sector</div>'
            f'<p>Ranks {sector["rank"]} of {sector["names"]} scanned '
            f'{_e(sector["sector"])} names &mdash; the '
            f'{sector["percentile"]:.0f}th percentile of its own group. The overall '
            f'rank compares it against the whole market; this asks whether it is '
            f'strong, or in a strong sector.</p></div>')
    elif sector.get("reason"):
        sector_html = (
            f'<div class="blk"><div class="h">Against its own sector</div>'
            f'<p style="color:var(--ash)">{_e(sector["reason"])}. Ranking inside a '
            f'group that small produces a number that looks like the others and means '
            f'far less.</p></div>')
    else:
        sector_html = ""

    earnings = ((entry.get("register") or {}).get("earnings") or {})
    earnings_html = ""
    if earnings.get("available") and earnings.get("soon"):
        earnings_html = (
            f'<div class="blk"><div class="h">Reporting soon</div>'
            f'<p>{_e(earnings.get("reading"))}</p></div>')

    sizing = entry["sizing"]
    if sizing.get("applicable"):
        sizing_html = (
            f'<div class="blk"><div class="h">Mechanical size</div>'
            f'<p><b class="mono">{sizing["weight"] * 100:.1f}%</b> of the sleeve'
            f'{" (capped)" if sizing["capped"] else ""}.</p>'
            f'<p style="color:var(--ash);font-size:12px">{_e(sizing["basis"])}</p></div>')
    else:
        sizing_html = ""

    # The agreement sentence already has its own block six lines up. Repeating it
    # verbatim as the first bullet is the kind of duplication that teaches a
    # reader to skim the list. It stays in the JSON, where the list is consumed
    # on its own.
    agreement_text = entry["agreement"]["text"]
    why = "".join(f"<li>{_e(reason)}</li>" for reason in entry["reasons"]
                  if reason != agreement_text)

    return f"""<tr class="detail" id="d-{index}"><td colspan="9">
      {_chart_block(entry)}
      <div class="det">
      <div>
        {_business_block(entry)}
        <h3>The five components</h3>
        {components}
      </div>
      <div>
        {gates}
        <div class="blk"><div class="h">How the score was built</div>
          <div class="arith">{arithmetic}</div>
        </div>
        <div class="blk"><div class="h">Cross-check</div>
          <p>{_e(entry['agreement']['text'])}</p>
          <p style="color:var(--ash);font-size:12px">
            {_e(entry['shrink']['text'])}</p>
        </div>
        {structure_html}{costs_html}{sector_html}{earnings_html}{penalties}{sizing_html}
        <div class="blk"><div class="h">In order</div>
          <ul class="why">{why}</ul>
        </div>
      </div>
    </div></td></tr>"""


def _row(index: int, entry: dict) -> str:
    score = entry["score"]
    score_html = ("&mdash;" if score is None else
                  f'<span class="score mono" style="color:{_score_colour(score)}">'
                  f'{score:.1f}</span>')
    held = '<span class="held">HELD</span>' if entry.get("held") else ""
    size = entry["sizing"]
    size_html = (f'{size["weight"] * 100:.1f}%' if size.get("applicable") else
                 '<span style="color:var(--faint)">&mdash;</span>')
    # The cross-check cell is the one column that says whether the app's central
    # claim applies to this row at all. A BUY with "one lens only" beside it is a
    # different statement from a BUY with "both", and the table must not make
    # them look alike.
    # THE ENTRY, AS DISTINCT FROM THE ASSET. A name the evidence likes reads
    # identically here whether it is sitting on support or two percent under a
    # ceiling it has failed at three times, and those are not the same trade.
    site = entry.get("structure") or {}
    band = site.get("band") if site.get("available") else None
    ratio = site.get("rewardRisk")
    entry_html = {
        None: '<span style="color:var(--faint)">&mdash;</span>',
        "fine": f'<span class="entry ok">{ratio:.1f}:1</span>' if ratio else "",
        "poor": f'<span class="entry poor">{ratio:.1f}:1</span>' if ratio else "",
        "bad": f'<span class="entry bad">{ratio:.2f}:1</span>' if ratio else "",
        "unbounded": '<span class="entry ok">no ceiling</span>',
        "noSupport": '<span class="entry poor">no floor</span>',
        "riskTooWide": '<span class="entry poor">stop too far</span>',
        # No ratio in this cell, on purpose. A sortable column of reward-to-risk
        # would put exactly the names whose stop is a rounding error at the top
        # of it, which is the ranking this band exists to refuse.
        "riskInsideNoise": '<span class="entry poor">stop in noise</span>',
        "unmeasured": '<span style="color:var(--faint)">&mdash;</span>',
    }.get(band, '<span style="color:var(--faint)">&mdash;</span>')

    cross_html = ('<span class="cross yes" title="Both the price record and the '
                  'filings returned a reading">both</span>'
                  if entry.get("crossChecked") else
                  '<span class="cross no" title="Only one body of data returned a '
                  'reading, so nothing cross-checked this score">one lens only</span>')
    return f"""<tr class="row" data-i="{index}">
      <td><span class="tick mono">{_e(entry['ticker'])}</span>{held}
          <div class="nm">{_e((entry.get('name') or '')[:44])}</div></td>
      <td class="num">{score_html}</td>
      <td><span class="pill {_tone_class(entry['tone'])}">
          {_e(entry['actionLabel'])}</span></td>
      <td><span class="conv {_e(entry['conviction'])}">{_e(entry['conviction'])}</span></td>
      <td>{cross_html}</td>
      <td>{entry_html}</td>
      <td class="num mono">{entry['rank'] or '&mdash;'}</td>
      <td class="num mono">{entry['coverage'] * 100:.0f}%</td>
      <td class="num mono">{size_html}</td>
    </tr>"""


def render(report: dict) -> str:
    counts = report["counts"]
    universe = report["universe"]
    provenance = report["provenance"]
    settings = report["settings"]

    body_rows = "".join(_row(i, v) + _detail(i, v)
                        for i, v in enumerate(report["verdicts"]))

    tally: dict[str, int] = {}
    for entry in report["verdicts"]:
        tally[entry["actionLabel"]] = tally.get(entry["actionLabel"], 0) + 1
    one_family_count = sum(1 for v in report["verdicts"] if not v.get("crossChecked"))
    # The selection warning is true of a shortlist run and false of a full one.
    # Printing it either way would train the reader to skip it on the runs where
    # it is load-bearing.
    # The paragraph about single-source rows is only worth printing when there
    # are some. It read "0 of these rest on one body of data" followed by four
    # lines explaining a situation that had not arisen — and the reason it had
    # not is itself the more interesting fact, so that is what prints instead.
    cross_check_note = (
        f'<p><b>{one_family_count} of these rest on one body of data.</b> Where a '
        f'listing publishes no usable statements &mdash; common among IDX small caps '
        f'&mdash; the value and quality lenses go quiet and the whole verdict comes from '
        f'price history. Those rows are marked '
        f'<span class="cross no">one lens only</span>, and their scores are already '
        f'pulled toward neutral for it. This app exists to cross-check independent '
        f'bodies of data; on those rows it could not.</p>'
        if one_family_count else
        '<p><b>Every row here was cross-checked.</b> At least two of the three '
        'independent bodies of data returned a reading for each one. That is not '
        'usually true of an Indonesian sweep &mdash; small caps routinely publish no '
        'usable statements, which silences both filings lenses &mdash; and it is true '
        'here because the share register reads for almost every listing and stands in '
        'as the second source when the filings do not.</p>')

    selection_note = (
        f'<p><b>The deepened set was pre-selected on the price rank.</b> These '
        f'{counts["deepened"]} names got the four lenses <i>because</i> they already '
        f'ranked in the top of {counts["tradeable"]} tradeable on price and volume, so '
        f'that component is high for nearly all of them by construction. It is not what '
        f'separates these rows from each other &mdash; the other four are.</p>'
        if counts["deepened"] < counts["tradeable"] else
        f'<p><b>Every tradeable name was deepened.</b> All {counts["deepened"]} names '
        f'that cleared the turnover and tick floors got all four lenses and the share '
        f'register, so nothing in this table was pre-selected on its price rank '
        f'&mdash; the ordering below is the blend, not the rank. Rank and score '
        f'genuinely disagree here, which is the point of running the rest.</p>')
    tally_html = " &nbsp;&middot;&nbsp; ".join(
        f"{k}: <b style='color:var(--chalk)'>{v}</b>" for k, v in tally.items())

    # THE MARKET THIS LIST WAS PRODUCED IN. A ranked table produced in a falling
    # market looks identical to one produced in a rising one, because every score
    # in it is cross-sectional — the top of a falling market is still a top.
    # THE MEASUREMENT THAT IS ACTUALLY ABOUT THIS TABLE. The provenance block
    # above covers the price composite — one component of nine. This covers the
    # blend, on the part of it that can be reconstructed without reading the
    # future, and carries its own scope so the coverage is never mistaken for
    # the whole score.
    blend = report.get("blendBacktest") or {}
    if blend.get("available"):
        rows = "".join(
            f'<div class="pen"><span>{t["horizonDays"]}d &mdash; '
            f'IC {t["icMean"]:+.3f} (q={t["icQ"]:.3f}), quintile spread '
            f'{t["spreadMean"] * 100:+.1f}% (q={t["spreadQ"]:.3f})'
            + (f', breakeven round trip {t["breakevenRoundTrip"] * 100:.2f}%'
               if t.get("breakevenRoundTrip") else '')
            + ('' if t.get("signsAgree", True)
               else ' <span style="color:var(--warn)">&mdash; signs disagree</span>')
            + '</span><b style="color:'
            + ("var(--warn)" if (t["icSurvived"] or t["spreadSurvived"])
               else "var(--faint)") + '">'
            + ("survived" if (t["icSurvived"] or t["spreadSurvived"]) else "null")
            + '</b></div>'
            for t in (blend.get("tests") or []))
        cost = blend.get("medianRoundTrip")
        resolved = blend.get("roundTripResolved")
        attempted = blend.get("roundTripAttempted")
        net = ""
        if cost is not None:
            net = (f'<p class="stamp">A quintile spread is gross. The spread estimator '
                   f'resolved for only {resolved} of {attempted} names &mdash; it clears '
                   f'its own noise floor on the widest ones and almost nowhere else '
                   f'&mdash; so the {cost * 100:.2f}% median of those is an UPPER BOUND '
                   f'on a typical cost rather than a measurement of one. The breakeven '
                   f'round trip beside each result is the number this data can support; '
                   f'compare it against your own dealing costs.</p>')
        excluded = "".join(
            f'<div class="pen"><span>{_e(k)}</span>'
            f'<span style="color:var(--faint)">{_e(v)}</span></div>'
            for k, v in (blend.get("excluded") or {}).items())
        blend_html = (
            f'<div class="provenance" style="border-left-color:var(--tech)">'
            f'<h3 style="color:var(--tech)">And what the BLEND is worth &mdash; '
            f'measured on {(blend.get("coverage") or 0) * 100:.0f}% of it</h3>'
            f'<p>{_e(blend.get("headline"))}</p>'
            f'{rows}'
            f'{net}'
            f'<p class="stamp">Five of the nine components cannot be reconstructed on '
            f'a past date at all:</p>{excluded}'
            f'<p class="stamp">The rest is measured prospectively by the scan log '
            f'beside this report, which takes months to say anything.</p></div>')
    else:
        blend_html = (
            f'<div class="provenance" style="border-left-color:var(--tech)">'
            f'<h3 style="color:var(--tech)">The blend has not been backtested</h3>'
            f'<p>{_e(blend.get("reason", "No blend backtest on this checkout."))} '
            f'Until it has, the score below is an ordering of evidence with no '
            f'established relationship to returns.</p></div>')

    market = report.get("regime") or {}
    regime_html = ""
    if market.get("available"):
        tone = {"good": "var(--acc)", "warn": "var(--warn)",
                "bad": "var(--dist)"}.get(market.get("tone"), "var(--ash)")
        regime_html = (
            f'<div class="blk" style="max-width:82ch;border-color:{tone}44">'
            f'<div class="h" style="color:{tone}">The market this list was produced in '
            f'&mdash; {_e(market.get("state"))}</div>'
            f'<p>{_e(market.get("reading"))}</p></div>')

    # HOW MANY BETS THE BUY LIST ACTUALLY IS. A property of the SET, invisible
    # from any row, and the thing a reader is most likely to get wrong by
    # reading sector labels off the table.
    bets = report.get("concentration") or {}
    if bets.get("available"):
        groups = [g for g in (bets.get("clusters") or []) if len(g) > 1]
        cluster_html = ""
        if groups:
            cluster_html = "".join(
                f'<div class="pen"><span>{" &middot; ".join(_e(n) for n in g)}</span>'
                f'<b style="color:var(--ash)">moves together</b></div>' for g in groups)
        concentration_html = (
            f'<div class="blk" style="max-width:82ch">'
            f'<div class="h">Is this buy list one bet?</div>'
            f'<p>{_e(bets.get("reading"))}</p>'
            f'{cluster_html}'
            f'<p style="color:var(--faint)">Quoted on weekly returns, because '
            f'non-synchronous trading attenuates daily correlations between thin names '
            f'and would flatter exactly the concentration this is here to find. On '
            f'daily returns the same list reads '
            f'{bets.get("effectiveBetsDaily", 0):.1f} bets against '
            f'{bets.get("effectiveBets", 0):.1f} weekly. Grouping uses a '
            f'{bets.get("clusterLink", 0):.2f} link, which is a drawn line rather than '
            f'a measured one &mdash; at '
            + ", ".join(f"{k} it would be {v} group{'' if v == 1 else 's'}"
                        for k, v in (bets.get("clusterSensitivity") or {}).items())
            + '. The bet count uses no threshold at all, which is why it is the '
              'headline.</p></div>')
    elif bets:
        concentration_html = (
            f'<div class="blk" style="max-width:82ch">'
            f'<div class="h">Is this buy list one bet?</div>'
            f'<p style="color:var(--ash)">{_e(bets.get("reason"))}</p></div>')
    else:
        concentration_html = ""

    stale = universe.get("staleness") or {}
    stale_html = (f'<p class="note{" stale" if stale.get("stale") else ""}">'
                  f'{_e(stale.get("text"))}</p>' if stale.get("text") else "")

    rejected: dict[str, int] = counts.get("rejectedByReason", {})
    reject_words = {
        "history": "too little price history for a 252-day cross-sectional window",
        "illiquid": "below the turnover floor",
        "turnoverUnknown": "no usable volume history, so tradeability is unmeasured",
        "tickFloor": "resting on the exchange's minimum tick",
    }
    reject_rows = "".join(
        f'<div class="pen"><span>{_e(reject_words.get(k, k))}</span>'
        f'<b style="color:var(--ash)">{v}</b></div>'
        for k, v in sorted(rejected.items(), key=lambda kv: -kv[1]))

    not_deepened = report.get("notDeepened") or []
    not_deepened_chips = "".join(
        f'<span class="chip">{_e(r["ticker"])} #{r["rank"]}</span>'
        for r in not_deepened[:120])

    overlap = report.get("signalOverlap") or {}
    overlap_html = (f'<p>{_e(overlap.get("reading"))}</p>'
                    if overlap.get("available") else
                    f'<p>{_e(overlap.get("reason", "Not measured on this scan."))}</p>')

    # WHETHER THE THREE FAMILIES ARE ACTUALLY THREE SOURCES. The score weights
    # them equally on the argument that they read different data; this is the
    # measurement that checks it. It renders next to the signal overlap because
    # the two answer the same question at different levels.
    family = report.get("familyOverlap") or {}
    if family.get("available"):
        rows = "".join(
            f'<div class="pen"><span>{_e(pair["aLabel"])} vs {_e(pair["bLabel"])} '
            f'<span style="color:var(--faint)">({pair["names"]} names)</span></span>'
            f'<b style="color:var(--ash)">{pair["correlation"]:+.2f}</b></div>'
            for pair in family["pairs"])
        family_html = f'<p>{_e(family.get("reading"))}</p>{rows}'
    else:
        family_html = (f'<p>{_e(family.get("reason", "Not measured on this scan."))}</p>'
                       if family else "<p>Not measured on this scan.</p>")

    study = report.get("patternStudy") or {}
    if study.get("patterns"):
        rows = []
        for spec in study["patterns"].values():
            best = spec.get("forward")
            if best:
                verdict_cell = (f'<b style="color:var(--dist)">'
                                f'{best["meanExcess"] * 100:+.1f}%</b> over '
                                f'{best["horizonDays"]}d')
            else:
                verdict_cell = '<span style="color:var(--faint)">no surviving horizon</span>'
            rate = spec.get("firingRate")
            rows.append(
                f'<div class="pen"><span>{_e(spec["label"])}'
                + (f' <span style="color:var(--faint)">&mdash; present in '
                   f'{rate * 100:.0f}% of names in a quarter</span>' if rate is not None
                   else "")
                + f'</span><span>{verdict_cell}</span></div>')
        survived = study.get("survived", 0)
        negative = [p for p in study["patterns"].values()
                    if (p.get("forward") or {}).get("meanExcess", 0) < 0]
        finding = ""
        if survived and len(negative) == survived:
            finding = (
                '<p><b>Every formation that survived predicted UNDERperformance</b>, '
                'whichever way the chart books read it &mdash; a head-and-shoulders and '
                'its bullish mirror image measured the same. What a five-point pattern '
                'needs is five turning points in thirty-five sessions, which only a stock '
                'going nowhere provides. The shape is a marker of chop, not a forecast, '
                'and this scanner scores it by the measured sign rather than the '
                'textbook one.</p>')
        pattern_html = (
            f'<p>Measured across {study.get("names")} names over {study.get("years")} '
            f'years in {_e(study.get("population"))}: {study.get("detections")} '
            f'detections, {study.get("tests")} tests, '
            f'<b style="color:var(--chalk)">{survived}</b> surviving a '
            f'false-discovery correction &mdash; against '
            f'{study.get("expectedByChance")} expected by chance before it.</p>'
            f'{finding}{"".join(rows)}')
    else:
        pattern_html = ('<p>No pattern study has been run for this market. Formations are '
                        'detected and score nothing. Run '
                        '<code>scripts/calibrate_patterns.py</code>.</p>')

    tape_stats = report.get("tapeSignificance") or {}
    if tape_stats.get("tested"):
        fired, expected = tape_stats["fired"], tape_stats["expectedByChance"]
        excess = max(0.0, fired - expected)
        tape_html = (
            f'<p>{_e(tape_stats.get("note"))}</p>'
            f'<p>Of the {fired} that fired, roughly <b style="color:var(--chalk)">'
            f'{excess:.0f}</b> are the real signal and <b style="color:var(--chalk)">'
            f'{min(fired, expected):.0f}</b> are chance. Which is which is not knowable '
            f'from this scan, so a single accumulation verdict below is worth rather '
            f'less than the sentence attached to it sounds.</p>')
    else:
        tape_html = (f'<p>{_e(tape_stats.get("note", "No tape reading on this scan."))}'
                     f'</p>')

    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(report['market'])} scan &mdash; {_e(report['generatedAt'][:10])}</title>
<style>{CSS}</style>
<div class="wrap">
  <h1>{_e(report['market'])} market scan</h1>
  <p class="sub">{_e(report['generatedAt'].replace('T', ' '))} &middot;
    {_e(universe.get('label'))} &middot; {report['elapsedSeconds']}s</p>

  <div class="provenance">
    <h3>What this ordering is worth &mdash; read before the table</h3>
    <p>{_e(provenance.get('headline'))}</p>
    {f"<p>That measurement applies to {_e(provenance.get('appliesTo'))}</p>"
     if provenance.get('appliesTo') else ""}
    <p class="stamp">Measured {_e(provenance.get('measuredOn'))} over
      {_e(provenance.get('years'))} years, {_e(provenance.get('tests'))} tests,
      {_e(provenance.get('significant'))} significant after correction.</p>
  </div>

  {regime_html}

  {blend_html}

  <div class="funnel">
    <div><div class="n">{counts['requested']}</div><div class="k">listed</div>
      <div class="w">{_e(universe.get('label'))}</div></div>
    <div><div class="n">{counts['fetched']}</div><div class="k">fetched</div>
      <div class="w">returned usable price history</div></div>
    <div><div class="n">{counts['tradeable']}</div><div class="k">tradeable</div>
      <div class="w">cleared a {_money(settings['turnoverFloor'])} daily turnover
        floor and the tick floor</div></div>
    <div><div class="n">{counts['deepened']}</div><div class="k">deepened</div>
      <div class="w">got all four lenses and the share register, one fetch at a
        time</div></div>
  </div>
  {stale_html}
  <p class="note">{tally_html}</p>
  {concentration_html}

  {_specialists_section(report)}

  <h2>Ranked</h2>
  <div class="blk" style="max-width:82ch">
    <div class="h">Two things about this table before you compare rows</div>
    {selection_note}
    {cross_check_note}
  </div>
  <p class="note">Click any row for the arithmetic behind its score &mdash; the five
    components, both family readings, the shrinkage, every flag and every gate.</p>
  <div class="tablewrap">
  <table>
    <thead><tr>
      <th>Name</th><th class="num">Score</th><th>Action</th><th>Conviction</th>
      <th>Cross-check</th><th>Entry</th><th class="num">Rank</th>
      <th class="num">Coverage</th><th class="num">Size</th>
    </tr></thead>
    <tbody>{body_rows}</tbody>
  </table>
  </div>

  <details><summary>How much of this table is one opinion wearing seven labels</summary>
    <div class="body">{overlap_html}</div></details>

  <details><summary>Are the three bodies of data actually three bodies of data</summary>
    <div class="body">
      <p>Every score above weights the price record, the filings and the share register
         equally, on the argument that they read different numbers. That is an
         assumption, so here it is measured across this scan rather than asserted.
         The share register has the weakest claim of the three &mdash; the share count
         is printed in the filings, and what is actually true is only that no filings
         lens reads it.</p>
      {family_html}
    </div></details>

  <details><summary>What the chart formations actually predicted</summary>
    <div class="body">
      <p>Head-and-shoulders, broadening, triangle, rectangle and double formations,
         defined by Lo, Mamaysky and Wang's kernel-regression method so that two
         implementations agree rather than by thresholds somebody picked. Detected in a
         rolling window with a confirmation lag, so nothing at day t uses a price from
         day t+1.</p>
      {pattern_html}
      <p style="color:var(--faint)">Flags, pennants, wedges and cup-and-handle are
         still refused: none has a numeric definition that survives two stocks of
         different volatility, and Lo, Mamaysky and Wang never gave them one.</p>
    </div></details>

  <details><summary>How many of the heavy-day readings are real</summary>
    <div class="body">
      <p>The tape test asks whether a name's heaviest sessions close nearer the high of
         their range than its ordinary ones, against that market's own median. One
         name's p-value needs no correction. A scan of hundreds does, and this is the
         count that makes the correction legible.</p>
      {tape_html}
      <p style="color:var(--faint)">This is not a broker summary. It cannot say who
         bought, cannot separate foreign from domestic money, and cannot tell a
         pre-arranged cross from open trading &mdash; the three things the exchange's
         own daily file would settle.</p>
    </div></details>

  <details><summary>{counts['rejected']}
    {"name" if counts['rejected'] == 1 else "names"} never reached the ranking</summary>
    <div class="body">
      <p>Dropped before any scoring, for reasons that are facts about the order book
         rather than judgements about the company. An absent name is not a bad name.</p>
      {reject_rows}
    </div></details>

  <details><summary>{len(not_deepened)} ranked but not deepened
    {"(showing the first 120)" if len(not_deepened) > 120 else ""}</summary>
    <div class="body">
      <p>These cleared every tradeability gate and were ranked on price signals, but
         the four filings-and-flow lenses were never run on them &mdash; the scan
         deepens a shortlist because each name costs its own fetch. Their absence
         from the table above says nothing about them.</p>
      <div class="chips">{not_deepened_chips}</div>
    </div></details>

  <footer>
    <p><b>Not investment advice.</b> This is a private research tool. Every score above
       is a blend of measurements taken from price history and the last published
       filing, ordered by a formula written by its user. It does not know what this
       company does, who runs it, what it announced this morning, or anything else
       that decides what a share is worth. The one predictive claim it could be read
       as making has been measured, and the measurement is at the top of this page.</p>
    <p>Universe as of {_e(universe.get('asOf') or 'unknown')}. Prices and filings from
       Yahoo Finance, an unofficial source with no service guarantee.</p>
  </footer>
</div>
<script>{JS}</script>
"""


if __name__ == "__main__":
    import sys
    from pathlib import Path
    source = Path(sys.argv[1])
    target = source.with_suffix(".html")
    target.write_text(render(json.loads(source.read_text())))
    print(target)
