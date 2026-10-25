"""
server.py
---------
CodeCrew HTTP API (FastAPI). The Next.js frontend in web/ is its only UI.

    python server.py          # http://127.0.0.1:8000, docs at /docs
"""

from __future__ import annotations

import io
import json
import mimetypes
import sys
import zipfile
from typing import Optional

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Header, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import Response, StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sse_starlette.sse import EventSourceResponse  # noqa: E402

from codecrew import __version__, llm, orchestrator, projects  # noqa: E402
from codecrew.config import ROOT_DIR, settings  # noqa: E402
from codecrew.runs import RunManager  # noqa: E402
from codecrew.schemas import RunState  # noqa: E402
from codecrew.store import Store  # noqa: E402
from codecrew.textio import UnsafePathError, safe_relpath  # noqa: E402

app = FastAPI(title="CodeCrew API", version=__version__,
              description="Multi-agent AI system for collaborative software development.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Last-Event-ID"],
)

store = Store(settings.db_path)
store.mark_interrupted()
manager = RunManager(store)

AGENTS = [
    {"id": "orchestrator", "name": "Orchestrator", "role": "Routes work between agents, enforces retry limits, keeps the best version."},
    {"id": "planner", "name": "Planner", "role": "Turns the requirement into a technical spec with signatures and acceptance criteria."},
    {"id": "test_author", "name": "Test Author", "role": "Writes unit tests from the spec before any code exists; rules on test disputes."},
    {"id": "coder", "name": "Coder", "role": "Implements the spec so the locked tests pass."},
    {"id": "verifier", "name": "Verifier", "role": "Deterministic checks: syntax, cross-file contracts, spec conformance, lint, security, sandboxed tests."},
    {"id": "debugger", "name": "Debugger", "role": "Root-causes failures and patches source code; may dispute tests that contradict the spec."},
    {"id": "reviewer", "name": "Reviewer", "role": "Adds behaviour-neutral docstrings and writes the README with real verification results."},
]


class CreateRun(BaseModel):
    requirement: str = Field(min_length=3, max_length=8000)


class IterateRun(BaseModel):
    request: str = Field(min_length=3, max_length=8000)


def _project_or_404(project_id: str) -> dict:
    try:
        return projects.load(project_id)
    except projects.ProjectNotFound:
        raise HTTPException(404, "Project not found")


# ---------------------------------------------------------------- meta

@app.get("/api/health")
def health():
    status = llm.provider_status()
    return {"status": "ok", "version": __version__,
            "providers_configured": [n for n, p in status["providers"].items() if p["configured"]]}


@app.get("/api/providers")
def providers():
    return llm.provider_status()


@app.get("/api/agents")
def agents():
    return {"agents": AGENTS, "graph": orchestrator.mermaid()}


# ---------------------------------------------------------------- runs

@app.post("/api/runs", response_model=RunState, status_code=201)
def create_run(body: CreateRun):
    return manager.start(body.requirement)


@app.get("/api/runs")
def list_runs(limit: int = Query(50, ge=1, le=200), project_id: Optional[str] = None):
    return {"runs": store.list_runs(limit, project_id)}


@app.get("/api/runs/{run_id}", response_model=RunState)
def get_run(run_id: str):
    state = manager.get(run_id)
    if not state:
        raise HTTPException(404, "Run not found")
    return state


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    if not manager.cancel(run_id):
        raise HTTPException(409, "Run is not active")
    return {"cancelled": True}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, after: int = Query(0, ge=0), last_event_id: Optional[str] = Header(None)):
    if not manager.get(run_id):
        raise HTTPException(404, "Run not found")
    start = max(after, int(last_event_id)) if last_event_id and last_event_id.isdigit() else after

    async def gen():
        async for e in manager.stream(run_id, start):
            if e.type == "ping":
                yield {"comment": "keep-alive"}
                continue
            yield {"id": str(e.seq), "event": e.type, "data": json.dumps({"seq": e.seq, "ts": e.ts, **e.data})}

    return EventSourceResponse(gen(), ping=None)


# ---------------------------------------------------------------- projects

@app.get("/api/projects")
def list_projects():
    return {"projects": projects.list_all()}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    p = _project_or_404(project_id)
    return {**p, "spec": p["spec"].model_dump() if p["spec"] else None}


@app.post("/api/projects/{project_id}/runs", response_model=RunState, status_code=201)
def iterate_project(project_id: str, body: IterateRun):
    p = _project_or_404(project_id)
    if not p["spec"]:
        raise HTTPException(422, "This project predates CodeCrew v3 and has no spec; rebuild it to iterate.")
    return manager.start(body.request, mode="iterate", project_id=project_id)


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: str):
    try:
        projects.delete(project_id)
    except projects.ProjectNotFound:
        raise HTTPException(404, "Project not found")
    return Response(status_code=204)


@app.get("/api/projects/{project_id}/download")
def download_project(project_id: str):
    p = _project_or_404(project_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, content in {**p["files"], **p["tests"]}.items():
            zf.writestr(rel, content)
        if p["readme"]:
            zf.writestr("README.md", p["readme"])
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{project_id}.zip"'})


@app.get("/api/projects/{project_id}/preview/{file_path:path}")
def preview(project_id: str, file_path: str):
    """Serves generated files for the live preview. The CSP sandbox gives the
    page an opaque origin, so generated scripts cannot call this API."""
    root = projects.project_path(project_id)
    try:
        rel = safe_relpath(file_path or "index.html")
    except UnsafePathError:
        raise HTTPException(403, "Invalid path")
    target = (root / rel).resolve()
    if root.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "File not found")
    media = mimetypes.guess_type(target.name)[0] or "text/plain"
    return Response(
        target.read_bytes(),
        media_type=media,
        headers={"Content-Security-Policy": "sandbox allow-scripts allow-forms allow-modals", "X-Content-Type-Options": "nosniff"},
    )


# ---------------------------------------------------------------- evaluation

EVAL_DIR = ROOT_DIR / "eval" / "results"


@app.get("/api/eval")
def list_eval_results():
    """Baseline-vs-CodeCrew benchmark results produced by `python -m eval.run`."""
    out = []
    for f in sorted(EVAL_DIR.glob("*.json"), reverse=True) if EVAL_DIR.exists() else []:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append({"name": data.get("name", f.stem), "finished_at": data.get("finished_at"),
                    "providers": data.get("providers"), "summary": data.get("summary", {})})
    return {"results": out}


@app.get("/api/eval/{name}")
def get_eval_result(name: str):
    if not name.replace("-", "").isdigit():
        raise HTTPException(404, "Result not found")
    f = EVAL_DIR / f"{name}.json"
    if not f.exists():
        raise HTTPException(404, "Result not found")
    return json.loads(f.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
