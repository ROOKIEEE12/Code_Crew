"""Runtime settings, read once from the environment / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent

ROLES = ("planner", "test_author", "coder", "debugger", "reviewer", "triage")

# Effort per role for Claude models. Planning, test design and debugging
# decide correctness, so they get the deepest reasoning; docs need little.
DEFAULT_EFFORT = {
    "planner": "high",
    "test_author": "high",
    "coder": "high",
    "debugger": "high",
    "reviewer": "low",
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
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5"))
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_models: list[str] = field(
        default_factory=lambda: _csv(os.getenv("OPENROUTER_MODELS", os.getenv("MODEL_POOL", _DEFAULT_OPENROUTER_POOL)))
    )
    gemini_api_keys: list[str] = field(default_factory=lambda: _csv(os.getenv("GEMINI_API_KEY", "")))
    gemini_models: list[str] = field(default_factory=lambda: _csv(os.getenv("GEMINI_MODELS", _DEFAULT_GEMINI_POOL)))
    # Provider order; providers without credentials are skipped automatically.
    provider_order: list[str] = field(
        default_factory=lambda: _csv(os.getenv("LLM_PROVIDERS", "anthropic,openrouter,gemini"))
    )

    max_debug_rounds: int = field(default_factory=lambda: int(os.getenv("MAX_DEBUG_ROUNDS", "4")))
    max_test_disputes: int = field(default_factory=lambda: int(os.getenv("MAX_TEST_DISPUTES", "3")))
    max_parallel_workers: int = field(default_factory=lambda: int(os.getenv("MAX_PARALLEL_WORKERS", "4")))
    test_timeout_sec: int = field(default_factory=lambda: int(os.getenv("TEST_TIMEOUT_SEC", "60")))
    # "process" runs tests in a scrubbed subprocess; "docker" adds a
    # network-less container (requires a running Docker daemon).
    sandbox: str = field(default_factory=lambda: os.getenv("SANDBOX", "process"))
    docker_image: str = field(default_factory=lambda: os.getenv("SANDBOX_IMAGE", "python:3.12-slim"))

    output_dir: Path = field(
        default_factory=lambda: (ROOT_DIR / os.getenv("OUTPUT_DIR", "generated_projects")).resolve()
    )
    db_path: Path = field(default_factory=lambda: (ROOT_DIR / os.getenv("DB_PATH", "codecrew.db")).resolve())
    cors_origins: list[str] = field(
        default_factory=lambda: _csv(os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"))
    )

    def effort_for(self, role: str) -> str:
        return os.getenv(f"EFFORT_{role.upper()}", DEFAULT_EFFORT.get(role, "medium"))

    def anthropic_model_for(self, role: str) -> str:
        return os.getenv(f"ANTHROPIC_MODEL_{role.upper()}", self.anthropic_model)


settings = Settings()
