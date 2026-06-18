"""Site-agnostic recursive thread scraper for archived message boards.

This is the *engine* layer. It owns traversal, retry/failure policy, snapshot
de-duplication and output, but contains no site-specific HTML or URL knowledge.
That knowledge lives in two pluggable layers:

- `extractor.archive.solrwayback` — the web-archive adapter (playback URL
  parsing, "never harvested" detection). Shared by any site behind SolrWayback.
- a *site profile* (see `extractor.sites.nick_messageboards.NickMessageboards`)
  — per-site link patterns and post parsing.

Workflow (per `instructions.txt`):
- Read a JSON list of board entries (with `board_link` and `has_playback`).
- Process only entries where `has_playback` is true.
- Find thread links on each board page (via the site profile) as seeds.
- For each thread URL, fetch the page, detect "never harvested" and either
  record metadata or extract posts.
- Recursively follow additional thread links discovered on thread pages until
  no new thread URLs remain.

To scrape a different board, implement a new site profile with the same methods
as `NickMessageboards` and pass it to the `scrape_*` functions; no engine code
changes are required.
"""

from __future__ import annotations

import json
import re
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple

from bs4 import BeautifulSoup

from extractor.archive import solrwayback
from extractor.export import export_json
from extractor.fetch import fetch_html
from extractor.sites.nick_messageboards import NickMessageboards
from extractor.utils import get_logger

logger = get_logger(__name__)

MAX_FETCH_FAILURES_PER_THREAD = 3
DEFAULT_BOARD_WORKERS = 4
DEFAULT_THREAD_WORKERS = 4


class SiteProfile(Protocol):
    """Interface the engine expects from a site profile.

    See `extractor.sites.nick_messageboards.NickMessageboards` for a reference
    implementation.
    """

    def thread_id(self, url: str) -> str: ...
    def board_id(self, url: str) -> str: ...
    def find_thread_links(self, soup: BeautifulSoup, base_url: str) -> List[str]: ...
    def find_thread_subjects(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]: ...
    def find_next_page_link(self, soup: BeautifulSoup, base_url: str) -> Optional[str]: ...
    def is_board_dead_end(self, page_text: str) -> bool: ...
    def extract_posts(self, soup: BeautifulSoup) -> List[Dict[str, Any]]: ...


# Default profile. Swap by passing `profile=` to the scrape_* functions.
DEFAULT_PROFILE: SiteProfile = NickMessageboards()


def _slugify(value: str) -> str:
    """Create a filesystem-safe, readable slug."""
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "board"


def _visit_key(url: str, profile: SiteProfile) -> str:
    """Visited-key that preserves distinct crawl snapshots by crawl date."""
    crawl_date = solrwayback.extract_crawl_date(url)
    return f"crawl={crawl_date}|{profile.thread_id(url)}"


def scrape_thread(
    start_url: str,
    visited: Optional[Set[str]] = None,
    profile: SiteProfile = DEFAULT_PROFILE,
) -> Dict[str, Any]:
    """Scrape a thread from `start_url`, following pagination/continuation.

    Returns a dict with keys: `thread_url`, `crawl_date`, `status`, `posts`.
    Stops after `MAX_FETCH_FAILURES_PER_THREAD` consecutive fetch failures; a
    successful fetch resets the counter.
    """
    if visited is None:
        visited = set()

    thread_result: Dict[str, Any] = {
        "thread_url": start_url,
        "crawl_date": solrwayback.extract_crawl_date(start_url),
        "status": "ok",
        "posts": [],
    }
    thread_crawl_year = solrwayback.extract_crawl_year(start_url)

    queue = deque([start_url])
    consecutive_failures = 0

    while queue:
        url = queue.popleft()
        page_id = _visit_key(url, profile)
        if page_id in visited:
            continue
        visited.add(page_id)

        logger.info("Fetching thread page: %s", url)
        html = fetch_html(url)

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

        # Detect 'never harvested' — treat as metadata-only, no posts.
        if solrwayback.is_not_harvested(soup.get_text()):
            logger.info("Thread not harvested: %s", url)
            thread_result["status"] = "not_harvested"
            continue

        posts = profile.extract_posts(soup)
        if posts:
            page_crawl_year = solrwayback.extract_crawl_year(url)
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

        # Queue any further thread links found on this page.
        for link in profile.find_thread_links(soup, url):
            if _visit_key(link, profile) not in visited:
                queue.append(link)

    # No posts but not explicitly "not harvested": leave status 'ok', empty posts.
    return thread_result


def _collect_board_seed_links(
    board_link: str,
    has_paging: bool,
    profile: SiteProfile,
) -> List[str]:
    """Phase 1: sequentially walk board pages and collect unique thread seed links."""
    seed_links: List[str] = []
    seen_seed: Set[str] = set()
    seen_board_pages: Set[str] = set()
    board_queue: deque = deque([board_link])

    while board_queue:
        current_board_url = board_queue.popleft()
        if current_board_url in seen_board_pages:
            continue
        seen_board_pages.add(current_board_url)

        logger.info("Scraping board page: %s", current_board_url)
        html = fetch_html(current_board_url)

        if html is None:
            logger.warning("Failed to fetch board page: %s", current_board_url)
            continue

        soup = BeautifulSoup(html, "lxml")
        page_text = soup.get_text(" ", strip=True).lower()

        if solrwayback.is_not_harvested(page_text) or profile.is_board_dead_end(page_text):
            logger.info("Board paging dead-end reached: %s", current_board_url)
            break

        for u in profile.find_thread_links(soup, current_board_url):
            key = _visit_key(u, profile)
            if key not in seen_seed:
                seed_links.append(u)
                seen_seed.add(key)

        if has_paging:
            next_page = profile.find_next_page_link(soup, current_board_url)
            if next_page and next_page not in seen_board_pages:
                logger.info("Following board pager Next posts: %s", next_page)
                board_queue.append(next_page)

    logger.info("Found %d unique thread seed links for board", len(seed_links))
    return seed_links


def scrape_board(
    board_link: str,
    has_paging: bool = False,
    profile: SiteProfile = DEFAULT_PROFILE,
    thread_workers: int = DEFAULT_THREAD_WORKERS,
) -> Dict[str, Any]:
    """Scrape all threads for a board page and optionally traverse pager pages.

    Phase 1 (sequential): walk board index pages to collect all thread seed links.
    Phase 2 (parallel): scrape each thread concurrently using a thread pool.
    """
    board_result: Dict[str, Any] = {"board_link": board_link, "threads": []}

    seed_links = _collect_board_seed_links(board_link, has_paging, profile)
    if not seed_links:
        return board_result

    with ThreadPoolExecutor(max_workers=thread_workers) as executor:
        futures = {
            executor.submit(scrape_thread, link, None, profile): link
            for link in seed_links
        }
        for future in as_completed(futures):
            try:
                board_result["threads"].append(future.result())
            except Exception as exc:
                logger.error("Thread scrape failed for %s: %s", futures[future], exc)

    return board_result


def scrape_boards_from_file(
    input_path: str,
    output_path: str,
    profile: SiteProfile = DEFAULT_PROFILE,
    board_workers: int = DEFAULT_BOARD_WORKERS,
    thread_workers: int = DEFAULT_THREAD_WORKERS,
) -> None:
    """Load input JSON of boards, process `has_playback` entries, write output."""
    with open(input_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    valid_entries = [
        e for e in entries
        if e.get("has_playback") and (e.get("board_link") or e.get("url"))
    ]

    def _scrape(entry: Dict[str, Any]) -> Dict[str, Any]:
        board_link: str = entry.get("board_link") or entry.get("url")  # type: ignore[assignment]
        assert board_link
        return scrape_board(
            board_link,
            has_paging=bool(entry.get("has_paging")),
            profile=profile,
            thread_workers=thread_workers,
        )

    results: List[Dict[str, Any]] = [None] * len(valid_entries)  # type: ignore[list-item]
    with ThreadPoolExecutor(max_workers=board_workers) as executor:
        future_to_index = {
            executor.submit(_scrape, entry): i
            for i, entry in enumerate(valid_entries)
        }
        for future in as_completed(future_to_index):
            i = future_to_index[future]
            try:
                results[i] = future.result()
            except Exception as exc:
                board_link = valid_entries[i].get("board_link") or valid_entries[i].get("url")
                logger.error("Board scrape failed for %s: %s", board_link, exc)

    export_json([r for r in results if r is not None], output_path)


def scrape_boards_from_file_chunked(
    input_path: str,
    output_dir: str,
    combined_output_path: Optional[str] = None,
    profile: SiteProfile = DEFAULT_PROFILE,
    board_workers: int = DEFAULT_BOARD_WORKERS,
    thread_workers: int = DEFAULT_THREAD_WORKERS,
) -> None:
    """Scrape boards and write one JSON file per board plus a manifest.

    Filenames include board id and crawl date when available.
    Boards are scraped in parallel; output files are written in input order.
    """
    with open(input_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pre-assign stable 1-based indices to valid entries.
    valid: List[Tuple[int, Dict[str, Any]]] = []
    board_index = 0
    for entry in entries:
        if not entry.get("has_playback"):
            continue
        if not (entry.get("board_link") or entry.get("url")):
            continue
        board_index += 1
        valid.append((board_index, entry))

    def _scrape(args: Tuple[int, Dict[str, Any]]) -> Tuple[int, Dict[str, Any], Dict[str, Any]]:
        idx, entry = args
        board_link: str = entry.get("board_link") or entry.get("url")  # type: ignore[assignment]
        assert board_link
        board_data = scrape_board(
            board_link,
            has_paging=bool(entry.get("has_paging")),
            profile=profile,
            thread_workers=thread_workers,
        )
        return idx, entry, board_data

    scraped: List[Tuple[int, Dict[str, Any], Dict[str, Any]]] = [None] * len(valid)  # type: ignore[list-item]
    with ThreadPoolExecutor(max_workers=board_workers) as executor:
        future_to_pos = {executor.submit(_scrape, item): pos for pos, item in enumerate(valid)}
        for future in as_completed(future_to_pos):
            pos = future_to_pos[future]
            try:
                scraped[pos] = future.result()
            except Exception as exc:
                idx, entry = valid[pos]
                logger.error("Board scrape failed (index %d): %s", idx, exc)

    manifest: List[Dict[str, Any]] = []
    combined_results: List[Dict[str, Any]] = []

    for item in scraped:
        if item is None:
            continue
        idx, entry, board_data = item
        board_link: str = entry.get("board_link") or entry.get("url")  # type: ignore[assignment]
        assert board_link
        combined_results.append(board_data)

        board_id = str(entry.get("board_id") or profile.board_id(board_link) or "unknown")
        crawl_date = solrwayback.extract_crawl_date(board_link) or "unknown"
        input_year = entry.get("year")
        crawl_year = str(input_year) if input_year is not None else (crawl_date[:4] if len(crawl_date) >= 4 else "unknown")
        board_name = str(entry.get("board_name") or f"board-{board_id}")
        slug = _slugify(board_name)

        file_name = f"{idx:04d}_y-{crawl_year}_bid-{board_id}_crawl-{crawl_date}_{slug}.json"
        file_path = out_dir / file_name

        with file_path.open("w", encoding="utf-8") as f:
            json.dump([board_data], f, indent=2, ensure_ascii=False)

        manifest.append(
            {
                "index": idx,
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

    manifest_path = out_dir / "index.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    logger.info("Wrote chunk manifest: %s", manifest_path)

    if combined_output_path:
        export_json(combined_results, combined_output_path)


def scrape_board_subjects(
    board_link: str,
    has_paging: bool = False,
    profile: SiteProfile = DEFAULT_PROFILE,
) -> List[Dict[str, str]]:
    """Collect thread subjects from a board index page (and its pager pages).

    Does not fetch individual thread pages — subjects and their URLs are read
    directly from the `viewthread.jhtml` links on the board listing.  Returns
    a de-duplicated, order-preserving list of dicts with 'subject' and 'url'.
    """
    threads: List[Dict[str, str]] = []
    seen_thread_ids: Set[str] = set()
    seen_board_pages: Set[str] = set()
    board_queue: deque = deque([board_link])

    while board_queue:
        current_url = board_queue.popleft()
        if current_url in seen_board_pages:
            continue
        seen_board_pages.add(current_url)

        logger.info("Fetching board subjects page: %s", current_url)
        html = fetch_html(current_url)

        if html is None:
            logger.warning("Failed to fetch board page: %s", current_url)
            continue

        soup = BeautifulSoup(html, "lxml")
        page_text = soup.get_text(" ", strip=True).lower()

        if solrwayback.is_not_harvested(page_text) or profile.is_board_dead_end(page_text):
            logger.info("Board paging dead-end reached: %s", current_url)
            break

        for item in profile.find_thread_subjects(soup, current_url):
            tid = profile.thread_id(item["url"])
            if tid not in seen_thread_ids:
                seen_thread_ids.add(tid)
                if item["subject"]:
                    threads.append({"subject": item["subject"], "url": item["url"]})

        if has_paging:
            next_page = profile.find_next_page_link(soup, current_url)
            if next_page and next_page not in seen_board_pages:
                logger.info("Following board pager: %s", next_page)
                board_queue.append(next_page)

    return threads


def scrape_board_subjects_from_file(
    input_path: str,
    output_path: str,
    profile: SiteProfile = DEFAULT_PROFILE,
) -> None:
    """Read board entries from input JSON and collect thread subjects for each.

    Processes only entries where `has_playback` is true.  Writes a JSON array
    where each element contains board metadata plus a `subjects` list grouped
    by `year` and `board_name` (as present in the input entry).
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

        threads = scrape_board_subjects(
            board_link, has_paging=bool(entry.get("has_paging")), profile=profile
        )
        logger.info(
            "Board '%s' (%s): %d threads collected",
            entry.get("board_name"),
            entry.get("year"),
            len(threads),
        )
        results.append(
            {
                "year": entry.get("year"),
                "board_name": entry.get("board_name"),
                "board_id": entry.get("board_id"),
                "board_link": board_link,
                "threads": threads,
            }
        )

    export_json(results, output_path)
