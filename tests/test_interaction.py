"""Live interaction: Planner questions, mid-run instructions, thinking/tool events.

Uses the scripted LLM from test_pipeline_offline; the verifier and tests are real.
"""

import json
import threading
import time

import pytest

from codecrew import llm, orchestrator
from codecrew.config import settings
from codecrew.context import RunContext
from codecrew.llm import Completion

from tests.test_pipeline_offline import FIXED, ScriptedProvider

QUESTIONS = {"questions": [{
    "question": "What should divide(1, 0) do?",
    "why": "It decides what the tests expect.",
    "options": [{"label": "Raise an error", "recommended": True}, {"label": "Return 0", "recommended": False}],
}]}


class AskingProvider(ScriptedProvider):
    def __init__(self, debugger_replies):
        super().__init__(debugger_replies)
        self.prompts: dict[str, list[str]] = {}

    def text(self, model, system, user, role):
        self.prompts.setdefault(role, []).append(user)
        if role == "clarifier":
            self.calls.append(role)
            return Completion(json.dumps(QUESTIONS), model, 5, 5)
        return super().text(model, system, user, role)


@pytest.fixture
def provider(monkeypatch, tmp_path):
    object.__setattr__(settings, "output_dir", tmp_path)
    p = AskingProvider([FIXED])
    monkeypatch.setattr(llm, "candidates", lambda role: [(p, "scripted")])
    llm.health._stats.clear()
    return p


def _run_in_thread(ctx):
    t = threading.Thread(target=lambda: orchestrator.Orchestrator(ctx).run())
    t.start()
    return t


def _wait_for(events, type_, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        for e in list(events):
            if e.type == type_:
                return e
        time.sleep(0.05)
    raise AssertionError(f"no {type_} event")


def test_user_answer_reaches_the_planner(provider):
    events = []
    ctx = RunContext(orchestrator.new_run("calculator", ask_questions=True), sink=events.append)
    t = _run_in_thread(ctx)
    q = _wait_for(events, "question")
    assert q.data["options"] == ["Raise an error", "Return 0"] and q.data["recommended"] == 0
    assert ctx.answer(q.data["id"], 1)
    assert not ctx.answer(q.data["id"], 0)  # a question is answered once
    t.join(timeout=120)

    answer = _wait_for(events, "answer")
    assert answer.data == {"id": q.data["id"], "choice": 1, "label": "Return 0", "auto": False}
    assert "What should divide(1, 0) do? -> Return 0" in provider.prompts["planner"][0]
    assert ctx.state.clarifications[0].answer == "Return 0" and not ctx.state.clarifications[0].auto
    assert ctx.state.status == "succeeded"


def test_unanswered_question_uses_the_recommended_option(provider):
    object.__setattr__(settings, "question_timeout_sec", 0.3)
    try:
        state = orchestrator.run_sync(orchestrator.new_run("calculator", ask_questions=True))
    finally:
        object.__setattr__(settings, "question_timeout_sec", 60)
    assert state.clarifications[0].answer == "Raise an error" and state.clarifications[0].auto
    assert "recommended default" in provider.prompts["planner"][0]


def test_questions_are_off_by_default_and_for_long_requests(provider):
    orchestrator.run_sync(orchestrator.new_run("calculator"))
    orchestrator.run_sync(orchestrator.new_run("calculator " + "x" * settings.clarify_max_chars, ask_questions=True))
    assert "clarifier" not in provider.calls


def test_instruction_added_mid_run_reaches_the_next_agent(provider):
    events = []
    ctx = RunContext(orchestrator.new_run("calculator", ask_questions=True), sink=events.append)
    t = _run_in_thread(ctx)
    q = _wait_for(events, "question")  # the run is paused on the question
    ctx.add_note("Use type hints everywhere")
    ctx.answer(q.data["id"], 0)
    t.join(timeout=120)

    assert "Use type hints everywhere" in provider.prompts["planner"][0]
    assert "Use type hints everywhere" in provider.prompts["coder"][0]
    delivered = [e for e in events if e.type == "steer_delivered"]
    assert len(delivered) == 1 and delivered[0].data["agent"] == "Planner"
    assert ctx.state.user_notes == ["Use type hints everywhere"]


def test_thinking_tool_and_diagnosis_events(provider):
    provider.debugger_replies = ["- divide lets ZeroDivisionError escape instead of ValueError\n" + FIXED]
    events = []
    state = orchestrator.run_sync(orchestrator.new_run("calculator"), sink=events.append)
    assert state.status == "succeeded"

    starts = [e for e in events if e.type == "llm_start"]
    ends = {e.data["id"]: e.data for e in events if e.type == "llm_end"}
    assert starts and all(ends[s.data["id"]]["ok"] for s in starts)
    assert all(ends[s.data["id"]]["role"] == s.data["role"] for s in starts)

    tools = [e.data for e in events if e.type == "tool"]
    finished = {t["id"]: t for t in tools if t["status"] != "running"}
    assert finished["v1-pytest"]["status"] == "bad" and "1 failed" in finished["v1-pytest"]["result"]
    assert finished["v2-pytest"]["status"] == "ok" and finished["v2-pytest"]["result"] == "3 passed"

    thoughts = {e.data["agent"]: e.data["points"] for e in events if e.type == "thought"}
    assert thoughts["Debugger"] == ["divide lets ZeroDivisionError escape instead of ValueError"]
    assert any("calc.py" in p for p in thoughts["Planner"])
