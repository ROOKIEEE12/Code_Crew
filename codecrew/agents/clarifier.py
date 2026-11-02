"""Clarifier (part of the Planner): before planning, decides whether the
requirement leaves an important choice open and, if so, asks the user up to
two multiple-choice questions. Every question has a recommended option, so
an unanswered question never blocks the build.
"""

from __future__ import annotations

from codecrew import llm
from codecrew.context import RunContext
from codecrew.schemas import ClarifyOut

MAX_QUESTIONS = 2

SYSTEM = """You are the Planner Agent of an AI software team, reading a
user's requirement before writing the technical plan.

Decide whether the requirement leaves open a choice that would change what
gets built or how it is tested: input range and invalid input handling,
output format, the platform (Python module, command-line tool, web page),
or a missing core feature. For a website with no reference link or
image, the overall look (e.g. dark and modern, light and minimal, bold
and colourful) is worth asking about. If so, ask at most 2 short
multiple-choice questions about the most important open choices.

Rules:
- Ask nothing (return an empty list) when the requirement is already clear
  enough, or when any sensible answer would lead to nearly the same result.
- Never ask about things you can decide well yourself: naming, file
  layout, code style, or libraries.
- Write for someone who may not be a programmer: plain words, no jargon.
- Each question has 2 to 4 short options. Mark exactly one option as
  recommended: the sensible default if the user does not answer.
"""


def validate(out: ClarifyOut) -> ClarifyOut:
    out.questions = out.questions[:MAX_QUESTIONS]
    for q in out.questions:
        if not q.question.strip():
            raise ValueError("Every question needs text.")
        if not 2 <= len(q.options) <= 4:
            raise ValueError(f"Question '{q.question}' needs 2 to 4 options, got {len(q.options)}.")
        if sum(1 for o in q.options if o.recommended) != 1:
            raise ValueError(f"Question '{q.question}' must mark exactly one option as recommended.")
    return out


def questions(ctx: RunContext, requirement: str) -> ClarifyOut:
    return llm.call_structured(ctx, "clarifier", SYSTEM, f"Requirement:\n{requirement}", ClarifyOut, validate=validate)


def with_answers(requirement: str, answers: list[tuple[str, str, bool]]) -> str:
    """Appends the user's answers (question, answer, chosen automatically) to the requirement."""
    if not answers:
        return requirement
    lines = "\n".join(
        f"- {q} -> {a}" + (" (the user did not answer; this is the recommended default)" if auto else "")
        for q, a, auto in answers
    )
    return f"{requirement}\n\nClarifications agreed with the user before planning:\n{lines}"
