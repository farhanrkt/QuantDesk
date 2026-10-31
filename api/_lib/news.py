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

import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Optional

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


# The feed's language and edition per market: Indonesian for IDX, English otherwise.
_EDITION = {"ID": ("id", "ID", "ID:id"), "US": ("en", "US", "US:en")}


def _search_url(query: str, market: str) -> str:
    hl, gl, ceid = _EDITION.get(market, _EDITION["US"])
    params = urllib.parse.urlencode({"q": query, "hl": hl, "gl": gl, "ceid": ceid})
    return f"https://news.google.com/rss/search?{params}"


def _feed_url(symbol: str) -> str:
    code = symbols.base_code(symbol)
    if symbols.market_of(symbol) == "ID":
        return _search_url(f"{code}+saham", "ID")
    return _search_url(f"{code}+stock", "US")


# One megabyte. Google's RSS for a single ticker runs about 25 KB; this is the
# ceiling that stops a hostile or broken upstream from deciding how much memory
# this function allocates.
MAX_FEED_BYTES = 1_048_576

# Entity declarations are refused outright rather than expanded.
#
# `xml.etree.ElementTree` does not resolve EXTERNAL entities, so there is no XXE
# here — verified against `file:///etc/passwd`, which raises rather than reads.
# It does expand INTERNAL ones, which is the billion-laughs shape: a few hundred
# bytes of nested declarations expands without bound inside the parser. Measured
# on this parser before the fix, a three-level nest expanded 300x from under 400
# bytes, and the nesting depth is the sender's to choose.
#
# REFUSED BY INSPECTION RATHER THAN BY A PARSER HOOK, because Python 3.12's
# `XMLParser` does not expose the underlying expat parser — there is no
# `EntityDeclHandler` to install. A feed has no legitimate reason to declare a
# doctype at all, so the declaration is rejected before parsing begins. A false
# positive costs the news panel one fetch, which already degrades to an empty
# list; there is no failure mode worse than that.
_DECLARATION = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)", re.IGNORECASE)


def _parse_feed(raw: bytes) -> ET.Element:
    """Parse a feed, refusing any payload that declares entities."""
    if _DECLARATION.search(raw):
        raise ET.ParseError("entity or doctype declarations are not accepted in a feed")
    return ET.fromstring(raw)


def _text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    return (node.text or "").strip() if node is not None else ""


def _fetch_feed(url: str) -> bytes:
    """The raw feed, or an exception. Every caller decides what a failure means."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT, context=_ssl_context()) as response:
        if getattr(response, "status", 200) != 200:
            raise OSError(f"feed answered {getattr(response, 'status', '?')}")
        # BOUNDED READ. `response.read()` with no argument will happily pull
        # a multi-gigabyte body into a serverless function's memory, and the
        # size is chosen by whoever is on the other end of the socket. A
        # timeout does not help: a slow drip inside the timeout still fills
        # memory. One megabyte is roughly forty times the largest real feed.
        raw = response.read(MAX_FEED_BYTES + 1)
    if len(raw) > MAX_FEED_BYTES:
        raise OSError("feed exceeded the size cap")
    return raw


def _items(root: ET.Element, limit: Optional[int] = None) -> list[dict]:
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
        if limit is not None and len(items) >= limit:
            break
    return items


def fetch_news(symbol: str, limit: int = MAX_ITEMS) -> list[dict]:
    """Recent headlines for `symbol`. Returns [] on any network or parse failure."""
    try:
        root = _parse_feed(_fetch_feed(_feed_url(symbol)))
    except Exception:
        # Network error, timeout, DNS failure, malformed XML -> no news, no crash.
        return []
    return _items(root, limit)


# --------------------------------------------------------------------------- #
# Market headlines, for the board of what moved the markets
# --------------------------------------------------------------------------- #
# DECLARED TOPICS, NOT FREE TEXT. `/api/markets/headlines` accepts a key from
# this table and nothing else, so a request cannot steer the query and every
# URL the edge caches is one of a few dozen. Indonesian readers get Indonesian
# queries, chosen by reading what each returns on 1 November 2026: "IHSG",
# "harga minyak", "harga emas" and "rupiah" all returned a day's worth of
# Indonesian financial press.
HEADLINE_TOPICS: dict[str, dict[str, str]] = {
    "market": {"US": "stock market", "ID": "IHSG"},
    "rates": {"US": "Treasury yields", "ID": "suku bunga"},
    "dollar": {"US": "dollar index", "ID": "dolar AS"},
    "rupiah": {"US": "Indonesian rupiah", "ID": "rupiah"},
    "oil": {"US": "oil prices", "ID": "harga minyak"},
    "gas": {"US": "natural gas prices", "ID": "harga gas"},
    "gold": {"US": "gold prices", "ID": "harga emas"},
    "silver": {"US": "silver prices", "ID": "harga perak"},
    "copper": {"US": "copper prices", "ID": "harga tembaga"},
    "bitcoin": {"US": "bitcoin", "ID": "bitcoin"},
}

# Google's search operator for "published in the past day". A market board is
# about today; a relevance-ranked feed otherwise leads with last month's story.
RECENT = "when:1d"


def _published(item: dict) -> float:
    try:
        return parsedate_to_datetime(item["published"]).timestamp()
    except (TypeError, ValueError, IndexError, KeyError):
        return float("-inf")


def fetch_headlines(topic: str, market: str = "US", limit: int = MAX_ITEMS) -> dict:
    """The past day's headlines that mention a market, newest first.

    A FAILURE IS NOT "NO NEWS". `fetch_news` returns an empty list either way,
    which is how the news panel once looked identical whether a company had no
    coverage or the feed had failed. This says which: `available` is False when
    the feed could not be read, and True with an empty list when it was read and
    held nothing from the past day.

    The order is by time, newest first. Google ranks the feed by relevance, and
    a board of what moved today should not lead with the most-linked story of
    the week.
    """
    queries = HEADLINE_TOPICS[topic]
    market = (market or "US").strip().upper()
    edition = market if market in queries else "US"
    query = queries[edition]
    try:
        root = _parse_feed(_fetch_feed(_search_url(f"{query} {RECENT}", edition)))
    except Exception:
        return {"topic": topic, "market": market, "query": query, "available": False,
                "items": [],
                "reason": "The news feed could not be read just now, which is not the same "
                          "as there being no news."}
    items = sorted(_items(root), key=_published, reverse=True)[:limit]
    return {"topic": topic, "market": market, "query": query, "available": True,
            "items": items,
            "reason": None if items else "The feed held no headlines from the past day."}
