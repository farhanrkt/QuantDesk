"""
lang.py
=======
Which language a request is answered in, and the one helper that picks it.

TWO LANGUAGES, CHOSEN PER REQUEST. English and Bahasa Indonesia. The reader
chooses in the browser; every request then carries `lang=id` (or nothing, for
English), the middleware in `api/index.py` sets it here for the life of that
request, and every sentence the server writes asks `tr(english, indonesian)`.

WHY INLINE PAIRS AND NOT A CATALOG. A sentence here is usually an f-string with
figures in it, chosen by branches that depend on those figures. A catalog keyed
by template would need every f-string rewritten as a format call and would put
the Indonesian in a file nobody reads beside the English. A pair keeps the two
side by side, built from the same values, so whoever changes one sees the other.

WHAT IS NEVER TRANSLATED: identifiers. Band names, tones, verdict codes, lens
keys and anything a client compares against stay English in both languages —
only the prose a reader reads changes. `tests/test_language.py` holds both
halves: English output is unchanged, and Indonesian output carries no English.

CONTEXT-LOCAL, NOT GLOBAL. A contextvar, so two requests on one warm instance
cannot answer in each other's language. It follows the request into FastAPI's
worker threads and into `asyncio.to_thread`; a bare `ThreadPoolExecutor` does
not carry it, so a route that fans out through one wraps the work in `carry`.
"""

from __future__ import annotations

import contextvars
import re
from collections.abc import Mapping
from typing import Callable, Iterator, TypeVar

SUPPORTED = ("en", "id")
DEFAULT = "en"

_current: contextvars.ContextVar[str] = contextvars.ContextVar("quantdesk_lang",
                                                               default=DEFAULT)

T = TypeVar("T")


def normalise(value) -> str:
    """A supported language code, or English for anything else."""
    text = str(value or "").strip().lower()[:2]
    return text if text in SUPPORTED else DEFAULT


def current() -> str:
    return _current.get()


def use(value) -> contextvars.Token:
    """Answer in `value` until the returned token is reset."""
    return _current.set(normalise(value))


def reset(token: contextvars.Token) -> None:
    _current.reset(token)


def tr(en: str, id_: str) -> str:
    """The English or the Indonesian, whichever this request asked for."""
    return id_ if _current.get() == "id" else en


def carry(fn: Callable[..., T]) -> Callable[..., T]:
    """`fn`, answering in this request's language from whatever thread runs it.

    Each call sets and resets its own value rather than sharing one copied
    context, because a context object cannot be entered by two threads at once
    and a pool runs several calls together.
    """
    language = _current.get()

    def run(*args, **kwargs):
        token = _current.set(language)
        try:
            return fn(*args, **kwargs)
        finally:
            _current.reset(token)

    return run


class Bilingual(Mapping):
    """A module-level table of prose, answering in the request's language.

    A string written at module level is evaluated once, at import, in whatever
    language the importing thread happened to have — English, always — so
    `tr()` cannot be used there. A table whose values are (english, indonesian)
    pairs defers the choice to the lookup instead: `TABLE[key]` and
    `TABLE.get(key, default)` read like a plain dict and answer in the language
    of the request doing the reading.
    """

    def __init__(self, pairs: dict):
        self._pairs = dict(pairs)

    def __getitem__(self, key):
        en, id_ = self._pairs[key]
        return tr(en, id_)

    def __iter__(self) -> Iterator:
        return iter(self._pairs)

    def __len__(self) -> int:
        return len(self._pairs)


_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MONTHS_ID = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
              "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


def month_abbr(month: int) -> str:
    """A month's short name in this request's language — `strftime("%b")` is the
    C locale's English whatever the reader chose, and changing the process
    locale would change it for every request on the instance at once."""
    return (_MONTHS_ID if _current.get() == "id" else _MONTHS_EN)[month - 1]


def names(text):
    """A list of proper names written for an English sentence — "the Dow Jones
    Industrial Average and the Nasdaq-100", as the calibration files store a
    universe — in this request's language. Indonesian takes no article and
    joins with "dan"; the names themselves are names."""
    if not text or _current.get() != "id":
        return text
    return re.sub(r"\b[Tt]he\s+", "", str(text)).replace(" and ", " dan ")

