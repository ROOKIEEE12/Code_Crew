"""Orchestrator triage for change requests on an existing project."""

from __future__ import annotations

from codecrew import llm
from codecrew.context import RunContext
from codecrew.schemas import Spec, TriageOut
from codecrew.textio import UnsafePathError, language_for, render_file_blocks, safe_relpath
from codecrew.verify import is_test_path

SYSTEM = """You are the Orchestrator of an AI software team, triaging a
change request for an existing project. Decide the minimal set of source
files to create or modify, give each its updated file spec (exact function
names/signatures), list any NEW acceptance criteria the change introduces
(so the Test Author can add tests for them), and write precise instructions
for the Coder. Do not include test files or README.md in `files`; set
update_readme when user-facing behaviour or usage changes. For a pure
documentation request, `files` may be empty.

For web pages: when the change alters the look or adds, removes or
reorders sections, return the complete updated `design` brief (keep every
section that stays, with its id); otherwise set `design` to null. Visual
requests ("make it modern", "like this site") deserve a real redesign of
the affected sections, not a one-line tweak. If the request includes
reference material or images, follow them closely."""


def _validate(t: TriageOut) -> TriageOut:
    for f in t.files:
        try:
            f.path = safe_relpath(f.path)
        except UnsafePathError as e:
            raise ValueError(str(e)) from e
        if is_test_path(f.path) or f.path.lower() == "readme.md":
            raise ValueError(f"{f.path}: tests and README are handled by other agents.")
        if language_for(f.path) != "text":
            f.language = language_for(f.path)
    if not t.files and not t.update_readme:
        raise ValueError("Triage selected no files and no README update.")
    return t


def triage(ctx: RunContext, spec: Spec, files: dict[str, str], request: str, references: str = "",
           images: list[llm.Image] | None = None) -> TriageOut:
    user = (
        f"Current specification:\n{spec.model_dump_json(indent=1)}\n\n"
        f"Current source files:\n{render_file_blocks(files, limit_chars=20000)}\n\n"
        f"Change request:\n{request}"
    )
    if references:
        user += f"\n\n{references}"
    return llm.call_structured(ctx, "triage", SYSTEM, user, TriageOut, validate=_validate, images=images)
