"""
run_calibrate_agent.py — Phase 1 four-model analysis via LLM API.

Headless counterpart to a Claude-Code-driven calibration session. Reads the
calibration brief + JSON sidecar produced by analysis/calibrate.py, fetches
the referenced item bodies from the corpus, calls the chosen LLM to apply
the four-model analysis (agent/calibrate_report_prompt.md), and writes the
annotated suppression model.

See analysis/llm_common.py for supported providers and their env vars.

Usage:
    python analysis/run_calibrate_agent.py \\
        --calibration outputs/calibration_2026-09-17.md \\
        --sidecar     outputs/calibration_2026-09-17.json \\
        --output      outputs/suppression_model_2026-09-17.md \\
        --provider deepseek

    # With no explicit paths, defaults to today's date:
    python analysis/run_calibrate_agent.py --provider deepseek
"""
from __future__ import annotations

import argparse
import datetime as dt
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

def collect_item_ids(sidecar: dict, max_items: int) -> list[str]:
    """Pull item IDs out of the T1/T2/T3 tier entries, deduped, capped."""
    seen: set[str] = set()
    ids: list[str] = []
    for tier in ("T1", "T2", "T3"):
        for entry in sidecar.get("tiers", {}).get(tier, []):
            for iid in entry.get("items", []):
                if iid not in seen:
                    seen.add(iid)
                    ids.append(iid)
    return ids[:max_items]


def build_prompt(report_prompt_md: str, calibration_md: str,
                 bodies: dict[str, dict]) -> tuple[str, str]:
    """Returns (system_instruction, user_message)."""
    system = report_prompt_md

    body_blocks: list[str] = []
    for iid, item in bodies.items():
        trunc = " [truncated]" if item["truncated"] else ""
        body_blocks.append(
            f"### [{iid}] {item['type']}/{item['source']} — {item['title']}\n"
            f"URL: {item['url']}\n\n"
            f"{item['body']}{trunc}"
        )

    body_section = (
        "\n\n---\n\n## Item bodies loaded from corpus\n\n"
        + "\n\n---\n\n".join(body_blocks)
    ) if body_blocks else ""

    user = textwrap.dedent(f"""\
        You have been given the `agent/calibrate_report_prompt.md`
        instructions as your system prompt. Below is the calibration brief
        produced by `analysis/calibrate.py` and the item bodies loaded from
        the corpus DB for the items referenced in its Tier 1/2/3 tables.

        Your task: follow Steps 1-7 of `agent/calibrate_report_prompt.md`
        exactly and produce the complete annotated suppression model.
        Write it as a single Markdown document suitable for saving directly
        to disk. Do not add any preamble or closing remarks outside the
        report itself.

        ---

        ## Calibration brief from calibrate.py

        {calibration_md}
        {body_section}
        """)
    return system, user


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="Run suppressed-voices Phase 1 four-model analysis via LLM API"
    )
    today = dt.date.today().isoformat()
    p.add_argument("--calibration", default=f"outputs/calibration_{today}.md",
                   help="Path to calibration .md from calibrate.py")
    p.add_argument("--sidecar", default=f"outputs/calibration_{today}.json",
                   help="Path to JSON sidecar from calibrate.py")
    p.add_argument("--output", default=f"outputs/suppression_model_{today}.md",
                   help="Output path for the annotated suppression model")
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
    p.add_argument("--max-items",      type=int, default=40)
    args = p.parse_args()

    default_model, env_var = PROVIDERS[args.provider]
    model   = args.model or default_model
    api_key = args.api_key or os.environ.get(env_var)

    if not api_key:
        print(f"[run_calibrate_agent] ERROR: no API key for provider '{args.provider}'.\n"
              f"  Pass --api-key KEY  or  set {env_var}=KEY", file=sys.stderr)
        sys.exit(1)

    prompt_path = PROJECT_ROOT / "agent" / "calibrate_report_prompt.md"
    if not prompt_path.exists():
        print(f"[run_calibrate_agent] ERROR: {prompt_path} not found.", file=sys.stderr)
        sys.exit(1)

    calibration_path = pathlib.Path(args.calibration)
    if not calibration_path.exists():
        print(f"[run_calibrate_agent] ERROR: {calibration_path} not found. "
              f"Run analysis/calibrate.py first.", file=sys.stderr)
        sys.exit(1)

    report_prompt_md = load_text(prompt_path)
    calibration_md   = load_text(calibration_path)

    db_path = pathlib.Path(args.db)
    bodies: dict[str, dict] = {}
    sidecar_path = pathlib.Path(args.sidecar)
    if sidecar_path.exists():
        sidecar  = json.loads(load_text(sidecar_path))
        item_ids = collect_item_ids(sidecar, args.max_items)
        bodies   = fetch_bodies(db_path, item_ids, args.max_body_chars)
        print(f"[run_calibrate_agent] loaded {len(bodies)}/{len(item_ids)} bodies",
              file=sys.stderr)
    else:
        print(f"[run_calibrate_agent] WARNING: sidecar {sidecar_path} not found; "
              f"proceeding with brief text only, no item bodies.", file=sys.stderr)

    system, user = build_prompt(report_prompt_md, calibration_md, bodies)
    result = dispatch(args.provider, api_key, system, user, model)

    out_path = pathlib.Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result, encoding="utf-8")
    print(f"[{args.provider}] wrote suppression model -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
