"""
ingest_rss.py — Read RSS feeds from independent or mainstream outlets,
normalise into the items schema, and insert into the corpus DB.

Usage:
    python tools/ingest_rss.py --config config/handles.yml --since 30d
    python tools/ingest_rss.py --config config/mainstream.yml --since 7d
    python tools/ingest_rss.py --config config/handles.yml --only thewire,caravan

This is the most reliable ingestion path. RSS doesn't require auth, doesn't
hit aggressive rate limits, and most independent + mainstream outlets still
maintain feeds. When an outlet's feed dies, log and move on; do not retry
indefinitely.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys
from typing import Any

import feedparser  # type: ignore
import yaml

# Make sibling tools importable when invoked as `python tools/ingest_rss.py`
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import connect, insert_items, init  # noqa: E402


def parse_since(s: str) -> dt.datetime:
    """Parse '7d', '30d', '24h', '2w' into a UTC cutoff datetime."""
    m = re.fullmatch(r"(\d+)([dhw])", s.strip().lower())
    if not m:
        raise ValueError(f"--since must be like '7d', '30d', '24h', '2w'; got {s!r}")
    n, unit = int(m.group(1)), m.group(2)
    delta = {"h": dt.timedelta(hours=n), "d": dt.timedelta(days=n), "w": dt.timedelta(weeks=n)}[unit]
    return dt.datetime.utcnow() - delta


def entry_to_item(entry: dict, outlet: dict, source_type: str) -> dict[str, Any]:
    """Normalise a feedparser entry into our items schema."""
    # published parsing — feedparser is forgiving but inconsistent
    pub: dt.datetime | None = None
    for key in ("published_parsed", "updated_parsed"):
        v = entry.get(key)
        if v:
            try:
                pub = dt.datetime(*v[:6])
                break
            except (TypeError, ValueError):
                continue

    body_html = (
        entry.get("content", [{}])[0].get("value")
        if entry.get("content")
        else entry.get("summary", "")
    )
    body = re.sub(r"<[^>]+>", " ", body_html or "")
    body = re.sub(r"\s+", " ", body).strip()

    return {
        "source_id": outlet["id"],
        "source_type": source_type,
        "medium": "article",
        "url": entry.get("link"),
        "title": (entry.get("title") or "").strip(),
        "body": body,
        "author": entry.get("author"),
        "published_at": pub.isoformat() + "Z" if pub else None,
        "lang": "en",
        "raw": {"feed_entry": dict(entry)},
        "tags": [t["term"] for t in entry.get("tags", []) if t.get("term")],
    }


def ingest_outlet(outlet: dict, source_type: str, since: dt.datetime) -> list[dict]:
    items: list[dict] = []
    for feed_url in outlet.get("rss", []) or []:
        try:
            feed = feedparser.parse(feed_url, request_headers={"User-Agent": "suppressed-voices/0.1"})
        except Exception as exc:
            print(f"[rss] {outlet['id']} {feed_url} -> error: {exc}", file=sys.stderr)
            continue
        if feed.bozo and not feed.entries:
            print(f"[rss] {outlet['id']} {feed_url} -> bozo, no entries", file=sys.stderr)
            continue
        kept = 0
        for entry in feed.entries:
            item = entry_to_item(entry, outlet, source_type)
            if item["published_at"]:
                pub = dt.datetime.fromisoformat(item["published_at"].rstrip("Z"))
                if pub < since:
                    continue
            items.append(item)
            kept += 1
        print(f"[rss] {outlet['id']:25s} {feed_url[:60]:60s} kept={kept}/{len(feed.entries)}")
    return items


def detect_source_type(config_path: pathlib.Path) -> str:
    name = config_path.name.lower()
    if "mainstream" in name:
        return "mainstream"
    return "independent"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, help="path to handles.yml or mainstream.yml")
    p.add_argument("--since", default="30d", help="time window, e.g. 7d, 30d, 2w")
    p.add_argument("--only", default="", help="comma-separated list of outlet ids to limit to")
    p.add_argument("--db", default="data/corpus.db")
    p.add_argument("--init", action="store_true", help="initialise DB if missing")
    args = p.parse_args()

    db_path = pathlib.Path(args.db)
    if args.init or not db_path.exists():
        init(db_path)

    config_path = pathlib.Path(args.config)
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    source_type = detect_source_type(config_path)
    since = parse_since(args.since)
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    conn = connect(db_path)
    total_inserted = 0
    total_failed = 0
    for outlet in cfg.get("outlets", []):
        if only and outlet["id"] not in only:
            continue
        items = ingest_outlet(outlet, source_type, since)
        ins, fail = insert_items(conn, items)
        total_inserted += ins
        total_failed += fail
    conn.close()
    print(f"[rss] DONE inserted={total_inserted} failed={total_failed} since={since.isoformat()}Z")


if __name__ == "__main__":
    main()
