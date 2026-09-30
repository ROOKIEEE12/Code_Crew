"""
config.py
---------
Loads settings from a .env file so we never hard-code secrets in the code.
"""

import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Every model below is on OpenRouter's genuinely free tier (its ID ends in
# ":free" — no card, no trial period, resets daily) as of 2026, and each
# comes from a DIFFERENT lab. That matters for reliability: if one lab's
# free model gets rate-limited or temporarily pulled, the others are
# unaffected, since free-tier limits are set per-model, not shared.
#
#   qwen/qwen3-coder:free        — Alibaba. Purpose-built FOR software
#                                   engineering; the strongest free model
#                                   for actually writing/fixing code.
#   nvidia/nemotron-3-ultra...   — NVIDIA. Strong general reasoning —
#                                   better suited to planning and judgment
#                                   calls than to writing code line-by-line.
#   openai/gpt-oss-120b:free     — OpenAI's open-weight model. Solid,
#                                   reliable all-rounder, good fallback.
#   deepseek/deepseek-chat:free  — DeepSeek. Another strong, independent
#                                   fallback from yet another lab.
#
# Override this list any time in .env (comma-separated) — no code changes
# needed. Check https://openrouter.ai/models?q=free for the current list;
# free models occasionally rotate out with little notice.
_default_pool = (
    "qwen/qwen3-coder:free,"
    "nvidia/nemotron-3-ultra-550b-a55b:free,"
    "openai/gpt-oss-120b:free,"
    "deepseek/deepseek-chat:free"
)
MODEL_POOL = [m.strip() for m in os.getenv("GEMINI_MODEL_POOL", os.getenv("MODEL_POOL", _default_pool)).split(",") if m.strip()]

# Which model each agent role tries FIRST — matching each agent's actual
# job to the model best suited for it, the way a real engineering manager
# would assign the right person to the right kind of task. Every role
# still falls back through the rest of MODEL_POOL above if its preferred
# model is busy, so this only decides the starting point, not a hard limit.
ROLE_PRIMARY_MODEL = {
    "planner": "nvidia/nemotron-3-ultra-550b-a55b:free",   # reasoning/judgment task
    "coder": "qwen/qwen3-coder:free",                       # a pure coding task
    "auditor": "qwen/qwen3-coder:free",                     # code fact-checking & audit
    "tester": "openai/gpt-oss-120b:free",                   # reviewing/reasoning task
    "debugger": "qwen/qwen3-coder:free",                    # also a pure coding task
    "reviewer": "openai/gpt-oss-120b:free",                 # writing/summarizing task
}

# Compatibility alias for components expecting a single default model name
MODEL_NAME = ROLE_PRIMARY_MODEL.get("coder", "qwen/qwen3-coder:free")

# How many times the Debugging Agent will try to fix a broken file before
# the Orchestrator gives up on it and moves on with the best attempt.
MAX_DEBUG_RETRIES = int(os.getenv("MAX_DEBUG_RETRIES", "3"))

# How many agents are allowed to work AT THE SAME TIME (e.g. multiple Coder
# Agents each writing a different file simultaneously, like different
# developers on a real team).
MAX_PARALLEL_WORKERS = int(os.getenv("MAX_PARALLEL_WORKERS", "4"))

# Where finished projects get saved. Each run creates its own timestamped
# sub-folder here so nothing ever gets overwritten.
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "generated_projects")
