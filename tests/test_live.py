"""Live code streaming: answers reach the UI while they are written, are never stored,
and a retried attempt starts the live view over."""

import pytest

from codecrew import llm, orchestrator
from codecrew.context import RunContext
from codecrew.runs import RunManager
from codecrew.schemas import RunState
from codecrew.store import Store

from tests.test_pipeline_offline import FIXED, ScriptedProvider


class Streaming(ScriptedProvider):
    """Writes every answer to the live view in small pieces, as a real model would."""

    def text(self, model, system, user, role, images=None, live=None):
        completion = super().text(model, system, user, role)
        if live:
            for i in range(0, len(completion.text), 7):
                live.write(completion.text[i:i + 7])
        return completion


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(llm.LiveText, "INTERVAL", 0)  # send every piece at once in tests
    llm.health._stats.clear()


def _streams(events):
    """Rebuilds each call's live text from its delta events, as the browser does."""
    out: dict[int, str] = {}
    for e in events:
        if e.type != "llm_delta":
            continue
        d = e.data
        if d["reset"]:
            out[d["id"]] = ""
            continue
        text = out.get(d["id"], "")
        assert d["offset"] == len(text), "deltas must arrive in order without gaps"
        out[d["id"]] = text + d["text"]
    return out


def test_code_streams_live_and_matches_the_final_answer(monkeypatch):
    provider = Streaming([FIXED])
    monkeypatch.setattr(llm, "candidates", lambda role: [(provider, "scripted")])
    events = []
    state = orchestrator.run_sync(orchestrator.new_run("calculator"), sink=events.append)
    assert state.status == "succeeded", state.error

    roles = {e.data["id"]: e.data["role"] for e in events if e.type == "llm_start"}
    live = _streams(events)
    coder_text = next(t for i, t in live.items() if roles[i] == "coder")
    assert '<<<FILE path="calc.py">>>' in coder_text and coder_text.rstrip().endswith("<<<END FILE>>>")
    assert any(roles[i] == "debugger" for i in live)  # fixes stream too
    planner_calls = [i for i, r in roles.items() if r == "planner"]
    assert planner_calls and not any(i in live for i in planner_calls)  # structured plans do not stream


def test_a_retried_attempt_restarts_the_live_view(monkeypatch):
    calls = {"n": 0}

    class FlakyFirst(Streaming):
        def text(self, model, system, user, role, images=None, live=None):
            if role == "coder" and calls["n"] == 0:
                calls["n"] += 1
                if live:
                    live.write("<<<FILE path=\"calc.py\">>>\ndef half_writt")
                raise llm.TransientError("connection dropped mid-answer")
            return super().text(model, system, user, role, images, live)

    provider = FlakyFirst([FIXED])
    other = Streaming([FIXED])
    other.name = "other"
    monkeypatch.setattr(llm, "candidates", lambda role: [(provider, "a"), (other, "b")])
    events = []
    state = orchestrator.run_sync(orchestrator.new_run("calculator"), sink=events.append)
    assert state.status == "succeeded", state.error
    live = _streams(events)  # would fail on an offset gap if the reset were missing
    assert all("half_writt" not in t for t in live.values())


def test_live_deltas_are_not_stored(tmp_path):
    store = Store(tmp_path / "runs.db")
    manager = RunManager(store)
    state = RunState(id="live1", requirement="x")
    ctx = RunContext(state, sink=lambda e: manager._on_event(state, e))
    store.save_run(state)
    sink = llm.LiveText(ctx, 1, "coder")
    sink.INTERVAL = 0
    ctx.emit("llm_start", {"id": 1, "role": "coder"})
    sink.write("<<<FILE path=\"a.py\">>>\nx = 1\n")
    sink.close()
    ctx.emit("llm_end", {"id": 1, "role": "coder"})
    stored = [e.type for e in store.events_after("live1", 0)]
    assert stored == ["llm_start", "llm_end"]


def test_closed_or_cancelled_live_view_sends_nothing():
    events = []
    ctx = RunContext(RunState(id="r", requirement="x"), sink=events.append)
    sink = llm.LiveText(ctx, 1, "coder")
    sink.INTERVAL = 0
    ctx.cancel_event.set()
    sink.write("ignored")
    sink.close()
    sink.write("after close")
    assert not [e for e in events if e.type == "llm_delta"]
