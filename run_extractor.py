"""CLI entry point for the Research HTML Data Extractor Framework.

Usage:
    python run.py --config configs/clubs_example.yaml
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from extractor.config_loader import load_config
from extractor.extract import extract_records
from extractor.export import export_all
from extractor.fetch import fetch_html
from extractor.utils import get_logger

logger = get_logger("run")


def load_manifest(manifest_path: str | Path) -> list[dict]:
    """Load a URL manifest CSV and return rows as a list of dicts.

    Args:
        manifest_path: Path to the CSV manifest file.

    Returns:
        List of row dicts (keys from CSV header, e.g. year, month, url).

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        ValueError: If the manifest is missing a 'url' column.
    """
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")

    df = pd.read_csv(path, dtype=str)

    if "url" not in df.columns:
        raise ValueError(f"Manifest must have a 'url' column: {path}")

    return df.to_dict(orient="records")


def run(config_path: str) -> None:
    """Execute the full data extraction pipeline for a given config file.

    Steps:
    1. Load config
    2. Load URL manifest
    3. For each URL: fetch HTML, extract records, accumulate
    4. Export aggregated records to CSV and JSON
    5. Print summary statistics

    Args:
        config_path: Path to the YAML configuration file.
    """
    # --- 1. Load config ---
    logger.info("Loading config: %s", config_path)
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Config error: %s", exc)
        sys.exit(1)

    extractor_name = config["name"]
    selectors = config["selectors"]
    output_config = config["output"]

    # --- 2. Load manifest ---
    manifest_path = config["manifest"]
    logger.info("Loading manifest: %s", manifest_path)
    try:
        manifest_rows = load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Manifest error: %s", exc)
        sys.exit(1)

    logger.info(
        "Starting extractor '%s' — %d URLs to process", extractor_name, len(manifest_rows)
    )

    # --- 3. Fetch, extract, accumulate ---
    all_records: list[dict] = []
    success_count = 0
    failure_count = 0

    for row in manifest_rows:
        url = row["url"]

        # Build metadata from all manifest columns except 'url'
        metadata = {
            key: (int(val) if str(val).isdigit() else val)
            for key, val in row.items()
            if key != "url"
        }
        metadata["source_url"] = url

        # --- 4. Fetch HTML ---
        try:
            html = fetch_html(url)
        except Exception as exc:
            logger.error("Unexpected error fetching %s: %s", url, exc)
            failure_count += 1
            continue

        if html is None:
            logger.warning("Skipping URL (fetch failed): %s", url)
            failure_count += 1
            continue

        # --- 5. Extract records ---
        try:
            records = extract_records(html, selectors, metadata)
        except Exception as exc:
            logger.error("Extraction failed for %s: %s", url, exc)
            failure_count += 1
            continue

        all_records.extend(records)
        success_count += 1

    # --- 6. Export ---
    logger.info(
        "Processing complete. Successful URLs: %d  Failed: %d  Total records: %d",
        success_count,
        failure_count,
        len(all_records),
    )

    export_all(all_records, output_config)

    # --- 7. Print summary ---
    print("\n" + "=" * 60)
    print(f"  Extractor: {extractor_name}")
    print(f"  URLs processed: {success_count} / {len(manifest_rows)}")
    print(f"  URLs failed:    {failure_count}")
    print(f"  Total records:  {len(all_records)}")
    if all_records:
        if "csv" in output_config:
            print(f"  CSV output:     {output_config['csv']}")
        if "json" in output_config:
            print(f"  JSON output:    {output_config['json']}")
    print("=" * 60 + "\n")


def main() -> None:
    """Parse CLI arguments and launch the extractor pipeline."""
    parser = argparse.ArgumentParser(
        description="Research HTML Data Extractor — config-driven data extraction framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  python run.py --config configs/clubs_example.yaml\n"
        ),
    )
    parser.add_argument(
        "--config",
        required=True,
        metavar="PATH",
        help="Path to a YAML configuration file",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )

    args = parser.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log_level))

    run(args.config)


if __name__ == "__main__":
    main()
