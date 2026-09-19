# suppressed-voices

An agentic research toolkit for surfacing ground-level narratives that are
systematically under-reported in Indian mainstream media. Runs standalone
on your own machine with your own LLM API key (Gemini, DeepSeek, or
OpenAI) — Claude Code is optional, not required.

## What this is

A two-phase agent:

**Phase 1 — Calibration.** Ingest recent output from independent media (The Wire, Caravan, Scroll, Newslaundry, Alt News, Article14, PARI, Khabar Lahariya, Maktoob, Mongabay, IndiaSpend, etc.) and from mainstream media (Times of India, Hindustan Times, Indian Express, NDTV, Republic, India Today, Aaj Tak, Zee) plus international outlets (BBC, Al Jazeera, Reuters). Compare. Build a *suppression model*: a structured map of (a) topics covered by independents but not mainstream, (b) topics where the *framings* differ sharply, and (c) topics that appear thinly even in independents. This model is the agent's understanding of what gets buried, by whom, and why.

**Phase 2 — Query.** Given a new topic — say `manual scavenging` or `Sundarbans climate displacement` — the agent searches across multiple sources (RSS, web search, YouTube transcripts), applies the suppression model, and returns a brief that surfaces the ground voices most likely to have been muted by the structural filters identified in Phase 1.

Both phases produce their deliverable (`outputs/calibration_<date>.md` /
`outputs/suppression_model_<date>.md` for Phase 1, `outputs/briefs/<slug>_final.md`
for Phase 2) via a plain LLM API call — no agentic tool-use loop required to
get a result, though one (Claude Code, or similar) can be used for deeper,
interactive analysis. See "Optional: driving it with Claude Code" below.

## What the agent reasons over

Four analytical models stacked at four scales:

1. **Herman & Chomsky** — structural / political-economic level (five filters)
2. **Ellul** — civilisational / symbolic level (sociological propaganda, agitation vs integration, absent fields)
3. **Jowett & O'Donnell** — artifact level (10-step analysis applied valence-agnostically)
4. **Cognitive Heuristics** — receiver level (why posts travel or don't)

See `agent/calibrate_report_prompt.md` and `agent/query_prompt.md` for the
prompts that operationalise these models via a plain LLM API call (the
`agent/calibrate_prompt.md` / interactive variants are for the optional
Claude-Code-driven mode).

## Quickstart

One-time setup — creates a venv, installs dependencies, initialises the DB,
and copies `.env.example` to `.env`:

```bash
python run.py setup
```

Activate the venv it created (`.venv\Scripts\Activate.ps1` on Windows,
`source .venv/bin/activate` elsewhere), then add an API key for whichever
LLM provider you want to use to `.env`:

```
GEMINI_API_KEY=...
# or
DEEPSEEK_API_KEY=...
# or
OPENAI_API_KEY=...
```

Then run either phase:

```bash
# Phase 1 — build/refresh the suppression model (works with zero API keys;
# adding one also runs the four-model analysis automatically)
python run.py calibrate
python run.py calibrate --since 7d --provider deepseek

# Phase 2 — fully automated topic query (ingest -> LLM analysis -> brief)
python run.py query "manual scavenging Dalit 2026" --provider deepseek
python run.py query "TCS Nashik NIA" --provider gemini --web-search
```

`run.py calibrate` with no `--provider` still produces
`outputs/calibration_<date>.md` (the deterministic tier/topic-token
breakdown) but skips the qualitative four-model write-up, since that step
needs an LLM. Pass `--provider`, or just have a key set in `.env` — it's
auto-detected.

`run.py query` passes everything after the topic straight through to
`pipeline.py` (see `python pipeline.py --help` for the full flag list —
extra URLs, model override, DuckDuckGo web search, etc.).

## Realistic constraints, named upfront

- **X/Twitter has no working free ingestion path**, confirmed by direct testing (2026-09-17): `ilo.so` is fully Cloudflare-gated (no scriptable access; its only real API returns follower-growth stats, not tweet content); Nitter mirrors are dead in practice; and X strips tweet text from `og:*` meta tags for unauthenticated fetches, so even finding a tweet URL via search doesn't yield retrievable content. X is out of scope for automation here — a human operator who spots a relevant tweet can copy its text by hand and insert it via `tools/db.py --insert-article`, but nothing scripted attempts it.
- **Instagram** is more workable: `instaloader` handles public profiles at low volume, without login.
- **RSS, news websites, YouTube** are the real workhorses. Most independent outlets publish to web first.
- **Mainstream comparison** is critical and tractable: TOI/HT/IE/NDTV/IndiaToday all have RSS or scrapeable websites.

## Project structure

```
suppressed-voices/
├── README.md                    # this file
├── SKILL.md                     # entry point for the optional Claude Code mode
├── LICENSE                      # MIT
├── requirements.txt             # Python deps
├── run.py                       # single entry point: setup / calibrate / query
├── pipeline.py                  # Phase 2 automation (ingest -> LLM -> brief); run.py wraps this
├── .env.example                 # copy to .env and fill in LLM API keys
├── config/
│   ├── handles.yml              # independent + international outlets, journalists, with priorities
│   ├── mainstream.yml           # mainstream outlets to compare against
│   └── vocabularies.yml         # framing phrases, heuristics, sociological substrates
├── tools/                       # individual ingestion + utility scripts
│   ├── db.py                    # SQLite schema + helpers
│   ├── ingest_rss.py            # RSS feeds (primary fuel)
│   ├── ingest_web.py            # article scraping with trafilatura
│   ├── ingest_youtube.py        # YouTube channel transcripts via yt-dlp
│   ├── ingest_social.py         # Instagram (best-effort); no automated X/Twitter path (see above)
│   └── normalize.py             # unify into common item schema
├── analysis/
│   ├── calibrate.py             # Phase 1: deterministic tier/topic-token scaffold
│   ├── run_calibrate_agent.py   # Phase 1: four-model analysis via LLM API -> suppression_model_<date>.md
│   ├── query_topic.py           # Phase 2: deterministic skeleton for a topic
│   ├── run_query_agent.py       # Phase 2: four-model analysis via LLM API -> final brief
│   └── llm_common.py            # shared provider dispatch (Gemini/DeepSeek/OpenAI) for both agents
├── agent/
│   ├── calibrate_report_prompt.md  # Phase 1 four-model prompt for the headless LLM-API path
│   ├── calibrate_prompt.md         # Phase 1 prompt for the optional Claude-Code-driven mode
│   └── query_prompt.md             # Phase 2 prompt — Steps 4-6 used headlessly; Steps 1-3 are Claude-Code-specific
├── data/
│   ├── raw/                     # per-source raw dumps (jsonl)
│   ├── processed/               # normalised
│   └── corpus.db                # SQLite — articles, posts, narratives, suppression model
└── outputs/
    ├── calibration_<date>.md/.json      # Phase 1 deterministic output
    ├── suppression_model_<date>.md      # Phase 1 four-model analysis
    └── briefs/                          # Phase 2 per-topic briefs (markdown)
```

## Optional: driving it with Claude Code

If you do have Claude Code (or a similar tool-using coding agent) available,
it can drive the project interactively instead of the headless `run.py`
path — with live web search, ad-hoc drill-down, and direct SQL access to
`data/corpus.db` for richer narrative clustering. This is what `SKILL.md`
and `agent/calibrate_prompt.md` document. In a Claude Code session, point it
at this directory and say one of:

```
Run the calibration phase. Read agent/calibrate_prompt.md and follow it.
```

```
Run a topic query for "manual scavenging in Indian Railways". Read agent/query_prompt.md and follow it.
```

The agent will read the relevant prompt and config files, run the ingestion
tools, read from `data/corpus.db`, apply the four-model analysis, and write
a markdown brief to `outputs/`. Neither mode is required for the other —
use whichever fits your setup.

The Python scripts are thin and self-contained. Each can also be run manually:

```bash
python tools/ingest_rss.py --config config/handles.yml --since 30d
python tools/ingest_web.py --url https://thewire.in/article/...
python tools/ingest_youtube.py --channel @newslaundry --max 50
python analysis/calibrate.py --window 30d
python analysis/query_topic.py "manual scavenging" --output outputs/briefs/manual_scavenging.md
```

## Honest caveats

- **The model is provisional.** Suppression is relative to a baseline. Re-calibrate weekly; political and media landscapes shift faster than any static model.
- **English-language bias.** Most outlets in `handles.yml` publish primarily in English. Vernacular extension (Hindi, Bengali, Tamil) is a v2 priority — that's where Tier-2 ground stories actually live.
- **Heuristic analysis explains virality, not validity.** A post that fails on cognitive fluency is not therefore false; one that exploits identifiable-victim is not therefore wrong. Hold this distinction.
- **Symmetry findings will be uncomfortable.** Independent-media and IT-cell posts on the same event often share rhetorical structure (identifiable victim, moral disgust, in-group cueing). Substantive content differs sharply (one usually factual, one fabricated) but the form converges. This is a feature of the analysis, not a bug — but it must not slide into false equivalence. Factual asymmetry outranks rhetorical symmetry. Always.
- **Your own filter as the operator.** The handle list, the topic queries you choose, the briefs you act on — all carry your priors. Rerun the calibration with a different handle weighting periodically as a sanity check.
