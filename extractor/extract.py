"""Extract structured records from raw HTML using config-driven CSS selectors."""

import re
from typing import Any

from bs4 import BeautifulSoup

from extractor.normalize import normalize_text, to_int
from extractor.utils import get_logger

logger = get_logger(__name__)

# Keys in `selectors` that are metadata blocks (not field selectors)
_META_SELECTOR_KEYS = {"row", "numeric_fields"}


def _extract_with_spec(
    row: Any,
    field_selector: str | dict[str, Any],
) -> str:
    """Extract a raw field value from a row using either string or dict spec.

    Supported selector forms:
    - "field": "css selector"
    - "field":
        selector: "css selector"   # or css
        attr: "href"              # optional, default text extraction
        regex: "bID=(\\d+)"       # optional
        group: 1                    # optional, default 1 when regex present
    """
    if isinstance(field_selector, str):
        element = row.select_one(field_selector)
        return element.get_text() if element else ""

    if not isinstance(field_selector, dict):
        return ""

    selector = field_selector.get("selector") or field_selector.get("css")
    if not selector or not isinstance(selector, str):
        return ""

    element = row.select_one(selector)
    if element is None:
        return ""

    attr = field_selector.get("attr")
    if attr:
        raw_value = element.get(attr, "")
    else:
        raw_value = element.get_text()

    regex = field_selector.get("regex")
    if regex and isinstance(regex, str):
        match = re.search(regex, str(raw_value))
        if not match:
            return ""

        group = field_selector.get("group", 1)
        try:
            return match.group(group)
        except (IndexError, TypeError):
            return ""

    return str(raw_value)


def extract_records(
    html: str,
    selectors: dict[str, Any],
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """Parse HTML and extract records using CSS selectors from config.

    For each row matched by `selectors['row']`, every other key in `selectors`
    is treated as a field name whose value is extracted via its CSS selector.

    The field named `member_count` (if present) is converted to int.
    All other fields are normalized text.

    Args:
        html: Raw HTML string to parse.
        selectors: Dict mapping field names to selector definitions.
               Must include a 'row' key for the row selector.
               Field definitions may be a CSS selector string or a dict
               containing selector/css, optional attr, and optional regex.
        metadata: Dict of metadata to attach to every record
                  (e.g. year, month, source_url).

    Returns:
        List of record dicts, each containing extracted fields plus metadata.
    """
    records: list[dict[str, Any]] = []

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:
        logger.error("Failed to parse HTML: %s", exc)
        return records

    row_selector = selectors["row"]
    rows = soup.select(row_selector)
    logger.info("Found %d rows matching selector '%s'", len(rows), row_selector)

    field_selectors: dict[str, Any] = {
        key: selector
        for key, selector in selectors.items()
        if key not in _META_SELECTOR_KEYS
    }

    # Fields to convert to integers — auto-detected by name or declared explicitly
    explicit_numeric = set(selectors.get("numeric_fields", []))

    for row in rows:
        record: dict[str, Any] = {}

        for field_name, selector in field_selectors.items():
            raw_text = _extract_with_spec(row, selector)
            value = normalize_text(raw_text)

            # Convert to int if field is explicitly listed or matches naming convention
            if (
                field_name in explicit_numeric
                or field_name == "member_count"
                or field_name.endswith("_count")
            ):
                value = to_int(value)

            record[field_name] = value

        # Only include rows where at least one field has content
        if not any(record.values()):
            continue

        record.update(metadata)
        records.append(record)

    logger.info("Extracted %d non-empty records", len(records))
    return records
