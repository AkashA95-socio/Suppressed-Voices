"""
ingest_web.py — Fetch and clean full article text using trafilatura.

Usage:
    # one-off: fetch a single URL
    python tools/ingest_web.py --url https://thewire.in/...

    # batch: fill in body for all items where body is empty/short
    python tools/ingest_web.py --from-rss-queue --max 100

    # from a search query (uses the configured outlets as site: filters)
    python tools/ingest_web.py --search "manual scavenging" --since 30d

trafilatura handles most modern news sites well. For SPA-only sites where
it fails, the agent (Claude Code) should fall back to its built-in web_fetch
tool and pipe the cleaned text in via `tools/db.py --insert-article`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys
import time
from typing import Any

import trafilatura  # type: ignore

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import connect, insert_item, init  # noqa: E402


def fetch_one(url: str, timeout: int = 20) -> dict[str, Any] | None:
    """Fetch a URL, extract the article. Return None on failure."""
    try:
        downloaded = trafilatura.fetch_url(url, no_ssl=False)
    except Exception as exc:
        print(f"[web] fetch error {url}: {exc}", file=sys.stderr)
        return None
    if not downloaded:
        print(f"[web] empty download {url}", file=sys.stderr)
        return None

    extracted = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=True,
        with_metadata=True,
        output_format="json",
    )
    if not extracted:
        print(f"[web] extract failed {url}", file=sys.stderr)
        return None

    import json

    data = json.loads(extracted)
    return {
        "url": url,
        "title": data.get("title"),
        "body": data.get("text") or data.get("raw_text") or "",
        "author": data.get("author"),
        "published_at": data.get("date"),
        "lang": data.get("language", "en"),
        "raw": data,
    }


def infer_source_id(url: str, source_map: dict[str, str]) -> str:
    """Crude domain-to-source-id map from configs."""
    for domain, sid in source_map.items():
        if domain in url:
            return sid
    return "unknown"


def build_source_map() -> tuple[dict[str, str], dict[str, str]]:
    """Returns (domain -> source_id, source_id -> source_type)."""
    import yaml

    configs = ["config/handles.yml", "config/mainstream.yml"]
    type_for_config = {"handles.yml": "independent", "mainstream.yml": "mainstream"}
    domain_to_id: dict[str, str] = {}
    id_to_type: dict[str, str] = {}
    for cp in configs:
        p = pathlib.Path(cp)
        if not p.exists():
            continue
        cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
        stype = type_for_config[p.name]
        for outlet in cfg.get("outlets", []):
            id_to_type[outlet["id"]] = stype
            site = outlet.get("website", "")
            if site:
                domain = site.replace("https://", "").replace("http://", "").rstrip("/")
                domain_to_id[domain] = outlet["id"]
    return domain_to_id, id_to_type


def cmd_url(args: argparse.Namespace) -> None:
    domain_to_id, id_to_type = build_source_map()
    item = fetch_one(args.url)
    if not item:
        sys.exit(1)

    source_id = infer_source_id(args.url, domain_to_id)
    source_type = id_to_type.get(source_id, "independent")
    item.update({
        "source_id": source_id,
        "source_type": source_type,
        "medium": "article",
    })

    db_path = pathlib.Path(args.db)
    if not db_path.exists():
        init(db_path)
    conn = connect(db_path)
    iid = insert_item(conn, item)
    conn.commit()
    conn.close()
    print(f"[web] inserted {iid} from {source_id} ({source_type})")


def cmd_from_rss_queue(args: argparse.Namespace) -> None:
    """Fill in body text for items inserted by RSS where body is short/empty."""
    db_path = pathlib.Path(args.db)
    conn = connect(db_path)
    rows = conn.execute(
        """SELECT id, url, source_id, source_type FROM items
           WHERE medium='article' AND (body IS NULL OR length(body) < 400)
                 AND url IS NOT NULL
           ORDER BY ingested_at DESC
           LIMIT ?""",
        (args.max,),
    ).fetchall()
    print(f"[web] backfill candidates: {len(rows)}")

    n_ok = n_fail = 0
    for row in rows:
        time.sleep(args.delay)  # be polite
        fetched = fetch_one(row["url"])
        if not fetched:
            n_fail += 1
            continue
        conn.execute(
            "UPDATE items SET body=?, title=COALESCE(?, title), author=COALESCE(?, author) "
            "WHERE id=?",
            (fetched["body"], fetched.get("title"), fetched.get("author"), row["id"]),
        )
        n_ok += 1
        if n_ok % 10 == 0:
            conn.commit()
            print(f"[web] backfilled {n_ok}/{len(rows)}")
    conn.commit()
    conn.close()
    print(f"[web] DONE backfilled={n_ok} failed={n_fail}")


def cmd_search(args: argparse.Namespace) -> None:
    """
    Search-driven ingestion. Takes a topic string and runs site-restricted
    searches against the configured outlets. This script does NOT do web
    search itself — it prints search queries for Claude Code to execute via
    its web_search tool, then accepts the URLs back via stdin.

    Usage:
        python tools/ingest_web.py --search "manual scavenging" --since 30d
        # then in Claude Code, run web_search on each suggested query, collect
        # URLs, and pipe them back:
        # echo "url1\\nurl2\\nurl3" | python tools/ingest_web.py --from-stdin
    """
    domain_to_id, _ = build_source_map()
    queries = []
    # group outlets into chunks of 3 for site: queries (search engines limit)
    domains = list(domain_to_id.keys())
    for i in range(0, len(domains), 3):
        chunk = domains[i:i + 3]
        sites = " OR ".join(f"site:{d}" for d in chunk)
        queries.append(f'"{args.search}" ({sites})')

    print("# Suggested web_search queries (run via Claude Code):")
    for q in queries:
        print(q)
    print("")
    print("# Then collect URLs and pipe back:")
    print("#   echo \"https://...\\nhttps://...\" | python tools/ingest_web.py --from-stdin")


def cmd_from_stdin(args: argparse.Namespace) -> None:
    """Read URLs from stdin, fetch each, insert."""
    domain_to_id, id_to_type = build_source_map()
    db_path = pathlib.Path(args.db)
    if not db_path.exists():
        init(db_path)
    conn = connect(db_path)
    n_ok = n_fail = 0
    for line in sys.stdin:
        url = line.strip()
        if not url or not url.startswith("http"):
            continue
        item = fetch_one(url)
        if not item:
            n_fail += 1
            continue
        sid = infer_source_id(url, domain_to_id)
        item.update({
            "source_id": sid,
            "source_type": id_to_type.get(sid, "independent"),
            "medium": "article",
        })
        insert_item(conn, item)
        n_ok += 1
    conn.commit()
    conn.close()
    print(f"[web] DONE from-stdin inserted={n_ok} failed={n_fail}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/corpus.db")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--url", help="fetch a single URL and insert")
    g.add_argument("--from-rss-queue", action="store_true", help="backfill body for RSS items")
    g.add_argument("--search", help="topic — prints search queries for Claude Code to run")
    g.add_argument("--from-stdin", action="store_true", help="read URLs from stdin, fetch and insert")
    p.add_argument("--max", type=int, default=50, help="for --from-rss-queue")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between fetches")
    p.add_argument("--since", default="30d", help="for --search context only")
    args = p.parse_args()

    if args.url:
        cmd_url(args)
    elif args.from_rss_queue:
        cmd_from_rss_queue(args)
    elif args.search:
        cmd_search(args)
    elif args.from_stdin:
        cmd_from_stdin(args)


if __name__ == "__main__":
    main()
