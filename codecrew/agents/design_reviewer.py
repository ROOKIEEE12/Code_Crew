"""Design review (part of the Review Agent): looks at screenshots of the
finished page, compares them with the design brief and the user's
references, and lists concrete visual fixes for the Coder.

The tests decide whether the code is correct; this decides whether it
looks like what was asked for. It only runs once the tests pass, and the
orchestrator keeps the polished version only if every check still passes.
"""

from __future__ import annotations

from codecrew import llm
from codecrew.context import RunContext
from codecrew.schemas import DesignReviewOut, Spec

SYSTEM = """You are the Review Agent acting as a senior product designer.
You get screenshots of a web page the team built (desktop at 1280px wide,
phone at 390px wide), the design brief it was built from, and the user's
reference material if there is any.

Judge what you SEE in the screenshots, not what the code intends:
- Is every planned section there, in order, with real content?
- Does it match the brief's style, palette and typography, and the
  references' layout, density and feel?
- Visual quality: hierarchy, spacing rhythm, alignment, contrast,
  consistency, depth. Does it look professionally designed, or like a bare
  template?
- Broken layout: text or buttons overlapping each other, unstyled default
  controls (plain browser buttons/selects), underlined nav links, elements
  touching the screen edge. These are the most important fixes.
- Phone: readable text, nothing cut off or overlapping, usable navigation.

Score 1-10, where 8 or more means ready to ship. List up to 8 fixes, most
important first. Each fix must be concrete enough for a developer who
cannot see the screenshot: name the section or element and exactly what
to change (sizes, palette colours, spacing, layout, alignment). Do not ask
for features beyond the brief, external images, or changes to app logic."""


def _validate(out: DesignReviewOut) -> DesignReviewOut:
    if not 1 <= out.score <= 10:
        raise ValueError("score must be between 1 and 10.")
    out.fixes = [f.strip() for f in out.fixes if f.strip()][:8]
    out.strengths = [s.strip() for s in out.strengths if s.strip()][:4]
    if out.score < 8 and not out.fixes:
        raise ValueError("A score below 8 needs the fixes that would raise it.")
    return out


def review(ctx: RunContext, spec: Spec, screenshots: list[tuple[str, bytes]], references: str = "",
           reference_images: list[llm.Image] | None = None) -> DesignReviewOut:
    """`screenshots` are (label, JPEG) pairs of the built page, e.g. ("index.html desktop", ...)."""
    images: list[llm.Image] = [("image/jpeg", data) for _, data in screenshots]
    labels = [f"Image {i}: the built page, {label}." for i, (label, _) in enumerate(screenshots, 1)]
    for i, _ in enumerate(reference_images or [], len(images) + 1):
        labels.append(f"Image {i}: the user's reference.")
    images += reference_images or []
    user = (
        "\n".join(labels)
        + "\n\nDesign brief:\n" + (spec.design.model_dump_json(indent=1) if spec.design else "none")
        + f"\n\nProject: {spec.summary}"
    )
    if references:
        user += f"\n\n{references}"
    return llm.call_structured(ctx, "design_review", SYSTEM, user, DesignReviewOut, validate=_validate,
                               images=images, images_required=True)
