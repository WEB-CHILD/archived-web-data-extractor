"""CLI wrapper for the messageboard thread scraper.

Example:
  python run_thread_scraper.py --input input.json --output output.json
"""

import argparse
import logging
from pathlib import Path

from extractor.thread_scraper import (
    scrape_boards_from_file,
    scrape_boards_from_file_chunked,
)
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
    parser = argparse.ArgumentParser(description="Thread scraper runner")
    parser.add_argument("--input", required=True, help="Path to input JSON file")
    parser.add_argument("--output", help="Path to combined output JSON file")
    parser.add_argument(
        "--output-dir",
        help="Directory for chunked output files (one JSON per board + index.json)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    args = parser.parse_args()
    level = getattr(logging, args.log_level)
    logging.getLogger().setLevel(level)

    # Attach file log handler next to output
    if args.output_dir:
        log_path = Path(args.output_dir) / "scrape.log"
    elif args.output:
        log_path = Path(args.output).with_suffix(".log")
    else:
        log_path = Path("scrape.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _add_file_log_handler(log_path, level)
    logging.getLogger("extractor").info("Log file: %s", log_path)

    if args.output_dir:
        scrape_boards_from_file_chunked(
            args.input,
            args.output_dir,
            combined_output_path=args.output,
        )
        return

    if not args.output:
        parser.error("--output is required unless --output-dir is provided")

    scrape_boards_from_file(args.input, args.output)


if __name__ == "__main__":
    main()
