"""Download SEP entries politely: one request every CRAWL_DELAY seconds, resumable.

The SEP terms allow crawling each entry for indexing, not redistributing it,
so everything lands in data/raw/ (gitignored) and never leaves this machine.
"""

import re
import time
from pathlib import Path

import httpx

BASE = "https://plato.stanford.edu/"
CRAWL_DELAY = 5.0  # robots.txt: crawl-delay: 5
USER_AGENT = "cite-or-silence/0.1 (research crawler; +https://github.com/abp002/cite-or-silence)"

ENTRY_LINK = re.compile(r'href="entries/([^"/#]+)/?"')


def entry_slugs(contents_html: str) -> list[str]:
    """Slugs of every entry linked from the table of contents, in order, without duplicates."""
    return list(dict.fromkeys(ENTRY_LINK.findall(contents_html)))


def entry_url(slug: str) -> str:
    return f"{BASE}entries/{slug}/"


def fetch_all(raw_dir: Path, limit: int | None = None, log=print) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as client:
        slugs = entry_slugs(client.get(f"{BASE}contents.html").raise_for_status().text)
        pending = [s for s in slugs if not (raw_dir / f"{s}.html").exists()]
        if limit is not None:
            pending = pending[:limit]
        log(f"{len(slugs)} entries in the SEP, {len(pending)} to download")
        for i, slug in enumerate(pending, 1):
            time.sleep(CRAWL_DELAY)
            response = client.get(entry_url(slug))
            if response.status_code != 200:
                log(f"[{i}/{len(pending)}] {slug}: HTTP {response.status_code}, skipped")
                continue
            tmp = raw_dir / f"{slug}.html.part"
            tmp.write_text(response.text, encoding="utf-8")
            tmp.rename(raw_dir / f"{slug}.html")
            log(f"[{i}/{len(pending)}] {slug}")
