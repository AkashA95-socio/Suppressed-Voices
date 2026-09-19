"""
ingest_youtube.py — Pull transcripts from outlet and journalist YouTube channels.

Usage:
    python tools/ingest_youtube.py --config config/handles.yml --max 20
    python tools/ingest_youtube.py --channel @newslaundry --max 50
    python tools/ingest_youtube.py --video https://www.youtube.com/watch?v=...

Many independent outlets and individual journalists publish primarily to
YouTube (Ravish Kumar, Khabar Lahariya, etc.). Auto-transcripts are
imperfect — Hindi / Bengali / Tamil ASR is noisy — but they are the only
scalable way to ingest video content.

Requires yt-dlp. Install: pip install yt-dlp youtube-transcript-api
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
from typing import Any

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from db import connect, insert_item, init  # noqa: E402

try:
    from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    HAS_TRANSCRIPT_API = True
except ImportError:
    HAS_TRANSCRIPT_API = False


def list_channel_videos(channel_url: str, max_videos: int) -> list[dict]:
    """Use yt-dlp to list recent videos from a channel without downloading them."""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        "--playlist-end", str(max_videos),
        f"{channel_url}/videos",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        print("[yt] yt-dlp not installed; install with: pip install yt-dlp", file=sys.stderr)
        return []
    except subprocess.TimeoutExpired:
        print(f"[yt] timeout listing {channel_url}", file=sys.stderr)
        return []

    if result.returncode != 0:
        print(f"[yt] yt-dlp failed for {channel_url}: {result.stderr[:200]}", file=sys.stderr)
        return []

    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            videos.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return videos


def get_transcript(video_id: str, langs: tuple[str, ...] = ("en", "hi", "bn", "ta")) -> str:
    """Best-effort transcript fetch. Returns '' on failure."""
    if not HAS_TRANSCRIPT_API:
        return ""
    try:
        for lang in langs:
            try:
                segments = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
                return " ".join(seg["text"] for seg in segments)
            except Exception:
                continue
        return ""
    except Exception as exc:
        print(f"[yt] transcript fail {video_id}: {exc}", file=sys.stderr)
        return ""


def video_to_item(video: dict, transcript: str, source_id: str, source_type: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_type": source_type,
        "medium": "youtube",
        "url": video.get("url") or video.get("webpage_url") or f"https://www.youtube.com/watch?v={video.get('id')}",
        "title": video.get("title"),
        "body": transcript,
        "author": video.get("uploader") or video.get("channel"),
        "published_at": _ts_to_iso(video.get("upload_date") or video.get("timestamp")),
        "lang": "auto",
        "raw": {"yt_meta": {k: video.get(k) for k in
                            ("id", "duration", "view_count", "like_count")}},
        "engagement": {
            "views": video.get("view_count"),
            "likes": video.get("like_count"),
            "comments": video.get("comment_count"),
        } if video.get("view_count") else None,
    }


def _ts_to_iso(ts) -> str | None:
    if not ts:
        return None
    if isinstance(ts, str) and len(ts) == 8 and ts.isdigit():
        # YYYYMMDD format from yt-dlp
        return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}T00:00:00Z"
    if isinstance(ts, (int, float)):
        return dt.datetime.utcfromtimestamp(ts).isoformat() + "Z"
    return None


def ingest_channel(channel_url: str, source_id: str, source_type: str,
                   max_videos: int, conn) -> int:
    print(f"[yt] {source_id}: listing up to {max_videos} videos from {channel_url}")
    videos = list_channel_videos(channel_url, max_videos)
    print(f"[yt] {source_id}: got {len(videos)} videos")
    n = 0
    for v in videos:
        vid = v.get("id")
        if not vid:
            continue
        transcript = get_transcript(vid)
        if not transcript:
            print(f"[yt]   no transcript for {vid} — keeping metadata only")
        item = video_to_item(v, transcript, source_id, source_type)
        try:
            insert_item(conn, item)
            n += 1
        except Exception as exc:
            print(f"[yt]   insert fail {vid}: {exc}", file=sys.stderr)
    conn.commit()
    return n


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", help="path to handles.yml — process all outlets with youtube field")
    p.add_argument("--channel", help="single channel URL or @handle")
    p.add_argument("--video", help="single video URL")
    p.add_argument("--max", type=int, default=20, help="max videos per channel")
    p.add_argument("--db", default="data/corpus.db")
    p.add_argument("--source-id", help="override source_id when using --channel")
    args = p.parse_args()

    db_path = pathlib.Path(args.db)
    if not db_path.exists():
        init(db_path)
    conn = connect(db_path)

    if args.config:
        cfg = yaml.safe_load(pathlib.Path(args.config).read_text(encoding="utf-8"))
        stype = "mainstream" if "mainstream" in pathlib.Path(args.config).name else "independent"
        total = 0
        for outlet in cfg.get("outlets", []):
            yt = outlet.get("youtube")
            if not yt:
                continue
            total += ingest_channel(yt, outlet["id"], stype, args.max, conn)
        print(f"[yt] DONE total inserted={total}")

    elif args.channel:
        url = args.channel
        if url.startswith("@"):
            url = f"https://www.youtube.com/{url}"
        sid = args.source_id or url.rstrip("/").split("/")[-1].lstrip("@")
        n = ingest_channel(url, sid, "independent", args.max, conn)
        print(f"[yt] DONE inserted={n}")

    elif args.video:
        # single video
        cmd = ["yt-dlp", "--dump-json", args.video]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"[yt] failed: {result.stderr[:200]}", file=sys.stderr)
            sys.exit(1)
        v = json.loads(result.stdout)
        transcript = get_transcript(v.get("id", ""))
        sid = args.source_id or v.get("channel_id", "unknown_yt")
        item = video_to_item(v, transcript, sid, "independent")
        insert_item(conn, item)
        conn.commit()
        print(f"[yt] inserted {v.get('id')} ({len(transcript)} chars transcript)")

    else:
        p.error("specify --config, --channel, or --video")

    conn.close()


if __name__ == "__main__":
    main()
