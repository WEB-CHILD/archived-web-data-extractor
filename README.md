# Research HTML Scraper Framework - archived-web-scraper 

A lightweight, config-driven Python framework for extracting structured data from static HTML pages
---

## Features

- Config-driven: define selectors in YAML, no code changes needed for new projects
- Manifest-driven: point at a CSV of URLs to scrape in bulk
- Supports standard URLs and Internet Archive (Wayback Machine) URLs
- Outputs structured CSV and JSON
- Robust error handling: failed URLs are logged and skipped; the run continues
- Fully unit-tested

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/WEB-CHILD/archived-web-scraper.git
cd archived-web-scraper
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

Each scraping project is defined by a YAML config file.

**Required keys:**

| Key | Description |
|---|---|
| `name` | Human-readable name for this scraping project |
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
- Fields ending in `_count` (including `member_count`) are automatically converted to integers.
- Extra columns in the manifest (beyond `year`, `month`, `url`) are automatically attached as metadata to every record.

---

## URL Manifest (CSV)

The manifest is a CSV file listing every URL to scrape, along with metadata columns that are attached to extracted records.

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

# Run a different scraping project
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

## Adding a New Scraping Project

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

3. **Run the scraper:**
   ```bash
   python run.py --config configs/my_new_project.yaml
   ```

No changes to any Python files are needed.

---

## Error Handling

- Network errors, timeouts, and parse failures are logged and skipped.
- The run continues through all remaining URLs even if individual ones fail.
- A summary is printed at the end showing success/failure counts and output paths.
