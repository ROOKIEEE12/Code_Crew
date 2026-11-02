"""Debugging Agent: root-causes verification failures and patches source files.

It sees the failing tests, tracebacks, contract/lint findings, every source
file, and what earlier rounds already tried. It may NOT edit tests; if it
believes a test contradicts the spec it files a dispute instead.
"""

from __future__ import annotations

import ast

from codecrew import llm
from codecrew.context import RunContext
from codecrew.schemas import DebugRound, Issue, Spec
from codecrew.textio import FILE_BLOCK_INSTRUCTIONS, parse_disputes, parse_file_blocks, render_file_blocks, strip_reasoning
from codecrew.verify import is_test_path

SYSTEM = f"""You are the Debugging Agent. Verification of the project
failed. Find the real root cause of each problem and fix the source code.

Rules:
- Fix causes, not symptoms. Never special-case test inputs, catch-and-ignore
  errors, or weaken behaviour to silence a failure. Skipping a test
  (pytest.skip, xfail, exiting early) counts as failing it, and files that
  change how tests run (conftest.py, sitecustomize.py, test configuration)
  are rejected.
- Change as little as needed; keep everything that already works.
- You may not modify test files. If, and only if, a test asserts something
  that contradicts or goes beyond the specification, dispute it:

<<<DISPUTE test="tests/test_x.py::test_name">>>
Why the test contradicts the specification, quoting the spec.
<<<END DISPUTE>>>

- Quality and runtime findings (a missing design section, placeholder
  text, a JavaScript error in the browser, a page wider than a phone
  screen) are real defects: fix them in the HTML/CSS/JS, keeping the
  design intact.
- Return complete contents for every source file you change.
- Do not repeat a fix that an earlier round already tried without success.
- Begin your reply with a short diagnosis: 1 to 3 lines, each starting
  with "- ", naming the root cause in plain words. Then the file blocks.

{FILE_BLOCK_INSTRUCTIONS}"""


def _format_issues(issues: list[Issue]) -> str:
    lines = []
    for i, issue in enumerate(issues, 1):
        where = issue.test_id or (f"{issue.file}:{issue.line}" if issue.line else issue.file) or "project"
        lines.append(f"{i}. [{issue.source}/{issue.severity}] {where}\n{issue.message.strip()}")
    return "\n\n".join(lines)


def diagnosis(text: str) -> list[str]:
    """The "- " lines written before the first file or dispute block."""
    head = strip_reasoning(text).split("<<<", 1)[0]
    return [ln.strip()[2:].strip() for ln in head.splitlines() if ln.strip().startswith(("- ", "* "))][:3]


def debug(
    ctx: RunContext,
    spec: Spec,
    files: dict[str, str],
    tests: dict[str, str],
    issues: list[Issue],
    history: list[DebugRound],
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Returns (changed source files, disputes {test_id: reason}, diagnosis lines)."""
    failing_test_files = {i.file for i in issues if i.source == "test" and i.file}
    relevant_tests = {p: c for p, c in tests.items() if p in failing_test_files} or tests
    parts = [
        "Specification:\n" + spec.model_dump_json(indent=1, exclude={"assumptions"}),
        "\nProblems found by verification:\n" + _format_issues(issues[:40]),
        "\nSource files:\n" + render_file_blocks(files),
    ]
    if relevant_tests:
        parts.append("\nTest files (read-only):\n" + render_file_blocks(relevant_tests))
    if history:
        parts.append("\nEarlier debug rounds:\n" + "\n".join(
            f"- round {h.round}: changed {', '.join(h.changed_files) or 'nothing'}; "
            f"{'improved' if h.kept else 'made things worse and was reverted'}"
            for h in history
        ))

    def parse(text: str) -> tuple[dict[str, str], dict[str, str], list[str]]:
        disputes = parse_disputes(text)
        try:
            changed = parse_file_blocks(text)
        except ValueError:
            if not disputes:
                raise
            changed = {}
        bad = [p for p in changed if is_test_path(p)]
        if bad:
            raise ValueError(f"You may not modify test files ({', '.join(bad)}); dispute the test instead.")
        for path, code in changed.items():
            if path.endswith(".py"):
                try:
                    ast.parse(code)
                except SyntaxError as e:
                    raise ValueError(f"{path} has a syntax error at line {e.lineno}: {e.msg}") from e
        changed = {p: c for p, c in changed.items() if files.get(p) != c}
        if not changed and not disputes:
            raise ValueError("No file changes and no disputes were returned.")
        return changed, disputes, diagnosis(text)

    return llm.call_text(ctx, "debugger", SYSTEM, "\n".join(parts), parse)
