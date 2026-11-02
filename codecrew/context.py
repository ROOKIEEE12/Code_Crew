"""Per-run context: event emission, activity log, cancellation, usage,
questions to the user, and instructions the user adds mid-run.

One RunContext exists per run and is passed explicitly to every agent, so
concurrent runs never share callbacks or counters.
"""

from __future__ import annotations

import itertools
import threading
import time
import uuid
from typing import Callable, Optional

from codecrew.schemas import ActivityEntry, Event, ImageRef, RunState

EventSink = Callable[[Event], None]

# Display name of the agent behind each LLM role.
ROLE_AGENT = {
    "clarifier": "Planner",
    "planner": "Planner",
    "triage": "Orchestrator",
    "test_author": "Test Author",
    "coder": "Coder",
    "debugger": "Debugger",
    "reviewer": "Reviewer",
    "design_review": "Reviewer",
}


class RunCancelled(Exception):
    pass


class _Question:
    def __init__(self, n_options: int):
        self.n_options = n_options
        self.choice: Optional[int] = None
        self.ready = threading.Event()


class RunContext:
    def __init__(self, state: RunState, sink: Optional[EventSink] = None, log: Optional[Callable[[str], None]] = None,
                 start_seq: int = 0):
        self.state = state
        self._sink = sink
        self._log = log
        self._lock = threading.Lock()
        self._seq = start_seq  # a resumed run continues its stored event sequence
        self._strikes: dict[str, int] = {}
        self._call_ids = itertools.count(1)
        self._questions: dict[str, _Question] = {}
        self._notes: list[tuple[str, str]] = []  # (id, text)
        self._delivered: set[str] = set()
        self.cancel_event = threading.Event()
        # Images the user attached plus screenshots of reference pages: (media type, bytes).
        self.reference_images: list[tuple[str, bytes]] = []
        # Persists an image and returns its id; None when nothing stores images (CLI, eval).
        self.image_store: Optional[Callable[[str, str, str, bytes], int]] = None

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

    def save_image(self, kind: str, label: str, media_type: str, data: bytes) -> Optional[ImageRef]:
        """Stores an image for the UI; returns its reference, or None if images are not stored."""
        if not self.image_store:
            return None
        ref = ImageRef(id=self.image_store(kind, label, media_type, data), kind=kind, label=label, media_type=media_type)
        with self._lock:
            self.state.images.append(ref)
        return ref

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise RunCancelled()

    def strike(self, model_key: str) -> int:
        """Records a timeout or repeated unusable output; returns the model's strike count."""
        with self._lock:
            self._strikes[model_key] = self._strikes.get(model_key, 0) + 1
            return self._strikes[model_key]

    def is_benched(self, model_key: str) -> bool:
        from codecrew.config import settings

        with self._lock:
            return self._strikes.get(model_key, 0) >= settings.model_strikes

    def next_call_id(self) -> int:
        return next(self._call_ids)

    def thought(self, agent: str, points: list[str]) -> None:
        """Short, factual notes on an agent's reasoning (shown under "Thought for Ns")."""
        points = [p.strip()[:240] for p in points if p and p.strip()][:5]
        if points:
            self.emit("thought", {"agent": agent, "points": points})

    # ------------------------------------------------------------ questions

    def ask(self, agent: str, question: str, why: str, options: list[str], recommended: int,
            timeout: float, interactive: bool = True) -> tuple[int, bool]:
        """Asks the user a multiple-choice question and blocks until it is
        answered, the timeout passes, or the run is cancelled. Returns
        (option index, chosen automatically)."""
        qid = uuid.uuid4().hex[:8]
        q = _Question(len(options))
        with self._lock:
            self._questions[qid] = q
        self.emit("question", {"id": qid, "agent": agent, "question": question, "why": why, "options": options,
                               "recommended": recommended, "timeout_sec": timeout if interactive else 0})
        deadline = time.monotonic() + (timeout if interactive else 0)
        while not q.ready.wait(timeout=0.25):
            self.check_cancelled()
            if time.monotonic() >= deadline:
                break
        with self._lock:
            self._questions.pop(qid, None)
            choice, auto = (q.choice, False) if q.choice is not None else (recommended, True)
        self.emit("answer", {"id": qid, "choice": choice, "label": options[choice], "auto": auto})
        return choice, auto

    def answer(self, question_id: str, choice: int) -> bool:
        with self._lock:
            q = self._questions.get(question_id)
            if not q or q.ready.is_set() or not 0 <= choice < q.n_options:
                return False
            q.choice = choice
            q.ready.set()
        return True

    # ------------------------------------------------------------ steering

    def add_note(self, text: str) -> str:
        note_id = uuid.uuid4().hex[:8]
        with self._lock:
            self._notes.append((note_id, text))
            self.state.user_notes.append(text)
        self.emit("steer", {"id": note_id, "text": text})
        return note_id

    def notes_for(self, role: str) -> str:
        """Every instruction the user has added so far, formatted for a prompt.
        The first agent to receive a note is reported back to the user."""
        with self._lock:
            notes = list(self._notes)
            fresh = [nid for nid, _ in notes if nid not in self._delivered]
            self._delivered.update(fresh)
        if fresh:
            self.emit("steer_delivered", {"ids": fresh, "agent": ROLE_AGENT.get(role, role)})
        if not notes:
            return ""
        lines = "\n".join(f"- {text}" for _, text in notes)
        return ("\n\n---\nInstructions the user added while the team was working. Follow them, "
                "unless one contradicts the specification or the locked tests:\n" + lines)
