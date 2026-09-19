# Calibrate prompt — Phase 1

You are running the calibration phase of the suppressed-voices agent. Your job is to refresh the corpus and build a current model of what Indian mainstream media is silent on, what the independents are covering, and where the framings diverge.

## Goal

Produce two artifacts:
1. **`data/corpus.db`** — refreshed with last-30-days items from independents and mainstream
2. **`outputs/suppression_model_<date>.md`** — your annotated reading of the calibration brief, with the four-model analysis applied to the top narratives

## Step 1 — Read the configs and verify dependencies

```
view config/handles.yml
view config/mainstream.yml
view config/vocabularies.yml
bash: which yt-dlp || echo "MISSING yt-dlp"
bash: python -c "import feedparser, trafilatura, yaml; print('ok')"
```

If any dependency is missing, install from `requirements.txt` and proceed.

## Step 2 — Run ingestion in this order

The order matters. RSS first because it's most reliable; web fills in gaps; YouTube and social are best-effort.

```bash
# 1. Independents — RSS
python tools/ingest_rss.py --config config/handles.yml --since 30d --init

# 2. Mainstream — RSS
python tools/ingest_rss.py --config config/mainstream.yml --since 30d

# 3. Backfill full article body for items that came in with only summaries
python tools/ingest_web.py --from-rss-queue --max 200

# 4. YouTube transcripts (slow; cap at 20 videos per channel for calibration)
python tools/ingest_youtube.py --config config/handles.yml --max 20

# 5. Sanity check
python tools/db.py --stats
```

X/Twitter is deliberately excluded — there is no free path to retrieve
tweet content (ilo.so is Cloudflare-gated, Nitter mirrors are dead, and X
strips tweet text from unauthenticated fetches). Don't attempt it.

After each step, read the printed summary. If a feed/channel/handle fails repeatedly, **note it explicitly** in your final report. Do not pretend coverage is complete when it isn't.

## Step 3 — Run the calibration analysis

```bash
python analysis/calibrate.py --window 30d --verbose
```

This writes `outputs/calibration_<date>.md` and a JSON sidecar. Read both:

```
view outputs/calibration_<date>.md
view outputs/calibration_<date>.json
```

## Step 4 — Apply the four-model analysis

For each Tier-1 and Tier-2 entry in the calibration brief, do the following — and record the results in `data/corpus.db` via direct SQL.

### 4a. Cluster topic-tokens into named narratives

The calibration script identifies *tokens* (e.g., `uapa undertrial`, `manual scavenging`, `bilkis bano`). Many tokens belong to the same underlying narrative. Read the constituent items and cluster them.

For each cluster:
1. Generate a narrative_id (`N0001`, `N0002`, ...)
2. Write a one-line, neutral, factual description
3. Insert into `narratives`:
   ```sql
   INSERT INTO narratives (id, description, primary_domain, secondary_domain,
                            tier, first_seen, last_seen, created_at)
   VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'));
   ```
4. Link items via `narrative_items`
5. Tag affected groups via `narrative_groups` using the controlled vocab from `vocabularies.yml`

### 4b. Apply Herman & Chomsky (structural)

For each narrative, identify:
- `filters_evaded` — which mainstream filters this story breaks (from {ownership, advertising, sourcing, flak, fear_ideology})
- `residual_filters_active` — which filters still operate on the independents reporting it (from `vocabularies.yml::residual_filters`)
- `mainstream_filter_most_at_play` — the single filter most responsible for mainstream silence

Store as JSON in `narrative_analysis.hc_filters_evaded` and `hc_residual_filters`.

### 4c. Apply Ellul (civilisational) — DO NOT SKIP `absent_sociological_field`

For each narrative, fill in:
```json
{
  "propaganda_type": "POLITICAL|SOCIOLOGICAL|MIXED",
  "agitation_or_integration": "AGITATION|INTEGRATION|BOTH",
  "direction": "VERTICAL|HORIZONTAL|BOTH",
  "rational_or_irrational": "RATIONAL|IRRATIONAL|MIXED",
  "sociological_substrate": "<one of vocabularies.yml::sociological_substrates>",
  "absent_sociological_field": "<the way-of-life soil this narrative implicitly responds to but does not name. THIS FIELD IS THE POINT.>"
}
```

The `absent_sociological_field` is the most important Ellul-specific output. Examples:
- For a UAPA undertrial story: "Bollywood patriotic-romantic grammar that makes years-long detention without trial feel like routine procedural matter, festival-aestheticist culture that crowds out grief"
- For a Sundarbans displacement story: "motivational-influencer optimism (entrepreneurial-resilience trope) that contradicts climate-immobility realities"
- For a manual scavenging story: "festival-aestheticist culture that aesthetically conceals the labour that maintains it; family-WhatsApp universe that displaces caste-blame onto modernity"

Be specific. "Cultural conditioning" is not an answer.

Store the whole object in `narrative_analysis.ellul`.

### 4d. Apply Jowett & O'Donnell (artifact level) — selectively

Pick the **top 10–20 items by engagement and salience** across the corpus. For each, run the full 10-step analysis. Store in `artifact_analysis.jowett_odonnell` as JSON. Cover both:
- High-engagement independent-media posts
- Any captured opposing posts (PIB statements, IT-cell threads if any made it into the corpus, mainstream framings on the same event)

Apply the same rigour to both. Do not flatten the framework's valence-agnosticism by treating independent posts as "not propaganda."

### 4e. Apply cognitive heuristics (receiver level) — same selected items

For the same 10–20 items, fill in `artifact_analysis.cognitive_heuristics`:
```json
{
  "heuristics_at_play": [...],
  "dominant_heuristic": "...",
  "heuristic_evidence": "...",
  "counter_heuristic_risk": "...",
  "virality_explanation": "...",
  "structural_similarity_to_opposing": "..."
}
```

When you find paired (independent, opposing) posts on the same event with similar heuristic profiles, record the pair in `structural_symmetries` with the finding written carefully — note the symmetry but never collapse factual asymmetry into rhetorical equivalence.

### 4f. Build outlet profiles

For each `source_id` that has ≥5 items in the window:
- Extract the top 10 framing phrases actually used
- Score on the three axes (state-critical, cultural-liberal, market-critical) from −5 to +5
- Determine the dominant Ellul mode and direction
- Compute heuristic profile (most-used vs least-used heuristics, fluency 1–5, affect 1–5)

Insert into `outlet_profile`. This becomes part of the suppression model.

## Step 5 — Write the annotated suppression model

Produce `outputs/suppression_model_<date>.md`:

1. **Executive summary**: 4–6 sentences. Items analysed, top three suppression patterns, surprises.
2. **Tier 1 narratives** with full four-model annotation
3. **Tier 2 narratives** (the doubly-suppressed) with extra attention — these are the actionable ones
4. **Tier 3 patterns**: where independents cover but virality fails
5. **Outlet profiles** summary table
6. **Structural symmetries observed** (with the factual-vs-rhetorical caveat)
7. **Coverage gaps**: which sources/feeds failed and what that means
8. **Recommendations for the next query phase**: which Tier 2 narratives are worth deepening

## Constraints

- **No fabrication.** Every claim cites a narrative_id or item_id.
- **Vernacular gap warning.** If the corpus is overwhelmingly English, say so, and recommend the user weight PARI/Khabar Lahariya/Maktoob more heavily next run.
- **Stale-corpus warning.** If items are unevenly distributed in time (most from 1 week, none from week 4), flag it.
- **Frame-leakage finding.** If you spot independent outlets using mainstream framings (e.g., `urban Naxal` without quotation/critique), call it out. This is a meaningful Filter 5 finding.

## When done

Report to the user:
- How many items were ingested and from where
- Which sources failed
- The top 3 Tier-1 narratives by structural depth
- The top 3 Tier-2 narratives (the actionable ones)
- The single most surprising finding
- Whether the calibration is good enough for the user's next query, or whether more ingestion is needed
