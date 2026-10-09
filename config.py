"""
config.py
---------
Loads settings from a .env file so we never hard-code secrets in the code.
"""

import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_API_KEYS = [k.strip() for k in os.getenv("GEMINI_API_KEY", "").split(",") if k.strip()]
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

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
# Active, verified free models on OpenRouter as of 2026.
# Each model ends in ":free" or uses OpenRouter's dynamic free routing.
_default_pool = (
    "poolside/laguna-s-2.1:free,"
    "liquid/lfm-2.5-2.6b:free,"
    "nvidia/nemotron-3.5-lightning:free,"
    "openrouter/free"
)
MODEL_POOL = [m.strip() for m in os.getenv("GEMINI_MODEL_POOL", os.getenv("MODEL_POOL", _default_pool)).split(",") if m.strip()]

# Role-to-model assignments: poolside laguna delivers instant JSON and zero-bloat code
ROLE_PRIMARY_MODEL = {
    "planner": "poolside/laguna-s-2.1:free",    # High-accuracy structured plan & JSON
    "coder": "poolside/laguna-s-2.1:free",      # Precision code generation & syntax
    "auditor": "poolside/laguna-s-2.1:free",    # Fact verification & code optimization
    "tester": "poolside/laguna-s-2.1:free",     # Structured QA review & PyTest synthesis
    "debugger": "poolside/laguna-s-2.1:free",   # Surgical bug repairs
    "reviewer": "poolside/laguna-s-2.1:free",   # Documentation & README generation
}

# Compatibility alias for components expecting a single default model name
MODEL_NAME = ROLE_PRIMARY_MODEL.get("coder", "poolside/laguna-s-2.1:free")

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
