"""
server.py
---------
CodeCrew HTTP API (FastAPI). The Next.js frontend in web/ is its only UI.

    python server.py          # http://127.0.0.1:8000, docs at /docs
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import mimetypes
import sys
import time
import traceback
from urllib.parse import urlparse
import zipfile
from typing import Optional

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Header, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from starlette.middleware.trustedhost import TrustedHostMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, Response, StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sse_starlette.sse import EventSourceResponse  # noqa: E402

from codecrew import __version__, llm, orchestrator, projects, sandbox  # noqa: E402
from codecrew.config import ROOT_DIR, settings  # noqa: E402
from codecrew.runs import RunManager  # noqa: E402
from codecrew.schemas import RunState  # noqa: E402
from codecrew.store import Store  # noqa: E402
from codecrew.textio import UnsafePathError, safe_relpath  # noqa: E402

app = FastAPI(title="CodeCrew API", version=__version__,
              description="Multi-agent AI system for collaborative software development.")


class _ErrorsAsJSON:
    """Turns an unexpected exception into a JSON 500 *inside* the CORS layer. Without
    this, a crash reaches the browser without CORS headers and shows up as a
    misleading "blocked by CORS policy" error instead of the real problem."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def tracked(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked)
        except Exception as e:
            if started:
                raise
            traceback.print_exc()
            await JSONResponse({"detail": f"Server error: {type(e).__name__}: {e}"}, status_code=500)(scope, receive, send)


class _SameSiteWrites:
    """Refuses requests that change something (POST, PUT, PATCH, DELETE) when the browser
    says they come from a page that is neither the CodeCrew UI nor this API itself.
    Browsers always send Origin on such requests, so a hostile page cannot forge it.
    "null" (sandboxed iframes, including the preview of generated pages) is refused
    too; clients that are not browsers send no Origin at all."""

    UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in self.UNSAFE:
            origin = dict(scope["headers"]).get(b"origin", b"").decode("latin-1")
            if origin and not _trusted_origin(origin):
                return await JSONResponse({"detail": "Request refused: it came from an untrusted web page."},
                                          status_code=403)(scope, receive, send)
        return await self.app(scope, receive, send)


def _trusted_origin(origin: str) -> bool:
    return origin in settings.cors_origins or (urlparse(origin).hostname or "") in settings.allowed_hosts


# Order matters: the last one added runs first. Host check -> CORS -> write-origin check -> errors.
app.add_middleware(_ErrorsAsJSON)
app.add_middleware(_SameSiteWrites)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Last-Event-ID"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

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
    {"id": "reviewer", "name": "Reviewer", "role": "Reviews screenshots of web pages against the design brief and asks for visual fixes; adds behaviour-neutral docstrings and writes the README with real verification results."},
]


class ImageIn(BaseModel):
    media_type: str = Field(description="image/png, image/jpeg, image/webp or image/gif")
    data: str = Field(max_length=7_000_000, description="Base64-encoded image, at most 5 MB.")


class CreateRun(BaseModel):
    requirement: str = Field(min_length=3, max_length=8000)
    ask: bool = Field(False, description="Let the Planner ask up to 2 multiple-choice questions before planning.")
    images: list[ImageIn] = Field(default_factory=list, max_length=4,
                                  description="Reference designs (screenshots) for vision-capable models.")


_IMAGE_MAGIC = {"image/png": (b"\x89PNG",), "image/jpeg": (b"\xff\xd8\xff",), "image/gif": (b"GIF87a", b"GIF89a"),
                "image/webp": (b"RIFF",)}


def _decode_images(images: list[ImageIn]) -> list[tuple[str, bytes]]:
    out = []
    for i, img in enumerate(images, 1):
        try:
            data = base64.b64decode(img.data, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, f"Image {i} is not valid base64.")
        if len(data) > 5_000_000:
            raise HTTPException(422, f"Image {i} is larger than 5 MB.")
        if not data.startswith(_IMAGE_MAGIC.get(img.media_type, ())):  # unknown types match nothing
            raise HTTPException(422, f"Image {i} is not a PNG, JPEG, WebP or GIF image.")
        out.append((img.media_type, data))
    return out


class AnswerBody(BaseModel):
    question_id: str = Field(min_length=1, max_length=32)
    choice: int = Field(ge=0, le=9)


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class IterateRun(BaseModel):
    request: str = Field(min_length=3, max_length=8000)


class ExecBody(BaseModel):
    path: str = Field(min_length=1, max_length=300, description="Project file to run, e.g. 'main.py'.")
    stdin: str = Field("", max_length=20000, description="Text typed into the program; each line answers one input().")
    args: list[str] = Field(default_factory=list, max_length=20)


_MAX_OUTPUT = 100_000


class RenameProject(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class SaveFile(BaseModel):
    content: str = Field(max_length=1_000_000)


def _not_busy(project_id: str) -> None:
    if manager.project_busy(project_id):
        raise HTTPException(409, "The crew is changing this project right now. Wait for that run to finish.")


def _project_or_404(project_id: str) -> dict:
    try:
        return projects.load(project_id)
    except projects.ProjectNotFound:
        raise HTTPException(404, "Project not found")


# ---------------------------------------------------------------- meta

def _code_mtime() -> float:
    """Newest modification time of the backend's own code."""
    paths = [ROOT_DIR / "server.py", *(ROOT_DIR / "codecrew").rglob("*.py")]
    return max((p.stat().st_mtime for p in paths if p.exists()), default=0.0)


_STARTED_CODE = _code_mtime()


@app.get("/api/health")
def health():
    status = llm.provider_status()
    return {"status": "ok", "version": __version__,
            "providers_configured": [n for n, p in status["providers"].items() if p["configured"]],
            # True when the code on disk changed after this server started: new features need a restart.
            "stale": _code_mtime() > _STARTED_CODE + 1}


@app.get("/api/providers")
def providers():
    return llm.provider_status()


@app.get("/api/agents")
def agents():
    return {"agents": AGENTS, "graph": orchestrator.mermaid()}


# ---------------------------------------------------------------- runs

@app.post("/api/runs", response_model=RunState, status_code=201)
def create_run(body: CreateRun):
    return manager.start(body.requirement, ask_questions=body.ask, images=_decode_images(body.images))


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


@app.delete("/api/runs/{run_id}", status_code=204)
def delete_run(run_id: str):
    if not manager.delete(run_id):
        raise HTTPException(404, "Run not found")
    return Response(status_code=204)


@app.post("/api/runs/{run_id}/resume", response_model=RunState)
def resume_run(run_id: str):
    state = manager.resume(run_id)
    if not state:
        raise HTTPException(409, "Only a stopped run (error or cancelled) that is not running can be resumed")
    return state


@app.get("/api/runs/{run_id}/images/{image_id}")
def run_image(run_id: str, image_id: int):
    """An image the user attached, a reference-page screenshot, or a design-review screenshot."""
    found = store.get_image(run_id, image_id)
    if not found:
        raise HTTPException(404, "Image not found")
    media_type, data = found
    return Response(data, media_type=media_type, headers={"Cache-Control": "private, max-age=86400",
                                                         "X-Content-Type-Options": "nosniff"})


@app.post("/api/runs/{run_id}/answer")
def answer_question(run_id: str, body: AnswerBody):
    if not manager.answer(run_id, body.question_id, body.choice):
        raise HTTPException(409, "That question is no longer waiting for an answer")
    return {"accepted": True}


@app.post("/api/runs/{run_id}/messages", status_code=201)
def send_message(run_id: str, body: MessageBody):
    note_id = manager.add_note(run_id, body.text.strip())
    if not note_id:
        raise HTTPException(409, "Run is not active")
    return {"id": note_id}


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
        yield {"event": "end", "data": "{}"}  # tells the browser not to reconnect

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


@app.patch("/api/projects/{project_id}")
def rename_project(project_id: str, body: RenameProject):
    try:
        projects.rename(project_id, body.name.strip())
    except projects.ProjectNotFound:
        raise HTTPException(404, "Project not found")
    return {"name": body.name.strip()}


@app.put("/api/projects/{project_id}/files/{file_path:path}")
def save_project_file(project_id: str, file_path: str, body: SaveFile):
    _project_or_404(project_id)
    _not_busy(project_id)
    try:
        projects.write_file(project_id, file_path, body.content)
    except UnsafePathError:
        raise HTTPException(403, "Invalid path")
    except projects.ProjectNotFound:
        raise HTTPException(404, "File not found")
    return {"saved": True}


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: str):
    _not_busy(project_id)
    try:
        projects.delete(project_id)
    except projects.ProjectNotFound:
        raise HTTPException(404, "Project not found")
    except PermissionError:
        raise HTTPException(409, "Windows would not let CodeCrew delete the project folder. It is probably open in "
                                 "another program (File Explorer, an editor or a terminal) or still syncing with "
                                 "OneDrive. Close it there and try again.")
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


@app.post("/api/projects/{project_id}/exec")
def exec_project(project_id: str, body: ExecBody):
    """Runs one program file of the project in the sandbox and returns what it printed."""
    p = _project_or_404(project_id)
    try:
        rel = safe_relpath(body.path)
    except UnsafePathError:
        raise HTTPException(403, "Invalid path")
    if rel not in p["files"]:
        raise HTTPException(404, "File not found")
    if rel.endswith(".py"):
        cmd = [*sandbox.python_cmd(), rel]
    elif rel.endswith((".js", ".mjs", ".cjs")):
        node = sandbox.node_path()
        if not node:
            raise HTTPException(422, "Node.js is not installed on the server, so JavaScript files cannot be run.")
        cmd = [node, rel]
    else:
        raise HTTPException(422, "Only Python (.py) and JavaScript (.js) files can be run here.")
    started = time.monotonic()
    with sandbox.workspace(p["files"]) as root:
        res = sandbox.run([*cmd, *body.args], root, timeout=settings.run_timeout_sec, stdin=body.stdin)
    output = res.output
    if len(output) > _MAX_OUTPUT:
        output = output[:_MAX_OUTPUT] + f"\n[output cut off after {_MAX_OUTPUT:,} characters]"
    return {"exit_code": res.returncode, "output": output, "timed_out": res.timed_out,
            "seconds": round(time.monotonic() - started, 2), "timeout_sec": settings.run_timeout_sec}


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
