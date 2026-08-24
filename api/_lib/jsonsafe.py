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


def clean(obj):
    if obj is None:
        return None
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        return value if math.isfinite(value) else None
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
        return [clean(v) for v in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [clean(v) for v in obj]
    return obj
