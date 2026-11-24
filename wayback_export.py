#!/usr/bin/env python3
"""wayback-html-export — download a domain's archived pages from the Wayback Machine
and save them as a plain static-HTML mirror.

No LLM, no rewriting of your content, no account, no paid API — just the public
Internet Archive CDX + Wayback endpoints and the Python standard library.

Usage:
    python3 wayback_export.py example.com
    python3 wayback_export.py example.com --out ./export --limit 200
    python3 wayback_export.py example.com --timestamp 20180101   # latest snapshot at/before this date

What it does:
    1. Asks the CDX index for every captured URL of the domain (HTTP 200, HTML only)
       and keeps the LATEST capture of each URL (at/before --timestamp if given).
    2. Downloads each page's RAW archived HTML (the `id_` Wayback variant, which omits
       the Archive toolbar/injected scripts).
    3. Writes the pages into --out as a browsable static site + _export-index.html + manifest.json.

This is a faithful export of what the Archive holds. It does not invent, rewrite or
"improve" any page. See https://waybackpress.com .
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
WB = "https://web.archive.org/web"
UA = "wayback-html-export/1.1.0 (+https://github.com/waybackpress/wayback-html-export)"
PAGE_ROWS = 20000          # CDX rows per request
_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def normalize_domain(raw: str) -> str | None:
    s = raw.strip().lower()
    s = re.sub(r"^https?://", "", s).split("/")[0]
    return s if _DOMAIN_RE.match(s) else None


def _get(url: str, tries: int = 4) -> bytes:
    """GET with a polite retry/backoff on 429/503."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503, 500):
                time.sleep(2 * (i + 1))
                continue
            raise
        except (urllib.error.URLError, http.client.IncompleteRead, ConnectionError, TimeoutError) as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last if last else RuntimeError("request failed: " + url)


def list_snapshots(domain: str, limit: int, timestamp: str | None) -> list[dict]:
    """Latest good (HTTP 200, HTML) capture of every archived URL of the domain.

    The CDX index returns captures oldest-first, so we read every 200/HTML row and keep
    the newest one per URL (at/before --timestamp when given), then apply --limit.
    Rows are read in pages (CDX resume key) so a large domain never needs one huge response.
    """
    params = {
        "url": f"{domain}/*",
        "output": "json",
        "fl": "timestamp,original,mimetype,statuscode,urlkey",
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "digest",   # drop identical consecutive captures
        "limit": str(PAGE_ROWS),
        "showResumeKey": "true",
    }
    if timestamp:
        params["to"] = timestamp   # only captures at/before this date
    latest: dict[str, dict] = {}
    resume = None
    while True:
        q = dict(params, resumeKey=resume) if resume else params
        raw = _get(CDX_ENDPOINT + "?" + urllib.parse.urlencode(q, doseq=True))
        rows = json.loads(raw.decode("utf-8", "replace") or "[]")
        if not isinstance(rows, list) or len(rows) <= 1:
            break
        resume = None
        if len(rows) >= 3 and rows[-2] == [] and len(rows[-1]) == 1:   # [..., [], [resumeKey]]
            resume = rows[-1][0]
            rows = rows[:-2]
        for row in rows[1:]:
            if len(row) != 5:
                continue
            ts, original, mimetype, _code, urlkey = row
            cur = latest.get(urlkey)
            if cur is None or ts > cur["timestamp"]:
                latest[urlkey] = {"timestamp": ts, "original": original, "mimetype": mimetype}
        if not resume:
            break
        print(f"  ...{len(latest)} URLs listed so far", file=sys.stderr)
    snaps = sorted(latest.values(), key=lambda r: r["original"])
    return snaps[:limit] if limit else snaps


def _local_path(original: str) -> str:
    """Map an archived URL to a safe local file path under the export root.

    Each path component is capped at 100 chars (long or non-ASCII names, e.g. a
    big query string, are collapsed to a short hash) so no filename exceeds the
    filesystem limit.
    """
    p = urllib.parse.urlparse(original if "://" in original else "http://" + original)
    path = p.path
    if not path or path.endswith("/"):
        path = path + "index.html"
    # keep query-bearing URLs distinct but filesystem-safe
    if p.query:
        path += "__" + p.query
    if not re.search(r"\.[A-Za-z0-9]{1,6}$", path):
        path += ".html"

    def _cap(seg: str) -> str:
        seg = re.sub(r"[^A-Za-z0-9._\-]", "_", seg)
        if len(seg) > 100:
            root, dot, ext = seg.rpartition(".")
            h = hashlib.sha1(seg.encode()).hexdigest()[:8]
            ext = (dot + ext) if dot and len(ext) <= 6 else ""
            seg = (root[:60] if root else seg[:60]) + "_" + h + ext
        return seg

    # never let ".." or "." segments climb out of the export folder
    return "/".join(_cap(s) for s in path.lstrip("/").split("/") if s and s not in (".", ".."))


def export(domain: str, out: str, limit: int, timestamp: str | None) -> dict:
    snaps = list_snapshots(domain, limit, timestamp)
    manifest = {"domain": domain, "generated_by": "wayback-html-export", "source": "web.archive.org",
                "count_requested": len(snaps), "pages": []}
    os.makedirs(out, exist_ok=True)
    saved = 0
    for i, s in enumerate(snaps, 1):
        rel = _local_path(s["original"])
        dest = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        url = f"{WB}/{s['timestamp']}id_/{s['original']}"
        try:
            body = _get(url)
        except Exception as e:  # noqa: BLE001 — one bad capture must not abort the mirror
            print(f"  [skip] {s['original']} ({e})", file=sys.stderr)
            continue
        with open(dest, "wb") as f:
            f.write(body)
        saved += 1
        manifest["pages"].append({"url": s["original"], "timestamp": s["timestamp"], "file": rel})
        print(f"  [{i}/{len(snaps)}] {s['original']} -> {rel}")
        time.sleep(0.3)  # be polite to the Archive
    manifest["count_saved"] = saved
    # a simple browsable index
    links = "\n".join(
        f'    <li><a href="{p["file"]}">{p["url"]}</a> <small>({p["timestamp"]})</small></li>'
        for p in manifest["pages"])
    index = (
        "<!doctype html><meta charset=utf-8>"
        f"<title>{domain} — Wayback export</title>"
        f"<h1>{domain}</h1>"
        f"<p>{saved} page(s) exported from the Wayback Machine by "
        '<a href="https://waybackpress.com">wayback-html-export</a>.</p>'
        f"<ul>\n{links}\n</ul>")
    # separate name: the site's own homepage is saved as index.html
    with open(os.path.join(out, "_export-index.html"), "w", encoding="utf-8") as f:
        f.write(index)
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export a domain's archived HTML from the Wayback Machine.")
    ap.add_argument("domain")
    ap.add_argument("--out", default=None, help="output directory (default: ./<domain>)")
    ap.add_argument("--limit", type=int, default=1000, help="max URLs to export (default 1000)")
    ap.add_argument("--timestamp", default=None, help="YYYYMMDD — snapshots at/before this date only")
    a = ap.parse_args(argv)
    domain = normalize_domain(a.domain)
    if not domain:
        print(f"error: '{a.domain}' is not a valid domain", file=sys.stderr)
        return 2
    out = a.out or ("./" + domain)
    print(f"Exporting {domain} -> {out}")
    m = export(domain, out, a.limit, a.timestamp)
    print(f"Done: {m['count_saved']} page(s) saved to {out} (manifest.json, _export-index.html written).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
