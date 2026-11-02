"""SQLite persistence for runs and their event streams.

Every event is stored with its sequence number, so a client that
disconnects can resume with Last-Event-ID and nothing is lost; finished
runs stay browsable after a server restart.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from codecrew.schemas import Event, RunState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    requirement TEXT NOT NULL,
    project_id TEXT,
    status TEXT NOT NULL,
    phase TEXT NOT NULL,
    created_at REAL NOT NULL,
    finished_at REAL,
    state_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    ts REAL NOT NULL,
    type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE INDEX IF NOT EXISTS runs_created ON runs(created_at DESC);
CREATE TABLE IF NOT EXISTS run_images (
    run_id TEXT NOT NULL,
    id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    media_type TEXT NOT NULL,
    data BLOB NOT NULL,
    PRIMARY KEY (run_id, id)
);
"""


class Store:
    def __init__(self, path: Path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def save_run(self, s: RunState) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO runs (id, mode, requirement, project_id, status, phase, created_at, finished_at, state_json) "
                "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id, "
                "status=excluded.status, phase=excluded.phase, finished_at=excluded.finished_at, state_json=excluded.state_json",
                (s.id, s.mode, s.requirement, s.project_id, s.status, s.phase, s.created_at, s.finished_at, s.model_dump_json()),
            )
            self._db.commit()

    def add_event(self, e: Event) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO events (run_id, seq, ts, type, data_json) VALUES (?,?,?,?,?)",
                (e.run_id, e.seq, e.ts, e.type, json.dumps(e.data)),
            )
            self._db.commit()

    def events_after(self, run_id: str, after: int) -> list[Event]:
        with self._lock:
            rows = self._db.execute(
                "SELECT seq, ts, type, data_json FROM events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after)
            ).fetchall()
        return [Event(run_id=run_id, seq=r[0], ts=r[1], type=r[2], data=json.loads(r[3])) for r in rows]

    def get_run(self, run_id: str) -> Optional[RunState]:
        with self._lock:
            row = self._db.execute("SELECT state_json FROM runs WHERE id=?", (run_id,)).fetchone()
        return RunState.model_validate_json(row[0]) if row else None

    def list_runs(self, limit: int = 50, project_id: Optional[str] = None) -> list[dict]:
        sql = "SELECT id, mode, requirement, project_id, status, phase, created_at, finished_at FROM runs"
        args: tuple = ()
        if project_id:
            sql += " WHERE project_id=?"
            args = (project_id,)
        sql += " ORDER BY created_at DESC LIMIT ?"
        with self._lock:
            rows = self._db.execute(sql, (*args, limit)).fetchall()
        keys = ("id", "mode", "requirement", "project_id", "status", "phase", "created_at", "finished_at")
        return [dict(zip(keys, r)) for r in rows]

    def add_image(self, run_id: str, kind: str, label: str, media_type: str, data: bytes) -> int:
        with self._lock:
            row = self._db.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM run_images WHERE run_id=?", (run_id,)).fetchone()
            self._db.execute("INSERT INTO run_images (run_id, id, kind, label, media_type, data) VALUES (?,?,?,?,?,?)",
                             (run_id, row[0], kind, label, media_type, data))
            self._db.commit()
        return row[0]

    def get_image(self, run_id: str, image_id: int) -> Optional[tuple[str, bytes]]:
        with self._lock:
            row = self._db.execute("SELECT media_type, data FROM run_images WHERE run_id=? AND id=?",
                                   (run_id, image_id)).fetchone()
        return (row[0], bytes(row[1])) if row else None

    def images(self, run_id: str, kind: str) -> list[tuple[str, bytes]]:
        with self._lock:
            rows = self._db.execute("SELECT media_type, data FROM run_images WHERE run_id=? AND kind=? ORDER BY id",
                                    (run_id, kind)).fetchall()
        return [(r[0], bytes(r[1])) for r in rows]

    def delete_run(self, run_id: str) -> bool:
        with self._lock:
            self._db.execute("DELETE FROM events WHERE run_id=?", (run_id,))
            self._db.execute("DELETE FROM run_images WHERE run_id=?", (run_id,))
            gone = self._db.execute("DELETE FROM runs WHERE id=?", (run_id,)).rowcount
            self._db.commit()
        return bool(gone)

    def mark_interrupted(self) -> int:
        """Runs left 'running'/'queued' by a previous process cannot resume."""
        with self._lock:
            rows = self._db.execute("SELECT state_json FROM runs WHERE status IN ('running','queued')").fetchall()
        for (raw,) in rows:
            s = RunState.model_validate_json(raw)
            s.status, s.phase, s.finished_at = "error", "done", time.time()
            s.error = "Interrupted: the server stopped while this run was in progress."
            self.save_run(s)
        return len(rows)
