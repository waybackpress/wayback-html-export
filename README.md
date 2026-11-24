# wayback-html-export

A tiny, dependency-free command-line tool that downloads a domain's archived
pages from the [Wayback Machine](https://web.archive.org) and saves them as a
plain **static-HTML mirror** you can browse offline, host anywhere, or inspect.

No LLM. No account. No API key. No paid service. Just the public Internet
Archive endpoints and the Python standard library — one file, nothing to install.

Built and maintained by [Wayback Press](https://waybackpress.com). Independent project — not affiliated
with the Internet Archive / Wayback Machine, nor with the Shift8 open-source tool that shares the
"Wayback Press" name.

## Why

Sometimes you just want the HTML the Archive actually holds for a domain —
nothing rewritten, nothing "reconstructed", nothing invented. This tool gives
you exactly that: a faithful export of the captured pages, as files on disk.

## Requirements

- Python 3.9+ (standard library only, no dependencies)

## Install

```bash
pip install wayback-html-export      # then run: wayback-html-export example.com
```

Or skip installing: download `wayback_export.py` and run it with `python3` as below.

## Usage

```bash
# export everything the Archive has (HTML pages, HTTP 200)
python3 wayback_export.py example.com

# choose an output folder and cap how many URLs you pull
python3 wayback_export.py example.com --out ./export --limit 200

# only snapshots captured on or before a date (YYYYMMDD)
python3 wayback_export.py example.com --timestamp 20180101
```

Output (under `--out`, default `./<domain>/`):

- the archived pages, written to files that mirror each URL's path
- the site's own homepage as `index.html`
- `_export-index.html` — a clickable list of everything exported
- `manifest.json` — `{ domain, pages: [{ url, timestamp, file }], count_saved, ... }`

## How it works

1. Queries the CDX index (`web.archive.org/cdx/search/cdx`) for every captured
   URL of the domain — HTTP 200, HTML only — and keeps the **latest** capture of
   each URL (at or before `--timestamp` when given).
2. Downloads each page's **raw** archived HTML (the `…id_/…` Wayback variant,
   which omits the Archive's navigation toolbar and injected scripts).
3. Writes the pages to disk and builds the index + manifest.

It is polite to the Archive (a short delay between requests, retry/backoff on
rate limits) and skips any single capture that fails rather than aborting.

## What it does *not* do

- It does not generate, rewrite, paraphrase or "improve" any content.
- It does not run a browser, so client-side-rendered pages export as the HTML
  the Archive stored (which may be a shell). It is an HTML export, not a scraper.
- It does not fetch assets referenced by absolute URLs to the live origin.

## Free tool vs. a working site

| | wayback-html-export (this repo) | [Wayback Press service](https://waybackpress.com/pricing/) |
|---|---|---|
| Price | Free, MIT | Fixed price per site |
| Output | Static HTML files, as archived | Editable WordPress site, original URLs kept |
| Missing CSS / images | Left as the Archive stored them | Rebuilt or replaced |
| Checking | None — a raw export | Every page checked by AI and a person before delivery |
| Live site | Untouched (you only get files) | Untouched unless you ask us to deploy |

Not sure what the Archive holds for your domain? Run the
[free scan](https://waybackpress.com/internet-archive-downloader/) first.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

Content retrieved from the Wayback Machine belongs to its original authors and
is subject to the [Internet Archive's terms](https://archive.org/about/terms.php)
and to copyright law in your jurisdiction. Export only what you have the right
to use.
