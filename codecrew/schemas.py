"""Typed data contracts shared by every agent, the orchestrator, the API and
(via OpenAPI) the Next.js frontend.

Models whose name ends in `Out` are what an LLM is asked to produce; they
keep every field required so structured-output schemas stay strict.
"""

from __future__ import annotations

import time
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

Language = Literal["python", "javascript", "typescript", "html", "css", "json", "markdown", "text"]


# ---------------------------------------------------------------- spec

class FunctionSpec(BaseModel):
    name: str = Field(description="Exact function/class name, as it will be imported by tests.")
    signature: str = Field(description="Full signature, e.g. 'def add(a: int, b: int) -> int'.")
    behavior: str = Field(description="What it does, including inputs, outputs and return values.")
    edge_cases: list[str] = Field(description="Edge cases and errors it must handle, e.g. 'raises ValueError on negative n'.")


class FileSpec(BaseModel):
    path: str = Field(description="Relative POSIX path inside the project, e.g. 'src/app.py'.")
    language: Language
    purpose: str
    depends_on: list[str] = Field(description="Other planned file paths this file must stay consistent with.")
    functions: list[FunctionSpec] = Field(description="Public functions/classes. Empty for markup/style files.")
    testable: bool = Field(description="True if this file exposes importable logic that unit tests can call.")


class AcceptanceCriterion(BaseModel):
    id: str = Field(description="Short id: AC1, AC2, ...")
    description: str = Field(description="One observable, checkable behaviour.")
    verification: Literal["automated_test", "static_check", "manual"]


class ColorToken(BaseModel):
    name: str = Field(description="Role of the colour, e.g. 'background', 'surface', 'text', 'muted', 'accent'.")
    hex: str = Field(description="Hex value, e.g. '#0b0b0f'.")
    usage: str = Field(description="Where it is used.")


class PageSection(BaseModel):
    id: str = Field(description="The HTML id attribute the section element must have, e.g. 'pricing'.")
    page: str = Field(description="HTML file the section is on, e.g. 'index.html'.")
    name: str = Field(description="Short name, e.g. 'Pricing'.")
    content: str = Field(description="What it shows: the real headline, copy, items and visuals, specific to this project.")


class DesignBrief(BaseModel):
    style: str = Field(description="The look and feel in 2-4 sentences: mood, density, shapes, imagery, motion.")
    palette: list[ColorToken] = Field(description="4 to 8 colours that work together with good contrast.")
    typography: str = Field(description="Font families (with fallbacks), the type scale and weights.")
    sections: list[PageSection] = Field(description="Every page section in order, top to bottom, including header/nav and footer.")
    interactions: list[str] = Field(description="Hover/focus states, animations, menus, toggles and other behaviour.")
    responsive: str = Field(description="How the layout adapts on phones and tablets.")
    reference_notes: str = Field(description="How the design follows the user's reference links or images; empty if there were none.")


class SpecOut(BaseModel):
    project_name: str = Field(description="short-kebab-case-name")
    project_type: Literal["script", "cli_tool", "web_app", "backend_api", "library", "other"]
    summary: str
    run_instructions: str = Field(description="Exact command or action to run/open the project.")
    files: list[FileSpec]
    acceptance_criteria: list[AcceptanceCriterion]
    assumptions: list[str] = Field(description="Ambiguities in the request and how they were resolved.")
    design: Optional[DesignBrief] = Field(description="Required for anything with a web page; null for projects without a UI.")

    @model_validator(mode="before")
    @classmethod
    def _older_specs(cls, data):
        # Specs saved before design briefs existed load with no design.
        if isinstance(data, dict) and "design" not in data:
            data = {**data, "design": None}
        return data


Spec = SpecOut


class TriageOut(BaseModel):
    intent: Literal["feature", "bugfix", "styling", "documentation", "refactor"]
    explanation: str
    files: list[FileSpec] = Field(description="Only the files to create or modify, with their updated spec.")
    new_acceptance_criteria: list[AcceptanceCriterion]
    instructions: str = Field(description="Precise instructions for the coder.")
    update_readme: bool
    design: Optional[DesignBrief] = Field(description="The complete updated design brief when the change alters the look or the page sections; otherwise null.")

    @model_validator(mode="before")
    @classmethod
    def _no_design(cls, data):
        if isinstance(data, dict) and "design" not in data:
            data = {**data, "design": None}
        return data


class DesignReviewOut(BaseModel):
    score: int = Field(description="1 to 10: how well the page matches the design brief and references, and how polished it looks.")
    strengths: list[str] = Field(description="Up to 4 things that already look good.")
    fixes: list[str] = Field(description="Up to 8 specific visual fixes, most important first, each naming the section or element and exactly what to change. Empty if nothing important is wrong.")


class Reference(BaseModel):
    """What the reference reader extracted from a link in the request."""
    url: str
    ok: bool
    error: str = ""
    title: str = ""
    description: str = ""
    outline: list[str] = []
    colors: list[str] = []
    fonts: list[str] = []
    excerpt: str = ""


class ImageRef(BaseModel):
    id: int
    kind: Literal["reference", "screenshot"]
    label: str = ""
    media_type: str


class DesignReview(BaseModel):
    round: int
    score: int
    strengths: list[str] = []
    fixes: list[str] = []
    applied: bool = False  # the Coder made the fixes
    kept: bool = True      # False when the polished version broke a check and was reverted
    screenshots: list[int] = []


class ReadmeOut(BaseModel):
    readme: str


class QuestionOption(BaseModel):
    label: str = Field(description="A short answer the user can pick, under 60 characters.")
    recommended: bool = Field(description="True for exactly one option: the sensible default if the user does not answer.")


class ClarifyQuestion(BaseModel):
    question: str = Field(description="One short question in plain language, under 120 characters.")
    why: str = Field(description="Why the answer changes what gets built, in one short sentence.")
    options: list[QuestionOption] = Field(description="2 to 4 mutually exclusive answers.")


class ClarifyOut(BaseModel):
    questions: list[ClarifyQuestion] = Field(
        description="0 to 2 questions. Empty when the requirement is already clear enough to build.")


class Clarification(BaseModel):
    question: str
    answer: str
    auto: bool = False


# ---------------------------------------------------------------- verification

class FileCheck(BaseModel):
    status: Literal["passed", "failed", "unchecked"]
    tool: str = ""
    output: str = ""


class Issue(BaseModel):
    source: Literal["syntax", "contract", "test", "lint", "security", "spec", "quality", "runtime"]
    severity: Literal["error", "warning"]
    file: Optional[str] = None
    line: Optional[int] = None
    message: str
    test_id: Optional[str] = None


class TestCaseResult(BaseModel):
    __test__ = False  # stop pytest from collecting this model

    id: str
    file: str
    name: str
    outcome: Literal["passed", "failed", "error", "skipped"]
    message: str = ""
    details: str = ""


class TestRun(BaseModel):
    __test__ = False

    runner: str
    ran: bool
    cases: list[TestCaseResult] = []
    output: str = ""
    collection_error: bool = False


class Verification(BaseModel):
    syntax: dict[str, FileCheck] = {}
    issues: list[Issue] = []
    test_runs: list[TestRun] = []
    passed: bool = False
    tests_total: int = 0
    tests_passed: int = 0
    level: Literal["tested", "static_only"] = "static_only"
    summary: str = ""

    def score(self) -> tuple[int, int, int, int]:
        """Higher is better. Used to keep the best version across debug rounds."""
        syntax_ok = -sum(1 for c in self.syntax.values() if c.status == "failed")
        # Suite-level test problems (crash, nothing collected) rank below any failing test.
        suite_broken = sum(1 for i in self.issues if i.source == "test" and i.test_id is None)
        errors = -sum(1 for i in self.issues if i.severity == "error" and i.source != "test")
        warnings = -sum(1 for i in self.issues if i.severity == "warning")
        return (syntax_ok, errors, self.tests_passed - self.tests_total - 1000 * suite_broken, warnings)


# ---------------------------------------------------------------- run state

class DebugRound(BaseModel):
    round: int
    targeted_issues: int
    changed_files: list[str]
    disputes: list[str] = []
    score_before: list[int]
    score_after: Optional[list[int]] = None
    kept: bool = True


class Usage(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    by_model: dict[str, int] = {}


class ActivityEntry(BaseModel):
    ts: float = Field(default_factory=time.time)
    agent: str
    message: str


RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "error"]


class RunState(BaseModel):
    id: str
    mode: Literal["build", "iterate"] = "build"
    requirement: str
    project_id: Optional[str] = None
    status: RunStatus = "queued"
    phase: str = "queued"
    spec: Optional[Spec] = None
    triage: Optional[TriageOut] = None
    files: dict[str, str] = {}
    tests: dict[str, str] = {}
    verification: Optional[Verification] = None
    best_round: int = 0
    debug_rounds: list[DebugRound] = []
    disputes_used: int = 0
    ask_questions: bool = False
    clarifications: list[Clarification] = []
    references: list[Reference] = []
    images: list[ImageRef] = []
    design_reviews: list[DesignReview] = []
    user_notes: list[str] = []
    readme: str = ""
    activity: list[ActivityEntry] = []
    usage: Usage = Usage()
    error: Optional[str] = None
    project_dir: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    finished_at: Optional[float] = None


class Event(BaseModel):
    run_id: str
    seq: int
    ts: float
    type: str
    data: dict
