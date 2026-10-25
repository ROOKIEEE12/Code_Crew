"""Planner Agent: natural-language requirement -> validated technical spec."""

from __future__ import annotations

from codecrew import llm
from codecrew.context import RunContext
from codecrew.schemas import Spec, SpecOut
from codecrew.textio import UnsafePathError, language_for, safe_relpath
from codecrew.verify import is_test_path

SYSTEM = """You are the Planner Agent, the tech lead of an AI software team
(Test Author, Coder, Debugger, Reviewer). Turn the user's requirement into a
precise, buildable technical specification. Every other agent works only
from your spec, and the Test Author writes unit tests from it BEFORE any
code exists, so names, signatures and behaviours must be exact.

Design rules:
- Keep the file set as small as the requirement genuinely allows.
- Use only the Python standard library and browser built-ins unless the
  user explicitly asks for a library; tests run offline with nothing extra
  installed.
- Separate pure logic from I/O so it can be unit-tested:
  * Python: logic in importable modules with no side effects at import
    time; any CLI/input()/printing lives in main() behind
    `if __name__ == "__main__":`.
  * Web apps: put pure logic (calculations, state transitions, validation,
    formatting) in its own JS file that touches no DOM and exports via
    `if (typeof module !== "undefined") module.exports = {...}`; DOM wiring
    goes in a separate script. Mark only the logic file testable.
- `functions` lists every public function/class other files or tests use,
  with exact names and full signatures. Describe return values and errors
  precisely (e.g. "raises ValueError if amount <= 0", "returns [] when
  empty"). Use "Class.method" for methods.
- `testable` is true only for files exposing importable pure logic.
- Acceptance criteria are concrete, observable behaviours (inputs ->
  expected outputs). Prefer "automated_test"; use "static_check" for
  structure (e.g. "index.html loads styles.css and app.js") and "manual"
  only for visual/subjective qualities.
- Do NOT plan test files or README.md; other agents own those.
- Paths are relative POSIX paths without hidden files or '..'.
- Record every ambiguity you resolved in `assumptions`.
"""


def validate_spec(spec: Spec) -> Spec:
    if not spec.files:
        raise ValueError("Spec has no files.")
    seen: set[str] = set()
    for f in spec.files:
        try:
            f.path = safe_relpath(f.path)
        except UnsafePathError as e:
            raise ValueError(f"Invalid file path: {e}") from e
        if f.path in seen:
            raise ValueError(f"Duplicate file path: {f.path}")
        if is_test_path(f.path) or f.path.lower() == "readme.md":
            raise ValueError(f"Do not plan test files or README.md ({f.path}); other agents write those.")
        if language_for(f.path) != f.language and language_for(f.path) != "text":
            f.language = language_for(f.path)
        seen.add(f.path)
    for f in spec.files:
        f.depends_on = [d for d in (safe_relpath(x) for x in f.depends_on if x) if d in seen and d != f.path]
    _assert_acyclic(spec)
    ids = [ac.id for ac in spec.acceptance_criteria]
    if len(ids) != len(set(ids)):
        raise ValueError("Acceptance criteria ids must be unique.")
    return spec


def _assert_acyclic(spec: Spec) -> None:
    graph = {f.path: f.depends_on for f in spec.files}
    state: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 1:
            raise ValueError(f"Circular depends_on: {' -> '.join(trail + [node])}. Make dependencies one-directional.")
        if state.get(node) == 2:
            return
        state[node] = 1
        for dep in graph.get(node, []):
            visit(dep, trail + [node])
        state[node] = 2

    for node in graph:
        visit(node, [])


def plan(ctx: RunContext, requirement: str) -> Spec:
    return llm.call_structured(ctx, "planner", SYSTEM, f"Requirement:\n{requirement}", SpecOut, validate=validate_spec)
