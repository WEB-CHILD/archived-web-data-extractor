"""Recursive thread scraper tailored to messageboard playback pages.

Follows the workflow described in `instructions.txt`:
- Read a JSON list of board entries (with `board_link` and `has_playback`).
- Only process entries where `has_playback` is true.
- From each board page find all links containing `viewthread.jhtml` and treat
  them as thread entry points.
- For each thread URL, fetch the page, wait 1-2s, detect "Url has never been
  harvested:" and either record metadata or extract posts.
- Recursively follow any additional `viewthread.jhtml` links discovered on
  thread pages until no new thread URLs remain.

This module re-uses `fetch_html` and `export_json` from the existing codebase.
"""

from __future__ import annotations

import json
import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from extractor.fetch import fetch_html
from extractor.export import export_json
from extractor.utils import get_logger

logger = get_logger(__name__)


def _sleep_polite() -> None:
    time.sleep(0.3)



def _extract_original_url(playback_url: str) -> str:
    """Extract original URL from a solrwayback playback URL when possible."""
    marker = "/services/web/"
    if marker in playback_url:
        try:
            after = playback_url.split(marker, 1)[1]
            # Format: <14-digit timestamp>/<original-url>
            parts = after.split("/", 1)
            if len(parts) == 2:
                return unquote(parts[1])
        except Exception:
            return playback_url
    return playback_url


def _extract_crawl_date(playback_url: str) -> str:
    """Extract 14-digit crawl date from solrwayback URL if present."""
    marker = "/services/web/"
    if marker not in playback_url:
        return ""
    try:
        after = playback_url.split(marker, 1)[1]
        date_part = after.split("/", 1)[0]
        return date_part if len(date_part) == 14 and date_part.isdigit() else ""
    except Exception:
        return ""


def _extract_crawl_year(playback_url: str) -> str:
    """Extract year from a playback crawl date (YYYYMMDDHHMMSS)."""
    crawl_date = _extract_crawl_date(playback_url)
    return crawl_date[:4] if len(crawl_date) >= 4 else ""


def _extract_board_id(url: str) -> str:
    """Extract board id from board URL query if present."""
    original = _extract_original_url(url)
    parsed = urlparse(original)
    query = parse_qs(parsed.query)
    return (query.get("bID") or query.get("bid") or [""])[0]


def _slugify(value: str) -> str:
    """Create filesystem-safe, readable slug."""
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "board"


def _canonical_thread_id(url: str) -> str:
    """Build stable id for a thread page based on bID/tID/mID.

    This collapses multiple archival snapshots of the same logical message.
    """
    original = _extract_original_url(url)
    parsed = urlparse(original)
    query = parse_qs(parsed.query)

    bid = (query.get("bID") or query.get("bid") or [""])[0]
    tid = (query.get("tID") or query.get("tid") or [""])[0]
    mid = (query.get("mID") or query.get("mid") or [""])[0]
    offset = (query.get("offset") or [""])[0]

    # If these keys are missing, fall back to original URL string.
    if not (bid or tid or mid):
        return original

    return f"bid={bid}|tid={tid}|mid={mid}|offset={offset}"


def _visit_key(url: str) -> str:
    """Visited-key that preserves distinct crawl snapshots by crawl date."""
    crawl_date = _extract_crawl_date(url)
    return f"crawl={crawl_date}|{_canonical_thread_id(url)}"


def _find_viewthread_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Find viewthread links but filter out obvious ad/calendar/third-party URLs.

    To avoid following unrelated links (ad.doubleclick, calendar wrappers,
    etc.) require that the resolved URL contain 'viewthread.jhtml' and also
    contain the site's host (e.g. 'nick.com') inferred from the base_url.
    """
    anchors = soup.find_all("a", href=True)
    urls: List[str] = []

    host_hint = "nick.com"
    if "nick.com" in base_url:
        host_hint = "nick.com"

    for a in anchors:
        # Skip links in the SolrWayback toolbar/modal (calendar, prev/next snapshots)
        if a.find_parent(id="tegModal") is not None:
            continue

        href = a["href"]
        if "viewthread.jhtml" not in href:
            continue

        full = urljoin(base_url, href)

        # Filter out known noise: ads, calendar wrappers, and third-party hosts
        if "doubleclick.net" in full or "/ads/" in full or "calendar?url=" in full:
            continue

        # Require host hint to be present to avoid unrelated hosts
        if host_hint and host_hint not in full:
            continue

        urls.append(full)

    return urls


def _find_next_posts_link(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Find board pager link labeled 'Next posts' if present."""
    for a in soup.find_all("a", href=True):
        if a.find_parent(id="tegModal") is not None:
            continue

        label = a.get_text(" ", strip=True).lower()
        if "next posts" not in label:
            continue

        full = urljoin(base_url, a["href"])
        if "viewboard.jhtml" in full:
            return full

    return None


def _extract_posts_from_soup(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    posts: List[Dict[str, Any]] = []

    # Find all main post content blocks
    for div in soup.find_all("div", class_="MainSubject"):
        # Content: flattened visible text
        content = div.get_text(" ", strip=True)

        # Try to find metadata nearby.
        # The original pages sometimes put `p.subInfo` and `p.subject` in a
        # sibling <td> or higher-level ancestor. Search ancestors and nearby
        # siblings up to a small depth to be robust.
        sub_info: List[str] = []
        subject_text = ""

        # Search up the ancestor chain for metadata
        for depth, anc in enumerate(div.parents):
            if depth > 6:
                break
            if hasattr(anc, "find_all"):
                for p in anc.find_all("p", class_="subInfo"):
                    text = p.get_text(" ", strip=True)
                    if text and text not in sub_info:
                        sub_info.append(text)
                subject = anc.find("p", class_="subject")
                if subject and not subject_text:
                    subject_text = subject.get_text(" ", strip=True)
            # Also check immediate previous siblings which often contain headers
            prev = getattr(anc, "previous_sibling", None)
            if prev and hasattr(prev, "find_all"):
                for p in prev.find_all("p", class_="subInfo"):
                    text = p.get_text(" ", strip=True)
                    if text and text not in sub_info:
                        sub_info.append(text)
                subject = prev.find("p", class_="subject")
                if subject and not subject_text:
                    subject_text = subject.get_text(" ", strip=True)

        # As a fallback, check immediate previous elements in the document
        if not sub_info or not subject_text:
            sib = div.previous_sibling
            checks = 0
            while sib and checks < 6:
                if hasattr(sib, "find_all"):
                    for p in sib.find_all("p", class_="subInfo"):
                        text = p.get_text(" ", strip=True)
                        if text and text not in sub_info:
                            sub_info.append(text)
                    subject = sib.find("p", class_="subject")
                    if subject and not subject_text:
                        subject_text = subject.get_text(" ", strip=True)
                sib = sib.previous_sibling
                checks += 1

        # Promote common subInfo entries to first-class metadata fields
        date_str = ""
        from_str = ""
        for info in sub_info:
            if not info:
                continue
            lowered = info.strip().lower()
            if lowered.startswith("date:"):
                date_str = info.split(":", 1)[1].strip()
            elif lowered.startswith("from:"):
                from_str = info.split(":", 1)[1].strip()

        posts.append(
            {
                "content": content,
                "metadata": {
                    "subject": subject_text,
                    "subInfo": sub_info,
                    "date": date_str,
                    "from": from_str,
                },
            }
        )

    return posts


MAX_FETCH_FAILURES_PER_THREAD = 3


def scrape_thread(start_url: str, visited: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Scrape a thread starting from `start_url`, following pagination/continuation.

    Returns a dict with keys: `thread_url`, `status`, `posts`.
    """
    if visited is None:
        visited = set()

    thread_result: Dict[str, Any] = {
        "thread_url": start_url,
        "crawl_date": _extract_crawl_date(start_url),
        "status": "ok",
        "posts": [],
    }
    thread_crawl_year = _extract_crawl_year(start_url)

    queue = deque([start_url])
    consecutive_failures = 0

    while queue:
        url = queue.popleft()
        page_id = _visit_key(url)
        if page_id in visited:
            continue
        visited.add(page_id)

        logger.info("Fetching thread page: %s", url)
        html = fetch_html(url)
        _sleep_polite()

        if html is None:
            consecutive_failures += 1
            logger.warning(
                "Failed to fetch thread page (%d/%d): %s",
                consecutive_failures,
                MAX_FETCH_FAILURES_PER_THREAD,
                url,
            )
            if consecutive_failures >= MAX_FETCH_FAILURES_PER_THREAD:
                logger.info(
                    "Reached max consecutive fetch failures (%d) for thread %s — stopping",
                    MAX_FETCH_FAILURES_PER_THREAD,
                    start_url,
                )
                break
            continue

        consecutive_failures = 0

        soup = BeautifulSoup(html, "lxml")

        # Detect 'Url has never been harvested:' — treat as metadata-only
        if "Url has never been harvested:" in soup.get_text():
            logger.info("Thread not harvested: %s", url)
            # If first page, mark status; otherwise ensure we don't overwrite ok
            if thread_result["status"] != "ok":
                thread_result["status"] = "not_harvested"
            else:
                thread_result["status"] = "not_harvested"
            # Do not attempt to scrape posts on this page; continue to next
            continue

        # Extract posts from this page
        posts = _extract_posts_from_soup(soup)
        if posts:
            page_crawl_year = _extract_crawl_year(url)
            year_jump_detected = (
                bool(thread_crawl_year)
                and bool(page_crawl_year)
                and page_crawl_year != thread_crawl_year
            )

            for post in posts:
                metadata = post.setdefault("metadata", {})
                metadata["playback_url"] = url
                metadata["year_time_jump_detected"] = year_jump_detected
            thread_result["posts"].extend(posts)

        # Find additional viewthread links on the page and add unseen ones to queue
        new_links = _find_viewthread_links(soup, url)
        for link in new_links:
            if _visit_key(link) not in visited:
                queue.append(link)

    # If no posts were captured but the page wasn't explicitly "not harvested",
    # leave status as 'ok' and empty posts (caller can interpret as needed).
    return thread_result


def scrape_board(board_link: str, has_paging: bool = False) -> Dict[str, Any]:
    """Scrape all threads for a board page and optionally traverse pager pages."""
    board_result: Dict[str, Any] = {"board_link": board_link, "threads": []}

    # Reuse one visited set across all board pages to avoid duplicate thread work
    visited_threads: Set[str] = set()
    seen_board_pages: Set[str] = set()
    board_queue = deque([board_link])

    while board_queue:
        current_board_url = board_queue.popleft()
        if current_board_url in seen_board_pages:
            continue
        seen_board_pages.add(current_board_url)

        logger.info("Scraping board page: %s", current_board_url)
        html = fetch_html(current_board_url)
        _sleep_polite()

        if html is None:
            logger.warning("Failed to fetch board page: %s", current_board_url)
            continue

        soup = BeautifulSoup(html, "lxml")
        page_text = soup.get_text(" ", strip=True).lower()

        # Pager dead ends: stop pursuing board paging when archive has no page
        if "url has never been harvested:" in page_text or "get flash" in page_text:
            logger.info("Board paging dead-end reached: %s", current_board_url)
            break

        # Find seed thread links on this board page
        seed_links = _find_viewthread_links(soup, current_board_url)
        seen_seed = set()
        deduped = []
        for u in seed_links:
            if u not in seen_seed:
                deduped.append(u)
                seen_seed.add(u)

        seed_links = deduped
        logger.info("Found %d seed thread links on board page", len(seed_links))

        for link in seed_links:
            if _visit_key(link) in visited_threads:
                continue
            thread_data = scrape_thread(link, visited_threads)
            board_result["threads"].append(thread_data)

        # After scraping threads from this page, follow pager if requested.
        if has_paging:
            next_posts = _find_next_posts_link(soup, current_board_url)
            if next_posts and next_posts not in seen_board_pages:
                logger.info("Following board pager Next posts: %s", next_posts)
                board_queue.append(next_posts)

    return board_result


def scrape_boards_from_file(input_path: str, output_path: str) -> None:
    """Load input JSON of boards, process entries with has_playback True and
    write output JSON to `output_path`.
    """
    with open(input_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    results: List[Dict[str, Any]] = []
    for entry in entries:
        if not entry.get("has_playback"):
            continue
        board_link = entry.get("board_link") or entry.get("url")
        if not board_link:
            continue
        board_data = scrape_board(board_link, has_paging=bool(entry.get("has_paging")))
        results.append(board_data)

    export_json(results, output_path)


def scrape_boards_from_file_chunked(
    input_path: str,
    output_dir: str,
    combined_output_path: Optional[str] = None,
) -> None:
    """Scrape boards and write one JSON file per board plus a manifest.

    Filenames include board id and crawl date when available.
    """
    with open(input_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: List[Dict[str, Any]] = []
    combined_results: List[Dict[str, Any]] = []

    board_index = 0
    for entry in entries:
        if not entry.get("has_playback"):
            continue

        board_link = entry.get("board_link") or entry.get("url")
        if not board_link:
            continue

        board_index += 1
        board_data = scrape_board(board_link, has_paging=bool(entry.get("has_paging")))
        combined_results.append(board_data)

        board_id = str(entry.get("board_id") or _extract_board_id(board_link) or "unknown")
        crawl_date = _extract_crawl_date(board_link) or "unknown"
        input_year = entry.get("year")
        crawl_year = str(input_year) if input_year is not None else (crawl_date[:4] if len(crawl_date) >= 4 else "unknown")
        board_name = str(entry.get("board_name") or f"board-{board_id}")
        slug = _slugify(board_name)

        file_name = f"{board_index:04d}_y-{crawl_year}_bid-{board_id}_crawl-{crawl_date}_{slug}.json"
        file_path = out_dir / file_name

        # Store one board per file for easy downstream chunk processing.
        with file_path.open("w", encoding="utf-8") as f:
            json.dump([board_data], f, indent=2, ensure_ascii=False)

        manifest.append(
            {
                "index": board_index,
                "board_name": board_name,
                "board_id": board_id,
                "year": input_year,
                "crawl_year": crawl_year,
                "crawl_date": crawl_date,
                "board_link": board_link,
                "has_paging": bool(entry.get("has_paging")),
                "threads": len(board_data.get("threads", [])),
                "file": str(file_path),
            }
        )

    # Manifest for downstream tools to enumerate chunks.
    manifest_path = out_dir / "index.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    logger.info("Wrote chunk manifest: %s", manifest_path)

    if combined_output_path:
        export_json(combined_results, combined_output_path)
