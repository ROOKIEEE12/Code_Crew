"""Run manager: starts orchestrator runs in worker threads, persists their
events, and fans them out to live SSE subscribers."""

from __future__ import annotations

import asyncio
import threading
from typing import AsyncIterator, Optional

from codecrew import orchestrator
from codecrew.context import RunContext
from codecrew.schemas import Event, RunState
from codecrew.store import Store

_PERSIST_ON = {"status", "phase", "spec", "triage", "verification", "debug_round", "readme", "done"}


class RunManager:
    def __init__(self, store: Store, max_concurrent: int = 2):
        self.store = store
        self._slots = threading.Semaphore(max_concurrent)
        self._lock = threading.Lock()
        self._contexts: dict[str, RunContext] = {}
        self._subscribers: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}

    def start(self, requirement: str, mode: str = "build", project_id: Optional[str] = None) -> RunState:
        state = orchestrator.new_run(requirement, mode=mode, project_id=project_id)
        ctx = RunContext(state, sink=lambda e: self._on_event(state, e))
        with self._lock:
            self._contexts[state.id] = ctx
        self.store.save_run(state)
        threading.Thread(target=self._work, args=(ctx,), name=f"run-{state.id}", daemon=True).start()
        return state

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

    def _on_event(self, state: RunState, event: Event) -> None:
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

    def get(self, run_id: str) -> Optional[RunState]:
        with self._lock:
            ctx = self._contexts.get(run_id)
        return ctx.state.model_copy(deep=True) if ctx else self.store.get_run(run_id)

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
            for event in self.store.events_after(run_id, after):
                last = event.seq
                yield event
                if event.type == "done":
                    return
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
