"""
llm_common.py — shared LLM provider dispatch + corpus body-fetch helpers.

Used by both run_query_agent.py (Phase 2) and run_calibrate_agent.py
(Phase 1) so a provider/model fix only needs to be made once.

Supported providers
-------------------
  gemini    Google Gemini          env: GEMINI_API_KEY
  deepseek  DeepSeek (V3 / R1)     env: DEEPSEEK_API_KEY
  openai    OpenAI (GPT-4o etc.)   env: OPENAI_API_KEY
"""
from __future__ import annotations

import pathlib
import sqlite3
import sys

# Provider -> (default model, env-var name)
PROVIDERS: dict[str, tuple[str, str]] = {
    "gemini":   ("gemini-3.1-pro-preview", "GEMINI_API_KEY"),
    "deepseek": ("deepseek-chat",          "DEEPSEEK_API_KEY"),
    "openai":   ("gpt-4o",                 "OPENAI_API_KEY"),
}

# DeepSeek's OpenAI-compatible base URL
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


# ---------------------------------------------------------------------------
# Corpus helpers
# ---------------------------------------------------------------------------

def load_text(path: str | pathlib.Path) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")


def fetch_bodies(db_path: pathlib.Path, item_ids: list[str],
                 max_chars: int = 3000) -> dict[str, dict]:
    if not db_path.exists() or not item_ids:
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    out: dict[str, dict] = {}
    for iid in item_ids:
        row = conn.execute(
            "SELECT title, source_id, source_type, url, body FROM items WHERE id = ?",
            (iid,)
        ).fetchone()
        if row:
            body = row["body"] or ""
            out[iid] = {
                "title":     row["title"] or "(untitled)",
                "source":    row["source_id"],
                "type":      row["source_type"],
                "url":       row["url"] or "",
                "body":      body[:max_chars],
                "truncated": len(body) > max_chars,
            }
    conn.close()
    return out


# ---------------------------------------------------------------------------
# Provider callers
# ---------------------------------------------------------------------------

def call_gemini(api_key: str, system: str, user: str, model: str) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("[llm_common] ERROR: google-genai not installed.\n"
              "  Run:  pip install google-genai", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    print(f"[gemini] model={model}  context~{(len(system)+len(user))//1000}K chars",
          file=sys.stderr)

    response = client.models.generate_content(
        model=model,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
            max_output_tokens=8192,
        ),
    )
    if not response.text:
        candidates = getattr(response, "candidates", [])
        reason = candidates[0].finish_reason if candidates else "unknown"
        print(f"[gemini] WARNING: empty response (finish_reason={reason})", file=sys.stderr)
        return f"# Analysis incomplete\n\nGemini returned an empty response (finish_reason={reason}).\n"
    return response.text


def call_openai_compat(api_key: str, system: str, user: str, model: str,
                       base_url: str | None = None, label: str = "openai") -> str:
    """Handles both OpenAI and any OpenAI-compatible endpoint (DeepSeek, etc.)."""
    try:
        from openai import OpenAI
    except ImportError:
        print("[llm_common] ERROR: openai package not installed.\n"
              "  Run:  pip install openai", file=sys.stderr)
        sys.exit(1)

    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    client = OpenAI(**kwargs)
    print(f"[{label}] model={model}  context~{(len(system)+len(user))//1000}K chars",
          file=sys.stderr)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.2,
        max_tokens=8192,
    )
    return response.choices[0].message.content or ""


def dispatch(provider: str, api_key: str, system: str,
             user: str, model: str) -> str:
    if provider == "gemini":
        return call_gemini(api_key, system, user, model)
    elif provider == "deepseek":
        return call_openai_compat(api_key, system, user, model,
                                  base_url=DEEPSEEK_BASE_URL, label="deepseek")
    elif provider == "openai":
        return call_openai_compat(api_key, system, user, model, label="openai")
    else:
        print(f"[llm_common] ERROR: unknown provider '{provider}'. "
              f"Choose from: {', '.join(PROVIDERS)}", file=sys.stderr)
        sys.exit(1)
