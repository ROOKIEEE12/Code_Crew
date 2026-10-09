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

OPENROUTER_MODEL_INFO = {
    "openrouter/free": {
        "name": "OpenRouter Free Auto-Router",
        "lab": "OpenRouter",
        "description": "Dynamic multi-model router that automatically selects available high-performance free models.",
        "preferred_role": "planner, tester, reviewer",
    },
    "poolside/laguna-s-2.1:free": {
        "name": "Poolside Laguna S 2.1 (Free)",
        "lab": "Poolside",
        "description": "Specialized model for precise software engineering, structured JSON, and code synthesis.",
        "preferred_role": "coder, auditor, debugger",
    },
    "nvidia/nemotron-3.5-lightning:free": {
        "name": "NVIDIA Nemotron 3.5 Lightning (Free)",
        "lab": "NVIDIA",
        "description": "High-throughput accelerated reasoning model for deep analysis and edge-case testing.",
        "preferred_role": "planner, tester",
    },
    "liquid/lfm-2.5-2.6b:free": {
        "name": "Liquid LFM 2.5 (Free)",
        "lab": "Liquid AI",
        "description": "Efficient non-transformer architecture optimized for low-latency completions.",
        "preferred_role": "fallback pool",
    },
    "dots-studio/dots-3-note-preview:free": {
        "name": "Dots 3 Note (Free)",
        "lab": "Dots Studio",
        "description": "High-context open-weight reasoning model for fallback processing.",
        "preferred_role": "fallback pool",
    },
    "apodex/apodex-1.1-mini:free": {
        "name": "Apodex 1.1 Mini (Free)",
        "lab": "Apodex",
        "description": "Compact inference model for swift task verification and fallback.",
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
