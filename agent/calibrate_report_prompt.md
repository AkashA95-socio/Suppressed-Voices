# Calibrate report prompt — Phase 1 (headless)

You are producing the annotated suppression model for the suppressed-voices
project, as a single Markdown report. You are being called via a plain LLM
API (no tool use, no database access) — everything you need is provided in
the user message: the calibration brief's Tier 1/2/3 topic tables and the
full text of the items referenced in them. You cannot execute SQL or run
scripts. Your only output is the Markdown report text itself.

This is the headless counterpart to `agent/calibrate_prompt.md` Steps 4-5 —
same analytical framework, but every "insert this into a database table"
instruction becomes "write this as a report section" instead.

## Goal

Produce the full content of `outputs/suppression_model_<date>.md`: an
annotated reading of the calibration brief, with the four-model analysis
applied to the Tier 1 and Tier 2 narratives.

## Step 1 — Cluster topic-tokens into named narratives

The calibration data identifies *tokens* (e.g., `uapa undertrial`, `manual
scavenging`, `bilkis bano`). Many tokens belong to the same underlying
narrative. Read the constituent items provided and cluster them.

For each cluster, give it a short narrative label and a one-line, neutral,
factual description. Everything below is organised per narrative.

## Step 2 — Apply Herman & Chomsky (structural)

For each narrative, identify:
- `filters_evaded` — which mainstream filters this story breaks (from
  {ownership, advertising, sourcing, flak, fear_ideology})
- `residual_filters_active` — which filters still operate on the
  independents reporting it (from `vocabularies.yml::residual_filters`)
- `mainstream_filter_most_at_play` — the single filter most responsible for
  mainstream silence

## Step 3 — Apply Ellul (civilisational) — DO NOT SKIP `absent_sociological_field`

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

The `absent_sociological_field` is the most important Ellul-specific output.
Examples:
- For a UAPA undertrial story: "Bollywood patriotic-romantic grammar that
  makes years-long detention without trial feel like routine procedural
  matter, festival-aestheticist culture that crowds out grief"
- For a Sundarbans displacement story: "motivational-influencer optimism
  (entrepreneurial-resilience trope) that contradicts climate-immobility
  realities"
- For a manual scavenging story: "festival-aestheticist culture that
  aesthetically conceals the labour that maintains it; family-WhatsApp
  universe that displaces caste-blame onto modernity"

Be specific. "Cultural conditioning" is not an answer.

## Step 4 — Apply Jowett & O'Donnell (artifact level) — selectively

Pick the **top 10-20 items by engagement and salience** across the items
provided. For each, run the full 10-step analysis and write it up. Cover
both:
- High-engagement independent-media posts
- Any captured opposing posts (PIB statements, mainstream framings on the
  same event) present in the provided items

Apply the same rigour to both. Do not flatten the framework's
valence-agnosticism by treating independent posts as "not propaganda."

## Step 5 — Apply cognitive heuristics (receiver level) — same selected items

For the same 10-20 items, write up:
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

When you find paired (independent, opposing) items on the same event with
similar heuristic profiles, note the pair explicitly under "Structural
symmetries observed" — record the finding carefully, noting the symmetry
but never collapsing factual asymmetry into rhetorical equivalence.

## Step 6 — Outlet profiles

For each source that has enough items in the provided set to judge:
- The top framing phrases actually used
- A rough score on the three axes (state-critical, cultural-liberal,
  market-critical) from -5 to +5
- The dominant Ellul mode and direction
- A heuristic profile (most-used vs least-used heuristics)

## Step 7 — Write the report

Produce the full Markdown report with these sections, in order:

1. **Executive summary**: 4-6 sentences. Items analysed, top three
   suppression patterns, surprises.
2. **Tier 1 narratives** with full four-model annotation
3. **Tier 2 narratives** (the doubly-suppressed) with extra attention —
   these are the actionable ones
4. **Tier 3 patterns**: where independents cover but virality fails
5. **Outlet profiles** summary table
6. **Structural symmetries observed** (with the factual-vs-rhetorical
   caveat)
7. **Coverage gaps**: which sources/feeds failed and what that means (use
   the failure notes given to you in the user message)
8. **Recommendations for the next query phase**: which Tier 2 narratives
   are worth deepening

Write it as a single Markdown document suitable for saving directly to
disk. Do not add any preamble or closing remarks outside the report itself.

## Constraints

- **No fabrication.** Every claim cites an item ID from the provided data.
- **Vernacular gap warning.** If the corpus is overwhelmingly English, say
  so, and recommend weighting PARI/Khabar Lahariya/Maktoob more heavily
  next run.
- **Stale-corpus warning.** If items are unevenly distributed in time (most
  from 1 week, none from week 4), flag it.
- **Frame-leakage finding.** If you spot independent outlets using
  mainstream framings (e.g., `urban Naxal` without quotation/critique),
  call it out. This is a meaningful Filter 5 finding.
