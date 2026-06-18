# Research HTML Data Extractor Framework

A lightweight, config-driven Python framework for extracting structured data from static HTML pages
---

## Features

- Config-driven: define selectors in YAML, no code changes needed for new projects
- Manifest-driven: point at a CSV of URLs to extract data in bulk
- Supports standard URLs
- Outputs structured CSV and JSON
- Robust error handling: failed URLs are logged and skipped; the run continues
- Fully unit-tested

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/WEB-CHILD/archived-web-data-extractor.git
cd archived-web-data-extractor
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Quick Start

```bash
python run.py --config configs/clubs_example.yaml
```

Output files appear in the `output/` directory as defined in the config.


---

## Configuration (YAML)

Each data extraction project is defined by a YAML config file.

**Required keys:**

| Key | Description |
|---|---|
| `name` | Human-readable name for this data extraction project |
| `manifest` | Path to the URL manifest CSV |
| `selectors` | CSS selectors — must include `row`; all other keys become field names |
| `output` | Output file paths — must include `csv` and `json` |

### Example: HTML table

```yaml
name: youth_clubs

manifest: manifests/clubs_urls.csv

selectors:
  row: "table tr"
  club_name: "td:nth-child(1)"
  member_count: "td:nth-child(2)"

output:
  csv: output/clubs.csv
  json: output/clubs.json
```

### Example: Unordered list

```yaml
name: university_societies

manifest: manifests/societies_urls.csv

selectors:
  row: "ul.society-list li"
  society_name: "span.name"
  member_count: "span.members"

output:
  csv: output/societies.csv
  json: output/societies.json
```

**Notes:**
- The `row` selector identifies repeating container elements.
- Every other key in `selectors` names a field; its value is the CSS selector applied within each row.
- Field definitions can also be objects for attribute or regex extraction:
  - `selector` (or `css`): CSS selector inside each row
  - `attr`: attribute name to extract instead of text (for example `href`)
  - `regex`: optional regex to post-process the extracted value
  - `group`: optional regex group index/name (default `1`)
- Fields ending in `_count` (including `member_count`) are automatically converted to integers.
- Extra columns in the manifest (beyond `year`, `month`, `url`) are automatically attached as metadata to every record.

Example field object:

```yaml
selectors:
  row: "ul li"
  board_name: "a"
  board_link:
    selector: "a"
    attr: "href"
  board_id:
    selector: "a"
    attr: "href"
    regex: "[?&]bID=(\\d+)"
    group: 1
  numeric_fields:
    - board_id
```

---

## URL Manifest (CSV)

The manifest is a CSV file listing every URL to extract data from, along with metadata columns that are attached to extracted records.

```csv
year,month,url
2001,01,https://example.com/jan2001.html
2001,02,https://example.com/feb2001.html

```

**Required column:** `url`  
**Common columns:** `year`, `month` — but any extra columns are supported and attached to records automatically.

---

## CLI Usage

```bash
python run.py --config <path-to-config.yaml> [--log-level LEVEL]
```

| Flag | Default | Description |
|---|---|---|
| `--config` | *(required)* | Path to the YAML config file |
| `--log-level` | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Examples

```bash
# Basic run
python run.py --config configs/clubs_example.yaml

# Verbose debug output
python run.py --config configs/clubs_example.yaml --log-level DEBUG

# Run a different data extraction project
python run.py --config configs/another_site.yaml
```

---

## Output Format

### CSV (`output/clubs.csv`)

```csv
year,month,club_name,member_count,source_url
2001,1,Chess Club,43,https://example.com/jan2001.html
2001,1,Football Club,88,https://example.com/jan2001.html
```

### JSON (`output/clubs.json`)

```json
[
  {
    "year": 2001,
    "month": 1,
    "club_name": "Chess Club",
    "member_count": 43,
    "source_url": "https://example.com/jan2001.html"
  }
]
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

Tests use inline HTML fixtures — no network access required.

---

## Adding a New Data Extraction Project

1. **Create a manifest CSV** in `manifests/`:
   ```csv
   year,month,url
   2005,03,https://example.org/2005/march.html
   ```

2. **Create a YAML config** in `configs/`, pointing at the manifest and defining selectors for the target HTML:
   ```yaml
   name: my_new_project
   manifest: manifests/my_urls.csv
   selectors:
     row: "div.item"
     title: "h2.title"
     member_count: "span.count"
   output:
     csv: output/my_new_project.csv
     json: output/my_new_project.json
   ```

3. **Run the extractor:**
   ```bash
   python run.py --config configs/my_new_project.yaml
   ```

No changes to any Python files are needed.

---

## Thread Scraper (messageboard playback)

`run_thread_scraper.py` scrapes messageboard threads from SolrWayback playback pages. It takes a JSON list of board entries, visits each board page, discovers thread links, and recursively extracts all posts.

### Input format

Each entry in the input JSON represents one board page snapshot:

| Field | Type | Description |
|---|---|---|
| `board_name` | string | Human-readable board name |
| `board_link` | string | Full SolrWayback playback URL for the board page |
| `board_id` | integer | Board ID extracted from the URL |
| `year`, `month`, `day` | integer | Crawl date components |
| `has_playback` | boolean | Skip this entry if `false` |
| `has_paging` | boolean | Follow "Next posts" pager links across board pages if `true` |

See `examples/thread_scraper_input.json` for a minimal working example.

### CLI usage

```bash
# Single combined output file
python run_thread_scraper.py --input examples/thread_scraper_input.json --output output/threads.json

# One JSON file per board + manifest index
python run_thread_scraper.py --input examples/thread_scraper_input.json --output-dir output/chunks/

# Both at once
python run_thread_scraper.py --input examples/thread_scraper_input.json --output-dir output/chunks/ --output output/threads_combined.json

# Tune parallelism (boards × threads concurrent requests; default 4×4)
python run_thread_scraper.py --input examples/thread_scraper_input.json --output-dir output/chunks/ --board-workers 8 --thread-workers 8
```

| Flag | Default | Description |
|---|---|---|
| `--input` | *(required)* | Path to input JSON file |
| `--output` | — | Path for combined output JSON |
| `--output-dir` | — | Directory for per-board JSON files and `index.json` manifest |
| `--board-workers` | `4` | Number of boards scraped in parallel |
| `--thread-workers` | `4` | Number of threads scraped in parallel per board |
| `--log-level` | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

A log file is written alongside the output (`scrape.log`).

**Performance note:** boards and threads within each board are scraped concurrently using `ThreadPoolExecutor`. With the defaults of 4×4 you get up to 16 concurrent requests to SolrWayback. Increase the worker counts if the server can handle more load.

### Architecture (3 layers)

The thread scraper is split so site-specific code is isolated from the generic engine:

| Layer | Module | Responsibility |
|---|---|---|
| Engine | `extractor/thread_scraper.py` | Traversal, retry/failure policy, snapshot de-dup, output. **No site-specific code.** |
| Archive adapter | `extractor/archive/solrwayback.py` | SolrWayback playback URL parsing, crawl-date extraction, "never harvested" detection. Shared by any site behind SolrWayback. |
| Site profile | `extractor/sites/nick_messageboards.py` | nick.com-specific: `viewthread.jhtml`/`viewboard.jhtml` link patterns, `bID`/`tID`/`mID` params, `MainSubject`/`subInfo`/`subject` HTML selectors, "Next posts" pager. |

The engine takes a **site profile** (defaults to `NickMessageboards`). To scrape a different board, add a new module under `extractor/sites/` implementing the same methods (`thread_id`, `board_id`, `find_thread_links`, `find_next_page_link`, `is_board_dead_end`, `extract_posts`) and pass an instance via the `profile=` argument of the `scrape_*` functions — no engine changes needed. The expected interface is documented by the `SiteProfile` Protocol in `extractor/thread_scraper.py`.

### How scraping works

1. Entries with `has_playback: false` are skipped.
2. **Phase 1 (sequential):** For each board, all `viewthread.jhtml` links are collected as thread seeds by walking the board index page(s). If `has_paging: true`, "Next posts" pager links are followed in order until all seeds are gathered.
3. **Phase 2 (parallel):** All collected thread seeds are scraped concurrently up to `--thread-workers` at a time. Multiple boards also run in parallel up to `--board-workers`.
4. Each thread is scraped by fetching its page and following any further `viewthread.jhtml` links found (handles thread pagination and continuation links).
5. If a page signals `"Url has never been harvested:"`, the thread is marked `not_harvested` and no posts are extracted from that page.
6. Scraping a thread stops after **3 consecutive fetch failures**. A successful page fetch resets the failure counter, so a single network hiccup does not terminate a long thread.

### Output format

```json
[
  {
    "board_link": "http://...",
    "threads": [
      {
        "thread_url": "http://...",
        "crawl_date": "20030101120000",
        "status": "ok",
        "posts": [
          {
            "content": "Post body text",
            "metadata": {
              "subject": "Thread title",
              "date": "January 1, 2003",
              "from": "Username",
              "subInfo": ["Date: January 1, 2003", "From: Username"],
              "playback_url": "http://...",
              "year_time_jump_detected": false
            }
          }
        ]
      }
    ]
  }
]
```

`status` values: `"ok"` (posts extracted), `"not_harvested"` (archive has no snapshot for this URL).

---

## Error Handling

- Network errors, timeouts, and parse failures are logged and skipped.
- The run continues through all remaining URLs even if individual ones fail.
- A summary is printed at the end showing success/failure counts and output paths.
