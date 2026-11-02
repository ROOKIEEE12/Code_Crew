"""Runtime settings, read once from the environment / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent

ROLES = ("clarifier", "planner", "test_author", "coder", "debugger", "reviewer", "design_review", "triage")

# Effort per role for Claude models. Planning, test design and debugging
# decide correctness, so they get the deepest reasoning; docs need little.
DEFAULT_EFFORT = {
    "clarifier": "low",
    "planner": "high",
    "test_author": "high",
    "coder": "high",
    "debugger": "high",
    "reviewer": "low",
    "design_review": "medium",
    "triage": "medium",
}

_DEFAULT_OPENROUTER_POOL = (
    "poolside/laguna-s-2.1:free,"
    "nvidia/nemotron-3.5-lightning:free,"
    "openrouter/free"
)
_DEFAULT_GEMINI_POOL = "gemini-flash-latest,gemini-3.5-flash,gemini-3.1-flash-lite"


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(repr=False, default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5"))
    openrouter_api_key: str = field(repr=False, default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_models: list[str] = field(
        default_factory=lambda: _csv(os.getenv("OPENROUTER_MODELS", os.getenv("MODEL_POOL", _DEFAULT_OPENROUTER_POOL)))
    )
    gemini_api_keys: list[str] = field(repr=False, default_factory=lambda: _csv(os.getenv("GEMINI_API_KEY", "")))
    gemini_models: list[str] = field(default_factory=lambda: _csv(os.getenv("GEMINI_MODELS", _DEFAULT_GEMINI_POOL)))
    # Provider order; providers without credentials are skipped automatically.
    provider_order: list[str] = field(
        default_factory=lambda: _csv(os.getenv("LLM_PROVIDERS", "anthropic,openrouter,gemini"))
    )

    max_debug_rounds: int = field(default_factory=lambda: int(os.getenv("MAX_DEBUG_ROUNDS", "4")))
    max_test_disputes: int = field(default_factory=lambda: int(os.getenv("MAX_TEST_DISPUTES", "3")))
    max_parallel_workers: int = field(default_factory=lambda: int(os.getenv("MAX_PARALLEL_WORKERS", "4")))
    test_timeout_sec: int = field(default_factory=lambda: int(os.getenv("TEST_TIMEOUT_SEC", "60")))
    # Longest a program started with the Run button may take (stops servers and endless loops).
    run_timeout_sec: int = field(default_factory=lambda: int(os.getenv("RUN_TIMEOUT_SEC", "20")))
    # Longest wait for one AI response before moving on to the next model. Free models can
    # legitimately take a few minutes for a big file, so this is generous but finite.
    llm_timeout_sec: int = field(default_factory=lambda: int(os.getenv("LLM_TIMEOUT_SEC", "300")))
    # A model that times out or keeps returning unusable output this many times is skipped
    # for the rest of the run.
    model_strikes: int = field(default_factory=lambda: int(os.getenv("MODEL_STRIKES", "2")))
    # When every model is cooling down (rate limits), wait up to this long for one to recover.
    max_model_wait_sec: int = field(default_factory=lambda: int(os.getenv("MAX_MODEL_WAIT_SEC", "300")))
    # How long the Planner waits for an answer to a question before using the recommended option.
    question_timeout_sec: int = field(default_factory=lambda: int(os.getenv("QUESTION_TIMEOUT_SEC", "60")))
    # Requirements at least this long are treated as detailed enough to skip questions.
    clarify_max_chars: int = field(default_factory=lambda: int(os.getenv("CLARIFY_MAX_CHARS", "400")))
    # Read links in a request (reference websites) and hand what they contain to the agents.
    read_links: bool = field(default_factory=lambda: os.getenv("READ_LINKS", "1") != "0")
    # Open generated web pages in a headless browser (Playwright) to catch JavaScript errors
    # and layout problems: "auto" (when Playwright is installed), "on" or "off".
    browser_checks: str = field(default_factory=lambda: os.getenv("BROWSER_CHECKS", "auto"))
    # After the tests pass, a vision model compares screenshots of the page with the design
    # brief and the user's references, and the Coder polishes. 0 turns it off.
    design_review_rounds: int = field(default_factory=lambda: int(os.getenv("DESIGN_REVIEW_ROUNDS", "2")))
    # Reviews scoring at least this (1-10) need no polish round.
    design_review_pass: int = field(default_factory=lambda: int(os.getenv("DESIGN_REVIEW_PASS", "8")))
    # "process" runs tests in a scrubbed subprocess; "docker" adds a
    # network-less container (requires a running Docker daemon).
    sandbox: str = field(default_factory=lambda: os.getenv("SANDBOX", "process"))
    docker_image: str = field(default_factory=lambda: os.getenv("SANDBOX_IMAGE", "python:3.12-slim"))

    output_dir: Path = field(
        default_factory=lambda: (ROOT_DIR / os.getenv("OUTPUT_DIR", "generated_projects")).resolve()
    )
    db_path: Path = field(default_factory=lambda: (ROOT_DIR / os.getenv("DB_PATH", "codecrew.db")).resolve())
    # Host names the API answers to. Anything else is refused, which blocks DNS-rebinding
    # attacks (a web page whose domain is switched to 127.0.0.1 to reach this API).
    allowed_hosts: list[str] = field(
        default_factory=lambda: _csv(os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost,[::1]"))
    )
    cors_origins: list[str] = field(
        default_factory=lambda: _csv(os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"))
    )

    def effort_for(self, role: str) -> str:
        return os.getenv(f"EFFORT_{role.upper()}", DEFAULT_EFFORT.get(role, "medium"))

    def anthropic_model_for(self, role: str) -> str:
        return os.getenv(f"ANTHROPIC_MODEL_{role.upper()}", self.anthropic_model)

    def pool_for(self, provider: str, role: str, default: list[str]) -> list[str]:
        """Per-role model list, e.g. GEMINI_MODELS_CODER=gemini-3.5-pro; falls back to the provider's pool."""
        override = _csv(os.getenv(f"{provider.upper()}_MODELS_{role.upper()}", ""))
        return override or list(default)


settings = Settings()
