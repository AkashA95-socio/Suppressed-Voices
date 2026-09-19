"""
pipeline.py — Fully automated suppressed-voices query pipeline.

Runs: ingestion -> optional web search -> query_topic -> LLM analysis -> brief

Providers and their env vars
-----------------------------
  gemini    GEMINI_API_KEY      models: gemini-3.1-pro-preview, gemini-2.5-flash
  deepseek  DEEPSEEK_API_KEY    models: deepseek-chat, deepseek-reasoner
  openai    OPENAI_API_KEY      models: gpt-4o, gpt-4o-mini

Usage examples:

  # DeepSeek (set env var once, then just run):
  $env:DEEPSEEK_API_KEY = "sk-..."
  python pipeline.py "manual scavenging Dalit 2026" --provider deepseek --skip-ingestion

  # Gemini:
  python pipeline.py "gig worker heat stress India" --provider gemini --api-key AIza...

  # OpenAI, with extra URLs to ingest first:
  python pipeline.py "Manipur internet shutdown" \\
      --provider openai --model gpt-4o \\
      --extra-urls https://article-14.com/...

  # Auto web-search via DuckDuckGo (needs: pip install duckduckgo-search):
  python pipeline.py "manual scavenging Dalit 2026" --provider deepseek --web-search
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

# Windows console fix: allow Unicode in stdout/stderr
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def _run(cmd: list[str], desc: str = "") -> None:
    label = desc or " ".join(cmd[:3])
    print(f"\n[pipeline] ▶ {label}", flush=True)
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"[pipeline] ✗ {label} failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"[pipeline] ✓ {label}", flush=True)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "topic"


def ddg_search(queries: list[str], max_per_query: int = 8) -> list[str]:
    """Return a deduplicated list of URLs from DuckDuckGo text search."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        print(
            "[pipeline] WARNING: duckduckgo-search not installed; skipping web search.\n"
            "  Install with:  pip install duckduckgo-search",
            file=sys.stderr,
        )
        return []

    seen: set[str] = set()
    urls: list[str] = []
    with DDGS() as ddgs:
        for q in queries:
            print(f"[pipeline] web search: {q}", flush=True)
            for r in ddgs.text(q, max_results=max_per_query):
                url = r.get("href", "")
                if url and url not in seen:
                    seen.add(url)
                    urls.append(url)
    return urls


def build_search_queries(topic: str) -> list[str]:
    """Generate targeted India-focused search queries for a topic."""
    base = topic.strip()
    return [
        f"{base} India 2026 site:indiaspend.com OR site:thewire.in OR site:scroll.in",
        f"{base} India ground report 2026",
        f"{base} India IndiaSpend OR Article14 OR Mongabay 2026",
    ]


_PROVIDER_ENV = {
    "gemini":   "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai":   "OPENAI_API_KEY",
}
_PROVIDER_DEFAULT_MODEL = {
    "gemini":   "gemini-3.1-pro-preview",
    "deepseek": "deepseek-chat",
    "openai":   "gpt-4o",
}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Suppressed-voices automated query pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("topic",
                    help="Topic string, e.g. 'TCS Nashik NIA conversion'")
    ap.add_argument("--provider", default="gemini",
                    choices=list(_PROVIDER_ENV),
                    help="LLM provider: gemini | deepseek | openai  (default: gemini)")
    ap.add_argument("--api-key",
                    help="API key. If omitted, reads from the provider's env var "
                         "(GEMINI_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY)")
    ap.add_argument("--model",
                    help="Model override. Defaults: gemini=gemini-3.1-pro-preview, "
                         "deepseek=deepseek-chat, openai=gpt-4o")
    ap.add_argument("--skip-ingestion", action="store_true",
                    help="Skip RSS ingestion (use existing corpus as-is)")
    ap.add_argument("--extra-urls", nargs="*", metavar="URL",
                    help="Additional URLs to ingest before querying")
    ap.add_argument("--web-search", action="store_true",
                    help="Auto-search DuckDuckGo and ingest found URLs "
                         "(requires: pip install duckduckgo-search)")
    ap.add_argument("--search-queries", nargs="*", metavar="QUERY",
                    help="Override default DuckDuckGo queries (used with --web-search)")
    ap.add_argument("--db", default="data/corpus.db")
    ap.add_argument("--rss-config", default="config/handles.yml")
    ap.add_argument("--max-body-chars", type=int, default=3000)
    ap.add_argument("--max-items",      type=int, default=25)
    args = ap.parse_args()

    # Resolve API key early so we fail fast
    env_var = _PROVIDER_ENV[args.provider]
    api_key = args.api_key or os.environ.get(env_var)
    if not api_key:
        print(
            f"[pipeline] ERROR: no API key for provider '{args.provider}'.\n"
            f"  Pass --api-key KEY  or  set $env:{env_var} = 'KEY'",
            file=sys.stderr,
        )
        sys.exit(1)

    model = args.model or _PROVIDER_DEFAULT_MODEL[args.provider]

    py   = sys.executable
    slug = slugify(args.topic)
    skeleton = f"outputs/briefs/{slug}.md"
    sidecar  = f"outputs/briefs/{slug}.json"
    final    = f"outputs/briefs/{slug}_final.md"

    pathlib.Path("outputs/briefs").mkdir(parents=True, exist_ok=True)

    # ── Step 1: RSS ingestion ────────────────────────────────────────────────
    if not args.skip_ingestion:
        _run(
            [py, "tools/ingest_rss.py", "--config", args.rss_config,
             "--db", args.db],
            "RSS ingestion"
        )
    else:
        print("[pipeline] skipping RSS ingestion (--skip-ingestion)", flush=True)

    # ── Step 2: Web search → ingest found URLs ───────────────────────────────
    if args.web_search:
        queries = args.search_queries or build_search_queries(args.topic)
        found_urls = ddg_search(queries)
        print(f"[pipeline] web search found {len(found_urls)} URLs", flush=True)
        for url in found_urls:
            _run(
                [py, "tools/ingest_web.py", "--url", url, "--db", args.db],
                f"ingest {url[:60]}…"
            )

    # ── Step 3: Extra URLs ───────────────────────────────────────────────────
    for url in (args.extra_urls or []):
        _run(
            [py, "tools/ingest_web.py", "--url", url, "--db", args.db],
            f"ingest {url[:60]}…"
        )

    # ── Step 4: Generate skeleton ────────────────────────────────────────────
    _run(
        [py, "analysis/query_topic.py", args.topic,
         "--output", skeleton, "--db", args.db],
        "query_topic skeleton"
    )

    # ── Step 5: LLM analysis → final brief ──────────────────────────────────
    agent_cmd = [
        py, "analysis/run_query_agent.py", args.topic,
        "--skeleton",       skeleton,
        "--sidecar",        sidecar,
        "--output",         final,
        "--provider",       args.provider,
        "--model",          model,
        "--db",             args.db,
        "--max-body-chars", str(args.max_body_chars),
        "--max-items",      str(args.max_items),
        "--api-key",        api_key,
    ]
    _run(agent_cmd, f"{args.provider} analysis ({model})")

    print(f"\n[pipeline] ✅  Done.  Final brief: {final}\n", flush=True)


if __name__ == "__main__":
    main()
