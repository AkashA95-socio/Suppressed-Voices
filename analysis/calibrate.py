"""
calibrate.py — Phase 1: build the suppression model.

This script:
  1. Pulls the recent corpus from data/corpus.db (independents + mainstream)
  2. Computes coverage statistics: which topics appear where, with what framing
  3. Identifies suppression patterns:
     - T1: covered by independents, absent from mainstream
     - T2: thin even in independents (low item count, low engagement)
     - T3: covered but low-virality (platform filter)
  4. Writes a calibration summary to outputs/calibration_<date>.md
  5. Stores structured findings in the DB (outlet_profile, narratives stubs)

Step 4 (the four-model annotation per narrative) is performed by Claude Code
using the agent prompt. This script produces the data scaffold; the agent
fills in the analytical layer.

Usage:
    python analysis/calibrate.py --window 30d --verbose
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import re
import sys

import yaml

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from db import connect  # noqa: E402


def parse_window(s: str) -> dt.timedelta:
    m = re.fullmatch(r"(\d+)([dhw])", s.strip().lower())
    if not m:
        raise ValueError(f"--window must be like '7d', '30d'; got {s!r}")
    n, unit = int(m.group(1)), m.group(2)
    return {"h": dt.timedelta(hours=n), "d": dt.timedelta(days=n),
            "w": dt.timedelta(weeks=n)}[unit]


def load_vocabularies() -> dict:
    return yaml.safe_load(
        (PROJECT_ROOT / "config" / "vocabularies.yml").read_text(encoding="utf-8")
    )


def naive_topics_from_title(title: str) -> set[str]:
    """
    Cheap topic extraction: lowercase content words, strip stopwords, n-grams.
    This is intentionally crude — the agent (Claude) does the semantic work.
    Calibration just needs a comparable vocabulary across outlets.
    """
    if not title:
        return set()
    text = re.sub(r"[^a-zA-Z\s]", " ", title.lower())
    words = [w for w in text.split() if len(w) > 3 and w not in STOPWORDS]
    bigrams = [" ".join(words[i:i + 2]) for i in range(len(words) - 1)]
    return set(words + bigrams)


STOPWORDS = {
    "this", "that", "with", "from", "have", "been", "their", "would",
    "about", "into", "after", "over", "than", "when", "what", "more",
    "says", "said", "will", "could", "should", "amid", "post", "year",
    "days", "week", "today", "still", "even", "also", "many", "much",
    "take", "make", "made", "back", "down", "year", "years", "first",
    "last", "next", "very", "just", "only", "some", "such", "they",
    "them", "these", "those", "your", "ours", "we're", "doesn", "didn",
    "isn", "wasn", "wouldn", "couldn", "shouldn", "report", "reports",
}


def compute_topic_overlap(conn, since_iso: str) -> dict:
    """
    For each topic-token observed across the corpus, count items per
    source_type (independent vs mainstream).
    """
    cursor = conn.execute(
        """SELECT id, source_id, source_type, title, body, published_at
           FROM items
           WHERE published_at >= ?""",
        (since_iso,),
    )
    topic_counts = collections.defaultdict(lambda: collections.Counter())
    topic_items = collections.defaultdict(list)

    n_items = 0
    for row in cursor:
        n_items += 1
        topics = naive_topics_from_title(row["title"] or "")
        for t in topics:
            topic_counts[t][row["source_type"]] += 1
            topic_items[t].append(row["id"])

    return {"topic_counts": topic_counts, "topic_items": topic_items, "n_items": n_items}


def identify_suppression_tiers(overlap: dict, min_independent: int = 3,
                               min_total: int = 3) -> dict:
    """
    Crude tier assignment:
      T1: independent_count >= min, mainstream_count == 0
      T2: independent_count low (1-2), mainstream_count == 0
      T3: independent + mainstream both > 0 but skewed
    The agent will refine these with semantic understanding.
    """
    tiers = {"T1": [], "T2": [], "T3": []}
    for topic, counts in overlap["topic_counts"].items():
        ind = counts.get("independent", 0) + counts.get("journalist", 0)
        main = counts.get("mainstream", 0)
        gov = counts.get("government", 0)
        total = ind + main + gov
        if total < min_total:
            continue
        if ind >= min_independent and main == 0:
            tiers["T1"].append({"topic": topic, "ind": ind, "main": main,
                                "items": overlap["topic_items"][topic][:8]})
        elif 1 <= ind <= 2 and main == 0:
            tiers["T2"].append({"topic": topic, "ind": ind, "main": main,
                                "items": overlap["topic_items"][topic][:8]})
        elif ind >= 1 and main >= 1 and (ind / max(main, 1)) >= 3:
            tiers["T3"].append({"topic": topic, "ind": ind, "main": main,
                                "items": overlap["topic_items"][topic][:8]})

    # sort each tier by independent count desc
    for k in tiers:
        tiers[k].sort(key=lambda x: x["ind"], reverse=True)
    return tiers


def detect_framing_phrases(conn, since_iso: str, vocab: dict) -> dict:
    """
    For each source, count occurrences of mainstream and independent
    framing phrases. The presence of MAINSTREAM phrases inside INDEPENDENT
    coverage is itself a finding (frame capture / Filter 5 leakage).
    """
    framing_counts = collections.defaultdict(lambda: collections.Counter())
    cursor = conn.execute(
        "SELECT source_id, source_type, title, body FROM items WHERE published_at >= ?",
        (since_iso,),
    )
    main_phrases = [p.lower() for p in vocab.get("mainstream_framings", [])]
    ind_phrases = [p.lower() for p in vocab.get("independent_framings", [])]

    for row in cursor:
        text = ((row["title"] or "") + " " + (row["body"] or "")).lower()
        for p in main_phrases:
            if p in text:
                framing_counts[row["source_id"]][f"main::{p}"] += 1
        for p in ind_phrases:
            if p in text:
                framing_counts[row["source_id"]][f"ind::{p}"] += 1
    return framing_counts


def write_calibration_brief(window_days: int, n_items: int, tiers: dict,
                            framing: dict, source_breakdown: dict,
                            out_path: pathlib.Path) -> None:
    today = dt.date.today().isoformat()
    lines: list[str] = []
    lines.append(f"# Calibration brief — {today}\n")
    lines.append(f"Window: last {window_days} days. Items analysed: **{n_items}**.\n")

    lines.append("## Source breakdown\n")
    lines.append("| Source type | Items |\n|---|---|")
    for k, v in sorted(source_breakdown.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} |")
    lines.append("")

    lines.append("## Tier 1 — covered by independents, absent in mainstream\n")
    lines.append("These are the visible-to-us-but-buried-elsewhere stories. "
                 "Mainstream filter most likely active: *sourcing* "
                 "(official/PIB frame closes story) and/or *fear ideology* "
                 "(security/anti-national frame).\n")
    if not tiers["T1"]:
        lines.append("*No T1 candidates in this window.*\n")
    else:
        lines.append("| Topic token | Independent items | Mainstream items |")
        lines.append("|---|---|---|")
        for entry in tiers["T1"][:30]:
            lines.append(f"| `{entry['topic']}` | {entry['ind']} | {entry['main']} |")
    lines.append("")

    lines.append("## Tier 2 — thin even in independents\n")
    lines.append("Doubly suppressed: stories that *should* fit independents' "
                 "DNA but get only 1–2 items. Often climate-gender-caste "
                 "intersectional stories that fit no national binary frame.\n")
    if not tiers["T2"]:
        lines.append("*No T2 candidates in this window.*\n")
    else:
        lines.append("| Topic token | Independent items | Mainstream items |")
        lines.append("|---|---|---|")
        for entry in tiers["T2"][:50]:
            lines.append(f"| `{entry['topic']}` | {entry['ind']} | {entry['main']} |")
    lines.append("")

    lines.append("## Tier 3 — covered but skewed (independent ≥ 3× mainstream)\n")
    if not tiers["T3"]:
        lines.append("*No T3 candidates in this window.*\n")
    else:
        lines.append("| Topic token | Independent | Mainstream |")
        lines.append("|---|---|---|")
        for entry in tiers["T3"][:30]:
            lines.append(f"| `{entry['topic']}` | {entry['ind']} | {entry['main']} |")
    lines.append("")

    lines.append("## Framing phrase distribution\n")
    lines.append("Counts of mainstream-coded and independent-coded framing "
                 "phrases per source. Rows where MAINSTREAM phrases appear "
                 "in INDEPENDENT outlets indicate possible frame leakage.\n")
    if framing:
        all_phrases = set()
        for c in framing.values():
            all_phrases.update(c.keys())
        # show top ~12 phrases overall
        agg = collections.Counter()
        for c in framing.values():
            agg.update(c)
        top = [p for p, _ in agg.most_common(12)]
        if top:
            header = "| Source | " + " | ".join(p.split("::", 1)[1] for p in top) + " |"
            lines.append(header)
            lines.append("|" + "---|" * (len(top) + 1))
            for src, c in sorted(framing.items()):
                row = [src] + [str(c.get(p, 0)) for p in top]
                lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    lines.append("## Next step (for Claude Code)\n")
    lines.append(
        "Read `agent/calibrate_prompt.md`. For each Tier-1 and Tier-2 "
        "topic above, cluster the constituent items into named narratives, "
        "apply the four-model analysis, and write the structured findings "
        "into the `narratives` and `narrative_analysis` tables. Then "
        "produce `outputs/suppression_model_<date>.md` summarising the "
        "annotated model.\n"
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[calibrate] wrote {out_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--window", default="30d", help="time window e.g. 7d, 30d")
    p.add_argument("--db", default="data/corpus.db")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    db_path = pathlib.Path(args.db)
    if not db_path.exists():
        print(f"[calibrate] DB missing at {db_path}. Run ingest first.", file=sys.stderr)
        sys.exit(1)

    delta = parse_window(args.window)
    since = dt.datetime.utcnow() - delta
    since_iso = since.isoformat() + "Z"
    window_days = delta.days or max(1, delta.total_seconds() // 86400)
    vocab = load_vocabularies()

    conn = connect(db_path)

    # source breakdown
    rows = conn.execute(
        "SELECT source_type, COUNT(*) FROM items WHERE published_at >= ? GROUP BY source_type",
        (since_iso,),
    ).fetchall()
    source_breakdown = {r[0]: r[1] for r in rows}

    if args.verbose:
        print(f"[calibrate] window since {since_iso}")
        print(f"[calibrate] source_breakdown {source_breakdown}")

    overlap = compute_topic_overlap(conn, since_iso)
    if args.verbose:
        print(f"[calibrate] n_items={overlap['n_items']} "
              f"unique_topics={len(overlap['topic_counts'])}")

    tiers = identify_suppression_tiers(overlap)
    if args.verbose:
        print(f"[calibrate] T1={len(tiers['T1'])} T2={len(tiers['T2'])} T3={len(tiers['T3'])}")

    framing = detect_framing_phrases(conn, since_iso, vocab)

    # log the run
    started = dt.datetime.utcnow().isoformat() + "Z"
    conn.execute(
        """INSERT INTO calibration_runs
           (started_at, finished_at, window_days, items_seen, narratives_created, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (started, started, int(window_days), overlap["n_items"], 0,
         f"T1={len(tiers['T1'])} T2={len(tiers['T2'])} T3={len(tiers['T3'])}"),
    )
    conn.commit()

    out_path = PROJECT_ROOT / "outputs" / f"calibration_{dt.date.today().isoformat()}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_calibration_brief(int(window_days), overlap["n_items"], tiers, framing,
                            source_breakdown, out_path)

    # stash a JSON sidecar for the agent prompt to read
    json_path = out_path.with_suffix(".json")
    json_path.write_text(json.dumps({
        "window_days": int(window_days),
        "n_items": overlap["n_items"],
        "source_breakdown": source_breakdown,
        "tiers": {k: v[:50] for k, v in tiers.items()},
        "framing_top": dict(collections.Counter(
            {f"{src}::{p}": cnt for src, c in framing.items() for p, cnt in c.items()}
        ).most_common(50)),
    }, indent=2, default=str), encoding="utf-8")
    print(f"[calibrate] wrote sidecar {json_path}")

    conn.close()


if __name__ == "__main__":
    main()
