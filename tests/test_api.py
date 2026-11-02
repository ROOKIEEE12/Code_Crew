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
    assert out and out[-1][0] == "end"  # the stream always closes with "end" so browsers stop reconnecting
    return [e for e in out if e[0] != "end"]


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


def test_answer_and_message_need_a_live_run(client):
    run_id = client.post("/api/runs", json={"requirement": "calculator"}).json()["id"]
    _events(client, run_id)  # wait until it finishes
    assert client.post(f"/api/runs/{run_id}/answer", json={"question_id": "abc", "choice": 0}).status_code == 409
    assert client.post(f"/api/runs/{run_id}/messages", json={"text": "use type hints"}).status_code == 409
    assert client.post(f"/api/runs/{run_id}/messages", json={"text": ""}).status_code == 422


def test_resume_endpoint_rejects_runs_that_cannot_resume(client):
    run_id = client.post("/api/runs", json={"requirement": "calculator"}).json()["id"]
    _events(client, run_id)
    assert client.post(f"/api/runs/{run_id}/resume").status_code == 409  # it succeeded; nothing to resume
    assert client.post("/api/runs/nope/resume").status_code == 409


def test_exec_runs_a_program_with_typed_input(client):
    root = settings.output_dir / "hello-20260101-000000"
    root.mkdir(parents=True)
    (root / "main.py").write_text('name = input("Name? ")\nprint(f"Hi {name}")\n', encoding="utf-8")
    (root / "style.css").write_text("body{}", encoding="utf-8")
    (root / "loop.py").write_text("while True:\n    pass\n", encoding="utf-8")
    url = "/api/projects/hello-20260101-000000/exec"

    r = client.post(url, json={"path": "main.py", "stdin": "Asha\n"}).json()
    assert r["exit_code"] == 0 and "Hi Asha" in r["output"] and not r["timed_out"]

    r = client.post(url, json={"path": "main.py"}).json()  # no input typed: input() sees end of input
    assert r["exit_code"] != 0 and "EOFError" in r["output"]

    object.__setattr__(settings, "run_timeout_sec", 1)
    try:
        assert client.post(url, json={"path": "loop.py"}).json()["timed_out"]
    finally:
        object.__setattr__(settings, "run_timeout_sec", 20)

    assert client.post(url, json={"path": "style.css"}).status_code == 422
    assert client.post(url, json={"path": "missing.py"}).status_code == 404
    assert client.post(url, json={"path": "../server.py"}).status_code in (403, 404)


def test_rename_edit_and_delete_project(client):
    root = settings.output_dir / "edit-me-20260101-000000"
    (root / ".codecrew").mkdir(parents=True)
    (root / "main.py").write_text("print('old')\n", encoding="utf-8")
    url = "/api/projects/edit-me-20260101-000000"

    assert client.patch(url, json={"name": "My game"}).json()["name"] == "My game"
    assert client.get(url).json()["name"] == "My game"

    assert client.put(f"{url}/files/main.py", json={"content": "print('new')\n"}).status_code == 200
    project = client.get(url).json()
    assert project["files"]["main.py"] == "print('new')\n" and project["verification_stale"]
    assert client.post(f"{url}/exec", json={"path": "main.py"}).json()["output"].strip() == "new"

    assert client.put(f"{url}/files/new.py", json={"content": "x"}).status_code == 404  # only existing files
    assert client.put(f"{url}/files/.codecrew/project.json", json={"content": "{}"}).status_code in (403, 404)
    assert client.put(f"{url}/files/..%2f..%2fserver.py", json={"content": "x"}).status_code in (403, 404)

    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


def test_delete_run(client):
    import time

    run_id = client.post("/api/runs", json={"requirement": "calculator"}).json()["id"]
    _events(client, run_id)
    project_id = client.get(f"/api/runs/{run_id}").json()["project_id"]
    assert client.delete(f"/api/runs/{run_id}").status_code == 204
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert run_id not in [r["id"] for r in client.get("/api/runs").json()["runs"]]
    assert client.get(f"/api/projects/{project_id}").status_code == 200  # the saved project stays
    assert client.delete(f"/api/runs/{run_id}").status_code == 404

    # A run that is still working is stopped, then removed.
    live = client.post("/api/runs", json={"requirement": "calculator"}).json()["id"]
    assert client.delete(f"/api/runs/{live}").status_code == 204
    deadline = time.time() + 30
    while client.get(f"/api/runs/{live}").status_code != 404:
        assert time.time() < deadline, "the stopped run was never removed"
        time.sleep(0.1)


def test_run_with_reference_images(client):
    import base64

    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 32).decode()
    r = client.post("/api/runs", json={"requirement": "calculator", "images": [{"media_type": "image/png", "data": png}]})
    assert r.status_code == 201
    run_id = r.json()["id"]
    assert r.json()["images"][0]["kind"] == "reference"
    img = client.get(f"/api/runs/{run_id}/images/1")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content.startswith(b"\x89PNG")
    assert client.get(f"/api/runs/{run_id}/images/9").status_code == 404
    _events(client, run_id)

    bad = [{"media_type": "image/png", "data": "not base64!"}, {"media_type": "image/png", "data": base64.b64encode(b"GIF89a").decode()},
           {"media_type": "text/html", "data": png}]
    for img in bad:
        assert client.post("/api/runs", json={"requirement": "calculator", "images": [img]}).status_code == 422


def test_delete_read_only_project_folder(client):
    import os
    import stat

    root = settings.output_dir / "locked-20260101-000000"
    root.mkdir(parents=True)
    (root / "index.html").write_text("<p>hi</p>", encoding="utf-8")
    os.chmod(root / "index.html", stat.S_IREAD)  # OneDrive often marks synced items read-only
    os.chmod(root, stat.S_IREAD)
    assert client.delete("/api/projects/locked-20260101-000000").status_code == 204
    assert not root.exists()


def test_server_errors_keep_cors_headers(monkeypatch, tmp_path):
    """A crash must reach the browser as a readable error, not as a fake CORS failure."""
    import importlib

    import server

    importlib.reload(server)

    def boom(_project_id):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(server.projects, "load", boom)
    with TestClient(server.app, raise_server_exceptions=False) as c:
        r = c.get("/api/projects/anything-1", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 500
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "disk on fire" in r.json()["detail"]


def test_dns_rebinding_and_foreign_pages_are_refused(client):
    """A page whose domain was re-pointed at 127.0.0.1 must not reach the API, and no
    other web page may make it change anything (write files, run code, delete)."""
    assert client.get("/api/health", headers={"Host": "rebind.attacker.example:8000"}).status_code == 400
    assert client.get("/api/health", headers={"Host": "127.0.0.1:8000"}).status_code == 200

    evil = {"Origin": "http://rebind.attacker.example:8000"}
    assert client.post("/api/runs", json={"requirement": "calculator"}, headers=evil).status_code == 403
    assert client.put("/api/projects/x-1/files/main.py", json={"content": "x"}, headers=evil).status_code == 403
    assert client.post("/api/projects/x-1/exec", json={"path": "main.py"}, headers=evil).status_code == 403
    assert client.delete("/api/projects/x-1", headers=evil).status_code == 403

    ui = {"Origin": "http://localhost:3000"}
    assert client.delete("/api/projects/x-1", headers=ui).status_code == 404  # allowed through; just not found
    docs = {"Origin": "http://127.0.0.1:8000"}  # the API's own /docs page
    assert client.delete("/api/projects/x-1", headers=docs).status_code == 404
