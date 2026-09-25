"""
config.py
---------
Loads settings from a .env file so we never hard-code secrets in the code.

Beginner note: a ".env" file is just a plain text file with KEY=VALUE lines.
python-dotenv reads it and puts those values into os.environ for us.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # reads the .env file in the project root, if it exists

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Google periodically retires older free-tier models for new API keys.
# gemini-3.5-flash-lite is the current recommended lightweight/free-tier
# model as of mid-2026. If Google ever returns a 404 "model not found" or
# "no longer available" error, check https://ai.google.dev/gemini-api/docs/models
# for the current model name and update this default (or set GEMINI_MODEL
# in your .env file instead of editing this file).
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# How many times the Debugging Agent will try to fix a broken file before
# the Orchestrator gives up on it and moves on with the best attempt.
MAX_DEBUG_RETRIES = int(os.getenv("MAX_DEBUG_RETRIES", "3"))

# How many agents are allowed to work AT THE SAME TIME (e.g. multiple Coder
# Agents each writing a different file simultaneously, like different
# developers on a real team). Higher = faster for multi-file projects, but
# uses more API quota at once. 4 is a safe default for a free-tier key.
MAX_PARALLEL_WORKERS = int(os.getenv("MAX_PARALLEL_WORKERS", "4"))

# Where finished projects get saved. Each run creates its own timestamped
# sub-folder here so nothing ever gets overwritten.
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "generated_projects")
