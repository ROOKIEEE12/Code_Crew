"""Test Author Agent: writes unit tests from the SPEC, before code exists.

Because tests encode the requirement rather than an implementation, a bug
in the code cannot be "confirmed" by a test generated from that same code.
Tests are locked afterwards; only a dispute reviewed here can change them.
"""

from __future__ import annotations

import ast
import re

from codecrew import llm
from codecrew.context import RunContext
from codecrew.schemas import AcceptanceCriterion, Spec
from codecrew.textio import FILE_BLOCK_INSTRUCTIONS, parse_file_blocks, render_file_blocks
from codecrew.verify import is_test_path

SYSTEM = f"""You are the Test Author Agent. You write automated unit tests
from a technical specification BEFORE the implementation exists. The
implementation will be written to make your tests pass, so your tests
define correctness.

Rules:
- Test only behaviour the spec states. Never assert on details the spec
  leaves open (exact error message wording, float formatting, ordering,
  print output) unless the spec defines them.
- Import exactly the names and signatures in the spec.
- Python: pytest files at tests/test_<module>.py. Import modules by their
  path from the project root (e.g. `from calc import add`,
  `from pkg.util import f`). Use pytest.raises for specified errors.
- JavaScript: node:test files at tests/<name>.test.js using
  `const test = require("node:test"); const assert = require("node:assert/strict");`
  and `require("../<path>")` for the module under test.
- Only write tests for files marked testable.
- Name tests after the acceptance criterion they cover where one applies,
  e.g. `test_ac2_rejects_negative_amount` / test("AC2 rejects negative amount").
- Cover normal cases, boundaries and specified error cases; 3-8 focused
  tests per function. Tests must be deterministic: no network, no sleeping,
  no stdin, no files outside pytest's tmp_path.

{FILE_BLOCK_INSTRUCTIONS}"""


def _spec_brief(spec: Spec) -> str:
    return spec.model_dump_json(indent=1, include={"summary", "files", "acceptance_criteria"})


def _validate(files: dict[str, str]) -> dict[str, str]:
    for path, code in files.items():
        if not is_test_path(path):
            raise ValueError(f"{path} is not a test file path (use tests/test_*.py or tests/*.test.js).")
        if path.endswith(".py"):
            try:
                ast.parse(code)
            except SyntaxError as e:
                raise ValueError(f"{path} has a syntax error at line {e.lineno}: {e.msg}") from e
    return files


def write_tests(ctx: RunContext, spec: Spec, criteria: list[AcceptanceCriterion] | None = None, existing: dict[str, str] | None = None) -> dict[str, str]:
    if not any(f.testable for f in spec.files):
        return {}
    user = f"Specification:\n{_spec_brief(spec)}"
    if criteria is not None:
        user += "\n\nWrite tests ONLY for these new acceptance criteria:\n" + "\n".join(
            f"- {c.id}: {c.description}" for c in criteria
        )
    if existing:
        user += "\n\nExisting tests (keep them; add new files or return a complete updated version of a file):\n" + render_file_blocks(existing)
    return llm.call_text(ctx, "test_author", SYSTEM, user, lambda t: _validate(parse_file_blocks(t)))


def uncovered_criteria(spec: Spec, tests: dict[str, str]) -> list[str]:
    blob = "\n".join(tests.values()).lower()
    out = []
    for ac in spec.acceptance_criteria:
        if ac.verification == "automated_test" and not re.search(rf"\b{re.escape(ac.id.lower())}(?:\b|_)", blob):
            out.append(ac.id)
    return out


DISPUTE_SYSTEM = f"""You are the Test Author Agent reviewing a dispute. The
Debugger claims one of your tests contradicts the specification. Decide
strictly by the specification, not by what the implementation happens to do.

Begin your answer with exactly one line:
VERDICT: TEST_WRONG   (the test asserts something the spec does not say)
VERDICT: TEST_CORRECT (the test follows the spec; the code must change)

Then one short paragraph of reasoning. If TEST_WRONG, also return the
complete corrected test file.

{FILE_BLOCK_INSTRUCTIONS}"""


def review_dispute(ctx: RunContext, spec: Spec, test_path: str, test_code: str, test_id: str, reason: str) -> tuple[bool, str, dict[str, str]]:
    user = (
        f"Specification:\n{_spec_brief(spec)}\n\nDisputed test: {test_id}\n"
        f"Debugger's reasoning:\n{reason}\n\nCurrent test file:\n"
        + render_file_blocks({test_path: test_code})
    )

    def parse(text: str) -> tuple[bool, str, dict[str, str]]:
        m = re.search(r"VERDICT:\s*(TEST_WRONG|TEST_CORRECT)", text)
        if not m:
            raise ValueError("Missing 'VERDICT: TEST_WRONG' or 'VERDICT: TEST_CORRECT' line.")
        wrong = m.group(1) == "TEST_WRONG"
        explanation = text[m.end():].split("<<<FILE", 1)[0].strip()[:1000]
        files = _validate(parse_file_blocks(text)) if wrong else {}
        if wrong and test_path not in files:
            raise ValueError(f"Verdict TEST_WRONG requires the corrected {test_path} file block.")
        return wrong, explanation, {test_path: files[test_path]} if wrong else {}

    return llm.call_text(ctx, "test_author", DISPUTE_SYSTEM, user, parse)
