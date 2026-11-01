"""
chartsvg.py
===========
The annotated chart as a standalone SVG, for the scan report.

WHY A SECOND RENDERER
----------------------
`components/AnnotatedChart.tsx` draws the same chart in the app, and duplicating
a drawing is normally how two views come to disagree. The duplication here is
deliberate and narrow, and the thing that makes it safe is that neither renderer
DECIDES anything: both consume `chartlayers.build()`, which is the single source
of every level, band, formation and heavy session. One geometry, two media.

The alternative was worse in both directions. Shipping recharts inside the scan
report would mean a megabyte of JavaScript in a file whose whole point is to be
one self-contained artifact that opens from disk with no server; driving a
headless browser per name would make a hundred-name report a twenty-minute
render that fails when Chrome updates.

WHAT IS DELIBERATELY NOT DRAWN HERE
------------------------------------
This is a REPORT chart, read at a glance beside forty others, not the app's
interactive one. Everything that needs a tooltip, a toggle or a legend to be
understood is left out: no Bollinger band, no moving averages beyond the slow
one, no pattern construction lines, no heavy-session scatter. What survives is
what answers "should I open this name's full reading" — the shape of the year,
where the trade is wrong, and where the year's volume actually sat.

The app is the place to interrogate a name. This is the place to decide which
name to interrogate.
"""

from __future__ import annotations

from typing import Optional

# Canvas, in user units. Wide and short: the report stacks these under table
# rows, where vertical space is the scarce resource and a tall chart pushes the
# next name off the screen.
WIDTH, HEIGHT = 720, 180
# The right gutter holds a price and a touch count — "21,825 · 1x" — and at 62
# the widest of those clipped against the frame. Measured off a rendered chart,
# not guessed.
PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 4, 78, 8, 14

# The same hues the app uses, so a reader moving between the two is not
# relearning the palette.
UP, DOWN = "#35C4A8", "#FF6B6B"
SLOW_MA = "#7387A0"
SUPPORT, RESISTANCE = "#80CBC4", "#EF9A9A"
PROFILE = "#4DD0E1"
PATTERN = "#A78BFA"
RULE, TEXT, FAINT = "#1E2A36", "#C3CFDC", "#7387A0"


def _e(value) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def render(chart: Optional[dict], currency: str = "") -> str:
    """One name's tape as inline SVG, or an empty string.

    Returns "" rather than a placeholder when there is nothing to draw: the
    report's layout already handles a missing chart, and an empty frame with
    axes on it reads as "this name has no price history", which is never why
    this returns nothing.
    """
    if not isinstance(chart, dict) or not chart.get("available"):
        return ""
    bars = [bar for bar in (chart.get("bars") or [])
            if _finite(bar.get("high")) is not None and _finite(bar.get("low")) is not None]
    if len(bars) < 5:
        return ""

    trade = chart.get("trade") or {}
    profile = chart.get("volumeProfile") or {}
    levels = chart.get("levels") or []

    # THE DOMAIN COVERS EVERY ANNOTATION, not just the candles — the same rule
    # the app's chart follows, and for the same reason: a stop just under the
    # window's low is exactly the line a reader needs and exactly the one that
    # gets clipped.
    values: list[float] = []
    for bar in bars:
        values.extend([bar["high"], bar["low"]])
    for level in levels:
        if _finite(level.get("price")) is not None:
            values.append(level["price"])
    for key in ("stop", "target", "entry"):
        if _finite(trade.get(key)) is not None:
            values.append(trade[key])
    area = profile.get("valueArea") or {}
    for key in ("low", "high"):
        if _finite(area.get(key)) is not None:
            values.append(area[key])
    low, high = min(values), max(values)
    if high <= low:
        return ""
    pad = (high - low) * 0.04
    low, high = low - pad, high + pad

    plot_w = WIDTH - PAD_LEFT - PAD_RIGHT
    plot_h = HEIGHT - PAD_TOP - PAD_BOTTOM
    step = plot_w / len(bars)

    def x_of(index: int) -> float:
        return PAD_LEFT + index * step + step / 2.0

    def y_of(price: float) -> float:
        return PAD_TOP + (high - price) / (high - low) * plot_h

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="100%" height="{HEIGHT}" role="img" '
        f'aria-label="Price, levels and volume bands for the last '
        f'{len(bars)} sessions">'
    ]

    def band(y1: float, y2: float, fill: str, opacity: float) -> None:
        top, bottom = sorted((y_of(y1), y_of(y2)))
        top, bottom = max(top, PAD_TOP), min(bottom, PAD_TOP + plot_h)
        if bottom - top <= 0:
            return
        parts.append(f'<rect x="{PAD_LEFT}" y="{top:.1f}" width="{plot_w:.1f}" '
                     f'height="{bottom - top:.1f}" fill="{fill}" '
                     f'fill-opacity="{opacity}"/>')

    # --- behind the candles: volume bands, then the trade ------------------
    if _finite(area.get("low")) is not None and _finite(area.get("high")) is not None:
        band(area["low"], area["high"], PROFILE, 0.05)
    control = profile.get("pointOfControl") or {}
    if _finite(control.get("low")) is not None and _finite(control.get("high")) is not None:
        band(control["low"], control["high"], PROFILE, 0.28)
    for shelf in (profile.get("shelves") or []):
        if _finite(shelf.get("low")) is not None and _finite(shelf.get("high")) is not None:
            band(shelf["low"], shelf["high"], PROFILE, 0.10)

    entry = _finite(trade.get("entry"))
    if entry is not None and _finite(trade.get("stop")) is not None:
        band(trade["stop"], entry, DOWN, 0.09)
    if entry is not None and _finite(trade.get("target")) is not None:
        band(entry, trade["target"], UP, 0.09)

    # --- the most recent formation's window, as a tint ---------------------
    # ONE FORMATION, NOT ALL OF THEM. The app draws one at a time behind a
    # selector; a static chart has no selector, and a choppy name carries six.
    # Tinting all six turned this chart into vertical stripes with the price
    # somewhere behind them — visible immediately on the first render, and the
    # reason the report gets the latest completion only.
    dates = [bar["date"] for bar in bars]
    latest = sorted((shape for shape in (chart.get("patterns") or [])
                     if shape.get("fromDate") and shape.get("toDate")),
                    key=lambda shape: shape.get("detectedAt") or "")[-1:]
    for shape in latest:
        if not (shape.get("fromDate") and shape.get("toDate")):
            continue
        try:
            start, finish = dates.index(shape["fromDate"]), dates.index(shape["toDate"])
        except ValueError:
            continue
        parts.append(
            f'<rect x="{x_of(start):.1f}" y="{PAD_TOP}" '
            f'width="{max(x_of(finish) - x_of(start), 1):.1f}" height="{plot_h:.1f}" '
            f'fill="{PATTERN}" fill-opacity="0.09"/>')

    # --- levels -------------------------------------------------------------
    for level in levels:
        price = _finite(level.get("price"))
        if price is None or not (low <= price <= high):
            continue
        hue = SUPPORT if level.get("side") == "support" else RESISTANCE
        nearest = bool(level.get("nearest"))
        y = y_of(price)
        parts.append(
            f'<line x1="{PAD_LEFT}" x2="{PAD_LEFT + plot_w:.1f}" y1="{y:.1f}" '
            f'y2="{y:.1f}" stroke="{hue}" stroke-width="{1.2 if nearest else 0.8}" '
            f'stroke-opacity="{0.85 if nearest else 0.3}"'
            + ("" if nearest else ' stroke-dasharray="4 4"') + "/>")
        parts.append(
            f'<text x="{PAD_LEFT + plot_w + 4:.1f}" y="{y + 3:.1f}" font-size="9" '
            f'fill="{TEXT if nearest else FAINT}" font-family="ui-monospace, monospace">'
            f'{_e(f"{price:,.0f}")} · {int(level.get("touches") or 0)}x</text>')

    # --- the slow average, where the window carries one ---------------------
    slow = [(x_of(i), y_of(bar["sma200"]))
            for i, bar in enumerate(bars) if _finite(bar.get("sma200")) is not None]
    if len(slow) > 2:
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in slow)
        parts.append(f'<polyline points="{points}" fill="none" stroke="{SLOW_MA}" '
                     f'stroke-width="1" stroke-opacity="0.7"/>')

    # --- candles ------------------------------------------------------------
    # FOUR PATHS, NOT SEVEN HUNDRED ELEMENTS. Drawn one rect and one line per
    # session, a 180-bar chart is roughly 370 SVG nodes and 38KB; a hundred of
    # them took the scan report from 2.1MB to 5.9MB, which is a file that opens
    # slowly and a diff nobody can read. Every up-wick shares a stroke and every
    # up-body shares a fill, so each of those four groups is one path and the
    # same drawing costs about a fifth as much.
    #
    # A BODY AND A WICK SURVIVE AT SUB-PIXEL WIDTH. At 180 sessions across 650
    # units each candle is 3.6 wide, so the body keeps a minimum height of half
    # a unit — without it a doji vanishes and a quiet stretch reads as a gap in
    # the data rather than as a quiet stretch.
    body_w = max(step * 0.62, 0.8)
    wicks: dict[str, list[str]] = {UP: [], DOWN: []}
    bodies: dict[str, list[str]] = {UP: [], DOWN: []}
    for position, bar in enumerate(bars):
        open_, close = _finite(bar.get("open")), _finite(bar.get("close"))
        if open_ is None or close is None:
            continue
        x = x_of(position)
        hue = UP if close >= open_ else DOWN
        wicks[hue].append(f'M{x:.1f} {y_of(bar["high"]):.1f}V{y_of(bar["low"]):.1f}')
        top = y_of(max(open_, close))
        height = max(abs(y_of(close) - y_of(open_)), 0.5)
        left = x - body_w / 2
        bodies[hue].append(f'M{left:.1f} {top:.1f}h{body_w:.1f}v{height:.1f}'
                           f'h-{body_w:.1f}Z')

    for hue in (UP, DOWN):
        if wicks[hue]:
            parts.append(f'<path d="{"".join(wicks[hue])}" fill="none" stroke="{hue}" '
                         f'stroke-width="0.7" stroke-opacity="0.75"/>')
        if bodies[hue]:
            parts.append(f'<path d="{"".join(bodies[hue])}" fill="{hue}" '
                         f'fill-opacity="0.9"/>')

    # --- the dates at either end, and nothing between ----------------------
    parts.append(f'<text x="{PAD_LEFT}" y="{HEIGHT - 3}" font-size="9" fill="{FAINT}" '
                 f'font-family="ui-monospace, monospace">{_e(bars[0]["date"])}</text>')
    parts.append(f'<text x="{PAD_LEFT + plot_w:.1f}" y="{HEIGHT - 3}" font-size="9" '
                 f'fill="{FAINT}" text-anchor="end" '
                 f'font-family="ui-monospace, monospace">'
                 f'{_e(bars[-1]["date"])}{(" · " + _e(currency)) if currency else ""}'
                 f'</text>')

    parts.append("</svg>")
    return "".join(parts)
