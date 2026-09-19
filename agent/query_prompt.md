# Query prompt — Phase 2

You are running a topic query in the suppressed-voices agent. Your job is to surface the ground voices most likely to have been suppressed on a specific topic, and to deliver a structured brief that names them precisely.

## Goal

Produce `outputs/briefs/<topic-slug>_final.md` — a fully annotated brief that:
1. Identifies all suppressed narratives on the topic (not just keywords)
2. Applies the four-model analysis to each narrative
3. Names specific people, communities, and places the user should follow up on
4. Gives an honest accounting of what sources you couldn't reach

## Step 1 — Check calibration freshness

Verify `data/corpus.db` has a recent calibration run:
```bash
python tools/db.py --stats
```

If the last calibration was more than 7 days ago, warn the user. Proceed with a stale-model caveat.

## Step 2 — Targeted ingestion

Before querying the existing corpus, pull fresh content specific to the topic. Order of preference:

```bash
# Web search via Claude Code's own web_search tool — use it directly
# Search patterns to try:
#   "<topic> India 2026 site:indiaspend.com OR site:thewire.in OR site:scroll.in"
#   "<topic> India ground report 2026"
#   "<topic> workers India heat 2026"
#   "<topic> IndiaSpend OR Mongabay OR BehanBox 2026"

# Then fetch the articles and insert:
python tools/ingest_web.py --from-stdin   # pipe in URLs collected from web_search

# Also check YouTube for relevant channels:
python tools/ingest_youtube.py --config config/handles.yml --max 5
```

Use web_fetch directly for any specific article URL you find. Insert via:
```bash
echo '{"source_id":"...", "source_type":"independent", "medium":"article", ...}' \
  | python tools/db.py --insert-article
```

Or better: use `ingest_web.py --url <url>` for each URL found.

## Step 3 — Run the query script

```bash
python analysis/query_topic.py "<topic>" \
  --output outputs/briefs/<slug>.md
```

Read both the `.md` skeleton and the `.json` sidecar it produces.

## Step 4 — Apply the four-model analysis

For every narrative cluster identified in the skeleton, apply all four models.

### 4a. Herman & Chomsky (structural)

Identify:
- `filters_evaded` — which of {ownership, advertising, sourcing, flak, fear_ideology} this narrative breaks past in independent media
- `residual_filters_active` — which filters still operate even on the independents (from `vocabularies.yml::residual_filters`)
- `mainstream_filter_most_at_play` — the single filter most responsible for mainstream silence
- **For this topic specifically:** is the silence about advertiser interests (platform companies), sourcing (no official frame), fear-ideology (security/anti-national), or ownership?

### 4b. Ellul (civilisational)

For each narrative:
```json
{
  "propaganda_type": "POLITICAL|SOCIOLOGICAL|MIXED",
  "agitation_or_integration": "AGITATION|INTEGRATION|BOTH",
  "direction": "VERTICAL|HORIZONTAL|BOTH",
  "rational_or_irrational": "RATIONAL|IRRATIONAL|MIXED",
  "sociological_substrate": "<from vocabularies.yml>",
  "absent_sociological_field": "<specific, named — this is the point>"
}
```

The `absent_sociological_field` must name the specific cultural grammar that makes the suppressed story unthinkable within the dominant information environment. "Cultural conditioning" is not acceptable. Name the specific grammar: a TV show, a government scheme, a festival aesthetic, a WhatsApp universe.

### 4c. Jowett & O'Donnell (artifact level)

Pick the **top 5–10 items by relevance and engagement** across the full set (independents + any mainstream counterparts). For each, run the full 10-step analysis:

1. **Ideology and purpose** — what does it want the audience to believe/do?
2. **Context** — historical, political, economic context the artifact assumes
3. **Identification of propagandist** — who produced it? What are their institutional interests?
4. **Structure of propaganda org** — outlet type, funding, editorial control
5. **Target audience** — who is the item actually written for?
6. **Media utilisation** — platform, format, distribution channel
7. **Special techniques** — from `vocabularies.yml::jo_special_techniques`
8. **Audience reaction** — what response did it generate or is designed to generate?
9. **Counter-propaganda** — what is the opposing frame, and where does it appear?
10. **Effects and evaluation** — what did this item actually accomplish?

Apply to BOTH independent and mainstream items. Do not treat independent posts as non-propaganda — they have purposes and techniques too.

### 4d. Cognitive heuristics (receiver level)

For the same top 5–10 items:
```json
{
  "heuristics_at_play": ["<from vocabularies.yml::heuristics>"],
  "dominant_heuristic": "...",
  "heuristic_evidence": "...",
  "counter_heuristic_risk": "...",
  "virality_explanation": "...",
  "structural_similarity_to_opposing": "..."
}
```

When you find paired (independent, opposing) posts on the same event with similar heuristic profiles, note the structural symmetry — but be explicit that rhetorical symmetry does not imply factual equivalence.

## Step 5 — Name the suppressed voices

This is the deliverable the user actually needs. For each suppressed narrative, produce a **Named Voices** section:

- **Named individuals:** specific people quoted or referenced in the independent coverage who should be followed up (with their role, location, and what they said)
- **Named communities:** specific villages, districts, or demographic groups identified in ground reports
- **Named institutions:** companies, government bodies, or agencies whose conduct is documented
- **Follow-up leads:** specific documents, RTI applications, legal filings, or data sources the user could pursue

These must come from items in the corpus. Do not invent.

## Step 6 — Write the final brief

`outputs/briefs/<slug>_final.md` must contain:

1. **Brief summary** (3–5 sentences): what the topic query found, who is suppressed, and why
2. **Narrative clusters** — each with:
   - Tier classification + reasoning
   - Full four-model annotation
   - Named voices section
   - Key items with item IDs (for DB traceability)
3. **Mainstream comparison** — what mainstream IS saying, and what frame it uses
4. **Structural symmetries** (if any) — with factual-asymmetry caveat
5. **Coverage gaps** — which sources failed and what that means
6. **Recommended actions** — concrete next steps for the user

## Constraints

- **No fabrication.** Every claim must cite an item ID or a web-fetched URL.
- **Honest about gaps.** If fresh web searches return nothing, say so.
- **No false equivalence.** Structural similarity in heuristics does not equal moral equivalence between factual and fabricated content.
- **The absent_sociological_field is mandatory.** Do not skip it. It is the most analytically distinctive output of this framework.
- **Name the people.** A brief that says "workers in Rajasthan" is less useful than one that says "Ravindra Rajpoot, 25, Flipkart delivery worker (IndiaSpend item c457e25b4720fbc4)."
