"""Temp query script for calibration analysis."""
import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

conn = sqlite3.connect("data/corpus.db")
conn.row_factory = sqlite3.Row

mode = sys.argv[1] if len(sys.argv) > 1 else "titles"

if mode == "titles":
    rows = conn.execute("""
      SELECT id, source_id, source_type, title, body, published_at
      FROM items
      WHERE source_type IN ('independent','journalist')
        AND published_at >= '2026-04-03'
        AND title IS NOT NULL AND length(title) > 20
      ORDER BY source_id, published_at DESC
    """).fetchall()
    for r in rows:
        print(f"{r['source_id']:22s} | {(r['title'] or '')[:110]}")

elif mode == "mainstream":
    rows = conn.execute("""
      SELECT id, source_id, source_type, title, published_at
      FROM items
      WHERE source_type = 'mainstream'
        AND published_at >= '2026-04-03'
        AND title IS NOT NULL AND length(title) > 20
      ORDER BY source_id, published_at DESC
      LIMIT 150
    """).fetchall()
    for r in rows:
        print(f"{r['source_id']:22s} | {(r['title'] or '')[:110]}")

elif mode == "body":
    item_id = sys.argv[2]
    r = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if r:
        print(f"SOURCE: {r['source_id']} ({r['source_type']})")
        print(f"TITLE:  {r['title']}")
        print(f"URL:    {r['url']}")
        print(f"DATE:   {r['published_at']}")
        print(f"BODY:\n{(r['body'] or '')[:2000]}")
