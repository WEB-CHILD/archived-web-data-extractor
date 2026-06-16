"""Site profile for nick.com message boards (jhtml board software).

Everything in this module is specific to how nick.com's old message boards
were built: the `viewthread.jhtml` / `viewboard.jhtml` link patterns, the
`bID`/`tID`/`mID` query parameters, the `MainSubject` / `subInfo` / `subject`
HTML classes, and the "Next posts" pager label.

To support a different archived board, add a sibling module here implementing
the same methods as `NickMessageboards` and pass an instance to the engine in
`extractor.thread_scraper`. The engine itself contains no site-specific logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from extractor.archive import solrwayback


class NickMessageboards:
    """Link discovery and post parsing for nick.com message boards."""

    # Link substrings identifying thread and board pages.
    THREAD_LINK = "viewthread.jhtml"
    BOARD_LINK = "viewboard.jhtml"

    # Require this host in resolved links to avoid following ads/third parties.
    HOST_HINT = "nick.com"

    # HTML hooks for post content and metadata.
    POST_BLOCK = ("div", "MainSubject")
    SUBINFO = ("p", "subInfo")
    SUBJECT = ("p", "subject")

    def thread_id(self, url: str) -> str:
        """Stable id for a thread page based on bID/tID/mID.

        Collapses multiple archival snapshots of the same logical message.
        Falls back to the original URL string when those params are absent.
        """
        original = solrwayback.extract_original_url(url)
        query = parse_qs(urlparse(original).query)

        bid = (query.get("bID") or query.get("bid") or [""])[0]
        tid = (query.get("tID") or query.get("tid") or [""])[0]
        mid = (query.get("mID") or query.get("mid") or [""])[0]
        offset = (query.get("offset") or [""])[0]

        if not (bid or tid or mid):
            return original

        return f"bid={bid}|tid={tid}|mid={mid}|offset={offset}"

    def board_id(self, url: str) -> str:
        """Extract the board id (bID) from a board URL, or '' if absent."""
        original = solrwayback.extract_original_url(url)
        query = parse_qs(urlparse(original).query)
        return (query.get("bID") or query.get("bid") or [""])[0]

    def find_thread_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Find thread links, filtering ads/calendar/third-party hosts."""
        urls: List[str] = []

        for a in soup.find_all("a", href=True):
            # Skip the SolrWayback toolbar/modal (calendar, prev/next snapshots).
            if a.find_parent(id="tegModal") is not None:
                continue

            href = a["href"]
            if self.THREAD_LINK not in href:
                continue

            full = urljoin(base_url, href)

            # Drop known noise: ads, calendar wrappers, third-party hosts.
            if "doubleclick.net" in full or "/ads/" in full or "calendar?url=" in full:
                continue

            if self.HOST_HINT and self.HOST_HINT not in full:
                continue

            urls.append(full)

        return urls

    def find_next_page_link(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        """Find the board pager link labeled 'Next posts', if present."""
        for a in soup.find_all("a", href=True):
            if a.find_parent(id="tegModal") is not None:
                continue

            label = a.get_text(" ", strip=True).lower()
            if "next posts" not in label:
                continue

            full = urljoin(base_url, a["href"])
            if self.BOARD_LINK in full:
                return full

        return None

    def is_board_dead_end(self, page_text: str) -> bool:
        """Site-specific board pager dead-end signals (lowercased text)."""
        return "get flash" in page_text

    def extract_posts(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract posts (content + metadata) from a thread page."""
        posts: List[Dict[str, Any]] = []
        block_tag, block_class = self.POST_BLOCK
        info_tag, info_class = self.SUBINFO
        subj_tag, subj_class = self.SUBJECT

        for div in soup.find_all(block_tag, class_=block_class):
            content = div.get_text(" ", strip=True)

            # Metadata (subInfo / subject) may sit in a sibling <td> or a
            # higher-level ancestor. Search ancestors and nearby siblings up to
            # a small depth to be robust.
            sub_info: List[str] = []
            subject_text = ""

            for depth, anc in enumerate(div.parents):
                if depth > 6:
                    break
                if hasattr(anc, "find_all"):
                    for p in anc.find_all(info_tag, class_=info_class):
                        text = p.get_text(" ", strip=True)
                        if text and text not in sub_info:
                            sub_info.append(text)
                    subject = anc.find(subj_tag, class_=subj_class)
                    if subject and not subject_text:
                        subject_text = subject.get_text(" ", strip=True)
                # Immediate previous siblings often contain headers.
                prev = getattr(anc, "previous_sibling", None)
                if prev and hasattr(prev, "find_all"):
                    for p in prev.find_all(info_tag, class_=info_class):
                        text = p.get_text(" ", strip=True)
                        if text and text not in sub_info:
                            sub_info.append(text)
                    subject = prev.find(subj_tag, class_=subj_class)
                    if subject and not subject_text:
                        subject_text = subject.get_text(" ", strip=True)

            # Fallback: walk immediate previous elements in the document.
            if not sub_info or not subject_text:
                sib = div.previous_sibling
                checks = 0
                while sib and checks < 6:
                    if hasattr(sib, "find_all"):
                        for p in sib.find_all(info_tag, class_=info_class):
                            text = p.get_text(" ", strip=True)
                            if text and text not in sub_info:
                                sub_info.append(text)
                        subject = sib.find(subj_tag, class_=subj_class)
                        if subject and not subject_text:
                            subject_text = subject.get_text(" ", strip=True)
                    sib = sib.previous_sibling
                    checks += 1

            # Promote common subInfo entries to first-class metadata fields.
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
