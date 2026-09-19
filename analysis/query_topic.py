"""
query_topic.py — Phase 2: given a new topic, surface suppressed voices.

This script:
  1. Searches the corpus DB for items matching the topic
  2. Compares independent vs mainstream coverage and framing
  3. Looks up the calibration's suppression patterns
  4. Generates a structured brief skeleton for Claude Code to fill in

The agent (Claude Code) is expected to:
  - Run additional ingestion BEFORE calling this script if the corpus
    is stale or thin on the topic (use ingest_web.py with --search,
    or web_search/web_fetch directly)
  - Read the brief skeleton this writes
  - Apply the four-model analysis
  - Write the final brief

Usage:
    python analysis/query_topic.py "manual scavenging" --output outputs/briefs/manual_scavenging.md
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import re
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from db import connect  # noqa: E402


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.lower()).strip("_")
    return s or "topic"


def search_corpus(conn, topic: str, limit: int = 200,
                  min_word_overlap: int = 2) -> list[dict]:
    """
    Match items containing at least `min_word_overlap` of the topic's
    significant (>3 char) words — not just any single one. A topic with
    fewer qualifying words than the threshold falls back to requiring all
    of them, so short topics still match something.

    Single-word OR matching let one coincidental word (e.g. "funding"
    appearing in an unrelated aside) pull an entire irrelevant article into
    the results for a multi-word topic it has nothing to do with. Requiring
    overlap makes a match mean the item is actually about several of the
    topic's words together, and ranks by how many of them it contains
    rather than by recency alone.

    We use simple LIKE because FTS5 isn't always available; Claude Code
    handles semantic refinement on top of this.
    """
    words = [w for w in re.findall(r"[a-zA-Z]+", topic) if len(w) > 3]
    if not words:
        return []

    threshold = min(min_word_overlap, len(words))

    match_exprs = ["(LOWER(title || ' ' || COALESCE(body,'')) LIKE ?)" for _ in words]
    match_count_sql = " + ".join(match_exprs)
    params = [f"%{w.lower()}%" for w in words]

    sql = f"""
        SELECT id, source_id, source_type, medium, url, title,
               substr(body, 1, 600) AS body_preview, author, published_at,
               ({match_count_sql}) AS word_matches
        FROM items
        WHERE ({match_count_sql}) >= ?
        ORDER BY word_matches DESC, published_at DESC
        LIMIT ?
    """
    rows = conn.execute(sql, params + params + [threshold, limit]).fetchall()
    return [dict(r) for r in rows]


def cluster_by_source_type(items: list[dict]) -> dict:
    out = collections.defaultdict(list)
    for it in items:
        out[it["source_type"]].append(it)
    return out


def find_unique_to_independents(items: list[dict]) -> list[dict]:
    """
    Items from independents whose URL/title doesn't have a mainstream
    counterpart on a similar topic. Crude version: independent items whose
    title shares no significant word with any mainstream title in the set.
    """
    main_titles = [it["title"].lower() for it in items
                   if it["source_type"] == "mainstream" and it.get("title")]
    main_words = set()
    for t in main_titles:
        for w in re.findall(r"[a-zA-Z]+", t):
            if len(w) > 4:
                main_words.add(w.lower())

    unique = []
    for it in items:
        if it["source_type"] != "independent":
            continue
        ind_words = {w.lower() for w in re.findall(r"[a-zA-Z]+",
                                                    it.get("title") or "")
                     if len(w) > 4}
        overlap = ind_words & main_words
        if not overlap:
            unique.append(it)
    return unique


def detect_framings(items: list[dict], vocab: dict) -> dict:
    """How often each framing phrase appears, by source type."""
    counts = {"independent": collections.Counter(),
              "mainstream": collections.Counter(),
              "journalist": collections.Counter()}
    main_phrases = [p.lower() for p in vocab.get("mainstream_framings", [])]
    ind_phrases = [p.lower() for p in vocab.get("independent_framings", [])]
    for it in items:
        text = ((it.get("title") or "") + " " + (it.get("body_preview") or "")).lower()
        bucket = counts.get(it["source_type"], counts["independent"])
        for p in main_phrases:
            if p in text:
                bucket[f"main::{p}"] += 1
        for p in ind_phrases:
            if p in text:
                bucket[f"ind::{p}"] += 1
    return counts


def write_brief_skeleton(topic: str, items: list[dict], by_type: dict,
                         unique_ind: list[dict], framing: dict,
                         out_path: pathlib.Path) -> None:
    today = dt.date.today().isoformat()
    lines: list[str] = []
    lines.append(f"# Suppressed-voices brief: {topic}\n")
    lines.append(f"_Generated {today}. This is a SKELETON — Claude Code should "
                 f"fill in the four-model analysis using `agent/query_prompt.md`._\n")

    lines.append("## Coverage at a glance\n")
    lines.append("| Source type | Items in corpus matching topic |")
    lines.append("|---|---|")
    for st in ("independent", "mainstream", "journalist", "government"):
        if st in by_type:
            lines.append(f"| {st} | {len(by_type[st])} |")
    lines.append("")

    if not items:
        lines.append("**No items in corpus match this topic.** "
                     "Run more ingestion: `python tools/ingest_web.py --search "
                     f"\"{topic}\"`, then re-run this query.\n")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return

    lines.append("## Items unique to independents (no mainstream counterpart)\n")
    lines.append("Candidate suppressed narratives. The agent should cluster "
                 "these into named narratives and apply the four-model "
                 "analysis to the cluster.\n")
    if not unique_ind:
        lines.append("*None — every independent item on this topic has a "
                     "mainstream counterpart by title-word overlap. "
                     "This usually means the topic IS being covered in "
                     "mainstream; check FRAMING differences instead "
                     "(next section).*\n")
    else:
        for it in unique_ind[:15]:
            t = it.get("title") or "(untitled)"
            url = it.get("url") or ""
            pub = (it.get("published_at") or "")[:10]
            lines.append(f"- **{t}** — `{it['source_id']}`, {pub}")
            lines.append(f"  - {url}")
            lines.append(f"  - id: `{it['id']}`")
        lines.append("")

    lines.append("## Mainstream coverage (for framing comparison)\n")
    if not by_type.get("mainstream"):
        lines.append("*No mainstream coverage of this topic in current corpus.* "
                     "This is itself a finding — likely Tier 1 suppression. "
                     "Mainstream silence usually indicates *sourcing* filter "
                     "(official frame closes story), *fear ideology* "
                     "(security framing forbids inquiry), or *advertising* "
                     "(advertiser interests at stake).\n")
    else:
        lines.append("| Source | Title | Date |\n|---|---|---|")
        for it in by_type["mainstream"][:10]:
            lines.append(f"| {it['source_id']} | {it.get('title','')[:80]} | "
                         f"{(it.get('published_at') or '')[:10]} |")
        lines.append("")

    lines.append("## Framing phrase distribution\n")
    if framing:
        all_phrases = set()
        for c in framing.values():
            all_phrases.update(c.keys())
        if all_phrases:
            top = collections.Counter()
            for c in framing.values():
                top.update(c)
            top_list = [p for p, _ in top.most_common(10)]
            if top_list:
                header = "| Source type | " + " | ".join(p.split("::", 1)[1]
                                                          for p in top_list) + " |"
                lines.append(header)
                lines.append("|" + "---|" * (len(top_list) + 1))
                for st, c in framing.items():
                    if not c:
                        continue
                    row = [st] + [str(c.get(p, 0)) for p in top_list]
                    lines.append("| " + " | ".join(row) + " |")
            lines.append("")

    lines.append("## Items the agent should analyse in depth\n")
    lines.append("Read each of the URLs below in full (use Claude Code's "
                 "`web_fetch` tool for any not in the DB body), then apply "
                 "the four-model analysis from `agent/query_prompt.md`.\n")
    for it in items[:20]:
        lines.append(f"- `{it['id']}` [{it['source_type']}/{it['source_id']}] "
                     f"{it.get('title','')[:100]}\n  {it.get('url','')}")
    lines.append("")

    lines.append("## What the final brief MUST contain\n")
    lines.append("(per `agent/query_prompt.md`)")
    lines.append("- Named narratives (not just topic keywords) with cluster IDs")
    lines.append("- Tier classification (T1/T2/T3) for each narrative with reasoning")
    lines.append("- For each narrative: Herman/Chomsky filters evaded + residual filters active")
    lines.append("- For each narrative: Ellul mapping including absent_sociological_field")
    lines.append("- For top 5 items by relevance: full Jowett & O'Donnell 10-step analysis")
    lines.append("- For top 5 items: cognitive heuristic profile + counter-heuristic risk")
    lines.append("- Explicit list of suppressed voices (named individuals, named "
                 "communities, named places) the user should follow up on")
    lines.append("- Honest caveat: which sources/platforms failed during ingestion "
                 "and what that means for completeness")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[query] wrote skeleton to {out_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("topic", help="topic to search for")
    p.add_argument("--db", default="data/corpus.db")
    p.add_argument("--output", help="path to brief markdown")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--min-word-overlap", type=int, default=2,
                   help="minimum number of significant topic words an item "
                        "must contain to match (default: 2). Falls back to "
                        "requiring all words if the topic has fewer than this.")
    args = p.parse_args()

    db_path = pathlib.Path(args.db)
    if not db_path.exists():
        print(f"[query] DB missing at {db_path}.", file=sys.stderr)
        sys.exit(1)

    import yaml
    vocab = yaml.safe_load(
        (PROJECT_ROOT / "config" / "vocabularies.yml").read_text(encoding="utf-8")
    )

    conn = connect(db_path)
    items = search_corpus(conn, args.topic, args.limit, args.min_word_overlap)
    by_type = cluster_by_source_type(items)
    unique_ind = find_unique_to_independents(items)
    framing = detect_framings(items, vocab)
    conn.close()

    if args.output:
        out_path = pathlib.Path(args.output)
    else:
        out_path = PROJECT_ROOT / "outputs" / "briefs" / f"{slugify(args.topic)}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    write_brief_skeleton(args.topic, items, by_type, unique_ind, framing, out_path)

    # JSON sidecar for the agent prompt
    json_path = out_path.with_suffix(".json")
    json_path.write_text(json.dumps({
        "topic": args.topic,
        "n_items": len(items),
        "by_type": {k: len(v) for k, v in by_type.items()},
        "unique_to_independents": [it["id"] for it in unique_ind],
        "all_items": [it["id"] for it in items],
        "framing": {st: dict(c) for st, c in framing.items()},
    }, indent=2, default=str), encoding="utf-8")
    print(f"[query] wrote sidecar {json_path}")


if __name__ == "__main__":
    main()
