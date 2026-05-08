"""Export extracted records to CSV and JSON formats."""

import json
from pathlib import Path
from typing import Any

import pandas as pd

from scraper.utils import get_logger

logger = get_logger(__name__)


def export_csv(records: list[dict[str, Any]], output_path: str | Path) -> None:
    """Export records to a CSV file using pandas.

    Args:
        records: List of record dicts to export.
        output_path: Destination file path for the CSV.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(records)
    df.to_csv(path, index=False, encoding="utf-8")
    logger.info("Exported %d records to CSV: %s", len(records), path)


def export_json(records: list[dict[str, Any]], output_path: str | Path) -> None:
    """Export records to a JSON file.

    Args:
        records: List of record dicts to export.
        output_path: Destination file path for the JSON.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    logger.info("Exported %d records to JSON: %s", len(records), path)


def export_all(
    records: list[dict[str, Any]],
    output_config: dict[str, str],
) -> None:
    """Export records to all configured output formats.

    Args:
        records: List of record dicts to export.
        output_config: Dict with keys 'csv' and/or 'json' mapping to file paths.
    """
    if not records:
        logger.warning("No records to export.")
        return

    if "csv" in output_config:
        export_csv(records, output_config["csv"])

    if "json" in output_config:
        export_json(records, output_config["json"])
