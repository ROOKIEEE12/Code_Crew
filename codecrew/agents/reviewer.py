"""Review / Documentation Agent: README plus docstrings.

Docstring edits are accepted only if the file's AST is otherwise identical,
so documentation can never change behaviour.
"""

from __future__ import annotations

import ast
import re

from codecrew import llm
from codecrew.context import RunContext
from codecrew.schemas import Spec, Verification
from codecrew.textio import FILE_BLOCK_INSTRUCTIONS, parse_file_blocks, render_file_blocks, strip_reasoning

README_SYSTEM = """You are the Review/Documentation Agent. Write the README.md
for a finished, verified project.

Include: what it does, file structure, exact steps to run or open it, how to
run the tests, and a short "Verification" section that reports the real test
results you are given (do not overstate them). Practical and concise.
Return only the Markdown content."""

DOCSTRING_SYSTEM = f"""You are the Review/Documentation Agent. Add concise,
accurate docstrings to the listed functions and classes that lack them.
Change NOTHING else: no code, names, imports, formatting or comments
outside docstrings. Return the complete files.

{FILE_BLOCK_INSTRUCTIONS}"""


def write_readme(ctx: RunContext, spec: Spec, files: dict[str, str], tests: dict[str, str], verification: Verification | None) -> str:
    listing = "\n".join(f"- {p}" for p in [*files, *tests])
    result = verification.summary if verification else "not verified"
    user = (
        f"Spec:\n{spec.model_dump_json(indent=1, include={'project_name', 'summary', 'run_instructions', 'acceptance_criteria'})}\n\n"
        f"Files:\n{listing}\n\nVerification result: {result}\n"
        f"Test command: python -m pytest tests   (JavaScript: node --test tests)"
    )

    def parse(text: str) -> str:
        text = strip_reasoning(text)
        m = re.match(r"^\s*```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$", text)
        text = m.group(1) if m else text
        if len(text.strip()) < 40:
            raise ValueError("README is empty or too short.")
        return text.strip() + "\n"

    return llm.call_text(ctx, "reviewer", README_SYSTEM, user, parse)


class _StripDocstrings(ast.NodeTransformer):
    def _strip(self, node):
        self.generic_visit(node)
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]
        return node

    visit_Module = visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _strip


def _code_fingerprint(code: str) -> str:
    return ast.dump(_StripDocstrings().visit(ast.parse(code)), include_attributes=False)


def missing_docstrings(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            if ast.get_docstring(node) is None:
                out.append(node.name)
    return out


def add_docstrings(ctx: RunContext, files: dict[str, str]) -> dict[str, str]:
    """Returns only files whose docstring-only edit passed the AST check."""
    targets = {p: c for p, c in files.items() if p.endswith(".py") and missing_docstrings(c)}
    if not targets:
        return {}
    wanted = "\n".join(f"- {p}: {', '.join(missing_docstrings(c))}" for p, c in targets.items())

    def parse(text: str) -> dict[str, str]:
        out = parse_file_blocks(text)
        return {p: c for p, c in out.items() if p in targets}

    proposed = llm.call_text(ctx, "reviewer", DOCSTRING_SYSTEM, f"Add docstrings to:\n{wanted}\n\n{render_file_blocks(targets)}", parse)
    accepted = {}
    for path, code in proposed.items():
        try:
            if _code_fingerprint(code) == _code_fingerprint(targets[path]):
                accepted[path] = code
        except SyntaxError:
            continue
    return accepted
