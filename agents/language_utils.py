"""
language_utils.py
-------------------
CodeCrew's Coder Agent can write code in ANY language, because it's just an
LLM producing text. But *automatically running* code to verify it needs the
right tool installed for that language (a Python interpreter, Node.js, a
Java compiler, etc.) — and we can't assume every one of those is installed
on every student's laptop.

So this module is honest about that: it checks what's actually available
on THIS machine, and only runs a real syntax check for languages it has a
tool for. For everything else, `checked` comes back False, and the Testing
Agent falls back to an LLM-based code review instead (see testing_agent.py)
— so the project never silently skips verification, it just uses a
different kind of verification when a compiler isn't available.
"""

import html.parser
import os
import shutil
import subprocess
import sys
import tempfile

EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".json": "json",
    ".md": "markdown",
}


def detect_language(file_path: str) -> str:
    _, ext = os.path.splitext(file_path)
    return EXTENSION_TO_LANGUAGE.get(ext.lower(), "text")


class _HTMLValidityParser(html.parser.HTMLParser):
    """A very forgiving parser — we only care whether Python's own parser
    can get through the document without raising an exception."""
    pass


def _check_python(code: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", path],
            capture_output=True, text=True, timeout=15,
        )
        return {"checked": True, "passed": result.returncode == 0, "output": result.stderr}
    finally:
        os.unlink(path)
        cache_dir = os.path.join(os.path.dirname(path), "__pycache__")
        shutil.rmtree(cache_dir, ignore_errors=True)


def _check_node_syntax(code: str, suffix: str) -> dict:
    node = shutil.which("node")
    if not node:
        return {"checked": False, "passed": True, "output": "Node.js not installed — skipped."}
    with tempfile.NamedTemporaryFile(suffix=suffix, mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        result = subprocess.run(
            [node, "--check", path], capture_output=True, text=True, timeout=15,
        )
        return {"checked": True, "passed": result.returncode == 0, "output": result.stderr}
    finally:
        os.unlink(path)


def _check_html(code: str) -> dict:
    parser = _HTMLValidityParser()
    try:
        parser.feed(code)
        return {"checked": True, "passed": True, "output": ""}
    except Exception as e:  # pragma: no cover - HTMLParser is very forgiving
        return {"checked": True, "passed": False, "output": str(e)}


def _check_css_braces(code: str) -> dict:
    # Not a real CSS parser — just a sanity check that braces balance.
    opens, closes = code.count("{"), code.count("}")
    passed = opens == closes
    output = "" if passed else f"Mismatched braces: {opens} '{{' vs {closes} '}}'"
    return {"checked": True, "passed": passed, "output": output}


def _check_json(code: str) -> dict:
    import json
    try:
        json.loads(code)
        return {"checked": True, "passed": True, "output": ""}
    except json.JSONDecodeError as e:
        return {"checked": True, "passed": False, "output": str(e)}


def check_syntax(language: str, code: str) -> dict:
    """
    Returns {"checked": bool, "passed": bool, "output": str}.
    `checked=False` means "we don't have a tool for this language on this
    machine" — the caller should NOT treat that as a failure, just as
    "no automated check ran, rely on the LLM review instead."
    """
    if language == "python":
        return _check_python(code)
    if language == "javascript":
        return _check_node_syntax(code, ".js")
    if language == "typescript":
        return _check_node_syntax(code, ".ts")
    if language == "html":
        return _check_html(code)
    if language == "css":
        return _check_css_braces(code)
    if language == "json":
        return _check_json(code)

    return {"checked": False, "passed": True, "output": f"No local syntax checker for '{language}' — skipped."}
