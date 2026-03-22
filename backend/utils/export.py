"""
JSON serialization helpers.

Provides NaN-safe encoding and a Flask response builder that ensures
no invalid JSON values (NaN, Infinity) ever reach the frontend.
"""
import json
import math
from flask import Response


def sanitize(obj):
    """
    Recursively replace NaN/Infinity floats with None, and convert
    numpy types to native Python so json.dumps succeeds.
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    # numpy scalar types
    type_name = type(obj).__name__
    if 'int' in type_name and hasattr(obj, 'item'):
        return int(obj)
    if 'float' in type_name and hasattr(obj, 'item'):
        val = float(obj)
        return None if (math.isnan(val) or math.isinf(val)) else val
    return obj


def json_response(data, status=200):
    """Build a Flask Response with sanitized JSON body."""
    safe = sanitize(data)
    body = json.dumps(safe, separators=(',', ':'), allow_nan=False)
    return Response(body, status=status, mimetype='application/json')


def error_response(message, status=500):
    """Build a JSON error response."""
    return json_response({'error': message}, status=status)
