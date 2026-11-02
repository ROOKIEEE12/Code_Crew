"""Run manager: starts orchestrator runs in worker threads, persists their
events, and fans them out to live SSE subscribers."""

from __future__ import annotations

import asyncio
import threading
from typing import AsyncIterator, Optional

from codecrew import llm, orchestrator
from codecrew.context import RunContext
from codecrew.schemas import Event, Reference, RunState, Spec
from codecrew.store import Store

_PERSIST_ON = {"status", "phase", "spec", "triage", "file", "verification", "debug_round", "readme", "done", "answer", "steer",
               "resumed", "references", "image", "design_review"}

RESUMABLE = {"error", "cancelled"}

# Sent to live viewers only, never stored: code streaming in while a model writes it.
# Its final form arrives as a stored "file" event, so a replay loses nothing.
_TRANSIENT = {"llm_delta"}


class RunManager:
    def __init__(self, store: Store, max_concurrent: int = 2):
        self.store = store
        self._slots = threading.Semaphore(max_concurrent)
        self._lock = threading.Lock()
        self._contexts: dict[str, RunContext] = {}
        self._subscribers: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
        self._delete_when_stopped: set[str] = set()

    def start(self, requirement: str, mode: str = "build", project_id: Optional[str] = None,
              ask_questions: bool = False, images: Optional[list[tuple[str, bytes]]] = None) -> RunState:
        state = orchestrator.new_run(requirement, mode=mode, project_id=project_id, ask_questions=ask_questions)
        ctx = self._context(state)
        for i, (media_type, data) in enumerate(images or [], 1):
            ctx.save_image("reference", f"Your image {i}", media_type, data)
            ctx.reference_images.append((media_type, data))
        with self._lock:
            self._contexts[state.id] = ctx
        self.store.save_run(state)
        threading.Thread(target=self._work, args=(ctx,), name=f"run-{state.id}", daemon=True).start()
        return state

    def resume(self, run_id: str) -> Optional[RunState]:
        """Continues a stopped run (error or cancelled) from its saved progress:
        the plan, answers, instructions, locked tests and every file already
        written are kept; the run carries on from the first unfinished step."""
        if self.is_live(run_id):
            return None
        state = self.store.get_run(run_id)
        if not state or state.status not in RESUMABLE:
            return None
        events = self.store.events_after(run_id, 0)
        _restore_progress(state, events)
        llm.health.reset_cooldowns()  # the user asked to try again now
        previous = state.error
        state.status, state.phase, state.error, state.finished_at = "queued", "queued", None, None
        ctx = self._context(state, start_seq=events[-1].seq if events else 0)
        ctx.reference_images = self.store.images(run_id, "reference")
        with self._lock:
            self._contexts[state.id] = ctx
        ctx.emit("resumed", {"previous_error": previous, "files": sorted(state.files), "tests": sorted(state.tests),
                             "has_spec": state.spec is not None})
        ctx.step("Orchestrator", "Resuming: " + ", ".join(filter(None, [
            "plan kept" if state.spec else "",
            f"{len(state.tests)} test file(s) kept" if state.tests else "",
            f"{len(state.files)} file(s) kept" if state.files else "",
        ])) + "." if (state.spec or state.files) else "Resuming from the start.")
        threading.Thread(target=self._work, args=(ctx,), name=f"run-{state.id}", daemon=True).start()
        return state

    def _context(self, state: RunState, start_seq: int = 0) -> RunContext:
        ctx = RunContext(state, sink=lambda e: self._on_event(state, e), start_seq=start_seq)
        ctx.image_store = lambda kind, label, media_type, data: self.store.add_image(state.id, kind, label, media_type, data)
        return ctx

    def _work(self, ctx: RunContext) -> None:
        with self._slots:
            if ctx.cancel_event.is_set():
                ctx.state.status, ctx.state.phase = "cancelled", "done"
                ctx.emit("done", {"status": "cancelled", "error": None, "project_id": None, "summary": None,
                                  "usage": ctx.state.usage.model_dump()})
            else:
                orchestrator.Orchestrator(ctx).run()
        self.store.save_run(ctx.state)
        with self._lock:
            self._contexts.pop(ctx.run_id, None)
            delete = ctx.run_id in self._delete_when_stopped
            self._delete_when_stopped.discard(ctx.run_id)
        if delete:
            self.store.delete_run(ctx.run_id)

    def _on_event(self, state: RunState, event: Event) -> None:
        if event.type not in _TRANSIENT:
            self.store.add_event(event)
        if event.type in _PERSIST_ON:
            self.store.save_run(state)
        with self._lock:
            subs = list(self._subscribers.get(event.run_id, []))
        for loop, queue in subs:
            loop.call_soon_threadsafe(queue.put_nowait, event)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            ctx = self._contexts.get(run_id)
        if not ctx:
            return False
        ctx.cancel_event.set()
        return True

    def delete(self, run_id: str) -> bool:
        """Removes a run and its history. A run still working is stopped first and
        removed as soon as it has stopped. Projects it saved are kept."""
        with self._lock:
            ctx = self._contexts.get(run_id)
            if ctx:
                self._delete_when_stopped.add(run_id)
                ctx.cancel_event.set()
                return True
        return self.store.delete_run(run_id)

    def _live(self, run_id: str) -> Optional[RunContext]:
        with self._lock:
            return self._contexts.get(run_id)

    def answer(self, run_id: str, question_id: str, choice: int) -> bool:
        ctx = self._live(run_id)
        return bool(ctx and ctx.answer(question_id, choice))

    def add_note(self, run_id: str, text: str) -> Optional[str]:
        ctx = self._live(run_id)
        return ctx.add_note(text) if ctx else None

    def get(self, run_id: str) -> Optional[RunState]:
        with self._lock:
            ctx = self._contexts.get(run_id)
        return ctx.state.model_copy(deep=True) if ctx else self.store.get_run(run_id)

    def project_busy(self, project_id: str) -> bool:
        """True while a run is changing this project."""
        with self._lock:
            return any(c.state.project_id == project_id for c in self._contexts.values())

    def is_live(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._contexts

    async def stream(self, run_id: str, after: int = 0) -> AsyncIterator[Event]:
        """Replays stored events after `after`, then follows live events until 'done'."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Event] = asyncio.Queue()
        entry = (loop, queue)
        with self._lock:
            self._subscribers.setdefault(run_id, []).append(entry)
        try:
            last = after
            # Replay everything stored. A resumed run can have an old "done" followed
            # by newer events, so the replay never stops early at a "done".
            for event in self.store.events_after(run_id, after):
                last = event.seq
                yield event
            if not self.is_live(run_id):
                for event in self.store.events_after(run_id, last):
                    yield event
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    if not self.is_live(run_id):
                        for event in self.store.events_after(run_id, last):
                            yield event
                        return
                    yield Event(run_id=run_id, seq=last, ts=0, type="ping", data={})
                    continue
                if event.seq <= last:
                    continue  # already replayed from the store
                last = event.seq
                yield event
                if event.type == "done":
                    return
        finally:
            with self._lock:
                subs = self._subscribers.get(run_id, [])
                if entry in subs:
                    subs.remove(entry)
                if not subs:
                    self._subscribers.pop(run_id, None)


def _restore_progress(state: RunState, events: list[Event]) -> None:
    """Rebuilds the work saved in a run's event history into its state."""
    for e in events:
        d = e.data
        if e.type == "spec":
            state.spec = Spec.model_validate(d)
        elif e.type == "file" and d.get("path") and d.get("content") is not None:
            target = state.tests if d.get("kind") == "test" else state.files
            target[d["path"]] = d["content"]
        elif e.type == "readme":
            state.readme = d.get("content", "")
        elif e.type == "references":
            state.references = [Reference.model_validate(r) for r in d.get("references", [])]
    if state.mode == "iterate":
        # A change request re-runs from the saved project; partial edits are not reused.
        state.spec, state.files, state.tests, state.triage = None, {}, {}, None
