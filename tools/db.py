"""
db.py — SQLite schema and helpers for the suppressed-voices corpus.

The DB is the agent's persistent memory. All ingestion scripts write here.
The analysis scripts read from here. Claude Code can query it directly via
sqlite3 or via the helpers below.

Run as:
    python tools/db.py --init                # create tables
    python tools/db.py --stats               # print row counts
    python tools/db.py --insert-article      # stdin JSON, for manual entry
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sqlite3
import sys
from typing import Any, Iterable

DEFAULT_DB = pathlib.Path("data/corpus.db")

SCHEMA = r"""
PRAGMA foreign_keys = ON;

-- One row per ingested item (article, post, video transcript)
CREATE TABLE IF NOT EXISTS items (
    id            TEXT PRIMARY KEY,           -- sha256(source||url||timestamp)[:16]
    source_id     TEXT NOT NULL,              -- e.g., 'thewire', 'timesofindia'
    source_type   TEXT NOT NULL CHECK (source_type IN
                    ('independent','mainstream','government','journalist')),
    medium        TEXT NOT NULL CHECK (medium IN
                    ('article','tweet','instagram','youtube','rss','other')),
    url           TEXT,
    title         TEXT,
    body          TEXT,                       -- cleaned full text
    author        TEXT,
    published_at  TEXT,                       -- ISO 8601
    ingested_at   TEXT NOT NULL,
    lang          TEXT,
    raw           TEXT,                       -- original JSON, for re-processing
    hash          TEXT NOT NULL,              -- content hash for dedup
    UNIQUE(source_id, url)
);

CREATE INDEX IF NOT EXISTS idx_items_published   ON items(published_at);
CREATE INDEX IF NOT EXISTS idx_items_source_type ON items(source_type);
CREATE INDEX IF NOT EXISTS idx_items_source_id   ON items(source_id);

-- Engagement metrics, stored separately because they update over time
CREATE TABLE IF NOT EXISTS engagement (
    item_id      TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    measured_at  TEXT NOT NULL,
    likes        INTEGER,
    shares       INTEGER,
    comments     INTEGER,
    views        INTEGER,
    PRIMARY KEY (item_id, measured_at)
);

-- Topic tags (loose; used for retrieval). Primary domain in items_classification.
CREATE TABLE IF NOT EXISTS tags (
    item_id  TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    tag      TEXT NOT NULL,
    PRIMARY KEY (item_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);

-- Narratives — clusters of items the agent identifies as one story
CREATE TABLE IF NOT EXISTS narratives (
    id              TEXT PRIMARY KEY,         -- 'N0001' style
    description     TEXT NOT NULL,            -- one-line, neutral
    primary_domain  TEXT,
    secondary_domain TEXT,
    tier            TEXT,                     -- 'T1'|'T2'|'T3'
    first_seen      TEXT,
    last_seen       TEXT,
    created_at      TEXT NOT NULL,
    suppression_reasoning  TEXT,
    mainstream_filter_most_at_play  TEXT
);

CREATE TABLE IF NOT EXISTS narrative_items (
    narrative_id  TEXT NOT NULL REFERENCES narratives(id) ON DELETE CASCADE,
    item_id       TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    PRIMARY KEY (narrative_id, item_id)
);

-- Affected groups per narrative
CREATE TABLE IF NOT EXISTS narrative_groups (
    narrative_id  TEXT NOT NULL REFERENCES narratives(id) ON DELETE CASCADE,
    group_tag     TEXT NOT NULL,
    PRIMARY KEY (narrative_id, group_tag)
);

-- The four-model analysis lives here, one row per narrative.
-- Stored as JSON to keep schema flexible; query via JSON1 functions.
CREATE TABLE IF NOT EXISTS narrative_analysis (
    narrative_id  TEXT PRIMARY KEY REFERENCES narratives(id) ON DELETE CASCADE,
    hc_filters_evaded         TEXT,    -- JSON array
    hc_residual_filters       TEXT,    -- JSON array
    ellul                     TEXT,    -- JSON object
    structural_depth          INTEGER, -- 1-5
    intersectional_count      INTEGER,
    updated_at                TEXT NOT NULL
);

-- Artifact-level analysis on selected items
CREATE TABLE IF NOT EXISTS artifact_analysis (
    item_id              TEXT PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    jowett_odonnell      TEXT NOT NULL,   -- JSON object
    cognitive_heuristics TEXT NOT NULL,   -- JSON object
    updated_at           TEXT NOT NULL
);

-- Outlet-level vocabulary and ideology mapping (output of calibration)
CREATE TABLE IF NOT EXISTS outlet_profile (
    source_id            TEXT PRIMARY KEY,
    framing_phrases      TEXT,        -- JSON array
    register             TEXT,
    state_axis           INTEGER,     -- -5..+5
    culture_axis         INTEGER,
    market_axis          INTEGER,
    ellul_profile        TEXT,        -- JSON
    heuristic_profile    TEXT,        -- JSON
    sample_evidence_ids  TEXT,        -- JSON array
    updated_at           TEXT NOT NULL
);

-- Structural symmetries — pairs of (independent, opposing) posts on same event
CREATE TABLE IF NOT EXISTS structural_symmetries (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    event_description     TEXT,
    independent_item_id   TEXT REFERENCES items(id),
    opposing_item_id      TEXT REFERENCES items(id),
    shared_heuristics     TEXT,    -- JSON array
    shared_techniques     TEXT,    -- JSON array
    finding               TEXT,
    created_at            TEXT NOT NULL
);

-- Calibration runs — audit trail of when the model was rebuilt
CREATE TABLE IF NOT EXISTS calibration_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    window_days   INTEGER,
    items_seen    INTEGER,
    narratives_created  INTEGER,
    notes         TEXT
);
"""


def hash_id(*parts: str) -> str:
    """Stable 16-char id from any number of parts."""
    h = hashlib.sha256("||".join(p or "" for p in parts).encode("utf-8"))
    return h.hexdigest()[:16]


def content_hash(text: str) -> str:
    """Hash of cleaned content, for dedup across mirrors/syndication."""
    norm = " ".join((text or "").lower().split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]


def connect(db_path: pathlib.Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(db_path: pathlib.Path = DEFAULT_DB) -> None:
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"[db] initialised at {db_path}")


def insert_item(conn: sqlite3.Connection, item: dict[str, Any]) -> str:
    """Insert one item. Returns the item id. Idempotent on (source_id, url)."""
    required = {"source_id", "source_type", "medium"}
    missing = required - item.keys()
    if missing:
        raise ValueError(f"missing required fields: {missing}")

    item_id = item.get("id") or hash_id(
        item["source_id"], item.get("url", ""), item.get("published_at", "")
    )
    body = item.get("body", "") or ""
    item_data = {
        "id": item_id,
        "source_id": item["source_id"],
        "source_type": item["source_type"],
        "medium": item["medium"],
        "url": item.get("url"),
        "title": item.get("title"),
        "body": body,
        "author": item.get("author"),
        "published_at": item.get("published_at"),
        "ingested_at": dt.datetime.utcnow().isoformat() + "Z",
        "lang": item.get("lang"),
        "raw": json.dumps(item.get("raw", {}), ensure_ascii=False),
        "hash": content_hash(body or item.get("title", "")),
    }
    cols = ",".join(item_data.keys())
    placeholders = ",".join("?" for _ in item_data)
    conn.execute(
        f"INSERT OR IGNORE INTO items ({cols}) VALUES ({placeholders})",
        list(item_data.values()),
    )

    if "engagement" in item and item["engagement"]:
        e = item["engagement"]
        conn.execute(
            """INSERT OR REPLACE INTO engagement
               (item_id, measured_at, likes, shares, comments, views)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                item_id,
                dt.datetime.utcnow().isoformat() + "Z",
                e.get("likes"),
                e.get("shares"),
                e.get("comments"),
                e.get("views"),
            ),
        )

    for tag in item.get("tags", []) or []:
        conn.execute(
            "INSERT OR IGNORE INTO tags (item_id, tag) VALUES (?, ?)",
            (item_id, tag),
        )

    return item_id


def insert_items(
    conn: sqlite3.Connection, items: Iterable[dict[str, Any]]
) -> tuple[int, int]:
    """Insert many items. Returns (inserted, skipped_or_failed)."""
    inserted = 0
    failed = 0
    for it in items:
        try:
            insert_item(conn, it)
            inserted += 1
        except Exception as exc:
            failed += 1
            print(f"[db] insert failed: {exc}", file=sys.stderr)
    conn.commit()
    return inserted, failed


def stats(db_path: pathlib.Path = DEFAULT_DB) -> dict[str, Any]:
    conn = connect(db_path)
    out = {}
    out["items_total"] = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    by_type = conn.execute(
        "SELECT source_type, COUNT(*) FROM items GROUP BY source_type"
    ).fetchall()
    out["items_by_type"] = {row[0]: row[1] for row in by_type}
    by_source = conn.execute(
        "SELECT source_id, COUNT(*) FROM items GROUP BY source_id "
        "ORDER BY COUNT(*) DESC LIMIT 30"
    ).fetchall()
    out["top_sources"] = {row[0]: row[1] for row in by_source}
    out["narratives"] = conn.execute("SELECT COUNT(*) FROM narratives").fetchone()[0]
    out["calibration_runs"] = conn.execute(
        "SELECT COUNT(*) FROM calibration_runs"
    ).fetchone()[0]
    conn.close()
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="suppressed-voices DB helper")
    p.add_argument("--init", action="store_true", help="create schema")
    p.add_argument("--stats", action="store_true", help="print row counts")
    p.add_argument(
        "--insert-article",
        action="store_true",
        help="read one item as JSON from stdin and insert",
    )
    p.add_argument("--db", default=str(DEFAULT_DB))
    args = p.parse_args()

    db_path = pathlib.Path(args.db)
    if args.init:
        init(db_path)
    if args.stats:
        s = stats(db_path)
        print(json.dumps(s, indent=2))
    if args.insert_article:
        item = json.loads(sys.stdin.read())
        conn = connect(db_path)
        item_id = insert_item(conn, item)
        conn.commit()
        conn.close()
        print(item_id)


if __name__ == "__main__":
    main()
