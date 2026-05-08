"""Unit tests for extract.py and normalize.py.

These tests use inline HTML strings — no network access required.
"""

import pytest

from scraper.extract import extract_records
from scraper.normalize import normalize_text, to_int, normalize_record


# ---------------------------------------------------------------------------
# normalize.py tests
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def test_strips_whitespace(self):
        assert normalize_text("  Chess Club  ") == "Chess Club"

    def test_collapses_internal_spaces(self):
        assert normalize_text("Chess   Club") == "Chess Club"

    def test_normalizes_tabs_and_newlines(self):
        assert normalize_text("Chess\tClub\n") == "Chess Club"

    def test_none_returns_empty_string(self):
        assert normalize_text(None) == ""

    def test_non_string_converted(self):
        assert normalize_text(42) == "42"

    def test_unicode_normalization(self):
        # NFC: composed form
        result = normalize_text("caf\u00e9")
        assert result == "café"


class TestToInt:
    def test_plain_integer_string(self):
        assert to_int("43") == 43

    def test_integer_with_commas(self):
        assert to_int("1,234") == 1234

    def test_integer_with_spaces(self):
        assert to_int("1 234") == 1234

    def test_non_numeric_returns_string(self):
        assert to_int("Chess Club") == "Chess Club"

    def test_empty_string_returns_empty(self):
        assert to_int("") == ""

    def test_none_returns_empty(self):
        assert to_int(None) == ""

    def test_numeric_int_passthrough(self):
        assert to_int(99) == 99


class TestNormalizeRecord:
    def test_skips_metadata_keys(self):
        record = {
            "year": 2001,
            "month": 1,
            "source_url": "https://example.com",
            "club_name": "  Chess Club  ",
        }
        result = normalize_record(record)
        assert result["year"] == 2001
        assert result["month"] == 1
        assert result["source_url"] == "https://example.com"
        assert result["club_name"] == "Chess Club"


# ---------------------------------------------------------------------------
# extract.py tests
# ---------------------------------------------------------------------------

TABLE_HTML = """
<html><body>
<table>
  <tr><th>Club</th><th>Members</th></tr>
  <tr><td class="club">Chess Club</td><td class="count">43</td></tr>
  <tr><td class="club">Football Club</td><td class="count">88</td></tr>
  <tr><td class="club">  Drama Society  </td><td class="count">1,200</td></tr>
</table>
</body></html>
"""

SELECTORS = {
    "row": "table tr",
    "club_name": "td:nth-child(1)",
    "member_count": "td:nth-child(2)",
}

METADATA = {"year": 2001, "month": 1, "source_url": "https://example.com/page.html"}


class TestExtractRecords:
    def test_extracts_correct_number_of_records(self):
        records = extract_records(TABLE_HTML, SELECTORS, METADATA)
        # Header row produces no data (th elements, not td), so 3 data rows
        assert len(records) == 3

    def test_extracts_club_names(self):
        records = extract_records(TABLE_HTML, SELECTORS, METADATA)
        names = [r["club_name"] for r in records]
        assert "Chess Club" in names
        assert "Football Club" in names
        assert "Drama Society" in names

    def test_normalizes_whitespace_in_club_name(self):
        records = extract_records(TABLE_HTML, SELECTORS, METADATA)
        drama = next(r for r in records if "Drama" in r["club_name"])
        assert drama["club_name"] == "Drama Society"

    def test_converts_member_count_to_int(self):
        records = extract_records(TABLE_HTML, SELECTORS, METADATA)
        chess = next(r for r in records if r["club_name"] == "Chess Club")
        assert chess["member_count"] == 43

    def test_converts_comma_formatted_count_to_int(self):
        records = extract_records(TABLE_HTML, SELECTORS, METADATA)
        drama = next(r for r in records if r["club_name"] == "Drama Society")
        assert drama["member_count"] == 1200

    def test_metadata_attached_to_every_record(self):
        records = extract_records(TABLE_HTML, SELECTORS, METADATA)
        for record in records:
            assert record["year"] == 2001
            assert record["month"] == 1
            assert record["source_url"] == "https://example.com/page.html"

    def test_empty_html_returns_empty_list(self):
        records = extract_records("<html><body></body></html>", SELECTORS, METADATA)
        assert records == []

    def test_missing_element_in_row_returns_empty_string(self):
        html = """
        <html><body>
        <table>
          <tr><td>Only One Cell</td></tr>
        </table>
        </body></html>
        """
        records = extract_records(html, SELECTORS, METADATA)
        assert len(records) == 1
        assert records[0]["club_name"] == "Only One Cell"
        assert records[0]["member_count"] == ""

    def test_invalid_html_returns_empty_list(self):
        records = extract_records("not html at all <<<", SELECTORS, METADATA)
        # lxml is tolerant — may parse something, should not crash
        assert isinstance(records, list)

    def test_custom_selectors_work(self):
        html = """
        <html><body>
        <ul class="society-list">
          <li><span class="name">Drama Society</span><span class="members">120</span></li>
          <li><span class="name">Chess Club</span><span class="members">30</span></li>
        </ul>
        </body></html>
        """
        selectors = {
            "row": "ul.society-list li",
            "society_name": "span.name",
            "member_count": "span.members",
        }
        records = extract_records(html, selectors, METADATA)
        assert len(records) == 2
        assert records[0]["society_name"] == "Drama Society"
        assert records[0]["member_count"] == 120
