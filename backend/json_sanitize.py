"""
Recursively replace NaN / ±Inf with None so responses and cache files are strict JSON.

FastAPI / stdlib json reject non-finite floats.
"""

from __future__ import annotations

import math
from typing import Any


def sanitize_for_json(obj: Any, *, ndigits: int = 3) -> Any:
    """Turn a nested structure into JSON-safe values; round finite floats."""
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, str):
        return obj
    # Reject bool subclass of int
    if isinstance(obj, int) and not isinstance(obj, bool):
        return int(obj)
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(obj, ndigits)

    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v, ndigits=ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(x, ndigits=ndigits) for x in obj]

    try:
        import numpy as np

        if isinstance(obj, np.generic):
            if isinstance(obj, np.floating):
                f = float(obj)
                if math.isnan(f) or math.isinf(f):
                    return None
                return round(f, ndigits)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.bool_):
                return bool(obj)
    except ImportError:
        pass

    try:
        import pandas as pd

        if obj is pd.NA:  # type: ignore[comparison-overlap]
            return None
    except ImportError:
        pass

    return obj
