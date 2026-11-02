"""Planner Agent: natural-language requirement -> validated technical spec."""

from __future__ import annotations

import re

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
- Keep the file set focused: no files the requirement does not need, but
  never trade away a complete, polished result to save a file.
- Use only the Python standard library and browser built-ins unless the
  user explicitly asks for a library; tests run offline with nothing extra
  installed. Web pages may load Google Fonts with a <link>.
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

Web pages (anything with an .html file) need a `design` brief; set it to
null only for projects with no web page. You are also the team's designer,
so plan something a professional studio would ship, never a bare page:
- `sections`: every section top to bottom (header/nav, hero, the content
  sections the request implies, footer), each with an exact HTML `id` and
  its real content: headline, copy, the actual items (features, plans,
  team members, products...), buttons. Write content specific to this
  project, never "Feature 1" or lorem ipsum. A landing page or company
  site usually needs 6-9 sections; an app page needs its working UI plus
  a header and footer.
- `palette`: 4-8 hex colours with roles (background, surface, text, muted
  text, accent, accent hover...) and strong text contrast.
- `typography`: font families with fallbacks, the type scale and weights.
- `style`: the look in a few sentences (e.g. "dark, glassy cards, soft
  gradients, generous whitespace, rounded 16px corners").
- `interactions`: hover/focus states, smooth scrolling, a phone menu,
  reveal animations, and any behaviour the request needs.
- `responsive`: how it adapts on phones (single column, collapsed nav...).
- Images: no external image URLs (they break); plan CSS gradients, shapes,
  inline SVG illustrations and icons instead.
- When the user gave reference links or images, follow them closely:
  same section order, layout, density, colours and typographic feel. Say
  how in `reference_notes`. If a reference could not be read, say so in
  `assumptions` instead of guessing what it contained.
Automated checks will confirm every section id exists, the page fits on a
phone and contains no placeholder text.
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
    validate_design(spec)
    return spec


_HTML_ID = re.compile(r"^[A-Za-z][\w-]*$")


def validate_design(spec: Spec) -> None:
    pages = [f.path for f in spec.files if f.path.endswith(".html")]
    if not pages:
        return
    d = spec.design
    if d is None:
        raise ValueError("This project has web pages, so `design` is required: sections with ids and real content, "
                         "palette, typography, style, interactions and responsive behaviour.")
    if len(d.sections) < 3:
        raise ValueError("The design needs every page section (at least a header, the main content and a footer).")
    if not 3 <= len(d.palette) <= 10:
        raise ValueError("The design palette needs 4 to 8 colours.")
    seen: set[tuple[str, str]] = set()
    for sec in d.sections:
        if sec.page not in pages:
            if len(pages) != 1:
                raise ValueError(f"Design section '{sec.name}' is on '{sec.page}', which is not a planned page ({', '.join(pages)}).")
            sec.page = pages[0]
        sec.id = sec.id.strip().lstrip("#")
        if not _HTML_ID.match(sec.id):
            raise ValueError(f"Design section '{sec.name}' has an invalid HTML id '{sec.id}'.")
        if (sec.page, sec.id) in seen:
            raise ValueError(f"Two design sections use id '{sec.id}' on {sec.page}.")
        seen.add((sec.page, sec.id))


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


def plan(ctx: RunContext, requirement: str, references: str = "", images: list[llm.Image] | None = None) -> Spec:
    user = f"Requirement:\n{requirement}"
    if references:
        user += f"\n\n{references}"
    if images:
        user += (f"\n\n{len(images)} reference image(s) are attached. Study the layout, sections, colours, type and "
                 "spacing in them and turn what you see into the design brief.")
    return llm.call_structured(ctx, "planner", SYSTEM, user, SpecOut, validate=validate_spec, images=images)
