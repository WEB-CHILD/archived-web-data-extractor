"""Shared utilities: logging setup."""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger instance.

    Creates a logger with a consistent format used across all scraper modules.
    Calling this multiple times with the same name returns the same logger.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger
