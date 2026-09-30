"""
orchestrator.py
-----------------
The multi-agent coordinator for CodeCrew.
Orchestrates Planner, Coder, Auditor (Fact-Checker), Tester, Debugger, and Reviewer.
Features parallel generation/auditing, automated multi-attempt bug resolution,
and live event streaming for the React/FastAPI interface.
"""

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from agents import (
    planner_agent,
    coder_agent,
    auditor_agent,
    testing_agent,
    debugger_agent,
    reviewer_agent,
)
from agents.llm_client import call_llm
from agents.model_manager import model_pool
from agents.code_utils import parse_json_response
from config import MAX_DEBUG_RETRIES, MAX_PARALLEL_WORKERS, OUTPUT_DIR


def _run_concurrently(jobs: dict, log, label: str) -> dict:
    """
    Executes multiple worker tasks concurrently using Python's ThreadPoolExecutor.
    Uses micro-staggering to prevent sudden token bursts on the free-tier quota bucket.
    """
    import time
    if not jobs:
        return {}

    log(f"[{label}] Launching {len(jobs)} agent(s): {', '.join(jobs.keys())}")
    results = {}
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        future_to_key = {}
        for idx, (key, fn) in enumerate(jobs.items()):
            if idx > 0:
                time.sleep(0.35)  # 350ms micro-stagger avoids simultaneous token spike
            future_to_key[executor.submit(fn)] = key

        for future in as_completed(future_to_key):
            key = future_to_key[future]
            results[key] = future.result()
    log(f"[{label}] All {len(jobs)} agent job(s) finished.")
    return results


def _compute_waves(files_spec: list) -> list:
    """
    Groups files into topological waves based on dependency contracts.
    Files in the same wave run concurrently.
    """
    remaining = {f["path"]: f for f in files_spec}
    done = set()
    waves = []

    while remaining:
        wave = [f for f in remaining.values() if all(dep in done for dep in f["depends_on"])]
        if not wave:
            # Fallback for circular dependency
            wave = list(remaining.values())
        waves.append(wave)
        for f in wave:
            done.add(f["path"])
            del remaining[f["path"]]

    return waves


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", name.strip().lower()).strip("-")
    return slug or "codecrew-project"


def run_pipeline(user_request: str, log=print, on_event=None) -> dict:
    """
    Runs the full CodeCrew multi-agent pipeline with deep reasoning,
    line-by-line fact verification, and real-time event streaming.
    """
    activity_log = []

    def dispatch_event(event_type: str, data: dict):
        if on_event:
            try:
                on_event(event_type, data)
            except Exception:
                pass

    def step(agent_name: str, message: str, meta: dict = None):
        line = f"[{agent_name}] {message}"
        activity_log.append(line)
        log(line)
        dispatch_event("log", {"agent": agent_name, "message": message, "meta": meta or {}})

    def model_event_forwarder(event_type: str, data: dict):
        dispatch_event(event_type, data)
        if "message" in data:
            step("TokenGuardian", data["message"])

    model_pool.set_event_callback(model_event_forwarder)

    step("Orchestrator", f"Received build request: '{user_request}'")
    dispatch_event("status", {"state": "planning", "message": "Architect is analyzing the request..."})

    # ---------- 1. Planning Phase ----------
    step("Planner", "Principal Systems Architect analyzing requirements and designing file architecture...")
    plan = planner_agent.plan(user_request)
    file_specs = plan["files"]
    step("Planner", f"Architectural Blueprint completed: '{plan['project_name']}' ({plan['project_type']}) with {len(file_specs)} file(s).")
    dispatch_event("plan", {"plan": plan})

    # ---------- 2. Concurrent Generation & Fact-Checking Audit ----------
    files = {}  # path -> {"language": str, "code": str, "audit": dict}
    audit_reports = {}
    waves = _compute_waves(file_specs)

    for i, wave in enumerate(waves, start=1):
        dispatch_event("status", {"state": "coding", "wave": i, "total_waves": len(waves)})
        # Step A: Coder Agents generate raw code
        coder_jobs = {}
        for f in wave:
            dep_contents = {dep: files[dep]["code"] for dep in f["depends_on"] if dep in files}
            coder_jobs[f["path"]] = (
                lambda f=f, dep_contents=dep_contents: coder_agent.generate_file(f, plan["summary"], dep_contents)
            )

        step("Code Generation", f"Wave {i}/{len(waves)}: Generating {len(wave)} file(s) concurrently...")
        raw_code_results = _run_concurrently(coder_jobs, log, f"Coder Wave {i}")

        # Step B: Auditor Agents verify every fact and strip unnecessary lines
        step("Code Auditor", f"Wave {i}/{len(waves)}: Performing line-by-line fact checking and dead code elimination...")
        auditor_jobs = {}
        for f in wave:
            path = f["path"]
            raw_code = raw_code_results[path]
            dep_contents = {dep: files[dep]["code"] for dep in f["depends_on"] if dep in files}
            auditor_jobs[path] = (
                lambda p=path, lang=f.get("language", "text"), code=raw_code, desc=f.get("description", ""), deps=dep_contents: (
                    auditor_agent.audit_and_refine(p, lang, code, desc, deps)
                )
            )

        audit_results = _run_concurrently(auditor_jobs, log, f"Auditor Wave {i}")

        for f in wave:
            path = f["path"]
            audit = audit_results[path]
            audit_reports[path] = audit
            files[path] = {
                "language": f.get("language", "text"),
                "code": audit["code"],
                "audit": audit,
                "description": f.get("description", ""),
            }
            removed = audit.get("unnecessary_lines_removed", 0)
            notes = audit.get("audit_notes", "")
            step("Code Auditor", f"Verified '{path}': {removed} unneeded lines eliminated. {notes}")
            dispatch_event("file_ready", {
                "path": path,
                "language": files[path]["language"],
                "code": files[path]["code"],
                "audit": audit,
            })

    step("Code Generation", f"All {len(files)} file(s) generated, audited, and fact-checked.")

    # ---------- 3. Testing & QA Review Loop ----------
    passed = False
    check_result = None
    dispatch_event("status", {"state": "testing", "message": "Running automated test suites and QA review..."})

    for attempt in range(1, MAX_DEBUG_RETRIES + 1):
        step("Testing", f"Executing project verification suite (Attempt {attempt} of {MAX_DEBUG_RETRIES})...")
        check_result = testing_agent.run_project_checks(plan, files)
        dispatch_event("testing_update", {"attempt": attempt, "result": check_result})

        if check_result["passed"]:
            step("Testing", "All automated checks and QA criteria passed successfully!")
            passed = True
            break

        broken = testing_agent.files_needing_fixes(check_result, list(files.keys()))
        if not broken:
            step("Testing", "No specific actionable file issues identified; proceeding with current state.")
            break

        preview = "; ".join(f"{p}: {msg.splitlines()[0]}" for p, msg in broken.items())
        step("Testing", f"Issues identified in {len(broken)} file(s) — {preview}")
        dispatch_event("status", {"state": "debugging", "attempt": attempt, "broken": list(broken.keys())})

        # Debugging Phase: surgical repairs
        debug_jobs = {}
        for path, issue_text in broken.items():
            sibling_summary = "\n".join(f"- {p} ({f['language']})" for p, f in files.items() if p != path)
            debug_jobs[path] = (
                lambda path=path, issue_text=issue_text, sibling_summary=sibling_summary: debugger_agent.debug(
                    path, files[path]["language"], files[path]["code"], issue_text, sibling_summary
                )
            )

        step("Debugging", f"Applying surgical fixes to {len(debug_jobs)} file(s) simultaneously...")
        fixed = _run_concurrently(debug_jobs, log, f"Debugger Attempt {attempt}")

        for path, new_code in fixed.items():
            # Re-audit fixed code
            re_audit = auditor_agent.audit_and_refine(
                path, files[path]["language"], new_code, files[path].get("description", "")
            )
            files[path]["code"] = re_audit["code"]
            files[path]["audit"] = re_audit
            dispatch_event("file_ready", {
                "path": path,
                "language": files[path]["language"],
                "code": files[path]["code"],
                "audit": re_audit,
            })

    if not passed:
        step("Orchestrator", "Reached retry limit — proceeding with the most refined build version.")

    # ---------- 4. Documentation Phase ----------
    dispatch_event("status", {"state": "documenting", "message": "Technical Writer generating documentation..."})
    step("Review", "Writing comprehensive project README...")
    readme = reviewer_agent.write_readme(plan, files)
    dispatch_event("readme_ready", {"readme": readme})

    # ---------- 5. Save to Disk ----------
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project_dir = os.path.join(OUTPUT_DIR, f"{_slugify(plan['project_name'])}-{timestamp}")
    for path, f in files.items():
        full_path = os.path.join(project_dir, path)
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as fh:
            fh.write(f["code"])

    with open(os.path.join(project_dir, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(readme)

    step("Orchestrator", f"Project successfully saved to disk: {project_dir}")
    step("Orchestrator", "Multi-agent pipeline completed.")

    final_result = {
        "plan": plan,
        "files": files,
        "readme": readme,
        "tests_passed": passed,
        "check_result": check_result,
        "activity_log": activity_log,
        "project_dir": project_dir,
        "timestamp": timestamp,
    }

    dispatch_event("status", {"state": "completed", "result": final_result})
    return final_result


TRIAGE_SYSTEM_PROMPT = """You are the CodeCrew Multi-Agent Orchestrator coordinating 5 specialist agents:
1. "coder": Writes new files or modifies existing code/styling.
2. "auditor": Line-by-line fact verification, dead code elimination, and API contract validation.
3. "tester": Runs project verification checks (syntax & tests).
4. "debugger": Diagnoses root causes and applies fixes for broken code/tests.
5. "reviewer": Updates project documentation and README.md.

When a user submits a change or bugfix request for an existing project:
1. Identify the minimal set of affected files (modify or create). Do NOT touch files that don't need changes.
2. Select ONLY the minimal required agents among [coder, auditor, tester, debugger, reviewer].
   - Simple styling/UI tweak: ["coder", "auditor"]
   - Feature additions: ["coder", "auditor", "tester"]
   - Bug repair: ["debugger", "auditor", "tester"]
   - Documentation update: ["reviewer"]

Respond with ONLY a single valid JSON object, formatted as:
{
  "intent": "feature | bugfix | styling | documentation | refactor",
  "explanation": "Why these specific agents were chosen and what changes are needed",
  "required_agents": ["coder", "auditor", "tester"],
  "target_files": [
    {
      "path": "relative/file/path.ext",
      "action": "modify | create",
      "language": "python | javascript | html | css | other",
      "instructions": "Specific instructions for what to change in this file"
    }
  ],
  "update_readme": false
}
"""


def _triage_change_request(change_request: str, existing_files: dict, project_summary: str = "") -> dict:
    file_overview = []
    for path, data in existing_files.items():
        lang = data.get("language", "text")
        snippet = data.get("code", "")[:350]
        file_overview.append(f"File: {path} ({lang})\nPreview:\n{snippet}\n...")

    prompt = (
        f"Project Architectural Summary: {project_summary or 'Existing project'}\n\n"
        f"Existing Project Files ({len(existing_files)}):\n" + "\n\n".join(file_overview) + "\n\n"
        f"User Change Request:\n{change_request}"
    )

    raw = call_llm(TRIAGE_SYSTEM_PROMPT, prompt, temperature=0.1, role="triage")
    plan = parse_json_response(raw)

    plan.setdefault("intent", "feature")
    plan.setdefault("explanation", "Orchestrator selected targeted agents for surgical update.")
    plan.setdefault("required_agents", ["coder", "auditor", "tester"])
    plan.setdefault("target_files", [])
    plan.setdefault("update_readme", False)

    if not plan["target_files"] and existing_files:
        first_path = list(existing_files.keys())[0]
        plan["target_files"] = [
            {
                "path": first_path,
                "action": "modify",
                "language": existing_files[first_path].get("language", "text"),
                "instructions": change_request,
            }
        ]
    return plan


def run_iteration_pipeline(
    project_id: str,
    change_request: str,
    log=print,
    on_event=None,
) -> dict:
    """
    Executes a targeted, selective iteration on an existing project.
    The Orchestrator triages the request and calls ONLY the necessary agents
    (e.g., Coder + Auditor, or Debugger + Tester) to avoid agent fatigue and reduce token waste.
    """
    activity_log = []

    def dispatch_event(event_type: str, data: dict):
        if on_event:
            try:
                on_event(event_type, data)
            except Exception:
                pass

    def step(agent_name: str, message: str, meta: dict = None):
        line = f"[{agent_name}] {message}"
        activity_log.append(line)
        log(line)
        dispatch_event("log", {"agent": agent_name, "message": message, "meta": meta or {}})

    def model_event_forwarder(event_type: str, data: dict):
        dispatch_event(event_type, data)
        if "message" in data:
            step("TokenGuardian", data["message"])

    model_pool.set_event_callback(model_event_forwarder)

    # 1. Load project files from disk
    project_dir = os.path.join(OUTPUT_DIR, project_id)
    if not os.path.exists(project_dir):
        raise FileNotFoundError(f"Project directory '{project_dir}' not found.")

    files = {}
    readme = ""
    for root, _, filenames in os.walk(project_dir):
        for fn in filenames:
            rel = os.path.relpath(os.path.join(root, fn), project_dir).replace("\\", "/")
            full = os.path.join(root, fn)
            try:
                with open(full, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue

            if rel == "README.md":
                readme = content
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
                files[rel] = {
                    "code": content,
                    "language": lang_map.get(ext, "text"),
                    "description": f"Existing component {rel}",
                }

    step("Orchestrator", f"Received change request for '{project_id}': '{change_request}'")
    dispatch_event(
        "status",
        {
            "state": "triaging",
            "message": "Orchestrator analyzing change request & selectively routing to specialists...",
        },
    )

    # 2. Orchestrator Triages the Request
    triage_plan = _triage_change_request(change_request, files, readme[:300])
    req_agents = triage_plan.get("required_agents", ["coder", "auditor"])
    target_files = triage_plan.get("target_files", [])
    intent = triage_plan.get("intent", "feature")
    explanation = triage_plan.get("explanation", "")

    step(
        "Orchestrator",
        f"Triage Decision: Intent='{intent}'. Swarm Assigned: {', '.join(req_agents)}. Action: {explanation}",
    )
    dispatch_event("orchestrator_triage", {"plan": triage_plan})

    # 3. Selective Code Updates (Coder or Debugger)
    if "coder" in req_agents or "debugger" in req_agents:
        dispatch_event(
            "status",
            {
                "state": "coding",
                "message": f"Assigned agents executing changes on {len(target_files)} target file(s)...",
                "required_agents": req_agents,
                "target_files": [tf["path"] for tf in target_files],
            },
        )

        coder_jobs = {}
        for tf in target_files:
            p = tf["path"]
            lang = tf.get("language") or files.get(p, {}).get("language", "text")
            action = tf.get("action", "modify")
            instructions = tf.get("instructions", change_request)

            sibling_context = {
                path: f["code"] for path, f in files.items() if path != p
            }

            if action == "modify" and p in files:
                coder_jobs[p] = (
                    lambda p=p, lang=lang, existing=files[p]["code"], inst=instructions, sibs=sibling_context: (
                        coder_agent.modify_file(p, lang, existing, inst, sibs)
                    )
                )
            else:
                file_spec = {"path": p, "language": lang, "description": instructions}
                coder_jobs[p] = (
                    lambda spec=file_spec, summary=change_request, sibs=sibling_context: (
                        coder_agent.generate_file(spec, summary, sibs)
                    )
                )

        step("Code Generation", f"Updating {len(coder_jobs)} file(s) with minimal diff precision...")
        updated_code_results = _run_concurrently(coder_jobs, log, "Selective Coder/Debugger")

        # 4. Selective Auditing
        if "auditor" in req_agents:
            dispatch_event(
                "status",
                {"state": "auditing", "message": "Auditor fact-checking changed files line-by-line..."},
            )
            auditor_jobs = {}
            for p, new_code in updated_code_results.items():
                lang = files.get(p, {}).get("language", "text")
                desc = files.get(p, {}).get("description", change_request)
                sibs = {path: f["code"] for path, f in files.items() if path != p}
                auditor_jobs[p] = (
                    lambda p=p, lang=lang, code=new_code, desc=desc, sibs=sibs: (
                        auditor_agent.audit_and_refine(p, lang, code, desc, sibs)
                    )
                )

            step("Code Auditor", f"Fact-checking {len(auditor_jobs)} updated file(s)...")
            audited_results = _run_concurrently(auditor_jobs, log, "Selective Auditor")

            for p, audit in audited_results.items():
                files[p] = {
                    "language": files.get(p, {}).get("language", "text"),
                    "code": audit["code"],
                    "audit": audit,
                    "description": files.get(p, {}).get("description", ""),
                }
                removed = audit.get("unnecessary_lines_removed", 0)
                step("Code Auditor", f"Verified '{p}': {removed} unneeded lines eliminated.")
                dispatch_event(
                    "file_ready",
                    {
                        "path": p,
                        "language": files[p]["language"],
                        "code": files[p]["code"],
                        "audit": audit,
                    },
                )
        else:
            for p, new_code in updated_code_results.items():
                files[p] = {
                    "language": files.get(p, {}).get("language", "text"),
                    "code": new_code,
                    "audit": {"fact_check_passed": True, "unnecessary_lines_removed": 0},
                    "description": files.get(p, {}).get("description", ""),
                }
                dispatch_event(
                    "file_ready",
                    {
                        "path": p,
                        "language": files[p]["language"],
                        "code": new_code,
                    },
                )

    # 5. Selective QA Testing
    check_result = None
    passed = True
    if "tester" in req_agents:
        dispatch_event(
            "status",
            {"state": "testing", "message": "Testing Agent running verification on updated project..."},
        )
        step("Testing", "Running project verification suite on modified code...")
        mock_plan = {
            "project_name": project_id,
            "project_type": "project",
            "files": [{"path": p, "language": f["language"]} for p, f in files.items()],
        }
        check_result = testing_agent.run_project_checks(mock_plan, files)
        passed = check_result.get("passed", True)
        dispatch_event("testing_update", {"attempt": 1, "result": check_result})
        step(
            "Testing",
            "Checks passed!" if passed else "Testing detected issues in updated code.",
        )

    # 6. Documentation Update (if requested by manager)
    if triage_plan.get("update_readme", False) or "reviewer" in req_agents:
        dispatch_event(
            "status",
            {"state": "documenting", "message": "Reviewer Agent refreshing documentation..."},
        )
        step("Review", "Updating README.md with changes...")
        mock_plan = {
            "project_name": project_id,
            "project_type": "project",
            "summary": f"Updated with: {change_request}",
        }
        readme = reviewer_agent.write_readme(mock_plan, files)
        dispatch_event("readme_ready", {"readme": readme})

    # 7. Persist changes to disk in existing project folder
    for path, f in files.items():
        full_path = os.path.join(project_dir, path)
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as fh:
            fh.write(f["code"])

    if readme:
        with open(os.path.join(project_dir, "README.md"), "w", encoding="utf-8") as fh:
            fh.write(readme)

    step("Orchestrator", f"Surgical iteration successfully applied to disk in: {project_dir}")

    final_result = {
        "project_id": project_id,
        "files": files,
        "readme": readme,
        "triage_plan": triage_plan,
        "tests_passed": passed,
        "check_result": check_result,
        "activity_log": activity_log,
        "project_dir": project_dir,
    }

    dispatch_event("status", {"state": "completed", "result": final_result})
    return final_result

