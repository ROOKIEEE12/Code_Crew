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

from config import OPENROUTER_API_KEY, MODEL_POOL, ROLE_PRIMARY_MODEL

_client = None  # created once and reused (lazy singleton)


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENROUTER_API_KEY:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env "
                "and paste your key in there (see README.md for how to get "
                "a free one, no credit card needed)."
            )
        _client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
    return _client


def _model_order_for(role: str) -> list:
    """This role's preferred model first, then the rest of the shared pool
    as fallbacks, with no duplicates."""
    preferred = ROLE_PRIMARY_MODEL.get(role)
    rest = [m for m in MODEL_POOL if m != preferred]
    ordered = ([preferred] if preferred else []) + rest
    return ordered or MODEL_POOL  # unknown role -> just use the whole pool


def _is_retryable(error: APIStatusError) -> bool:
    # 429 = rate-limited, 404 = model retired/unknown, 503 = provider
    # temporarily overloaded. All three mean "try the next model", not
    # "something is broken."
    return error.status_code in (429, 404, 503)


def call_llm(
    system_prompt: str,
    user_prompt: str,
    role: str = "coder",
    temperature: float = 0.2,
    model_override: Optional[str] = None,
) -> str:
    """
    Sends a prompt to whichever model is best suited for `role` — one of
    "planner", "coder", "tester", "debugger", "reviewer" — falling back
    through the rest of the model pool if that model is currently busy,
    rate-limited, or unavailable.
    """
    client = get_client()
    models_to_try = [model_override] if model_override else _model_order_for(role)

    last_error = None
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
            return (response.choices[0].message.content or "").strip()
        except APIStatusError as e:
            if _is_retryable(e):
                last_error = e
                continue  # this model is busy/retired — try the next one
            raise  # a different kind of error is a real problem, don't hide it

    raise RuntimeError(
        f"Every free model available for role '{role}' is currently "
        "rate-limited or unavailable. Wait a bit and try again, or add "
        "more models to MODEL_POOL in your .env file. "
        f"Last error: {last_error}"
    )
