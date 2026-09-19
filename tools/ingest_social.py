"""
ingest_social.py — Best-effort ingestion from X (Twitter) and Instagram.

THIS MODULE WILL OFTEN FAIL. Read this header before debugging.

X/Twitter (2026 reality):
  - snscrape: broken since X disabled the read API for unauth users
  - twscrape: works but requires real X accounts (ToS-grey-zone)
  - Nitter: most public instances are dead; the few that survive get
    rate-limited fast
  - Official API: tiered pricing, ~$200/month for Basic (10k tweets)

Our approach:
  1. Try a list of Nitter mirrors (configurable). Get RSS-style output.
  2. If all mirrors fail, log it cleanly and exit 0. The agent should
     then fall back to web_search for archived/quoted versions of the
     handles' posts.
  3. We do NOT log into X.

Instagram (2026 reality):
  - instaloader works for public profiles at low volume (~50 posts/day
     before challenge prompts appear)
  - We use it without login (--no-login) which is more limited but
    safer

Usage:
    python tools/ingest_social.py --config config/handles.yml --best-effort
    python tools/ingest_social.py --twitter-handle thewire_in --max 50
    python tools/ingest_social.py --instagram-handle thewire_in --max 30
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys
import time
from typing import Any
from urllib.parse import quote

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import connect, insert_item, init  # noqa: E402

# Nitter mirrors. Most will be dead at any given time; the script tries each
# in turn. Update this list periodically. The "official" wiki of working
# instances is at https://github.com/zedeus/nitter/wiki/Instances
NITTER_MIRRORS = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.privacyredirect.com",
    "https://nitter.tiekoetter.com",
]


def try_nitter_rss(handle: str, max_items: int = 50) -> list[dict]:
    """Try Nitter mirrors until one works. Returns parsed RSS-like items."""
    import feedparser  # type: ignore

    for mirror in NITTER_MIRRORS:
        url = f"{mirror}/{handle}/rss"
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "suppressed-voices/0.1"})
            if feed.bozo or not feed.entries:
                print(f"[social] nitter mirror dead: {mirror}", file=sys.stderr)
                continue
            print(f"[social] nitter OK: {mirror} -> {len(feed.entries)} entries for @{handle}")
            items = []
            for entry in feed.entries[:max_items]:
                pub = None
                if entry.get("published_parsed"):
                    pub = dt.datetime(*entry["published_parsed"][:6]).isoformat() + "Z"
                # nitter RSS body is HTML; strip tags
                body_html = entry.get("summary", "")
                body = re.sub(r"<[^>]+>", " ", body_html or "")
                body = re.sub(r"\s+", " ", body).strip()
                items.append({
                    "url": entry.get("link"),
                    "title": (entry.get("title") or "").strip(),
                    "body": body,
                    "author": handle,
                    "published_at": pub,
                    "raw": {"nitter_entry": dict(entry), "mirror": mirror},
                })
            return items
        except Exception as exc:
            print(f"[social] nitter mirror error {mirror}: {exc}", file=sys.stderr)
            continue
    print(f"[social] all Nitter mirrors failed for @{handle}", file=sys.stderr)
    return []


def ingest_twitter_handle(handle: str, source_id: str, source_type: str,
                          max_items: int, conn) -> int:
    items = try_nitter_rss(handle, max_items)
    n = 0
    for item in items:
        item.update({
            "source_id": source_id,
            "source_type": source_type,
            "medium": "tweet",
        })
        try:
            insert_item(conn, item)
            n += 1
        except Exception as exc:
            print(f"[social]   insert fail: {exc}", file=sys.stderr)
    conn.commit()
    return n


def ingest_instagram_handle(handle: str, source_id: str, source_type: str,
                            max_items: int, conn) -> int:
    """Public-only instagram via instaloader."""
    try:
        import instaloader  # type: ignore
    except ImportError:
        print("[social] instaloader not installed; skipping IG. "
              "pip install instaloader", file=sys.stderr)
        return 0

    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )
    try:
        profile = instaloader.Profile.from_username(L.context, handle)
    except Exception as exc:
        print(f"[social] IG profile fetch failed for @{handle}: {exc}", file=sys.stderr)
        return 0

    n = 0
    for i, post in enumerate(profile.get_posts()):
        if i >= max_items:
            break
        try:
            item = {
                "source_id": source_id,
                "source_type": source_type,
                "medium": "instagram",
                "url": f"https://www.instagram.com/p/{post.shortcode}/",
                "title": (post.caption or "")[:200],
                "body": post.caption or "",
                "author": handle,
                "published_at": post.date_utc.isoformat() + "Z",
                "raw": {"shortcode": post.shortcode, "typename": post.typename},
                "engagement": {
                    "likes": post.likes,
                    "comments": post.comments,
                },
            }
            insert_item(conn, item)
            n += 1
            time.sleep(2)  # IG is touchy
        except Exception as exc:
            print(f"[social]   IG insert fail: {exc}", file=sys.stderr)
            time.sleep(10)
    conn.commit()
    return n


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", help="path to handles.yml")
    p.add_argument("--twitter-handle", help="single X handle to fetch")
    p.add_argument("--instagram-handle", help="single IG handle to fetch")
    p.add_argument("--max", type=int, default=50)
    p.add_argument("--db", default="data/corpus.db")
    p.add_argument("--best-effort", action="store_true",
                   help="ignore failures, continue through all configured handles")
    args = p.parse_args()

    db_path = pathlib.Path(args.db)
    if not db_path.exists():
        init(db_path)
    conn = connect(db_path)

    if args.config:
        cfg = yaml.safe_load(pathlib.Path(args.config).read_text(encoding="utf-8"))
        stype = "mainstream" if "mainstream" in pathlib.Path(args.config).name else "independent"
        total_tw = total_ig = 0
        for outlet in cfg.get("outlets", []):
            sid = outlet["id"]
            if outlet.get("twitter"):
                n = ingest_twitter_handle(outlet["twitter"], sid, stype, args.max, conn)
                total_tw += n
                print(f"[social] {sid} twitter inserted={n}")
            if outlet.get("instagram"):
                n = ingest_instagram_handle(outlet["instagram"], sid, stype, args.max, conn)
                total_ig += n
                print(f"[social] {sid} instagram inserted={n}")
        # journalists too
        for j in cfg.get("journalists", []):
            if j.get("twitter"):
                n = ingest_twitter_handle(j["twitter"], j["name"].lower().replace(" ", "_"),
                                          "journalist", args.max, conn)
                total_tw += n
        print(f"[social] DONE twitter_total={total_tw} instagram_total={total_ig}")

    elif args.twitter_handle:
        n = ingest_twitter_handle(args.twitter_handle, args.twitter_handle,
                                  "journalist", args.max, conn)
        print(f"[social] DONE twitter inserted={n}")

    elif args.instagram_handle:
        n = ingest_instagram_handle(args.instagram_handle, args.instagram_handle,
                                    "journalist", args.max, conn)
        print(f"[social] DONE instagram inserted={n}")
    else:
        p.error("specify --config, --twitter-handle, or --instagram-handle")

    conn.close()


if __name__ == "__main__":
    main()
