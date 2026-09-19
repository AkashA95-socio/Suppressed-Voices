# suppressed-voices SKILL

This file tells Claude Code how to operate inside the suppressed-voices project. Read it before doing anything else in this directory.

## When to use this skill

Use it whenever the user asks for:
- "Run the calibration" / "build the suppression model" / "update the corpus" → Phase 1
- "Find suppressed voices on TOPIC" / "ground reports on TOPIC" / "what are independents covering on TOPIC that mainstream isn't" → Phase 2
- Any analytical question that requires reading the suppression model in `data/corpus.db`

## Operating principles

1. **Read configs first.** Always start by viewing `config/handles.yml`, `config/mainstream.yml`, and `config/vocabularies.yml`. These define the corpus and the analytical vocabulary.

2. **Prefer RSS and web over X/Instagram.** When ingesting, the order of preference is: RSS feed → outlet website → YouTube channel → Instagram (public profiles only) → web search for archived content. X/Twitter has no working free ingestion path at all (see Failure modes below) — don't attempt scripted ingestion; a human operator can manually insert an individual tweet's text via `tools/db.py --insert-article` if one is worth including.

3. **Be honest about coverage gaps.** If a source returns nothing or fails, log it in the brief explicitly. A brief that says "X/Twitter ingestion failed; relied on RSS + web" is more useful than one that pretends X data was complete.

4. **The four-model analysis is mandatory but staged.** Do Herman/Chomsky structural reading on the corpus. Do Ellul mapping per narrative. Do Jowett & O'Donnell only on the top ~20 posts/articles by engagement. Do cognitive heuristics on the same subset plus paired opposing posts. Don't run the artifact-level steps on every item; that's wasteful.

5. **Cite primary sources by URL or post ID.** Every claim in a brief must be traceable to a specific item in `data/corpus.db`. No fabrication.

6. **Use the database, not memory.** The agent's reasoning lives in your prompts. The agent's *facts* live in SQLite. Query the DB; don't hallucinate from prior context.

## Phase 1 — Calibration (build suppression model)

Trigger: "calibrate", "update the model", "refresh the corpus".

Steps:
1. Read `agent/calibrate_prompt.md` in full. It is the operative instruction set.
2. View the configs.
3. Run the ingestion tools in this order:
   - `python tools/ingest_rss.py --config config/handles.yml --since 30d` (independents)
   - `python tools/ingest_rss.py --config config/mainstream.yml --since 30d` (mainstream)
   - `python tools/ingest_web.py --from-rss-queue` (fetches full article text for items found in RSS)
   - `python tools/ingest_youtube.py --config config/handles.yml --max 20`
4. Run `python analysis/calibrate.py --window 30d --verbose`.
5. Read the calibration summary it writes to `outputs/calibration_<date>.md`.
6. Surface to the user: how many items, which sources failed, what the headline suppression patterns look like.

Non-interactive alternative: `python run.py calibrate --provider <gemini|deepseek|openai>` runs steps 3-4 procedurally and then calls `analysis/run_calibrate_agent.py` to do the Step-4 four-model analysis via that provider's API, writing `outputs/suppression_model_<date>.md` directly — no Claude Code session needed. Use this skill's live, tool-using flow above when deeper interactive drill-down is wanted instead.

## Phase 2 — Topic Query (find ground voices on a new topic)

Trigger: "find suppressed voices on X", "ground reports on X", "what's missing on X".

Steps:
1. Read `agent/query_prompt.md` in full.
2. Confirm the calibration is recent (within 7 days). If not, suggest running calibration first or proceeding with a stale-model warning.
3. Run targeted ingestion for the topic:
   - `python tools/ingest_web.py --search "TOPIC ground report site:thewire.in OR site:caravanmagazine.in OR ..."` (use the WebSearch tool inside Claude Code if the script-level search hits limits)
   - For YouTube: search the channels in handles.yml for the topic
   - Also run web_search and web_fetch (Claude Code's own tools) to get fresh items not in the calibration corpus
4. Insert any new items into `data/corpus.db` via the ingestion scripts (idempotent on URL).
5. Run `python analysis/query_topic.py "TOPIC" --output outputs/briefs/<slug>.md`.
6. Read the generated brief, identify the most suppressed voices, and produce a refined version applying the four-model analysis with specific quotes and post IDs.
7. Save the final brief to `outputs/briefs/<slug>_final.md` and surface its key findings to the user.

## Failure modes to expect

- **RSS feeds change URLs.** If `ingest_rss.py` reports a feed as 404, update `config/handles.yml` and retry. Don't silently skip.
- **trafilatura fails on JS-heavy sites.** Some outlets (especially newer ones) are SPAs. Fallback: Claude Code's own `web_fetch` tool, then store the cleaned text manually via `tools/db.py --insert-article`.
- **YouTube transcripts may not exist.** For older videos or non-English content, auto-transcripts may be absent or wrong. Note this and skip — don't fabricate.
- **X/Twitter has no free scripted ingestion path — confirmed dead ends (2026-09-17):** ilo.so is fully Cloudflare-gated (403 even on `robots.txt`) and its only real API returns follower-growth stats, not tweet content; Nitter mirrors are dead in practice; and X strips tweet text from `og:*` meta tags for unauthenticated fetches, so even finding a tweet URL via web search doesn't yield retrievable content. Do not re-attempt scripted X ingestion without a paid API (~$200+/mo) or a real logged-in session. Manual-only fallback: if a human operator spots a relevant tweet, copy its text by hand and insert via `tools/db.py --insert-article`.
- **Mainstream paywalls.** TOI, HT often paywall. Use Google News snippets + headlines for comparison; the *headline framing* is itself analytically valuable.

## What NOT to do

- Do not invent quotes, post IDs, URLs, or engagement numbers.
- Do not skip the four-model analysis to "save time" — the analysis IS the deliverable.
- Do not let the agent's outputs stand without sanity-checking for the structural-symmetry trap (cynical relativism between independent and IT-cell posts). Factual asymmetry outranks rhetorical symmetry. Always.
- Do not write briefs without naming which sources were attempted and which failed.
- Do not assume an outlet's stance from its reputation; derive it from the calibration corpus.

## Relevant tools available to Claude Code

Beyond the project scripts, Claude Code has direct access to:
- `web_search` — useful for topic discovery and finding articles not in the calibration corpus
- `web_fetch` — useful for retrieving specific URLs when scraping fails
- `bash` — to run all the project scripts
- `view`, `str_replace`, `create_file` — to read configs, edit briefs

Use these freely. They are *complements* to the project's own ingestion scripts, not replacements.
