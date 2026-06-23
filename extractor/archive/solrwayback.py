"""SolrWayback playback-layer helpers.

This module is the *archive adapter*: it knows how SolrWayback wraps an
original URL in a playback URL and how it signals missing snapshots. It is
not specific to any particular archived site — any site replayed through
SolrWayback shares these conventions.

A SolrWayback playback URL looks like:

    http://host/solrwayback/services/web/<14-digit-crawl-date>/<original-url>
"""

from __future__ import annotations

from urllib.parse import unquote

# Marker that separates the SolrWayback service prefix from the snapshot part.
_SERVICE_MARKER = "/services/web/"

# Text SolrWayback shows when a URL was never captured.
NOT_HARVESTED_MARKER = "Url has never been harvested:"


def extract_original_url(playback_url: str) -> str:
    """Return the original (pre-archive) URL embedded in a playback URL.

    Falls back to the input unchanged when it is not a SolrWayback URL.
    """
    if _SERVICE_MARKER in playback_url:
        try:
            after = playback_url.split(_SERVICE_MARKER, 1)[1]
            # Format: <14-digit timestamp>/<original-url>
            parts = after.split("/", 1)
            if len(parts) == 2:
                return unquote(parts[1])
        except Exception:
            return playback_url
    return playback_url


def extract_crawl_date(playback_url: str) -> str:
    """Return the 14-digit crawl date (YYYYMMDDHHMMSS) or '' if absent."""
    if _SERVICE_MARKER not in playback_url:
        return ""
    try:
        after = playback_url.split(_SERVICE_MARKER, 1)[1]
        date_part = after.split("/", 1)[0]
        return date_part if len(date_part) == 14 and date_part.isdigit() else ""
    except Exception:
        return ""


def extract_crawl_year(playback_url: str) -> str:
    """Return the 4-digit year of the crawl date, or '' if unavailable."""
    crawl_date = extract_crawl_date(playback_url)
    return crawl_date[:4] if len(crawl_date) >= 4 else ""


def is_not_harvested(page_text: str) -> bool:
    """True if the page is a SolrWayback 'never harvested' placeholder."""
    return NOT_HARVESTED_MARKER.lower() in page_text.lower()
