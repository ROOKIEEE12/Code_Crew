"""Typed data contracts shared by every agent, the orchestrator, the API and
(via OpenAPI) the Next.js frontend.

Models whose name ends in `Out` are what an LLM is asked to produce; they
keep every field required so structured-output schemas stay strict.
"""

from __future__ import annotations

import time
from typing import Literal, Optional

from pydantic import BaseModel, Field

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


class SpecOut(BaseModel):
    project_name: str = Field(description="short-kebab-case-name")
    project_type: Literal["script", "cli_tool", "web_app", "backend_api", "library", "other"]
    summary: str
    run_instructions: str = Field(description="Exact command or action to run/open the project.")
    files: list[FileSpec]
    acceptance_criteria: list[AcceptanceCriterion]
    assumptions: list[str] = Field(description="Ambiguities in the request and how they were resolved.")


Spec = SpecOut


class TriageOut(BaseModel):
    intent: Literal["feature", "bugfix", "styling", "documentation", "refactor"]
    explanation: str
    files: list[FileSpec] = Field(description="Only the files to create or modify, with their updated spec.")
    new_acceptance_criteria: list[AcceptanceCriterion]
    instructions: str = Field(description="Precise instructions for the coder.")
    update_readme: bool


class ReadmeOut(BaseModel):
    readme: str


# ---------------------------------------------------------------- verification

class FileCheck(BaseModel):
    status: Literal["passed", "failed", "unchecked"]
    tool: str = ""
    output: str = ""


class Issue(BaseModel):
    source: Literal["syntax", "contract", "test", "lint", "security", "spec"]
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
