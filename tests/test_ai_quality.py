"""Reference links, attached images, web-quality checks and the design review."""

import json

import pytest

from codecrew import llm, orchestrator, reference, render
from codecrew.agents import planner
from codecrew.config import settings
from codecrew.context import RunContext
from codecrew.llm import Completion, Provider
from codecrew.schemas import RunState, Spec
from codecrew.verify import check_web_quality

DESIGN = {
    "style": "Dark, calm, rounded cards.",
    "typography": "Inter, system-ui, sans-serif; 16px base.",
    "interactions": ["Buttons lighten on hover."],
    "responsive": "Single column under 700px.",
    "reference_notes": "",
    "palette": [{"name": n, "hex": h, "usage": n} for n, h in
                (("background", "#0b0b10"), ("text", "#f2f2f5"), ("accent", "#7c66dc"), ("muted", "#9a9aa8"))],
    "sections": [
        {"id": "top", "page": "index.html", "name": "Header", "content": "Logo and navigation."},
        {"id": "hero", "page": "index.html", "name": "Hero", "content": "Headline: Fresh waffles every morning."},
        {"id": "contact", "page": "index.html", "name": "Footer", "content": "Address and opening hours."},
    ],
}

SITE_SPEC = {
    "project_name": "waffle-site",
    "project_type": "web_app",
    "summary": "A one-page site for a waffle shop.",
    "run_instructions": "Open index.html",
    "files": [
        {"path": "index.html", "language": "html", "purpose": "Page.", "depends_on": ["styles.css"], "functions": [], "testable": False},
        {"path": "styles.css", "language": "css", "purpose": "Styles.", "depends_on": [], "functions": [], "testable": False},
    ],
    "acceptance_criteria": [{"id": "AC1", "description": "index.html loads styles.css", "verification": "static_check"}],
    "assumptions": [],
    "design": DESIGN,
}

CSS = (":root{--bg:#0b0b10;--text:#f2f2f5;--accent:#7c66dc;--muted:#9a9aa8}"
       "body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif}"
       "a:hover{color:var(--accent)}@media (max-width:700px){h1{font-size:2rem}}")


def page(extra: str = "", headline: str = "Fresh waffles every morning") -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>Waffles</title>'
            f'<link rel="stylesheet" href="styles.css"></head><body>'
            f'<header id="top"><a href="#hero">Menu</a></header><main><section id="hero"><h1>{headline}</h1></section></main>'
            f'<footer id="contact">12 Baker Street, open 7-14</footer>{extra}</body></html>')


def blocks(files: dict[str, str]) -> str:
    return "\n".join(f'<<<FILE path="{p}">>>\n{c}\n<<<END FILE>>>' for p, c in files.items())


# ---------------------------------------------------------------- reference links

def test_find_urls():
    text = "Make it like https://stripe.com/payments, and see (https://example.org/a?b=1)."
    assert reference.find_urls(text) == ["https://stripe.com/payments", "https://example.org/a?b=1"]


def test_reference_digest(monkeypatch):
    html = """<html><head><title>Acme</title><meta name="description" content="Rockets for everyone">
      <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;700">
      <style>body{background:#101820;color:#FEE715} .btn{font-family:'Space Grotesk',sans-serif}</style></head>
      <body><nav><a href="/">Home</a><a href="/pricing">Pricing</a></nav>
      <section id="hero"><h1>Launch faster</h1><p>Rockets that are ready when you are, with no paperwork at all.</p>
      <a class="btn" href="/start">Start now</a></section><footer>(c) Acme</footer></body></html>"""
    monkeypatch.setattr(reference, "_fetch", lambda client, url, limit: (200, "text/html", html))
    monkeypatch.setattr(render, "available", lambda: False)
    ref, shot = reference.read("https://acme.test/")
    assert ref.ok and shot is None
    assert ref.title == "Acme" and ref.description == "Rockets for everyone"
    assert "Navigation: Home · Pricing" in ref.outline and "H1: Launch faster" in ref.outline
    assert any("Start now" in o for o in ref.outline)
    assert ref.colors[:2] == ["#101820", "#fee715"] and ref.fonts[0] == "Space Grotesk"
    assert "Launch faster" in reference.brief([ref])


def test_blocked_and_private_references_are_reported_not_guessed(monkeypatch):
    monkeypatch.setattr(render, "available", lambda: False)
    monkeypatch.setattr(reference, "_fetch", lambda client, url, limit: (403, "text/html", "<title>Just a moment...</title>"))
    ref, _ = reference.read("https://blocked.test/")
    assert not ref.ok and "403" in ref.error
    assert "could NOT be read" in reference.brief([ref])

    monkeypatch.undo()
    monkeypatch.setattr(render, "available", lambda: False)
    ref, _ = reference.read("http://127.0.0.1:9/admin")
    assert not ref.ok and "public" in ref.error


# ---------------------------------------------------------------- plan validation and quality checks

def test_web_pages_need_a_design_brief():
    spec = Spec.model_validate({**SITE_SPEC, "design": None})
    with pytest.raises(ValueError, match="design"):
        planner.validate_spec(spec)
    spec = Spec.model_validate({**SITE_SPEC, "design": {**DESIGN, "sections": [{**s, "page": "home.html", "id": "#" + s["id"]}
                                                                            for s in DESIGN["sections"]]}})
    planner.validate_spec(spec)  # one page: sections are moved onto it and "#" is dropped from ids
    assert {(s.page, s.id) for s in spec.design.sections} == {("index.html", "top"), ("index.html", "hero"), ("index.html", "contact")}


def test_older_specs_load_without_design():
    old = {k: v for k, v in SITE_SPEC.items() if k != "design"}
    assert Spec.model_validate(old).design is None


def test_quality_checks_catch_incomplete_pages():
    spec = Spec.model_validate(SITE_SPEC)
    good = check_web_quality({"index.html": page(), "styles.css": CSS}, spec)
    assert not [i for i in good if i.severity == "error"], good

    bad_html = page(headline="Lorem ipsum dolor").replace('<meta name="viewport" content="width=device-width, initial-scale=1">', "")
    bad_html = bad_html.replace('<footer id="contact">', "<footer>")
    errors = [i.message for i in check_web_quality({"index.html": bad_html, "styles.css": "body{margin:0}"}, spec) if i.severity == "error"]
    assert any("viewport" in m for m in errors)
    assert any("Lorem ipsum" in m for m in errors)
    assert any('id="contact"' in m for m in errors)
    assert any("responsive" in m for m in errors)


# ---------------------------------------------------------------- images

class _Blind(Provider):
    name = "blind"

    def __init__(self):
        self.seen = []

    def configured(self):
        return True

    def models_for(self, role):
        return ["m"]

    def text(self, model, system, user, role, images=None):
        self.seen.append(len(images or []))
        if images:
            raise llm.VisionUnsupported("this model has no vision")
        return Completion("plain answer", model, 1, 1)


def test_images_fall_back_to_text_when_no_model_can_see(monkeypatch):
    provider = _Blind()
    monkeypatch.setattr(llm, "candidates", lambda role: [(provider, "m")])
    llm._NO_VISION.clear()
    ctx = RunContext(RunState(id="r1", requirement="x"))
    assert llm.call_text(ctx, "planner", "s", "u", str, images=[("image/png", b"\x89PNG")]) == "plain answer"
    assert provider.seen == [1, 0]
    assert any("could look at the 1 image" in a.message for a in ctx.state.activity)
    assert "blind:m" in llm._NO_VISION and llm.health.available("blind:m")  # still fine for text

    with pytest.raises(llm.LLMError):  # a review of screenshots never runs blind
        llm.call_structured(ctx, "design_review", "s", "u", type("M", (llm.BaseModel,), {"__annotations__": {"x": int}}),
                            images=[("image/png", b"\x89PNG")], images_required=True)
    llm._NO_VISION.clear()


# ---------------------------------------------------------------- design review (real browser)

needs_browser = pytest.mark.skipif(not render.available(), reason="Playwright/Chromium not installed")


class Designer(Provider):
    name = "designer"

    def __init__(self, polished: dict[str, str]):
        self.polished = polished
        self.calls = []
        self.review_images = []

    def configured(self):
        return True

    def models_for(self, role):
        return ["m"]

    def text(self, model, system, user, role, images=None):
        self.calls.append(role)
        if role == "planner":
            reply = json.dumps(SITE_SPEC)
        elif role == "coder":
            files = self.polished if "Design review fixes" in user else {"index.html": page(), "styles.css": CSS}
            reply = blocks(files)
        elif role == "design_review":
            self.review_images = images or []
            reply = json.dumps({"score": 5, "strengths": ["Clear headline."],
                                "fixes": ["Hero: make the headline larger and add a call-to-action button in the accent colour."]})
        elif role == "reviewer":
            reply = "# Waffle site\n\nOpen index.html in a browser to see the page.\n"
        else:
            raise AssertionError(role)
        return Completion(reply, model, 1, 1)


@pytest.fixture
def browser_on():
    object.__setattr__(settings, "browser_checks", "auto")
    object.__setattr__(settings, "design_review_rounds", 1)
    llm.health._stats.clear()
    yield
    object.__setattr__(settings, "design_review_rounds", 2)


@needs_browser
def test_design_review_polishes_the_page(monkeypatch, browser_on):
    polished = {"index.html": page(headline="Fresh waffles, every single morning"), "styles.css": CSS + "h1{font-size:3.5rem}"}
    provider = Designer(polished)
    monkeypatch.setattr(llm, "candidates", lambda role: [(provider, "m")])
    state = orchestrator.run_sync(orchestrator.new_run("A site for my waffle shop"))
    assert state.status == "succeeded", state.error
    assert provider.calls.count("coder") == 2 and "design_review" in provider.calls
    assert len(provider.review_images) == 2 and all(data[:3] == b"\xff\xd8\xff" for _, data in provider.review_images)
    review = state.design_reviews[0]
    assert review.score == 5 and review.applied and review.kept
    assert state.files["styles.css"].rstrip().endswith("h1{font-size:3.5rem}")


@needs_browser
def test_design_polish_that_breaks_the_page_is_reverted(monkeypatch, browser_on):
    broken = {"index.html": page(extra="<script>document.getElementById('missing').remove()</script>"), "styles.css": CSS}
    provider = Designer(broken)
    monkeypatch.setattr(llm, "candidates", lambda role: [(provider, "m")])
    state = orchestrator.run_sync(orchestrator.new_run("A site for my waffle shop"))
    assert state.status == "succeeded", state.error
    assert not state.design_reviews[0].kept
    assert "<script>" not in state.files["index.html"]  # the version from before the polish
    assert any("polish broke a check" in a.message for a in state.activity)
