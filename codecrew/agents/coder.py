"""Code Generation Agent: implements the spec so the locked tests pass."""

from __future__ import annotations

import ast

from codecrew import llm
from codecrew.context import RunContext
from codecrew.schemas import FileSpec, Spec
from codecrew.textio import FILE_BLOCK_INSTRUCTIONS, parse_file_blocks, render_file_blocks

SYSTEM = f"""You are the Code Generation Agent, a senior engineer on an AI
software team. Implement exactly the files assigned to you, following the
technical specification. Tests were written from the same spec before you
started; your code must make them pass without special-casing them.

Rules:
- Use the exact file paths, function/class names and signatures from the spec.
- Write complete, working code: no TODOs, stubs or placeholders.
- Match every cross-file contract exactly: element ids, imports, exported
  names, routes, data shapes.
- Use only the Python standard library and browser built-ins unless the
  spec says otherwise.
- Python modules must have no side effects at import time; put any CLI or
  input()/print flow in main() behind `if __name__ == "__main__":`.
- JavaScript logic files must not touch `document`/`window` at load time;
  export logic with `if (typeof module !== "undefined") module.exports = {{...}};`.
  DOM scripts should wait for DOMContentLoaded.
- Add docstrings/brief comments where they help a reader; don't over-comment.
- Never skip or short-circuit tests (pytest.skip, xfail, exiting early), and
  never write conftest.py, sitecustomize.py or test configuration: the
  Verifier rejects them, and a skipped test counts as failing.

Web pages: you are also a senior front-end developer with a designer's
eye. Build the spec's `design` brief faithfully and make it look like a
real, modern, professionally designed site:
- Every section in `design.sections`, in order, on the element with that
  exact id, with real, specific content (no lorem ipsum, no "Feature 1",
  no example.com).
- Semantic HTML: <header>, <nav>, <main>, <section>, <footer>; <html
  lang>, <meta charset>, <meta name="viewport" content="width=device-width,
  initial-scale=1">, a real <title>; alt text and labelled form controls.
- CSS: the palette as custom properties in :root and used everywhere; the
  planned fonts (Google Fonts <link> plus system fallbacks); fluid type
  with clamp(); a max-width container; a consistent spacing scale;
  CSS grid/flexbox layouts; consistent radii and shadows; visual depth with
  gradients, inline SVG shapes and icons (no external image URLs).
- Responsive, mobile first: media queries; nothing wider than a 375px
  screen; the nav collapses into a working menu button on phones.
- Polish: :hover, :focus-visible and :active states; smooth transitions;
  scroll-behavior: smooth; subtle reveal animations, all disabled under
  @media (prefers-reduced-motion: reduce). Content must be visible even
  if JavaScript fails.
- When reference material or images are given, match their layout,
  section order, spacing, colours and typographic feel closely.

{FILE_BLOCK_INSTRUCTIONS}"""


def _validator(expected: list[str]):
    def parse(text: str) -> dict[str, str]:
        files = parse_file_blocks(text)
        missing = [p for p in expected if p not in files]
        if missing:
            raise ValueError(f"Missing file block(s) for: {', '.join(missing)}")
        for path in expected:
            if path.endswith(".py"):
                try:
                    ast.parse(files[path])
                except SyntaxError as e:
                    raise ValueError(f"{path} has a syntax error at line {e.lineno}: {e.msg}") from e
        return {p: files[p] for p in expected}

    return parse


def generate(
    ctx: RunContext,
    spec: Spec,
    assigned: list[FileSpec],
    existing: dict[str, str],
    tests: dict[str, str],
    instructions: str = "",
    references: str = "",
    images: list[llm.Image] | None = None,
) -> dict[str, str]:
    """Generate (or rewrite) the assigned files. `existing` holds already
    written files: dependencies for a fresh build, or current contents for
    an iteration (the coder then changes them minimally)."""
    paths = [f.path for f in assigned]
    parts = [
        "Full specification:\n" + spec.model_dump_json(indent=1, exclude={"assumptions"}),
        "\nYour assigned files: " + ", ".join(paths),
    ]
    if instructions:
        parts.append(f"\nChange request (modify existing code minimally to satisfy it):\n{instructions}")
    if existing:
        parts.append("\nExisting project files (stay consistent with them; rewrite only your assigned files):\n" + render_file_blocks(existing))
    if tests:
        parts.append("\nLocked unit tests your code must pass:\n" + render_file_blocks(tests))
    # Reference material only matters for files that decide how the page looks.
    visual = any(p.endswith((".html", ".css")) for p in paths)
    if visual and references:
        parts.append("\n" + references)
    if visual and images:
        parts.append(f"\n{len(images)} image(s) are attached: match what they show.")
    return llm.call_text(ctx, "coder", SYSTEM, "\n".join(parts), _validator(paths), images=images if visual else None)
