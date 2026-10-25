"""Text-level helpers for model output: safe paths, file blocks, JSON.

Agents return code as *file blocks* rather than as JSON strings, so code is
never escaped/unescaped by the model (a frequent source of corrupted output):

    <<<FILE path="src/app.py">>>
    ...code...
    <<<END FILE>>>
"""

from __future__ import annotations

import json
import posixpath
import re

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".html", ".htm", ".css", ".json",
    ".md", ".txt", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".csv", ".svg",
}

EXT_LANGUAGE = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".html": "html", ".htm": "html", ".css": "css",
    ".json": "json", ".md": "markdown",
}

_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class UnsafePathError(ValueError):
    pass


def safe_relpath(path: str) -> str:
    """Normalise a model-supplied path and reject anything that could escape
    the project folder or is not a source file we expect to write."""
    if not path or not isinstance(path, str):
        raise UnsafePathError("empty path")
    p = path.strip().replace("\\", "/")
    if p.startswith("/") or re.match(r"^[a-zA-Z]:", p) or "\x00" in p:
        raise UnsafePathError(f"absolute path not allowed: {path!r}")
    norm = posixpath.normpath(p)
    parts = norm.split("/")
    if norm in (".", "") or any(part in ("..", "") for part in parts):
        raise UnsafePathError(f"path escapes project: {path!r}")
    if any(part.startswith(".") for part in parts):
        raise UnsafePathError(f"hidden files/directories not allowed: {path!r}")
    if any(part.split(".")[0].lower() in _WINDOWS_RESERVED for part in parts):
        raise UnsafePathError(f"reserved file name: {path!r}")
    ext = posixpath.splitext(norm)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsafePathError(f"file type {ext or '(none)'} not allowed: {path!r}")
    return norm


def language_for(path: str) -> str:
    return EXT_LANGUAGE.get(posixpath.splitext(path)[1].lower(), "text")


_THINK = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
_FILE_BLOCK = re.compile(r'<<<FILE\s+path="([^"]+)"\s*>>>\r?\n([\s\S]*?)\r?\n?<<<END FILE>>>')
_DISPUTE_BLOCK = re.compile(r'<<<DISPUTE\s+test="([^"]+)"\s*>>>\r?\n([\s\S]*?)\r?\n?<<<END DISPUTE>>>')
_OUTER_FENCE = re.compile(r"^\s*```[\w+-]*\r?\n([\s\S]*?)\r?\n```\s*$")


def strip_reasoning(text: str) -> str:
    return _THINK.sub("", text or "").strip()


def _unfence(code: str) -> str:
    """Remove a single markdown fence wrapping the whole block, if present."""
    m = _OUTER_FENCE.match(code)
    return m.group(1) if m else code


def parse_file_blocks(text: str) -> dict[str, str]:
    """Return {safe_path: content}. Raises if the output contains no blocks or
    an unsafe path, so a malformed response is retried instead of accepted."""
    text = strip_reasoning(text)
    files: dict[str, str] = {}
    for raw_path, body in _FILE_BLOCK.findall(text):
        path = safe_relpath(raw_path)
        content = _unfence(body)
        files[path] = content if content.endswith("\n") else content + "\n"
    if not files:
        raise ValueError("Response contained no <<<FILE path=\"...\">>> ... <<<END FILE>>> blocks.")
    return files


def parse_disputes(text: str) -> dict[str, str]:
    return {tid.strip(): reason.strip() for tid, reason in _DISPUTE_BLOCK.findall(strip_reasoning(text))}


def render_file_blocks(files: dict[str, str], limit_chars: int | None = None) -> str:
    out = []
    for path, content in files.items():
        if limit_chars is not None and len(content) > limit_chars:
            content = content[:limit_chars] + "\n... [truncated for context]"
        out.append(f'<<<FILE path="{path}">>>\n{content.rstrip()}\n<<<END FILE>>>')
    return "\n\n".join(out)


FILE_BLOCK_INSTRUCTIONS = """Output format (mandatory):
Return every file you write as a file block, with the complete file content
and nothing else inside the block (no markdown fences):

<<<FILE path="relative/path.ext">>>
...complete file content...
<<<END FILE>>>

Text outside file blocks is ignored."""


def extract_json(text: str) -> dict:
    """Best-effort JSON object extraction for providers without native
    structured output. Callers must still validate against a schema."""
    cleaned = strip_reasoning(text)
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    candidates = [fence.group(1)] if fence else []
    candidates.append(cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        candidates.append(cleaned[start : end + 1])
    for c in candidates:
        try:
            value = json.loads(c)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    raise ValueError("No JSON object found in model response.")
