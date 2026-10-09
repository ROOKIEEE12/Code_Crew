"""
llm_client.py
-------------
This is the ONLY file that actually talks to an LLM. Every agent calls
`call_llm(system_prompt, user_prompt, role=...)` instead of talking to a
provider directly.

We use OpenRouter (https://openrouter.ai) — a single OpenAI-compatible API
in front of 100+ models from many different labs, several of which are
genuinely free. This gives us two things real production agentic systems
use:

1. TASK-APPROPRIATE MODEL ROUTING — each agent role gets whichever model
   is actually best suited to its job (see ROLE_PRIMARY_MODEL in
   config.py): the Coder and Debugger prefer a model built specifically
   for software (Qwen3-Coder), while the Planner prefers a strong general
   reasoning model, and so on.

2. POOLED FALLBACK — every role still has the rest of the model pool
   behind it. If its preferred model is rate-limited, temporarily down, or
   retired, the call automatically retries with the next model in line
   instead of crashing the pipeline.

Because OpenRouter speaks the same API shape as OpenAI, this uses the
standard `openai` Python package pointed at OpenRouter's base_url — no
provider-specific SDK needed, and the same pattern works if you ever want
to point this at a different OpenAI-compatible provider later.
"""

from typing import Optional
from openai import OpenAI, APIStatusError

from config import OPENROUTER_API_KEY, MODEL_POOL, ROLE_PRIMARY_MODEL, GEMINI_API_KEYS, GEMINI_MODEL

import time

_client = None  # created once and reused (lazy singleton)
_gemini_key_idx = 0
_openrouter_exhausted_until = 0


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENROUTER_API_KEY:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env "
                "and paste your key in there."
            )
        _client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
    return _client


from agents.model_manager import model_pool


GEMINI_MODELS = [
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
]


def _call_gemini(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    """Fallback to official Google Gemini API using active keys and resilient model pool."""
    global _gemini_key_idx
    if not GEMINI_API_KEYS:
        raise RuntimeError("No GEMINI_API_KEYS configured in .env")

    from google import genai
    from google.genai import types

    last_err = None
    for i in range(len(GEMINI_API_KEYS)):
        idx = (_gemini_key_idx + i) % len(GEMINI_API_KEYS)
        key = GEMINI_API_KEYS[idx]
        try:
            client = genai.Client(api_key=key)
            config = types.GenerateContentConfig(
                system_instruction=system_prompt.strip(),
                temperature=temperature,
            )
            for m in GEMINI_MODELS:
                try:
                    response = client.models.generate_content(
                        model=m,
                        contents=user_prompt.strip(),
                        config=config,
                    )
                    text = (response.text or "").strip()
                    if text:
                        _gemini_key_idx = idx
                        return text
                except Exception as model_err:
                    last_err = model_err
                    continue
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"All configured Gemini API keys & models failed: {last_err}")


def _model_order_for(role: str) -> list:
    """This role's preferred model first, then the rest of the shared pool
    as fallbacks, with no duplicates."""
    preferred = ROLE_PRIMARY_MODEL.get(role)
    rest = [m for m in MODEL_POOL if m != preferred]
    ordered = ([preferred] if preferred else []) + rest
    return ordered or MODEL_POOL


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, APIStatusError):
        return error.status_code in (429, 404, 503, 502, 500, 400)
    return True


def call_llm(
    system_prompt: str,
    user_prompt: str,
    role: str = "coder",
    temperature: float = 0.2,
    model_override: Optional[str] = None,
) -> str:
    """
    Sends a prompt to OpenRouter pool; if free tier limit (429) or daily limit is hit,
    instantly routes to Gemini API (1,500 req/day free) with zero delay.
    """
    global _openrouter_exhausted_until
    now = time.time()
    last_error = None

    # Step 1: Try OpenRouter pool if not in daily quota cooldown
    if OPENROUTER_API_KEY and now >= _openrouter_exhausted_until:
        try:
            client = get_client()
            models_to_try = [model_override] if model_override else _model_order_for(role)

            for model in models_to_try:
                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt.strip()},
                            {"role": "user", "content": user_prompt.strip()},
                        ],
                        temperature=temperature,
                    )

                    if not response or not getattr(response, "choices", None):
                        model_pool.record_failure(model, cooldown_sec=45)
                        last_error = RuntimeError(f"Model {model} returned empty choices payload.")
                        continue

                    msg = response.choices[0].message
                    text = (msg.content or getattr(msg, "reasoning", "") or "").strip()
                    if not text:
                        model_pool.record_failure(model, cooldown_sec=45)
                        last_error = RuntimeError(f"Model {model} returned empty text.")
                        continue

                    model_pool.record_success(model)
                    return text

                except Exception as e:
                    model_pool.record_failure(model, cooldown_sec=60)
                    last_error = e
                    err_str = str(e)
                    # If daily free quota limit is exceeded, avoid trying other OpenRouter models today
                    if "free-models-per-day" in err_str:
                        _openrouter_exhausted_until = now + 3600  # Cooldown OpenRouter for 1 hour
                        break

                    if _is_retryable(e):
                        continue
                    break

        except Exception as e:
            last_error = e

    # Step 2: High-capacity Google Gemini fallback (1,500 free req/day)
    if GEMINI_API_KEYS:
        try:
            return _call_gemini(system_prompt, user_prompt, temperature=temperature)
        except Exception as e:
            last_error = e

    raise RuntimeError(
        f"All available AI models for role '{role}' are currently rate-limited or unavailable.\n"
        f"OpenRouter free quota reached (50/day) and Gemini fallback error: {last_error}"
    )
