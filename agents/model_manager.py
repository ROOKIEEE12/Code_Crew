"""
model_manager.py
----------------
OpenRouter Multi-Model Free-Tier Pool & Telemetry Guardian.

Features:
1. Multi-Model Free-Tier Pool: Utilizes all active OpenRouter free models (Qwen, Nemotron, GPT-OSS, DeepSeek).
2. Role-Based Dynamic Allocation: Maps specialist agents (Planner, Coder, Auditor,
   Tester, Debugger, Reviewer) to the best suited models for their task.
3. Telemetry & Health Reporting: Powers live status tracking for VS Code Extension,
   Web Studio, and CLI.
"""

import os
import time
from typing import Dict, List, Any

from config import OPENROUTER_API_KEY, MODEL_POOL, ROLE_PRIMARY_MODEL

# Supported OpenRouter free models metadata
OPENROUTER_MODEL_INFO = {
    "qwen/qwen3-coder:free": {
        "name": "Qwen 3 Coder (Free)",
        "lab": "Alibaba",
        "description": "Purpose-built for software engineering; premier free model for writing & debugging code.",
        "preferred_role": "coder, debugger",
    },
    "nvidia/nemotron-3-ultra-550b-a55b:free": {
        "name": "NVIDIA Nemotron 3 Ultra (Free)",
        "lab": "NVIDIA",
        "description": "High-parameter reasoning model; superior architectural planning & deconstruction.",
        "preferred_role": "planner",
    },
    "openai/gpt-oss-120b:free": {
        "name": "OpenAI GPT-OSS 120B (Free)",
        "lab": "OpenAI",
        "description": "Reliable open-weight general intelligence model; excellent for QA review & documentation.",
        "preferred_role": "tester, reviewer",
    },
    "deepseek/deepseek-chat:free": {
        "name": "DeepSeek Chat (Free)",
        "lab": "DeepSeek",
        "description": "Resilient multi-turn coding and reasoning model from an independent lab.",
        "preferred_role": "fallback pool",
    },
}


class OpenRouterModelPool:
    """Tracks and reports status for OpenRouter free-tier multi-model routing."""

    def __init__(self):
        self.models = list(MODEL_POOL)
        self.role_primary = dict(ROLE_PRIMARY_MODEL)
        self._stats: Dict[str, Dict[str, Any]] = {
            m: {"success": 0, "failures": 0, "cooldown_until": 0} for m in self.models
        }
        self._event_callback = None

    def set_event_callback(self, callback):
        self._event_callback = callback

    def dispatch_event(self, event_type: str, data: dict):
        if self._event_callback:
            try:
                self._event_callback(event_type, data)
            except Exception:
                pass


    def record_success(self, model: str):
        if model not in self._stats:
            self._stats[model] = {"success": 0, "failures": 0, "cooldown_until": 0}
        self._stats[model]["success"] += 1

    def record_failure(self, model: str, cooldown_sec: int = 60):
        if model not in self._stats:
            self._stats[model] = {"success": 0, "failures": 0, "cooldown_until": 0}
        self._stats[model]["failures"] += 1
        self._stats[model]["cooldown_until"] = time.time() + cooldown_sec

    def get_status_report(self) -> dict:
        now = time.time()
        model_reports = []
        active_count = 0

        for m in self.models:
            st = self._stats.get(m, {"success": 0, "failures": 0, "cooldown_until": 0})
            cooldown_rem = max(0, int(st["cooldown_until"] - now))
            is_healthy = cooldown_rem == 0
            if is_healthy:
                active_count += 1

            info = OPENROUTER_MODEL_INFO.get(m, {
                "name": m,
                "lab": "OpenRouter",
                "description": "Free-tier multi-model route.",
                "preferred_role": "general",
            })

            model_reports.append({
                "id": m,
                "name": info["name"],
                "lab": info["lab"],
                "description": info["description"],
                "preferred_role": info.get("preferred_role", "general"),
                "is_healthy": is_healthy,
                "cooldown_remaining_sec": cooldown_rem,
                "consecutive_failures": st["failures"],
                "success_count": st["success"],
            })

        return {
            "active_models": active_count,
            "total_models": len(self.models),
            "keys_configured": 1 if bool(OPENROUTER_API_KEY) else 0,
            "models": model_reports,
            "role_routing": self.role_primary,
            "provider": "OpenRouter (openrouter.ai)",
        }


# Singleton model pool instance
model_pool = OpenRouterModelPool()
