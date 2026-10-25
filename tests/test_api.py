"""API tests: run lifecycle over HTTP, SSE replay/resume, project endpoints."""

import json

import pytest
from fastapi.testclient import TestClient

from codecrew import llm
from codecrew.config import settings

from tests.test_pipeline_offline import FIXED, ScriptedProvider


@pytest.fixture
def client(monkeypatch, tmp_path):
    object.__setattr__(settings, "output_dir", tmp_path / "projects")
    object.__setattr__(settings, "db_path", tmp_path / "test.db")
    provider = ScriptedProvider([FIXED])
    monkeypatch.setattr(llm, "candidates", lambda role: [(provider, "scripted")])
    llm.health._stats.clear()
    import importlib

    import server

    importlib.reload(server)
    with TestClient(server.app) as c:
        yield c


def _events(client, run_id, after=0):
    out = []
    with client.stream("GET", f"/api/runs/{run_id}/events", params={"after": after}) as r:
        assert r.status_code == 200
        event_type = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                event_type = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                out.append((event_type, json.loads(line.split(":", 1)[1])))
    return out


def test_run_lifecycle_and_replay(client):
    r = client.post("/api/runs", json={"requirement": "calculator"})
    assert r.status_code == 201
    run_id = r.json()["id"]

    events = _events(client, run_id)
    types = [t for t, _ in events]
    assert types[-1] == "done" and events[-1][1]["status"] == "succeeded"
    assert {"spec", "file", "verification", "readme"} <= set(types)
    seqs = [d["seq"] for _, d in events]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))

    # Resume mid-stream: only later events are sent.
    resumed = _events(client, run_id, after=seqs[5])
    assert [d["seq"] for _, d in resumed] == seqs[6:]

    state = client.get(f"/api/runs/{run_id}").json()
    assert state["status"] == "succeeded" and state["verification"]["tests_passed"] == 3
    assert client.get("/api/runs").json()["runs"][0]["id"] == run_id

    project_id = state["project_id"]
    project = client.get(f"/api/projects/{project_id}").json()
    assert "calc.py" in project["files"] and project["spec"]["project_name"] == "safe-calc"
    assert client.get(f"/api/projects/{project_id}/download").headers["content-type"] == "application/zip"


def test_bad_inputs_rejected(client):
    assert client.post("/api/runs", json={"requirement": ""}).status_code == 422
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/projects/..%2f..%2fetc").status_code == 404
    assert client.post("/api/runs/nope/cancel").status_code == 409
