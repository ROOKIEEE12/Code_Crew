"""Per-run context: event emission, activity log, cancellation, usage.

One RunContext exists per run and is passed explicitly to every agent, so
concurrent runs never share callbacks or counters.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from codecrew.schemas import ActivityEntry, Event, RunState

EventSink = Callable[[Event], None]


class RunCancelled(Exception):
    pass


class RunContext:
    def __init__(self, state: RunState, sink: Optional[EventSink] = None, log: Optional[Callable[[str], None]] = None):
        self.state = state
        self._sink = sink
        self._log = log
        self._lock = threading.Lock()
        self._seq = 0
        self.cancel_event = threading.Event()

    @property
    def run_id(self) -> str:
        return self.state.id

    def emit(self, type_: str, data: dict | None = None) -> None:
        with self._lock:
            self._seq += 1
            event = Event(run_id=self.state.id, seq=self._seq, ts=time.time(), type=type_, data=data or {})
        if self._sink:
            self._sink(event)

    def step(self, agent: str, message: str) -> None:
        entry = ActivityEntry(agent=agent, message=message)
        with self._lock:
            self.state.activity.append(entry)
        if self._log:
            self._log(f"[{agent}] {message}")
        self.emit("activity", entry.model_dump())

    def phase(self, name: str, detail: str = "") -> None:
        self.state.phase = name
        self.emit("phase", {"phase": name, "detail": detail})

    def record_usage(self, model: str, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            u = self.state.usage
            u.calls += 1
            u.input_tokens += input_tokens
            u.output_tokens += output_tokens
            u.by_model[model] = u.by_model.get(model, 0) + 1
            snapshot = u.model_dump()
        self.emit("usage", snapshot)

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise RunCancelled()
