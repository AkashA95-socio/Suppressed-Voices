"""
run_query_agent.py — Phase 2 analysis via LLM API (Gemini, DeepSeek, or OpenAI).

Reads the skeleton + article bodies from corpus, calls the chosen LLM to apply
the four-model analysis, and writes the final brief.

See analysis/llm_common.py for supported providers and their env vars.

Usage:
    python analysis/run_query_agent.py "TCS Nashik NIA" \\
        --skeleton outputs/briefs/tcs_nashik_nia.md \\
        --sidecar  outputs/briefs/tcs_nashik_nia.json \\
        --output   outputs/briefs/tcs_nashik_nia_final.md \\
        --provider deepseek \\
        --api-key  sk-...

    # Or use an env var:
    $env:DEEPSEEK_API_KEY = "sk-..."
    python analysis/run_query_agent.py ... --provider deepseek
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import textwrap

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from llm_common import PROVIDERS, load_text, fetch_bodies, dispatch  # noqa: E402


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_prompt(query_prompt_md: str, skeleton_md: str,
                 bodies: dict[str, dict]) -> tuple[str, str]:
    """Returns (system_instruction, user_message)."""
    system = query_prompt_md

    body_blocks: list[str] = []
    for iid, item in bodies.items():
        trunc = " [truncated]" if item["truncated"] else ""
        body_blocks.append(
            f"### [{iid}] {item['type']}/{item['source']} — {item['title']}\n"
            f"URL: {item['url']}\n\n"
            f"{item['body']}{trunc}"
        )

    body_section = (
        "\n\n---\n\n## Article bodies loaded from corpus\n\n"
        + "\n\n---\n\n".join(body_blocks)
    ) if body_blocks else ""

    user = textwrap.dedent(f"""\
        You have been given the `agent/query_prompt.md` instructions as your
        system prompt.  Below is the skeleton produced by `query_topic.py`
        and the article bodies loaded from the corpus DB.

        Your task: follow Steps 4-6 of `agent/query_prompt.md` exactly and
        produce the complete final brief.  Write it as a single Markdown
        document suitable for saving directly to disk.  Do not add any
        preamble or closing remarks outside the brief itself.

        ---

        ## Skeleton from query_topic.py

        {skeleton_md}
        {body_section}
        """)
    return system, user


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="Run suppressed-voices query analysis via LLM API"
    )
    p.add_argument("topic", help="Topic string (for logging only)")
    p.add_argument("--skeleton", required=True,
                   help="Path to skeleton .md from query_topic.py")
    p.add_argument("--sidecar",
                   help="Path to JSON sidecar from query_topic.py")
    p.add_argument("--output", required=True,
                   help="Output path for final brief markdown")
    p.add_argument("--provider", default="gemini",
                   choices=list(PROVIDERS),
                   help="LLM provider: gemini | deepseek | openai  (default: gemini)")
    p.add_argument("--api-key",
                   help="API key. If omitted, reads from the provider's env var "
                        "(GEMINI_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY)")
    p.add_argument("--model",
                   help="Model ID. Defaults: gemini=gemini-3.1-pro-preview, "
                        "deepseek=deepseek-chat, openai=gpt-4o")
    p.add_argument("--db", default="data/corpus.db")
    p.add_argument("--max-body-chars", type=int, default=3000)
    p.add_argument("--max-items",      type=int, default=25)
    args = p.parse_args()

    default_model, env_var = PROVIDERS[args.provider]
    model   = args.model or default_model
    api_key = args.api_key or os.environ.get(env_var)

    if not api_key:
        print(f"[run_query_agent] ERROR: no API key for provider '{args.provider}'.\n"
              f"  Pass --api-key KEY  or  set {env_var}=KEY", file=sys.stderr)
        sys.exit(1)

    prompt_path = PROJECT_ROOT / "agent" / "query_prompt.md"
    if not prompt_path.exists():
        print(f"[run_query_agent] ERROR: {prompt_path} not found.", file=sys.stderr)
        sys.exit(1)

    query_prompt_md = load_text(prompt_path)
    skeleton_md     = load_text(args.skeleton)

    db_path = pathlib.Path(args.db)
    bodies: dict[str, dict] = {}
    if args.sidecar:
        sidecar_path = pathlib.Path(args.sidecar)
        if sidecar_path.exists():
            sidecar  = json.loads(load_text(sidecar_path))
            item_ids = sidecar.get("all_items", [])[:args.max_items]
            bodies   = fetch_bodies(db_path, item_ids, args.max_body_chars)
            print(f"[run_query_agent] loaded {len(bodies)}/{len(item_ids)} bodies",
                  file=sys.stderr)

    system, user = build_prompt(query_prompt_md, skeleton_md, bodies)
    result = dispatch(args.provider, api_key, system, user, model)

    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result, encoding="utf-8")
    print(f"[{args.provider}] wrote final brief -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
