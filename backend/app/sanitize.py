"""Input sanitization utilities for user-provided string fields.

Uses stdlib html.escape to prevent stored XSS. Applied at API boundaries
before data is persisted to the database.
"""

import html


def sanitize_string(value: str) -> str:
    """Escape HTML special characters in user input.

    Converts &, <, >, ", ' to their HTML entity equivalents.
    This prevents stored XSS when values are rendered in the frontend.
    """
    if not value:
        return value
    return html.escape(value, quote=True)


def sanitize_dict_strings(data: dict, fields: list[str]) -> dict:
    """Sanitize specific string fields in a dictionary.

    Returns a new dict with the specified fields HTML-escaped.
    Non-string values and unspecified fields are left unchanged.
    """
    result = dict(data)
    for field in fields:
        if field in result and isinstance(result[field], str):
            result[field] = sanitize_string(result[field])
    return result
