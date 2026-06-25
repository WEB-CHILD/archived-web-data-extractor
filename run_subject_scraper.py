"""CLI wrapper for board subject scraping.

Reads a boards JSON (same format as thread scraper input) and collects the
post subjects listed on each board index page — without fetching individual
thread pages.  Output is grouped by year and board_name.

Example:
  python run_subject_scraper.py --input input.json --output subjects.json
"""

import argparse
import logging
from pathlib import Path

from extractor.thread_scraper import DEFAULT_PROFILE, load_profile, scrape_board_subjects_from_file
from extractor.utils import get_logger


def _add_file_log_handler(log_path: Path, level: int) -> None:
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(level)
    logging.getLogger().addHandler(fh)


def main() -> None:
    parser = argparse.ArgumentParser(description="Board subject scraper")
    parser.add_argument("--input", required=True, help="Path to input JSON file")
    parser.add_argument("--output", required=True, help="Path to output JSON file")
    parser.add_argument(
        "--profile",
        default=None,
        metavar="PKG.MODULE.CLASS",
        help=(
            "Dotted import path to a site profile class, e.g. "
            "my_private_pkg.sites.nick.NickMessageboards. "
            "Falls back to the built-in nick profile when omitted."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    args = parser.parse_args()
    level = getattr(logging, args.log_level)
    logging.getLogger().setLevel(level)

    profile = load_profile(args.profile) if args.profile else DEFAULT_PROFILE

    log_path = Path(args.output).with_suffix(".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _add_file_log_handler(log_path, level)
    logging.getLogger("extractor").info("Log file: %s", log_path)

    scrape_board_subjects_from_file(args.input, args.output, profile=profile)


if __name__ == "__main__":
    main()
