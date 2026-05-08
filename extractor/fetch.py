"""Fetch raw HTML from a URL with retry and timeout handling."""

import time
from typing import Optional

import requests

from scraper.utils import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds between retries

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ResearchScraper/1.0; "
        "+https://github.com/WEB-CHILD/archived-web-data-extractor)"
    )
}


def fetch_html(url: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[str]:
    """Download HTML from a URL and return it as a string.

    Handles standard URLs using the same code path — requests follows redirects automatically.

    Retries up to MAX_RETRIES times on network errors or 5xx responses.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        Raw HTML string, or None if all retries failed.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Fetching URL (attempt %d/%d): %s", attempt, MAX_RETRIES, url)
            response = requests.get(url, headers=HEADERS, timeout=timeout)

            if response.status_code == 200:
                return response.text

            logger.warning(
                "Non-200 status %d for URL: %s", response.status_code, url
            )

            # Only retry on server errors
            if response.status_code < 500:
                return None

        except requests.exceptions.Timeout:
            logger.warning("Timeout on attempt %d for URL: %s", attempt, url)
        except requests.exceptions.ConnectionError as exc:
            logger.warning("Connection error on attempt %d for %s: %s", attempt, url, exc)
        except requests.exceptions.RequestException as exc:
            logger.error("Request failed for %s: %s", url, exc)
            return None

        if attempt < MAX_RETRIES:
            logger.info("Retrying in %d seconds...", RETRY_BACKOFF)
            time.sleep(RETRY_BACKOFF)

    logger.error("All %d attempts failed for URL: %s", MAX_RETRIES, url)
    return None
