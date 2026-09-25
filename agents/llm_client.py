"""
llm_client.py
-------------
Unified LLM Client interface for CodeCrew.
Powers each isolated specialist agent with dedicated system instructions,
strict persona grounding, and model configuration.
"""

from google import genai
from google.genai import types
from config import GEMINI_API_KEY, MODEL_NAME

_client = None  # Lazy singleton


def get_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and "
                "paste your Gemini API key there."
            )
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    model_override: str = None,
) -> str:
    """
    Sends a request with genuine system instruction isolation.
    Every agent maintains its independent persona and domain specialization.
    """
    client = get_client()
    target_model = model_override or MODEL_NAME

    config = types.GenerateContentConfig(
        system_instruction=system_prompt.strip(),
        temperature=temperature,
    )

    response = client.models.generate_content(
        model=target_model,
        contents=user_prompt.strip(),
        config=config,
    )

    return (response.text or "").strip()
