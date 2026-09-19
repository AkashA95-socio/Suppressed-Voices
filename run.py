"""
run.py — single entry point for suppressed-voices.

One-time setup:
    python run.py setup

Phase 1 — build/refresh the suppression model:
    python run.py calibrate
    python run.py calibrate --since 7d --provider deepseek

Phase 2 — fully automated topic query (ingest -> LLM analysis -> brief):
    python run.py query "manual scavenging Dalit 2026" --provider deepseek
    python run.py query "TCS Nashik NIA" --provider gemini --web-search

`query` is a thin wrapper around pipeline.py — see `python pipeline.py --help`
for every flag it accepts (extra URLs, model override, etc.); anything after
the topic is passed through untouched.

API keys: copy .env.example to .env and fill in whichever provider(s) you
use. Loaded automatically; no need to set environment variables by hand.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
VENV_DIR = PROJECT_ROOT / ".venv"
IS_WINDOWS = sys.platform.startswith("win")
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# Kept in sync with analysis/llm_common.py's PROVIDERS keys/env vars.
_PROVIDER_ENV_VARS = {
    "gemini":   "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai":   "OPENAI_API_KEY",
}


def _detect_provider() -> str | None:
    """Pick the first provider with a key available in the environment/.env."""
    for name, env_var in _PROVIDER_ENV_VARS.items():
        if os.environ.get(env_var):
            return name
    return None


def _run(cmd: list[str], desc: str = "", check: bool = True) -> int:
    label = desc or " ".join(cmd[:3])
    print(f"\n[run] >> {label}", flush=True)
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        marker = "FAILED" if check else "non-fatal failure"
        print(f"[run] {marker}: {label} (exit {result.returncode})", file=sys.stderr)
        if check:
            sys.exit(result.returncode)
    else:
        print(f"[run] OK: {label}", flush=True)
    return result.returncode


def cmd_setup(args: argparse.Namespace) -> None:
    if VENV_PYTHON.exists():
        print(f"[run] venv already exists at {VENV_DIR}")
    else:
        _run([sys.executable, "-m", "venv", str(VENV_DIR)], "create virtualenv (.venv)")

    _run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"], "upgrade pip")
    _run([str(VENV_PYTHON), "-m", "pip", "install", "-r", "requirements.txt"],
         "install dependencies")
    _run([str(VENV_PYTHON), "tools/db.py", "--init"], "initialise SQLite schema")

    env_file = PROJECT_ROOT / ".env"
    env_example = PROJECT_ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copy(env_example, env_file)
        print(f"[run] created {env_file.name} — fill in API keys before running `query`")

    activate_hint = (
        r".venv\Scripts\Activate.ps1" if IS_WINDOWS else "source .venv/bin/activate"
    )
    print(
        "\n[run] setup complete.\n"
        f"  1. Activate the venv:   {activate_hint}\n"
        "  2. Add API keys to .env (only needed for `run.py query`)\n"
        "  3. Run a calibration:   python run.py calibrate\n"
    )


def cmd_calibrate(args: argparse.Namespace) -> None:
    py = sys.executable
    db = args.db
    window = args.since

    _run([py, "tools/ingest_rss.py", "--config", "config/handles.yml",
          "--since", window, "--db", db, "--init"],
         "ingest independent RSS")
    _run([py, "tools/ingest_rss.py", "--config", "config/mainstream.yml",
          "--since", window, "--db", db],
         "ingest mainstream RSS")
    _run([py, "tools/ingest_web.py", "--from-rss-queue", "--db", db],
         "backfill article bodies")
    _run([py, "tools/ingest_youtube.py", "--config", "config/handles.yml",
          "--max", "20", "--db", db],
         "ingest YouTube transcripts", check=False)
    _run([py, "analysis/calibrate.py", "--window", window, "--db", db, "--verbose"],
         "build suppression model")

    provider = args.provider or _detect_provider()
    if provider:
        agent_cmd = [py, "analysis/run_calibrate_agent.py", "--provider", provider, "--db", db]
        if args.api_key:
            agent_cmd += ["--api-key", args.api_key]
        if args.model:
            agent_cmd += ["--model", args.model]
        _run(agent_cmd, f"{provider} four-model analysis")
        print("\n[run] calibration done — see outputs/calibration_<date>.md "
              "and outputs/suppression_model_<date>.md\n")
    else:
        print(
            "\n[run] calibration done — see outputs/calibration_<date>.md\n"
            "  No LLM provider key found, so the four-model analysis "
            "(outputs/suppression_model_<date>.md) was skipped.\n"
            "  Set GEMINI_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY in .env, "
            "or pass --provider, to generate it.\n"
        )


def cmd_query(pipeline_args: list[str]) -> None:
    if not pipeline_args or pipeline_args[0] in ("-h", "--help"):
        subprocess.run([sys.executable, "pipeline.py", "--help"], cwd=PROJECT_ROOT)
        return
    _run([sys.executable, "pipeline.py", *pipeline_args],
         f"query pipeline: {' '.join(pipeline_args)}")


def main() -> None:
    # "query" passes everything after it straight through to pipeline.py —
    # handled before argparse so its flags (--provider, --help, ...) are
    # never mistaken for run.py's own.
    if len(sys.argv) >= 2 and sys.argv[1] == "query":
        cmd_query(sys.argv[2:])
        return

    ap = argparse.ArgumentParser(
        description="suppressed-voices — single entry point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("setup", help="create venv, install deps, init DB")

    p_cal = sub.add_parser("calibrate", help="Phase 1: build/refresh the suppression model")
    p_cal.add_argument("--since", default="30d", help="ingestion + calibration window, e.g. 7d, 30d")
    p_cal.add_argument("--db", default="data/corpus.db")
    p_cal.add_argument("--provider", choices=list(_PROVIDER_ENV_VARS),
                        help="LLM provider for the four-model analysis. If omitted, "
                             "auto-detected from whichever API key is set in .env; "
                             "if none, the analysis step is skipped.")
    p_cal.add_argument("--api-key", help="API key override for --provider")
    p_cal.add_argument("--model", help="Model ID override for --provider")

    sub.add_parser("query", help="Phase 2: automated topic query (delegates to pipeline.py)")

    args = ap.parse_args()
    {"setup": cmd_setup, "calibrate": cmd_calibrate}[args.command](args)


if __name__ == "__main__":
    main()
