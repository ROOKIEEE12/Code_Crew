"""End-to-end orchestrator tests with a scripted fake LLM (no network, no keys).

Everything except the LLM is real: the verifier runs real pytest in the
sandbox, so these tests prove the control flow reacts to actual results.
"""

import json

import pytest

from codecrew import llm, orchestrator, projects
from codecrew.config import settings
from codecrew.llm import Completion, Provider

SPEC = {
    "project_name": "safe-calc",
    "project_type": "library",
    "summary": "Arithmetic helpers.",
    "run_instructions": "python -c 'import calc'",
    "files": [{
        "path": "calc.py", "language": "python", "purpose": "Arithmetic.", "depends_on": [], "testable": True,
        "functions": [
            {"name": "add", "signature": "def add(a: float, b: float) -> float", "behavior": "Returns a + b.", "edge_cases": []},
            {"name": "divide", "signature": "def divide(a: float, b: float) -> float", "behavior": "Returns a / b.",
             "edge_cases": ["raises ValueError when b == 0"]},
        ],
    }],
    "acceptance_criteria": [
        {"id": "AC1", "description": "add(2, 3) == 5", "verification": "automated_test"},
        {"id": "AC2", "description": "divide(1, 0) raises ValueError", "verification": "automated_test"},
    ],
    "assumptions": [],
}

TESTS = '''<<<FILE path="tests/test_calc.py">>>
import pytest
from calc import add, divide

def test_ac1_add():
    assert add(2, 3) == 5

def test_ac2_divide_by_zero_raises():
    with pytest.raises(ValueError):
        divide(1, 0)

def test_divide():
    assert divide(6, 3) == 2
<<<END FILE>>>'''

BUGGY = '''<<<FILE path="calc.py">>>
def add(a, b):
    """Add."""
    return a + b


def divide(a, b):
    """Divide."""
    return a / b
<<<END FILE>>>'''

FIXED = '''The bug: divide lets ZeroDivisionError escape instead of ValueError.
<<<FILE path="calc.py">>>
def add(a, b):
    """Add."""
    return a + b


def divide(a, b):
    """Divide a by b; raises ValueError when b is zero."""
    if b == 0:
        raise ValueError("division by zero")
    return a / b
<<<END FILE>>>'''

WORSE = '''<<<FILE path="calc.py">>>
def add(a, b):
    return a - b


def divide(a, b):
    return a / b
<<<END FILE>>>'''

README = "# safe-calc\n\nArithmetic helpers. Run `python -m pytest tests`.\n"


class ScriptedProvider(Provider):
    name = "fake"

    def __init__(self, debugger_replies):
        self.debugger_replies = list(debugger_replies)
        self.calls = []

    def configured(self):
        return True

    def models_for(self, role):
        return ["scripted"]

    def text(self, model, system, user, role):
        self.calls.append(role)
        if role == "planner":
            reply = json.dumps(SPEC)
        elif role == "test_author":
            reply = TESTS
        elif role == "coder":
            reply = BUGGY
        elif role == "debugger":
            reply = self.debugger_replies.pop(0)
        elif role == "reviewer":
            reply = README
        else:
            raise AssertionError(role)
        return Completion(reply, model, 10, 10)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    object.__setattr__(settings, "output_dir", tmp_path)

    def install(debugger_replies):
        provider = ScriptedProvider(debugger_replies)
        monkeypatch.setattr(llm, "candidates", lambda role: [(provider, "scripted")])
        llm.health._stats.clear()
        return provider

    return install


def test_build_catches_bug_with_real_tests_and_debugs_it(fake):
    provider = fake([FIXED])
    events = []
    state = orchestrator.run_sync(orchestrator.new_run("calculator"), sink=events.append)

    assert state.status == "succeeded", state.error
    assert state.verification.passed and state.verification.tests_passed == 3
    # Tests came before code; exactly one debug round was needed.
    assert provider.calls.index("test_author") < provider.calls.index("coder")
    assert len(state.debug_rounds) == 1 and state.debug_rounds[0].kept
    assert "raise ValueError" in state.files["calc.py"]

    saved = projects.load(state.project_id)
    assert saved["spec"].project_name == "safe-calc"
    assert "tests/test_calc.py" in saved["tests"] and saved["readme"].startswith("# safe-calc")
    types = [e.type for e in events]
    assert types[-1] == "done" and "verification" in types and [e.seq for e in events] == sorted(e.seq for e in events)


def test_regressing_debug_round_is_reverted(fake):
    fake([WORSE, FIXED])
    state = orchestrator.run_sync(orchestrator.new_run("calculator"))

    assert state.status == "succeeded"
    first, second = state.debug_rounds
    assert not first.kept and second.kept
    assert "a + b" in state.files["calc.py"]


def test_unfixable_run_reports_failure_honestly(fake):
    object.__setattr__(settings, "max_debug_rounds", 2)
    try:
        fake([WORSE, WORSE])
        state = orchestrator.run_sync(orchestrator.new_run("calculator"))
    finally:
        object.__setattr__(settings, "max_debug_rounds", 4)

    assert state.status == "failed"
    assert not state.verification.passed
    assert state.verification.tests_passed == 2  # best version (the buggy original) is kept, not the worse one
    assert "a + b" in state.files["calc.py"]


def test_invalid_model_output_is_retried_not_accepted(fake, monkeypatch):
    provider = fake([FIXED])
    original = provider.text
    sent = {"planner": 0}

    def flaky(model, system, user, role):
        if role == "planner" and sent["planner"] == 0:
            sent["planner"] += 1
            bad = dict(SPEC, files=[dict(SPEC["files"][0], path="../../evil.py")])
            return Completion(json.dumps(bad), model, 1, 1)
        return original(model, system, user, role)

    monkeypatch.setattr(provider, "text", flaky)
    state = orchestrator.run_sync(orchestrator.new_run("calculator"))
    assert state.status == "succeeded"
    assert all(".." not in p for p in state.files)
