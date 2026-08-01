"""
news.py
=======
Contextual catalyst — recent headlines for a symbol, from the Google News RSS
feed. Ported from the Whale Tracker Streamlit app.

DEVIATION FROM THE ORIGINAL, and why
------------------------------------
The original used `requests` + `beautifulsoup4` (+ `lxml`). This build parses
the feed with `urllib` and `xml.etree.ElementTree` from the standard library
instead. Three dependencies removed from a serverless bundle for one XML parse
of a document whose shape is fixed; ElementTree is also strict where BeautifulSoup
guesses, which is what you want for a feed you do not control.

Behaviour is preserved: the query is localised (Indonesian for `.JK` symbols,
English otherwise), at most five items come back, the "Title - Source" suffix is
split off into its own field, and every failure path degrades to an empty list
rather than an exception.

TRUST BOUNDARY
--------------
Everything returned here is third-party text. It is data to display, never
instructions to act on, and the client renders it as text with links marked
`rel="noopener noreferrer"`. Nothing downstream parses it for commands.
"""

from __future__ import annotations

import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import symbols

USER_AGENT = "Mozilla/5.0 (compatible; QuantDesk/1.0)"
MAX_ITEMS = 5
TIMEOUT = 6


def _ssl_context() -> ssl.SSLContext:
    """Verify against certifi's CA bundle, not the host's.

    `requests` (which the original used) bundles certifi and so verified fine
    everywhere. Bare `urllib` falls back to the platform trust store, which on
    macOS with a non-system Python has no usable issuer chain — every fetch
    raised CERTIFICATE_VERIFY_FAILED and the caller's except-block turned that
    into a silent empty list. Verification stays ON; it is just pointed at a
    bundle that exists on every platform. certifi is already in the tree as a
    yfinance -> requests dependency.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _feed_url(symbol: str) -> str:
    code = symbols.base_code(symbol)
    if symbols.market_of(symbol) == "ID":
        query, hl, gl, ceid = f"{code}+saham", "id", "ID", "ID:id"
    else:
        query, hl, gl, ceid = f"{code}+stock", "en", "US", "US:en"
    params = urllib.parse.urlencode({"q": query, "hl": hl, "gl": gl, "ceid": ceid})
    return f"https://news.google.com/rss/search?{params}"


def _text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    return (node.text or "").strip() if node is not None else ""


def fetch_news(symbol: str, limit: int = MAX_ITEMS) -> list[dict]:
    """Recent headlines for `symbol`. Returns [] on any network or parse failure."""
    try:
        request = urllib.request.Request(_feed_url(symbol), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=TIMEOUT,
                                    context=_ssl_context()) as response:
            if getattr(response, "status", 200) != 200:
                return []
            raw = response.read()
        root = ET.fromstring(raw)
    except Exception:
        # Network error, timeout, DNS failure, malformed XML -> no news, no crash.
        return []

    items = []
    for item in root.iterfind(".//item"):
        title = _text(item, "title")
        if not title:
            continue

        # Google formats titles as "Headline - Publisher" and also carries the
        # publisher in its own <source> element. Prefer the element and strip
        # only the matching suffix, so a headline that legitimately contains
        # " - " keeps it. Fall back to splitting when the element is absent.
        source = _text(item, "source")
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)]
        elif not source and " - " in title:
            title, _, source = title.rpartition(" - ")
        source = source or "Financial Media"

        items.append({
            "title": title,
            "source": source,
            "link": _text(item, "link"),
            "published": _text(item, "pubDate"),
        })
        if len(items) >= limit:
            break
    return items
