"""Generate a self-contained HTML viewer from a subjects JSON file.

Example:
  python generate_subjects_html.py --input output/subjects.json --output output/subjects.html
"""

import argparse
import json
from pathlib import Path


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: system-ui, sans-serif;
    font-size: 14px;
    background: #f4f4f4;
    color: #222;
    line-height: 1.5;
  }}

  header {{
    background: #ff6600;
    color: #fff;
    padding: 16px 24px;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }}
  header h1 {{ font-size: 1.3rem; flex: 1; }}

  #controls {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }}
  #search {{
    padding: 6px 10px;
    border: none;
    border-radius: 4px;
    font-size: 13px;
    width: 240px;
  }}
  #yearFilter {{
    padding: 6px 8px;
    border: none;
    border-radius: 4px;
    font-size: 13px;
  }}
  #stats {{
    font-size: 12px;
    color: #ffe0cc;
    white-space: nowrap;
  }}

  main {{
    max-width: 1100px;
    margin: 20px auto;
    padding: 0 16px;
  }}

  .board {{
    background: #fff;
    border-radius: 6px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,.1);
    overflow: hidden;
  }}
  .board-header {{
    background: #fff8f4;
    padding: 10px 16px;
    border-bottom: 2px solid #ff6600;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }}
  .board-title {{
    font-weight: 700;
    font-size: 1rem;
  }}
  .board-title a {{
    color: #cc4400;
    text-decoration: none;
  }}
  .board-title a:hover {{ text-decoration: underline; }}
  .board-meta {{
    font-size: 11px;
    color: #888;
    white-space: nowrap;
  }}

  .thread-list {{
    list-style: none;
  }}
  .thread-list li {{
    border-top: 1px solid #f0f0f0;
  }}
  .thread-list li:first-child {{ border-top: none; }}
  .thread-list a {{
    display: block;
    padding: 7px 16px;
    color: #1a1a9e;
    text-decoration: none;
    transition: background .1s;
  }}
  .thread-list a:hover {{
    background: #fff3eb;
    color: #cc4400;
  }}

  .hidden {{ display: none; }}

  #noResults {{
    text-align: center;
    padding: 40px;
    color: #888;
    font-size: 1.1rem;
  }}
</style>
</head>
<body>

<header>
  <h1>{title}</h1>
  <div id="controls">
    <input id="search" type="search" placeholder="Search subjects…" autocomplete="off">
    <select id="yearFilter">
      <option value="">All years</option>
      {year_options}
    </select>
    <span id="stats">{board_count} boards &middot; {thread_count} threads</span>
  </div>
</header>

<main id="main">
  <div id="noResults" class="hidden">No matching threads.</div>
</main>

<script>
(function () {{
  var boards = {data_json};

  var main = document.getElementById('main');
  var noResults = document.getElementById('noResults');
  var searchEl = document.getElementById('search');
  var yearEl = document.getElementById('yearFilter');
  var statsEl = document.getElementById('stats');

  function esc(s) {{
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }}

  boards.forEach(function (board) {{
    var section = document.createElement('div');
    section.className = 'board';
    section.dataset.year = board.year;

    var hdr = document.createElement('div');
    hdr.className = 'board-header';
    hdr.innerHTML =
      '<span class="board-title"><a href="' + esc(board.board_link) + '" target="_blank" rel="noopener">' +
      esc(board.board_name) + '</a></span>' +
      '<span class="board-meta">' + board.year + ' · ' + board.threads.length +
      ' thread' + (board.threads.length !== 1 ? 's' : '') + '</span>';

    var ul = document.createElement('ul');
    ul.className = 'thread-list';

    board.threads.forEach(function (t) {{
      var li = document.createElement('li');
      li.dataset.subject = t.subject.toLowerCase();
      li.innerHTML = '<a href="' + esc(t.url) + '" target="_blank" rel="noopener">' + esc(t.subject) + '</a>';
      ul.appendChild(li);
    }});

    section.appendChild(hdr);
    section.appendChild(ul);
    main.insertBefore(section, noResults);
  }});

  function filter() {{
    var q = searchEl.value.toLowerCase().trim();
    var yr = yearEl.value;
    var visBoards = 0, visThreads = 0;

    document.querySelectorAll('.board').forEach(function (board) {{
      var matchYear = !yr || board.dataset.year === yr;
      var boardVisible = false;

      board.querySelectorAll('.thread-list li').forEach(function (li) {{
        var show = matchYear && (!q || li.dataset.subject.includes(q));
        li.classList.toggle('hidden', !show);
        if (show) {{ boardVisible = true; visThreads++; }}
      }});

      board.classList.toggle('hidden', !boardVisible);
      if (boardVisible) visBoards++;
    }});

    noResults.classList.toggle('hidden', visBoards > 0);
    statsEl.textContent = visBoards + ' boards · ' + visThreads + ' threads';
  }}

  searchEl.addEventListener('input', filter);
  yearEl.addEventListener('change', filter);
}})();
</script>
</body>
</html>
"""


def generate_html(boards: list, title: str = "Message Boards") -> str:
    years = sorted({b["year"] for b in boards})
    year_options = "\n      ".join(f'<option value="{y}">{y}</option>' for y in years)
    total_threads = sum(len(b["threads"]) for b in boards)

    return _HTML_TEMPLATE.format(
        title=title,
        year_options=year_options,
        board_count=len(boards),
        thread_count=total_threads,
        data_json=json.dumps(boards, ensure_ascii=False),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate self-contained HTML viewer from subjects JSON")
    parser.add_argument("--input", required=True, help="Path to subjects JSON file")
    parser.add_argument("--output", required=True, help="Path to output HTML file")
    parser.add_argument("--title", default="Message Boards", help="Page title (default: 'Message Boards')")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    boards = json.loads(input_path.read_text(encoding="utf-8"))
    html = generate_html(boards, title=args.title)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    total_threads = sum(len(b["threads"]) for b in boards)
    print(f"Written: {output_path} ({output_path.stat().st_size // 1024} KB, {len(boards)} boards, {total_threads} threads)")


if __name__ == "__main__":
    main()
