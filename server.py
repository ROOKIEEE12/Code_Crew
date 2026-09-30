"""
server.py
---------
FastAPI Backend for CodeCrew.
Provides REST and Server-Sent Events (SSE) endpoints for controlling the
multi-agent engineering pipeline, streaming live execution, and serving
generated projects.
"""

import asyncio
import io
import json
import os
import queue
import zipfile
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from orchestrator import run_pipeline, run_iteration_pipeline
from config import OUTPUT_DIR, MODEL_NAME
from agents.model_manager import model_pool

app = FastAPI(
    title="CodeCrew API",
    description="Multi-Agent Software Engineering Team Backend",
    version="2.0.0",
)

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BuildRequest(BaseModel):
    prompt: str


class AuditRequest(BaseModel):
    path: str
    code: str
    language: Optional[str] = "text"
    description: Optional[str] = ""


class TestRequest(BaseModel):
    path: str
    code: str
    language: Optional[str] = "python"


class RefactorRequest(BaseModel):
    path: str
    code: str
    language: Optional[str] = "text"
    instruction: str


class DebugRequest(BaseModel):
    path: str
    code: str
    language: Optional[str] = "text"
    error: str


class ExplainRequest(BaseModel):
    path: str
    code: str
    language: Optional[str] = "text"



@app.get("/api/health")
def health_check():
    status = model_pool.get_status_report()
    return {
        "status": "online",
        "model": MODEL_NAME,
        "output_dir": OUTPUT_DIR,
        "version": "2.0.0",
        "active_models": status["active_models"],
        "total_models": status["total_models"],
        "keys_configured": status["keys_configured"],
    }


@app.get("/api/models/status")
def get_models_status():
    """Returns live telemetry of all Gemini free models, cooldowns, and auto-refresh."""
    return model_pool.get_status_report()


@app.get("/api/agents")
def get_agents():
    """Information on each isolated specialist agent in CodeCrew."""
    return {
        "agents": [
            {
                "id": "planner",
                "name": "Principal Systems Architect",
                "role": "Planner Agent",
                "avatar": "🧠",
                "description": "Deconstructs prompts into atomic software specifications, technology choices, and dependency graphs.",
                "color": "#8b5cf6",
            },
            {
                "id": "coder",
                "name": "Senior Staff Polyglot Engineer",
                "role": "Coder Agent",
                "avatar": "💻",
                "description": "Writes production-grade, zero-bloat code with strict cross-file contract synchronization.",
                "color": "#3b82f6",
            },
            {
                "id": "auditor",
                "name": "Principal Code Auditor & Fact-Checker",
                "role": "Auditor Agent",
                "avatar": "🔍",
                "description": "Line-by-line API/method fact verification, eliminates redundant lines, dead code, and hallucinations.",
                "color": "#10b981",
            },
            {
                "id": "tester",
                "name": "QA Automation Architect",
                "role": "Testing Agent",
                "avatar": "🧪",
                "description": "Multi-tier testing: syntax validation, dynamic PyTest execution in isolated sandbox, and cross-file contract checks.",
                "color": "#f59e0b",
            },
            {
                "id": "debugger",
                "name": "Root-Cause Triage Specialist",
                "role": "Debugger Agent",
                "avatar": "🛠️",
                "description": "Pinpoints exact failure lines and applies surgical patches with minimal diffs and zero regressions.",
                "color": "#ef4444",
            },
            {
                "id": "reviewer",
                "name": "Lead Technical Writer",
                "role": "Reviewer Agent",
                "avatar": "📝",
                "description": "Authors crystal-clear, runnable README documentation and installation guides.",
                "color": "#06b6d4",
            },
        ]
    }


@app.post("/api/agent/audit")
def run_agent_audit(req: AuditRequest):
    """Executes Principal Code Auditor Agent on the provided code."""
    from agents.auditor_agent import audit_and_refine
    try:
        result = audit_and_refine(
            path=req.path,
            language=req.language,
            code=req.code,
            file_description=req.description or "Audit and eliminate bloat/inconsistencies",
        )
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/test")
def run_agent_test(req: TestRequest):
    """Executes QA Tester Agent to generate test suite for code."""
    from agents.llm_client import call_llm
    from agents.code_utils import clean_code_block
    import os

    try:
        module_name = os.path.splitext(os.path.basename(req.path))[0]
        if req.language == "python":
            prompt = f"Module name to import: {module_name}\nTarget file: {req.path}\n\nCode:\n{req.code}"
            system_prompt = (
                "You are the QA Automation Architect (Testing Agent). Write comprehensive PyTest tests "
                "covering happy paths, edge cases, error conditions, and mocks where needed. "
                "Return ONLY valid runnable Python code with no markdown fences and no chatter."
            )
            raw = call_llm(system_prompt, prompt, role="tester")
            test_code = clean_code_block(raw)
            return {"status": "success", "test_file": f"test_{module_name}.py", "code": test_code}
        else:
            prompt = f"File: {req.path} ({req.language})\n\nCode:\n{req.code}"
            system_prompt = (
                f"You are the QA Automation Architect (Testing Agent). Write an automated unit test suite for this {req.language} code. "
                "Return ONLY valid test code with no markdown fences and no chatter."
            )
            raw = call_llm(system_prompt, prompt, role="tester")
            test_code = clean_code_block(raw)
            return {"status": "success", "test_file": f"test_{module_name}.test.js", "code": test_code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/refactor")
def run_agent_refactor(req: RefactorRequest):
    """Executes Senior Staff Polyglot Coder Agent to refactor code."""
    from agents.llm_client import call_llm
    from agents.code_utils import clean_code_block

    try:
        system_prompt = (
            f"You are a Senior Staff Software Engineer specializing in {req.language}. "
            "Refactor and improve the provided code strictly following the instruction. "
            "Maintain surgical economy: zero stubs, zero bloat, complete runnable implementation. "
            "Return ONLY the updated code, no markdown fences, no conversational text."
        )
        user_prompt = f"File: {req.path}\nInstruction: {req.instruction}\n\nCode:\n{req.code}"
        raw = call_llm(system_prompt, user_prompt, role="coder")
        return {"status": "success", "code": clean_code_block(raw)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/debug")
def run_agent_debug(req: DebugRequest):
    """Executes Root-Cause Triage Specialist (Debugger Agent) to patch errors."""
    from agents.debugger_agent import debug
    try:
        fixed = debug(
            path=req.path,
            language=req.language,
            code=req.code,
            issue_description=req.error,
            sibling_summary="VS Code active workspace document diagnostics",
        )
        return {"status": "success", "code": fixed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/explain")
def run_agent_explain(req: ExplainRequest):
    """Executes Lead Systems Architect to explain architecture and flow."""
    from agents.llm_client import call_llm
    try:
        system_prompt = (
            "You are the Principal Systems Architect in CodeCrew. Explain the architectural design, "
            "data flow, potential bottlenecks, and key mechanisms of this code in clear, concise bullet points."
        )
        user_prompt = f"File: {req.path} ({req.language})\n\nCode:\n{req.code}"
        explanation = call_llm(system_prompt, user_prompt, role="planner")
        return {"status": "success", "explanation": explanation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/build/stream")
async def stream_build(prompt: str = Query(..., min_length=2)):
    """
    Streams the live execution of CodeCrew agents via Server-Sent Events (SSE).
    React frontend listens to this stream to render real-time UI state.
    """
    event_queue = asyncio.Queue()

    def sync_event_callback(event_type: str, data: dict):
        # Push into async queue from sync pipeline thread
        asyncio.run_coroutine_threadsafe(
            event_queue.put({"event": event_type, "data": json.dumps(data)}),
            loop,
        )

    loop = asyncio.get_running_loop()

    def run_job():
        try:
            run_pipeline(prompt, log=lambda m: None, on_event=sync_event_callback)
        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                event_queue.put({
                    "event": "error",
                    "data": json.dumps({"error": str(e)}),
                }),
                loop,
            )
        finally:
            asyncio.run_coroutine_threadsafe(
                event_queue.put({"event": "done", "data": "{}"}),
                loop,
            )

    # Launch pipeline in background thread executor
    loop.run_in_executor(None, run_job)

    async def event_generator():
        while True:
            item = await event_queue.get()
            if item.get("event") == "done":
                yield {"event": "done", "data": "{}"}
                break
            yield item

    return EventSourceResponse(event_generator())


@app.get("/api/projects/{project_id}/iterate/stream")
async def stream_iteration(project_id: str, prompt: str = Query(..., min_length=2)):
    """
    Streams selective multi-agent iteration on an existing project via SSE.
    Manager Agent dynamically routes work to only required agents.
    """
    event_queue = asyncio.Queue()

    def sync_event_callback(event_type: str, data: dict):
        asyncio.run_coroutine_threadsafe(
            event_queue.put({"event": event_type, "data": json.dumps(data)}),
            loop,
        )

    loop = asyncio.get_running_loop()

    def run_job():
        try:
            run_iteration_pipeline(
                project_id,
                prompt,
                log=lambda m: None,
                on_event=sync_event_callback,
            )
        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                event_queue.put({
                    "event": "error",
                    "data": json.dumps({"error": str(e)}),
                }),
                loop,
            )
        finally:
            asyncio.run_coroutine_threadsafe(
                event_queue.put({"event": "done", "data": "{}"}),
                loop,
            )

    loop.run_in_executor(None, run_job)

    async def event_generator():
        while True:
            item = await event_queue.get()
            if item.get("event") == "done":
                yield {"event": "done", "data": "{}"}
                break
            yield item

    return EventSourceResponse(event_generator())


@app.get("/api/projects")
def list_projects():
    """Returns list of saved generated projects."""
    if not os.path.exists(OUTPUT_DIR):
        return {"projects": []}

    entries = []
    for folder in os.listdir(OUTPUT_DIR):
        folder_path = os.path.join(OUTPUT_DIR, folder)
        if os.path.isdir(folder_path):
            files = []
            for root, _, filenames in os.walk(folder_path):
                for fn in filenames:
                    rel = os.path.relpath(os.path.join(root, fn), folder_path)
                    files.append(rel)

            has_readme = "README.md" in files
            stat = os.stat(folder_path)
            entries.append({
                "id": folder,
                "name": folder.rsplit("-", 2)[0] if "-" in folder else folder,
                "file_count": len(files),
                "files": files,
                "created_at": stat.st_ctime,
                "has_readme": has_readme,
            })

    entries.sort(key=lambda x: x["created_at"], reverse=True)
    return {"projects": entries}


@app.get("/api/projects/{project_id}")
def get_project_details(project_id: str):
    """Retrieves full details, files, and README for a specific project."""
    folder_path = os.path.join(OUTPUT_DIR, project_id)
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        raise HTTPException(status_code=404, detail="Project not found")

    project_files = {}
    readme_content = ""

    for root, _, filenames in os.walk(folder_path):
        for fn in filenames:
            rel = os.path.relpath(os.path.join(root, fn), folder_path).replace("\\", "/")
            full = os.path.join(root, fn)
            try:
                with open(full, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                content = "[Binary or unreadable content]"

            if rel == "README.md":
                readme_content = content
            else:
                ext = os.path.splitext(fn)[1].lower()
                lang_map = {
                    ".py": "python",
                    ".js": "javascript",
                    ".jsx": "javascript",
                    ".ts": "typescript",
                    ".html": "html",
                    ".css": "css",
                    ".json": "json",
                    ".md": "markdown",
                    ".sql": "sql",
                }
                project_files[rel] = {
                    "code": content,
                    "language": lang_map.get(ext, "text"),
                }

    return {
        "id": project_id,
        "files": project_files,
        "readme": readme_content,
    }


@app.get("/api/projects/{project_id}/download")
def download_project_zip(project_id: str):
    """Generates and serves a .zip archive of the generated project."""
    folder_path = os.path.join(OUTPUT_DIR, project_id)
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        raise HTTPException(status_code=404, detail="Project not found")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, filenames in os.walk(folder_path):
            for fn in filenames:
                file_path = os.path.join(root, fn)
                rel_path = os.path.relpath(file_path, folder_path)
                zf.write(file_path, arcname=rel_path)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={project_id}.zip"},
    )


# Serve React app when built
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_dist):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
