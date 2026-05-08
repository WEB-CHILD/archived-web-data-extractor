"""Text and numeric normalization utilities."""

import re
import unicodedata
from typing import Any


def normalize_text(value: Any) -> str:
    """Normalize a text value.

    Steps applied:
    1. Convert to string.
    2. Normalize unicode to NFC form.
    3. Strip leading/trailing whitespace.
    4. Collapse internal whitespace runs to a single space.

    Args:
        value: Any value; will be converted to string.

    Returns:
        Normalized string.
    """
    if value is None:
        return ""
    text = str(value)
    text = unicodedata.normalize("NFC", text)
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def to_int(value: Any) -> int | str:
    """Convert a value to an integer if possible, otherwise return normalized text.

    Strips non-numeric characters (commas, spaces) before attempting conversion.

    Args:
        value: Value to convert.

    Returns:
        Integer if conversion succeeds, otherwise the normalized string.
    """
    text = normalize_text(value)
    # Remove common numeric formatting characters
    cleaned = re.sub(r"[,\s]", "", text)
    try:
        return int(cleaned)
    except (ValueError, TypeError):
        return text


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize all string values in a record dictionary.

    Does not modify metadata keys (year, month, source_url).

    Args:
        record: Raw extracted record.

    Returns:
        Record with normalized values.
    """
    skip_keys = {"year", "month", "source_url"}
    normalized = {}
    for key, value in record.items():
        if key in skip_keys:
            normalized[key] = value
        else:
            normalized[key] = normalize_text(value)
    return normalized
