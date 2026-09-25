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

from agents import planner_agent, coder_agent, auditor_agent, testing_agent, debugger_agent, reviewer_agent
from config import MAX_DEBUG_RETRIES, MAX_PARALLEL_WORKERS, OUTPUT_DIR


def _run_concurrently(jobs: dict, log, label: str) -> dict:
    """
    Executes multiple worker tasks concurrently using Python's ThreadPoolExecutor.
    """
    if not jobs:
        return {}

    log(f"[{label}] Launching {len(jobs)} agent(s) simultaneously: {', '.join(jobs.keys())}")
    results = {}
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        future_to_key = {executor.submit(fn): key for key, fn in jobs.items()}
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
