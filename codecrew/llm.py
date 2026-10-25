"""LLM access for every agent.

`call_text` / `call_structured` walk an ordered chain of (provider, model)
candidates. Each response is validated (by a parser or a Pydantic schema);
an invalid response is retried with the validation error fed back to the
model, then the next candidate is tried. Nothing invalid is ever returned
as if it were valid.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from codecrew.config import settings
from codecrew.context import RunContext
from codecrew.textio import extract_json, strip_reasoning

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

# Models that accept the server-side refusal fallback parameter.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_NON_STREAMING_MAX_TOKENS = 20000
_STREAMING_MAX_TOKENS = 64000


class LLMError(RuntimeError):
    pass


class TransientError(LLMError):
    """Rate limit / overload / network: try the next candidate, cool this one down."""


class PermanentError(LLMError):
    """Auth / bad model id: disable this candidate for a long time."""


@dataclass
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


# ---------------------------------------------------------------- health

class ModelHealth:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: dict[str, dict[str, Any]] = {}

    def _get(self, key: str) -> dict[str, Any]:
        return self._stats.setdefault(key, {"ok": 0, "fail": 0, "cooldown_until": 0.0, "last_error": ""})

    def available(self, key: str) -> bool:
        with self._lock:
            return self._get(key)["cooldown_until"] <= time.time()

    def success(self, key: str) -> None:
        with self._lock:
            s = self._get(key)
            s["ok"] += 1
            s["cooldown_until"] = 0.0

    def failure(self, key: str, error: str, cooldown: float) -> None:
        with self._lock:
            s = self._get(key)
            s["fail"] += 1
            s["last_error"] = error[:300]
            s["cooldown_until"] = time.time() + cooldown

    def report(self) -> dict[str, dict[str, Any]]:
        now = time.time()
        with self._lock:
            return {
                k: {
                    "successes": v["ok"],
                    "failures": v["fail"],
                    "cooldown_remaining_sec": max(0, int(v["cooldown_until"] - now)),
                    "last_error": v["last_error"],
                }
                for k, v in self._stats.items()
            }


health = ModelHealth()


# ---------------------------------------------------------------- providers

class Provider:
    name = "base"

    def configured(self) -> bool:
        raise NotImplementedError

    def models_for(self, role: str) -> list[str]:
        raise NotImplementedError

    def text(self, model: str, system: str, user: str, role: str) -> Completion:
        raise NotImplementedError

    def structured(self, model: str, system: str, user: str, schema: Type[M], role: str) -> tuple[M, Completion]:
        """Default: ask for JSON in the prompt and validate it ourselves."""
        schema_json = schema.model_json_schema()
        prompt = (
            f"{user}\n\nRespond with ONLY one JSON object (no prose, no markdown fences) "
            f"that validates against this JSON Schema:\n{schema_json}"
        )
        completion = self.text(model, system, prompt, role)
        data = extract_json(completion.text)
        return schema.model_validate(data), completion


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self) -> None:
        self._client = None

    def configured(self) -> bool:
        return bool(settings.anthropic_api_key)

    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2)
        return self._client

    def models_for(self, role: str) -> list[str]:
        return [settings.anthropic_model_for(role)]

    def _extra(self, model: str) -> dict[str, Any]:
        if model in _FALLBACK_MODELS:
            return {"betas": [_FALLBACK_BETA], "fallbacks": "default"}
        return {}

    def _call(self, fn: Callable[[], Any]) -> Any:
        import anthropic

        try:
            return fn()
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError) as e:
            raise PermanentError(str(e)) from e
        except anthropic.BadRequestError as e:
            raise PermanentError(str(e)) from e
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as e:
            raise TransientError(str(e)) from e
        except anthropic.APIStatusError as e:
            raise TransientError(str(e)) from e

    @staticmethod
    def _check_stop(message: Any) -> None:
        if message.stop_reason == "refusal":
            raise PermanentError("Model declined the request (refusal).")
        if message.stop_reason == "max_tokens":
            raise TransientError("Response truncated at max_tokens.")

    def text(self, model: str, system: str, user: str, role: str) -> Completion:
        def run():
            with self.client().beta.messages.stream(
                model=model,
                max_tokens=_STREAMING_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": settings.effort_for(role)},
                **self._extra(model),
            ) as stream:
                return stream.get_final_message()

        message = self._call(run)
        self._check_stop(message)
        text = "".join(b.text for b in message.content if b.type == "text")
        return Completion(text, message.model, message.usage.input_tokens, message.usage.output_tokens)

    def structured(self, model: str, system: str, user: str, schema: Type[M], role: str) -> tuple[M, Completion]:
        message = self._call(
            lambda: self.client().beta.messages.parse(
                model=model,
                max_tokens=_NON_STREAMING_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                output_config={"effort": settings.effort_for(role)},
                **self._extra(model),
            )
        )
        self._check_stop(message)
        parsed = message.parsed_output
        if parsed is None:
            raise ValueError("Structured output missing from response.")
        completion = Completion("", message.model, message.usage.input_tokens, message.usage.output_tokens)
        return parsed, completion


class OpenRouterProvider(Provider):
    name = "openrouter"

    def __init__(self) -> None:
        self._client = None

    def configured(self) -> bool:
        return bool(settings.openrouter_api_key)

    def models_for(self, role: str) -> list[str]:
        return list(settings.openrouter_models)

    def text(self, model: str, system: str, user: str, role: str) -> Completion:
        from openai import APIConnectionError, APIStatusError, OpenAI

        if self._client is None:
            self._client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key, max_retries=1)
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.2,
            )
        except APIStatusError as e:
            if e.status_code in (401, 403, 404):
                raise PermanentError(str(e)) from e
            raise TransientError(str(e)) from e
        except APIConnectionError as e:
            raise TransientError(str(e)) from e
        if not resp or not resp.choices:
            raise TransientError("Empty choices payload.")
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise TransientError("Response truncated (finish_reason=length).")
        text = strip_reasoning(choice.message.content or "")
        if not text:
            raise TransientError("Empty response text.")
        usage = resp.usage
        return Completion(text, model, getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0)


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self) -> None:
        self._key_idx = 0

    def configured(self) -> bool:
        return bool(settings.gemini_api_keys)

    def models_for(self, role: str) -> list[str]:
        return list(settings.gemini_models)

    def text(self, model: str, system: str, user: str, role: str) -> Completion:
        from google import genai
        from google.genai import types

        keys = settings.gemini_api_keys
        last: Exception | None = None
        for i in range(len(keys)):
            idx = (self._key_idx + i) % len(keys)
            try:
                client = genai.Client(api_key=keys[idx])
                resp = client.models.generate_content(
                    model=model,
                    contents=user,
                    config=types.GenerateContentConfig(system_instruction=system, temperature=0.2),
                )
                text = strip_reasoning(resp.text or "")
                if not text:
                    raise TransientError("Empty response text.")
                self._key_idx = idx
                meta = getattr(resp, "usage_metadata", None)
                return Completion(
                    text,
                    model,
                    getattr(meta, "prompt_token_count", 0) or 0,
                    getattr(meta, "candidates_token_count", 0) or 0,
                )
            except Exception as e:  # google-genai raises varied error types
                last = e
        msg = str(last)
        if "404" in msg or "not found" in msg.lower():
            raise PermanentError(msg)
        raise TransientError(msg)


PROVIDERS: dict[str, Provider] = {
    "anthropic": AnthropicProvider(),
    "openrouter": OpenRouterProvider(),
    "gemini": GeminiProvider(),
}


def candidates(role: str) -> list[tuple[Provider, str]]:
    out = []
    for name in settings.provider_order:
        provider = PROVIDERS.get(name)
        if provider and provider.configured():
            out.extend((provider, m) for m in provider.models_for(role))
    return out


def provider_status() -> dict[str, Any]:
    return {
        "order": settings.provider_order,
        "providers": {
            name: {"configured": p.configured(), "models": p.models_for("coder") if p.configured() else []}
            for name, p in PROVIDERS.items()
        },
        "health": health.report(),
    }


# ---------------------------------------------------------------- calls

_REPAIRS_PER_MODEL = 1


def _run_chain(
    ctx: Optional[RunContext],
    role: str,
    attempt: Callable[[Provider, str, str], tuple[T, Completion]],
    user: str,
) -> T:
    chain = candidates(role)
    if not chain:
        raise LLMError(
            "No LLM provider configured. Set ANTHROPIC_API_KEY (recommended), "
            "OPENROUTER_API_KEY or GEMINI_API_KEY in .env."
        )
    errors: list[str] = []
    for provider, model in chain:
        key = f"{provider.name}:{model}"
        if not health.available(key):
            errors.append(f"{key}: cooling down")
            continue
        prompt = user
        for repair in range(_REPAIRS_PER_MODEL + 1):
            if ctx:
                ctx.check_cancelled()
            try:
                result, completion = attempt(provider, model, prompt)
            except PermanentError as e:
                health.failure(key, str(e), cooldown=3600)
                errors.append(f"{key}: {e}")
                break
            except TransientError as e:
                health.failure(key, str(e), cooldown=60)
                errors.append(f"{key}: {e}")
                break
            except (ValueError, ValidationError) as e:
                # The model answered but the answer is invalid: feed the error back.
                errors.append(f"{key}: invalid output ({str(e)[:200]})")
                if ctx:
                    ctx.step("LLM", f"{role}: invalid output from {model}, requesting a corrected response.")
                prompt = (
                    f"{user}\n\n---\nYour previous response was rejected because it was invalid:\n"
                    f"{str(e)[:1500]}\nReturn a corrected, complete response in the required format."
                )
                continue
            health.success(key)
            if ctx:
                ctx.record_usage(completion.model, completion.input_tokens, completion.output_tokens)
            return result
        else:
            health.failure(key, "repeatedly invalid output", cooldown=30)
    raise LLMError(f"All models failed for role '{role}':\n" + "\n".join(errors[-8:]))


def call_text(ctx: Optional[RunContext], role: str, system: str, user: str, parse: Callable[[str], T]) -> T:
    """Free-text call whose output must survive `parse` (which raises on invalid output)."""

    def attempt(provider: Provider, model: str, prompt: str) -> tuple[T, Completion]:
        completion = provider.text(model, system, prompt, role)
        return parse(completion.text), completion

    return _run_chain(ctx, role, attempt, user)


def call_structured(
    ctx: Optional[RunContext],
    role: str,
    system: str,
    user: str,
    schema: Type[M],
    validate: Optional[Callable[[M], M]] = None,
) -> M:
    """Schema-validated call. `validate` may raise ValueError for semantic
    problems, which triggers the same corrective retry as a schema error."""

    def attempt(provider: Provider, model: str, prompt: str) -> tuple[M, Completion]:
        result, completion = provider.structured(model, system, prompt, schema, role)
        return (validate(result) if validate else result), completion

    return _run_chain(ctx, role, attempt, user)
