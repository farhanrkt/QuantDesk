"""
jsonsafe.py
===========
pandas hands back NaN, numpy scalars and Timestamps. `json.dumps` turns NaN
into the literal token `NaN`, which is valid Python and invalid JSON —
`JSON.parse` on the client throws on it. Every payload goes through `clean()`
so NaN and +/-inf become `null` and numpy scalars become Python primitives.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd


# SIGNIFICANT DIGITS ON THE WIRE. A float leaves Python with seventeen, and a
# company read carries some forty thousand of them — 1,255 days of thirty chart
# series — so the digits nobody can see were most of its 1.35 MB (docs/AUDIT.md,
# PERF-2). No figure on the page is shown to more than six, and every statistic
# is computed on the full values before it gets here, so eight loses nothing a
# reader or a CSV can use: 345.91468811 is still 345.91469. Measured on AAPL:
# 408 KB to 263 KB compressed. Integers are untouched.
WIRE_DIGITS = 8


def _rounded(value: float, digits: int) -> float:
    if value == 0.0:
        return value
    return float(f"{value:.{digits}g}")


def clean(obj, digits: int | None = None):
    """`obj` made JSON-safe; with `digits`, every float cut to that many
    significant digits, which is what goes on the wire (see WIRE_DIGITS)."""
    if obj is None:
        return None
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        if not math.isfinite(value):
            return None
        return _rounded(value, digits) if digits else value
    if isinstance(obj, (str, bytes)):
        return obj.decode() if isinstance(obj, bytes) else obj
    # NaT MUST be tested before the date branch. NaTType subclasses
    # datetime.datetime, so `isinstance(pd.NaT, dt.datetime)` is True and the
    # strftime call below reaches it first — raising "NaTType does not support
    # strftime" and turning one missing date into a 500 for the whole payload.
    # This check used to sit at the bottom of the function, where it was
    # unreachable. A missing date is exactly what `clean` exists to survive.
    if obj is pd.NaT:
        return None
    if isinstance(obj, (pd.Timestamp, dt.datetime, dt.date)):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, np.ndarray):
        return [clean(v, digits) for v in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): clean(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [clean(v, digits) for v in obj]
    return obj
