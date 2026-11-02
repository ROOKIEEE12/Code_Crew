"""LLM access for every agent.

`call_text` / `call_structured` walk an ordered chain of (provider, model)
candidates. Each response is validated (by a parser or a Pydantic schema);
an invalid response is retried with the validation error fed back to the
model, then the next candidate is tried. Nothing invalid is ever returned
as if it were valid.
"""

from __future__ import annotations

import base64
import inspect
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from codecrew.config import settings
from codecrew.context import RunCancelled, RunContext
from codecrew.textio import extract_json, strip_reasoning

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

# (media type, bytes), e.g. ("image/png", b"...")
Image = tuple[str, bytes]

# Models that accept the server-side refusal fallback parameter.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_NON_STREAMING_MAX_TOKENS = 20000
_STREAMING_MAX_TOKENS = 64000


class LiveText:
    """Receives a model's answer while it is being written, so the UI can show the
    code appearing live. Chunks are batched (about 3 updates a second) and sent as
    transient "llm_delta" events; nothing here is stored or affects the result."""

    INTERVAL = 0.3

    def __init__(self, ctx: RunContext, call_id: int, role: str):
        self.ctx, self.call_id, self.role = ctx, call_id, role
        self.attempt = 0
        self.closed = False
        self._lock = threading.Lock()
        self._sent = 0          # characters already sent for this attempt
        self._pending: list[str] = []
        self._last = 0.0

    def restart(self) -> None:
        """A new attempt (another model or key) starts from an empty answer."""
        with self._lock:
            self.attempt += 1
            self._sent = 0
            self._pending = []
        self._emit("", reset=True)

    def for_attempt(self) -> "LiveText":
        """A writer bound to the current attempt, handed to the provider."""
        return _AttemptLive(self)  # type: ignore[return-value]

    def write(self, chunk: str, attempt: Optional[int] = None) -> None:
        if not chunk or self.closed:
            return
        with self._lock:
            if attempt is not None and attempt != self.attempt:
                return  # from a call abandoned before a newer attempt started
            self._pending.append(chunk)
            due = time.monotonic() - self._last >= self.INTERVAL
        if due:
            self.flush()

    def flush(self) -> None:
        with self._lock:
            text = "".join(self._pending)
            self._pending = []
            offset = self._sent
            self._sent += len(text)
            self._last = time.monotonic()
        if text:
            self._emit(text, offset=offset)

    def close(self) -> None:
        self.flush()
        self.closed = True

    def _emit(self, text: str, offset: int = 0, reset: bool = False) -> None:
        if self.closed or self.ctx.cancel_event.is_set():
            return
        self.ctx.emit("llm_delta", {"id": self.call_id, "role": self.role, "attempt": self.attempt,
                                    "offset": offset, "text": text, "reset": reset})


class _AttemptLive:
    """One attempt's view of a LiveText. The watchdog can give up on a call whose
    thread keeps running; once a newer attempt has started, what it writes is dropped."""

    def __init__(self, live: LiveText):
        self._live, self._attempt = live, live.attempt

    def write(self, chunk: str) -> None:
        self._live.write(chunk, self._attempt)

    def restart(self) -> None:
        if self._live.attempt == self._attempt:
            self._live.restart()
            self._attempt = self._live.attempt


class LLMError(RuntimeError):
    pass


class TransientError(LLMError):
    """Rate limit / overload / network: try the next candidate, cool this one down."""


class VisionUnsupported(LLMError):
    """The model cannot take images; it is skipped for image calls only."""


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

    def remaining(self, key: str) -> float:
        with self._lock:
            return max(0.0, self._get(key)["cooldown_until"] - time.time())

    def reset_cooldowns(self) -> None:
        """Gives every model a fresh chance (used when the user presses Resume)."""
        with self._lock:
            for s in self._stats.values():
                s["cooldown_until"] = 0.0

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

    def text(self, model: str, system: str, user: str, role: str, images: Optional[list[Image]] = None,
             live: Optional[LiveText] = None) -> Completion:
        """`live`, when given, receives the answer as it streams in."""
        raise NotImplementedError

    def structured(self, model: str, system: str, user: str, schema: Type[M], role: str,
                   images: Optional[list[Image]] = None) -> tuple[M, Completion]:
        """Default: ask for JSON in the prompt and validate it ourselves."""
        schema_json = schema.model_json_schema()
        prompt = (
            f"{user}\n\nRespond with ONLY one JSON object (no prose, no markdown fences) "
            f"that validates against this JSON Schema:\n{schema_json}"
        )
        completion = self.text(model, system, prompt, role, **_img(images))
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

            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2,
                                               timeout=max(600, settings.llm_timeout_sec))
        return self._client

    def models_for(self, role: str) -> list[str]:
        return [settings.anthropic_model_for(role)]

    def _extra(self, model: str) -> dict[str, Any]:
        if model in _FALLBACK_MODELS:
            return {"betas": [_FALLBACK_BETA], "fallbacks": "default"}
        return {}

    def _call(self, fn: Callable[[], Any], images: Optional[list[Image]] = None) -> Any:
        import anthropic

        try:
            return fn()
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError) as e:
            raise PermanentError(str(e)) from e
        except anthropic.BadRequestError as e:
            if images and "image" in str(e).lower():
                raise VisionUnsupported(str(e)) from e
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

    @staticmethod
    def _content(user: str, images: Optional[list[Image]]) -> Any:
        if not images:
            return user
        blocks: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": mt, "data": base64.b64encode(data).decode()}}
            for mt, data in images
        ]
        return [*blocks, {"type": "text", "text": user}]

    def text(self, model: str, system: str, user: str, role: str, images: Optional[list[Image]] = None,
             live: Optional[LiveText] = None) -> Completion:
        def run():
            with self.client().beta.messages.stream(
                model=model,
                max_tokens=_STREAMING_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": self._content(user, images)}],
                output_config={"effort": settings.effort_for(role)},
                **self._extra(model),
            ) as stream:
                if live:
                    for chunk in stream.text_stream:
                        live.write(chunk)
                return stream.get_final_message()

        message = self._call(run, images)
        self._check_stop(message)
        text = "".join(b.text for b in message.content if b.type == "text")
        return Completion(text, message.model, message.usage.input_tokens, message.usage.output_tokens)

    def structured(self, model: str, system: str, user: str, schema: Type[M], role: str,
                   images: Optional[list[Image]] = None) -> tuple[M, Completion]:
        message = self._call(
            lambda: self.client().beta.messages.parse(
                model=model,
                max_tokens=_NON_STREAMING_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": self._content(user, images)}],
                output_format=schema,
                output_config={"effort": settings.effort_for(role)},
                **self._extra(model),
            ),
            images,
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
        return settings.pool_for("openrouter", role, settings.openrouter_models)

    def text(self, model: str, system: str, user: str, role: str, images: Optional[list[Image]] = None,
             live: Optional[LiveText] = None) -> Completion:
        from openai import APIConnectionError, APIStatusError, OpenAI

        if self._client is None:
            self._client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key,
                                  max_retries=1, timeout=settings.llm_timeout_sec)
        content: Any = user
        if images:
            content = [{"type": "text", "text": user}, *(
                {"type": "image_url", "image_url": {"url": f"data:{mt};base64,{base64.b64encode(data).decode()}"}}
                for mt, data in images)]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        try:
            if live:
                return self._stream(model, messages, live)
            resp = self._client.chat.completions.create(model=model, messages=messages, temperature=0.2)
        except APIStatusError as e:
            if images and e.status_code in (400, 404, 415, 422):
                raise VisionUnsupported(str(e)) from e
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

    def _stream(self, model: str, messages: list[dict[str, Any]], live: LiveText) -> Completion:
        parts: list[str] = []
        finish, usage = None, None
        for chunk in self._client.chat.completions.create(model=model, messages=messages, temperature=0.2, stream=True):
            usage = getattr(chunk, "usage", None) or usage
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish = choice.finish_reason or finish
            piece = getattr(choice.delta, "content", None) or ""
            if piece:
                parts.append(piece)
                live.write(piece)
        if finish == "length":
            raise TransientError("Response truncated (finish_reason=length).")
        text = strip_reasoning("".join(parts))
        if not text:
            raise TransientError("Empty response text.")
        return Completion(text, model, getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0)


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self) -> None:
        self._key_idx = 0

    def configured(self) -> bool:
        return bool(settings.gemini_api_keys)

    def models_for(self, role: str) -> list[str]:
        return settings.pool_for("gemini", role, settings.gemini_models)

    def text(self, model: str, system: str, user: str, role: str, images: Optional[list[Image]] = None,
             live: Optional[LiveText] = None) -> Completion:
        from google import genai
        from google.genai import types

        contents: Any = user
        if images:
            contents = [*(types.Part.from_bytes(data=data, mime_type=mt) for mt, data in images), user]

        keys = settings.gemini_api_keys
        last: Exception | None = None
        for i in range(len(keys)):
            idx = (self._key_idx + i) % len(keys)
            try:
                client = genai.Client(api_key=keys[idx], http_options=types.HttpOptions(timeout=settings.llm_timeout_sec * 1000))
                config = types.GenerateContentConfig(system_instruction=system, temperature=0.2)
                if live:
                    if i:
                        live.restart()  # the previous key failed part-way; start the live view over
                    parts: list[str] = []
                    meta = None
                    for chunk in client.models.generate_content_stream(model=model, contents=contents, config=config):
                        meta = getattr(chunk, "usage_metadata", None) or meta
                        piece = chunk.text or ""
                        if piece:
                            parts.append(piece)
                            live.write(piece)
                    raw = "".join(parts)
                else:
                    resp = client.models.generate_content(model=model, contents=contents, config=config)
                    raw = resp.text or ""
                    meta = getattr(resp, "usage_metadata", None)
                text = strip_reasoning(raw)
                if not text:
                    raise TransientError("Empty response text.")
                self._key_idx = idx
                return Completion(
                    text,
                    model,
                    getattr(meta, "prompt_token_count", 0) or 0,
                    getattr(meta, "candidates_token_count", 0) or 0,
                )
            except Exception as e:  # google-genai raises varied error types
                last = e
        msg = str(last)
        if images and ("400" in msg or "INVALID_ARGUMENT" in msg):
            raise VisionUnsupported(msg)
        if "404" in msg or "not found" in msg.lower():
            raise PermanentError(msg)
        if "limit: 0" in msg:  # this key's plan has no quota for the model (e.g. Pro models on the free tier)
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
    attempt: Callable[..., tuple[T, Completion]],
    user: str,
    with_images: bool = False,
    stream: bool = False,
) -> T:
    chain = candidates(role)
    if not chain:
        raise LLMError(
            "No LLM provider configured. Set ANTHROPIC_API_KEY (recommended), "
            "OPENROUTER_API_KEY or GEMINI_API_KEY in .env."
        )
    call_id = ctx.next_call_id() if ctx else 0
    started = time.monotonic()
    live = LiveText(ctx, call_id, role) if ctx and stream else None
    if ctx:
        user = user + ctx.notes_for(role)
        ctx.emit("llm_start", {"id": call_id, "role": role, "live": bool(live)})
    result_info: dict[str, Any] = {"ok": False, "model": None, "input_tokens": 0, "output_tokens": 0, "attempts": 0}
    try:
        for round_ in range(2):
            try:
                return _attempt_chain(ctx, role, attempt, user, chain, result_info, with_images, live)
            except LLMError:
                # Free models are often all rate-limited for a minute at the same time.
                # Rather than failing the run, wait once for the first one to recover.
                usable = [f"{p.name}:{m}" for p, m in chain if not (ctx and ctx.is_benched(f"{p.name}:{m}"))]
                wait = min((health.remaining(k) for k in usable), default=None)
                if round_ == 1 or wait is None or wait > settings.max_model_wait_sec:
                    raise
                if ctx:
                    ctx.step("LLM", f"Every AI model is busy or rate-limited right now; waiting {max(1, round(wait))}s, then trying again.")
                _wait(ctx, wait + 1)
        raise AssertionError("unreachable")
    finally:
        if live:
            live.close()
        if ctx:
            ctx.emit("llm_end", {"id": call_id, "role": role, "seconds": round(time.monotonic() - started, 1), **result_info})


def _wait(ctx: Optional[RunContext], seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if ctx:
            ctx.check_cancelled()
        time.sleep(min(0.5, max(0.0, end - time.monotonic())))


class NoResponse(TransientError):
    """The model sent nothing back within the time limit."""


def _with_watchdog(ctx: Optional[RunContext], fn: Callable[[], T]) -> T:
    """Runs one provider call on a helper thread so that neither a hung network
    connection nor the Stop button can leave the run waiting forever. The SDKs
    have their own timeouts; this is the guarantee if one of them fails."""
    box: dict[str, Any] = {}
    done = threading.Event()

    def work() -> None:
        try:
            box["value"] = fn()
        except BaseException as e:  # handed back to the caller below
            box["error"] = e
        finally:
            done.set()

    threading.Thread(target=work, name="llm-call", daemon=True).start()
    grace = min(30, settings.llm_timeout_sec)  # extra time for the SDK's own timeout to fire first
    deadline = time.monotonic() + settings.llm_timeout_sec + grace
    while not done.wait(timeout=0.25):
        if ctx and ctx.cancel_event.is_set():
            raise RunCancelled()  # the abandoned call finishes (or times out) on its own thread
        if time.monotonic() > deadline:
            raise NoResponse(f"No response after {settings.llm_timeout_sec + grace}s.")
    if "error" in box:
        err = box["error"]
        if _is_timeout(err):
            raise NoResponse(f"No response within {settings.llm_timeout_sec}s ({type(err).__name__}).") from err
        raise err
    return box["value"]


def _is_timeout(err: BaseException) -> bool:
    text = f"{type(err).__name__} {err}".lower()
    return any(s in text for s in ("timeout", "timed out", "deadline_exceeded", "deadline expired"))


def _strike(ctx: Optional[RunContext], key: str, model: str, reason: str) -> None:
    if ctx and ctx.strike(key) == settings.model_strikes:
        ctx.step("LLM", f"Skipping {model} for the rest of this run: {reason}.")


_NO_VISION: set[str] = set()  # models that rejected images; still used for text-only calls


def _accepts_live(provider: Provider) -> bool:
    """Whether this provider's text() can stream (custom or test providers may not)."""
    try:
        return "live" in inspect.signature(provider.text).parameters
    except (TypeError, ValueError):
        return False


def _img(images: Optional[list[Image]]) -> dict[str, Any]:
    """Passes images only when there are some, so text-only providers keep their simple signature."""
    return {"images": images} if images else {}


def _attempt_chain(
    ctx: Optional[RunContext],
    role: str,
    attempt: Callable[[Provider, str, str], tuple[T, Completion]],
    user: str,
    chain: list[tuple[Provider, str]],
    info: dict[str, Any],
    with_images: bool = False,
    live: Optional[LiveText] = None,
) -> T:
    errors: list[str] = []
    for provider, model in chain:
        key = f"{provider.name}:{model}"
        if with_images and key in _NO_VISION:
            errors.append(f"{key}: cannot read images")
            continue
        if not health.available(key):
            errors.append(f"{key}: cooling down")
            continue
        if ctx and ctx.is_benched(key):
            errors.append(f"{key}: skipped for this run")
            continue
        prompt = user
        for repair in range(_REPAIRS_PER_MODEL + 1):
            if ctx:
                ctx.check_cancelled()
            info["attempts"] += 1
            if live and info["attempts"] > 1:
                live.restart()
            extra = {"live": live.for_attempt()} if live and _accepts_live(provider) else {}
            try:
                result, completion = _with_watchdog(ctx, lambda p=provider, m=model, q=prompt: attempt(p, m, q, **extra))
            except VisionUnsupported as e:
                _NO_VISION.add(key)
                errors.append(f"{key}: cannot read images ({str(e)[:120]})")
                break
            except PermanentError as e:
                health.failure(key, str(e), cooldown=3600)
                errors.append(f"{key}: {e}")
                break
            except NoResponse as e:
                health.failure(key, str(e), cooldown=300)
                errors.append(f"{key}: {e}")
                _strike(ctx, key, model, "it stopped responding")
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
            info.update(ok=True, model=completion.model, input_tokens=completion.input_tokens,
                        output_tokens=completion.output_tokens)
            if ctx:
                ctx.record_usage(completion.model, completion.input_tokens, completion.output_tokens)
            return result
        else:
            health.failure(key, "repeatedly invalid output", cooldown=120)
            _strike(ctx, key, model, "it kept giving unusable answers")
    raise LLMError(f"All models failed for role '{role}':\n" + "\n".join(errors[-8:]))


def _with_image_fallback(ctx: Optional[RunContext], role: str, images: Optional[list[Image]],
                         run: Callable[[Optional[list[Image]]], T], required: bool = False) -> T:
    """Tries with the images; if no model could take them, carries on from the text alone
    (unless the images are `required`, e.g. a review of screenshots)."""
    if not images or required:
        return run(images or None)
    try:
        return run(images)
    except LLMError:
        if ctx:
            ctx.step("LLM", f"No available model could look at the {len(images)} image(s) for the "
                            f"{role.replace('_', ' ')}; continuing from the text alone.")
        return run(None)


def call_text(ctx: Optional[RunContext], role: str, system: str, user: str, parse: Callable[[str], T],
              images: Optional[list[Image]] = None, stream: bool = True) -> T:
    """Free-text call whose output must survive `parse` (which raises on invalid output).
    `images` (reference designs, screenshots) go to vision-capable models. With `stream`
    the answer is shown live in the UI while it is written (code appearing as it is typed)."""

    def run(imgs: Optional[list[Image]]) -> T:
        def attempt(provider: Provider, model: str, prompt: str, live: Optional[LiveText] = None) -> tuple[T, Completion]:
            completion = provider.text(model, system, prompt, role, **_img(imgs), **({"live": live} if live else {}))
            return parse(completion.text), completion

        return _run_chain(ctx, role, attempt, user, bool(imgs), stream)

    return _with_image_fallback(ctx, role, images, run)


def call_structured(
    ctx: Optional[RunContext],
    role: str,
    system: str,
    user: str,
    schema: Type[M],
    validate: Optional[Callable[[M], M]] = None,
    images: Optional[list[Image]] = None,
    images_required: bool = False,
) -> M:
    """Schema-validated call. `validate` may raise ValueError for semantic
    problems, which triggers the same corrective retry as a schema error."""

    def run(imgs: Optional[list[Image]]) -> M:
        def attempt(provider: Provider, model: str, prompt: str) -> tuple[M, Completion]:
            result, completion = provider.structured(model, system, prompt, schema, role, **_img(imgs))
            return (validate(result) if validate else result), completion

        return _run_chain(ctx, role, attempt, user, bool(imgs))

    return _with_image_fallback(ctx, role, images, run, images_required)
