"""Resilience: hung models, Stop during a call, setting aside bad models, waiting
out shared rate limits, and resuming a stopped run from its saved progress.
Scripted LLM, real verifier."""

import json
import threading
import time

import pytest

from codecrew import llm, orchestrator
from codecrew.config import settings
from codecrew.context import RunContext
from codecrew.llm import Completion, Provider
from codecrew.runs import RunManager
from codecrew.store import Store

from tests.test_pipeline_offline import FIXED, SPEC, ScriptedProvider


@pytest.fixture(autouse=True)
def _isolated(tmp_path):
    object.__setattr__(settings, "output_dir", tmp_path / "projects")
    llm.health._stats.clear()
    yield
    llm.health._stats.clear()


@pytest.fixture
def short_timeout():
    old = settings.llm_timeout_sec
    object.__setattr__(settings, "llm_timeout_sec", 1)
    yield
    object.__setattr__(settings, "llm_timeout_sec", old)


class Hangs(Provider):
    """A model whose request never comes back (like the stuck Gemini call)."""
    name = "hangs"

    def __init__(self):
        self.calls = 0

    def configured(self):
        return True

    def models_for(self, role):
        return ["frozen"]

    def text(self, model, system, user, role):
        self.calls += 1
        threading.Event().wait(60)
        raise AssertionError("should have been abandoned")


class Garbage(Provider):
    name = "garbage"

    def __init__(self):
        self.calls = 0

    def configured(self):
        return True

    def models_for(self, role):
        return ["junk"]

    def text(self, model, system, user, role):
        self.calls += 1
        return Completion("no file blocks here", model, 1, 1)


def test_hung_model_is_abandoned_and_the_next_one_finishes(monkeypatch, short_timeout):
    hung, good = Hangs(), ScriptedProvider([FIXED])
    monkeypatch.setattr(llm, "candidates", lambda role: [(hung, "frozen"), (good, "scripted")])
    started = time.monotonic()
    state = orchestrator.run_sync(orchestrator.new_run("calculator"))
    assert state.status == "succeeded", state.error
    # after one timeout it cools down, so later calls skip it instead of waiting again
    assert hung.calls == 1
    assert time.monotonic() - started < 60


def test_stop_works_while_a_call_is_in_flight(monkeypatch):
    hung = Hangs()
    monkeypatch.setattr(llm, "candidates", lambda role: [(hung, "frozen")])
    ctx = RunContext(orchestrator.new_run("calculator"))
    t = threading.Thread(target=lambda: orchestrator.Orchestrator(ctx).run())
    t.start()
    while hung.calls == 0:
        time.sleep(0.05)
    stopped_at = time.monotonic()
    ctx.cancel_event.set()
    t.join(timeout=10)
    assert not t.is_alive() and ctx.state.status == "cancelled"
    assert time.monotonic() - stopped_at < 3


def test_model_with_unusable_output_is_set_aside(monkeypatch):
    junk, good = Garbage(), ScriptedProvider([FIXED])
    monkeypatch.setattr(llm, "candidates", lambda role: [(junk, "junk"), (good, "scripted")])
    state = orchestrator.run_sync(orchestrator.new_run("calculator"))
    assert state.status == "succeeded"
    # one try + one corrected retry, then it is set aside instead of being retried for every call
    assert junk.calls == 2


def test_strikes_bench_a_model_for_the_rest_of_the_run():
    ctx = RunContext(orchestrator.new_run("x"))
    assert not ctx.is_benched("p:m")
    for _ in range(settings.model_strikes):
        ctx.strike("p:m")
    assert ctx.is_benched("p:m") and not ctx.is_benched("p:other")


def test_waits_for_a_rate_limited_model_instead_of_failing(monkeypatch):
    class LimitedOnce(ScriptedProvider):
        def __init__(self, replies):
            super().__init__(replies)
            self.limited = False

        def text(self, model, system, user, role):
            if role == "planner" and not self.limited:
                self.limited = True
                raise llm.TransientError("429 rate limited")
            return super().text(model, system, user, role)

    provider = LimitedOnce([FIXED])
    monkeypatch.setattr(llm, "candidates", lambda role: [(provider, "scripted")])
    monkeypatch.setattr(llm.health, "failure",
                        lambda key, err, cooldown: llm.ModelHealth.failure(llm.health, key, err, min(cooldown, 1)))
    state = orchestrator.run_sync(orchestrator.new_run("calculator"))
    assert state.status == "succeeded", state.error
    assert any("busy or rate-limited" in a.message for a in state.activity)


WAVE_SPEC = dict(SPEC, files=[SPEC["files"][0]] + [
    {"path": f"page{i}.html", "language": "html", "purpose": "Page.", "depends_on": [], "functions": [], "testable": False}
    for i in range(7)
], design={
    "style": "Plain.", "typography": "System fonts.", "interactions": [], "responsive": "Stacks.", "reference_notes": "",
    "palette": [{"name": n, "hex": h, "usage": n} for n, h in (("bg", "#ffffff"), ("text", "#111111"), ("accent", "#3355ff"), ("muted", "#666666"))],
    "sections": [{"id": f"s{i}", "page": f"page{i}.html", "name": f"Page {i}", "content": "Text."} for i in range(7)],
})


class Waves(ScriptedProvider):
    """Planner returns 8 files (so the Coder works in parallel); page0 is slow."""

    def text(self, model, system, user, role):
        if role == "planner":
            return Completion(json.dumps(WAVE_SPEC), model, 1, 1)
        if role == "coder":
            assigned = user.split("Your assigned files: ", 1)[1].split("\n", 1)[0].split(", ")
            if assigned != ["calc.py"]:
                if "page0.html" in assigned:
                    time.sleep(1.5)
                blocks = [f'<<<FILE path="{p}">>>\n<!doctype html><title>{p}</title>\n<<<END FILE>>>' for p in assigned]
                return Completion("\n".join(blocks), model, 1, 1)
        return super().text(model, system, user, role)


def test_parallel_files_are_saved_as_soon_as_each_is_ready(monkeypatch):
    provider = Waves([FIXED])
    monkeypatch.setattr(llm, "candidates", lambda role: [(provider, "scripted")])
    events = []
    orchestrator.run_sync(orchestrator.new_run("site"), sink=events.append)
    order = [e.data["path"] for e in events if e.type == "file" and e.data["kind"] == "source" and e.data["by"] == "Coder"]
    pages = [p for p in order if p.startswith("page")]
    assert len(pages) == 7 and pages[-1] == "page0.html"  # the slow one no longer blocks the rest


def test_stopped_run_resumes_from_saved_progress(monkeypatch, tmp_path):
    class CoderBreaks(ScriptedProvider):
        def text(self, model, system, user, role):
            if role == "coder":
                self.calls.append(role)
                raise llm.PermanentError("quota exhausted")
            return super().text(model, system, user, role)

    broken = CoderBreaks([FIXED])
    monkeypatch.setattr(llm, "candidates", lambda role: [(broken, "scripted")])
    store = Store(tmp_path / "runs.db")
    manager = RunManager(store)
    run = manager.start("calculator")
    while manager.is_live(run.id):
        time.sleep(0.05)
    failed = store.get_run(run.id)
    assert failed.status == "error" and "quota" in failed.error

    # The model is still cooling down from the failure; Resume must give it a fresh chance.
    working = ScriptedProvider([FIXED])
    monkeypatch.setattr(llm, "candidates", lambda role: [(working, "scripted")])
    assert manager.resume(run.id) is not None
    assert manager.resume(run.id) is None  # cannot resume a run that is already running
    while manager.is_live(run.id):
        time.sleep(0.05)

    done = store.get_run(run.id)
    assert done.status == "succeeded", done.error
    assert "planner" not in working.calls and "test_author" not in working.calls  # plan and tests were kept
    assert working.calls.count("coder") == 1
    events = store.events_after(run.id, 0)
    seqs = [e.seq for e in events]
    assert seqs == sorted(set(seqs))  # the resumed run continued the same event stream
    assert [e.type for e in events].count("resumed") == 1


def test_run_interrupted_by_a_restart_can_be_resumed(monkeypatch, tmp_path):
    """Like the stuck build: the server died mid-run, leaving it 'running' in the DB."""
    provider = ScriptedProvider([FIXED])
    monkeypatch.setattr(llm, "candidates", lambda role: [(provider, "scripted")])
    store = Store(tmp_path / "runs.db")
    events = []
    state = orchestrator.new_run("calculator")
    ctx = RunContext(state, sink=lambda e: (store.add_event(e), events.append(e)))
    orch = orchestrator.Orchestrator(ctx)
    orch.plan({})
    orch.write_tests({})
    state.status = "running"
    store.save_run(state)  # the process "dies" here

    assert Store(tmp_path / "runs.db").mark_interrupted() == 1
    manager = RunManager(store)
    calls_before = list(provider.calls)
    assert manager.resume(state.id) is not None
    while manager.is_live(state.id):
        time.sleep(0.05)
    done = store.get_run(state.id)
    assert done.status == "succeeded", done.error
    new_calls = provider.calls[len(calls_before):]
    assert "planner" not in new_calls and "test_author" not in new_calls


class StreamsThenHangs(Provider):
    """Streams a few characters, stalls past the watchdog, then keeps streaming:
    a call the run has already given up on."""
    name = "stalls"

    def __init__(self):
        self.resume = threading.Event()
        self.finished = threading.Event()

    def configured(self):
        return True

    def models_for(self, role):
        return ["slow"]

    def text(self, model, system, user, role, live=None):
        live.write("OLD-")
        self.resume.wait(30)
        for _ in range(5):
            live.write("STALE")
            time.sleep(0.35)  # past LiveText.INTERVAL, so every piece is flushed
        self.finished.set()
        return Completion("too late", model, 1, 1)


class StreamsNew(Provider):
    name = "streams"

    def __init__(self, stalled):
        self.stalled = stalled

    def configured(self):
        return True

    def models_for(self, role):
        return ["fresh"]

    def text(self, model, system, user, role, live=None):
        self.stalled.resume.set()  # the abandoned call wakes up while this one streams
        for piece in ("NEW-", "1", "2", "3"):
            live.write(piece)
            time.sleep(0.4)
        self.stalled.finished.wait(10)
        return Completion("ok", model, 1, 1)


def test_an_abandoned_call_does_not_write_into_the_retrys_live_view(monkeypatch, short_timeout):
    stalled = StreamsThenHangs()
    monkeypatch.setattr(llm, "candidates", lambda role: [(stalled, "slow"), (StreamsNew(stalled), "fresh")])
    events = []
    ctx = RunContext(orchestrator.new_run("x"), sink=events.append)
    assert llm.call_text(ctx, "coder", "s", "u", parse=lambda t: t) == "ok"

    text: dict[int, str] = {}
    for e in events:
        if e.type == "llm_delta":
            d = e.data
            text[d["attempt"]] = "" if d["reset"] else text.get(d["attempt"], "") + d["text"]
    assert text[max(text)] == "NEW-123"
