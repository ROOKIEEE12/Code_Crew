# Prompt for Antigravity — Upgrade CodeCrew v1 → v2

Paste this whole file into Antigravity (or tell it to open and follow this
file) inside your existing **CodeCrew** project folder. It contains
everything needed to upgrade the project from a single-function Python
generator into a real multi-agent software engineering team.

---

## Context: what you're upgrading

The current project (v1) is a working multi-agent pipeline with these
agents: Planner, Coder, Testing, Debugger, Reviewer — coordinated by
`orchestrator.py`. It only ever writes ONE Python function per run, tested
with PyTest, in a fully sequential (one agent at a time) pipeline. It uses
the Google Gemini API via `agents/llm_client.py`, which is NOT changing.

## Goal: what v2 needs to do differently

1. **Every agent keeps its own independent "brain"** — each is its own LLM
   call with its own system prompt written as a specific professional
   persona (a senior software engineer, a senior QA engineer, a debugging
   specialist), not a shared/generic prompt.
2. **Agents work simultaneously, not just in sequence.** When a project has
   multiple files that don't depend on each other, generate/fix them all
   AT THE SAME TIME using real concurrency (Python threads — LLM calls are
   network I/O, so threads give genuine parallelism here), the way
   different developers on a real team pick up different tickets at once.
3. **The Coder Agent supports ANY language**, not just Python — whatever
   language actually fits the user's request (HTML/CSS/JS for a website,
   Python for a script/backend, etc.), decided by the Planner.
4. **The system must be able to build ANYTHING the user describes** — a
   single function, a CLI tool, or a full multi-file website/app — not
   just one Python function every time.
5. **Testing must adapt to whatever was built**: real PyTest execution for
   Python files, real syntax checks for languages where a checker is
   available locally (Node.js for JS/TS, Python's stdlib for HTML/CSS/JSON),
   AND a language-agnostic LLM "senior QA engineer" review of the whole
   project together — this last one is what catches cross-file logic bugs
   (e.g. JavaScript referencing an HTML element ID that doesn't actually
   exist) that no syntax checker could ever catch.
6. **Debugging fixes only the specific broken file(s)**, and can fix
   several different broken files at the same time (same concurrency
   mechanism as code generation).
7. Finished projects get saved to a real folder on disk
   (`generated_projects/<project-name>-<timestamp>/`) instead of just being
   printed to the screen.

## How to apply this document

For each file below:
- If it says **CREATE**, it's a new file — create it at that exact path.
- If it says **REPLACE**, overwrite the entire existing file with the given
  content (don't merge/patch — replace it completely).
- Preserve the project's existing `.env`, `.env.example`, `requirements.txt`,
  and `.gitignore` as-is (no changes needed there — no new dependencies
  are required; everything new uses Python's standard library).
- After making all the changes, run the verification steps at the very end
  of this document BEFORE telling the user it's done.

---

## CREATE: `agents/language_utils.py`

````python
"""
language_utils.py
-------------------
CodeCrew's Coder Agent can write code in ANY language, because it's just an
LLM producing text. But *automatically running* code to verify it needs the
right tool installed for that language (a Python interpreter, Node.js, a
Java compiler, etc.) — and we can't assume every one of those is installed
on every student's laptop.

So this module is honest about that: it checks what's actually available
on THIS machine, and only runs a real syntax check for languages it has a
tool for. For everything else, `checked` comes back False, and the Testing
Agent falls back to an LLM-based code review instead (see testing_agent.py)
— so the project never silently skips verification, it just uses a
different kind of verification when a compiler isn't available.
"""

import html.parser
import os
import shutil
import subprocess
import sys
import tempfile

EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".json": "json",
    ".md": "markdown",
}


def detect_language(file_path: str) -> str:
    _, ext = os.path.splitext(file_path)
    return EXTENSION_TO_LANGUAGE.get(ext.lower(), "text")


class _HTMLValidityParser(html.parser.HTMLParser):
    """A very forgiving parser — we only care whether Python's own parser
    can get through the document without raising an exception."""
    pass


def _check_python(code: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", path],
            capture_output=True, text=True, timeout=15,
        )
        return {"checked": True, "passed": result.returncode == 0, "output": result.stderr}
    finally:
        os.unlink(path)
        cache_dir = os.path.join(os.path.dirname(path), "__pycache__")
        shutil.rmtree(cache_dir, ignore_errors=True)


def _check_node_syntax(code: str, suffix: str) -> dict:
    node = shutil.which("node")
    if not node:
        return {"checked": False, "passed": True, "output": "Node.js not installed — skipped."}
    with tempfile.NamedTemporaryFile(suffix=suffix, mode="w", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        result = subprocess.run(
            [node, "--check", path], capture_output=True, text=True, timeout=15,
        )
        return {"checked": True, "passed": result.returncode == 0, "output": result.stderr}
    finally:
        os.unlink(path)


def _check_html(code: str) -> dict:
    parser = _HTMLValidityParser()
    try:
        parser.feed(code)
        return {"checked": True, "passed": True, "output": ""}
    except Exception as e:  # pragma: no cover - HTMLParser is very forgiving
        return {"checked": True, "passed": False, "output": str(e)}


def _check_css_braces(code: str) -> dict:
    # Not a real CSS parser — just a sanity check that braces balance.
    opens, closes = code.count("{"), code.count("}")
    passed = opens == closes
    output = "" if passed else f"Mismatched braces: {opens} '{{' vs {closes} '}}'"
    return {"checked": True, "passed": passed, "output": output}


def _check_json(code: str) -> dict:
    import json
    try:
        json.loads(code)
        return {"checked": True, "passed": True, "output": ""}
    except json.JSONDecodeError as e:
        return {"checked": True, "passed": False, "output": str(e)}


def check_syntax(language: str, code: str) -> dict:
    """
    Returns {"checked": bool, "passed": bool, "output": str}.
    `checked=False` means "we don't have a tool for this language on this
    machine" — the caller should NOT treat that as a failure, just as
    "no automated check ran, rely on the LLM review instead."
    """
    if language == "python":
        return _check_python(code)
    if language == "javascript":
        return _check_node_syntax(code, ".js")
    if language == "typescript":
        return _check_node_syntax(code, ".ts")
    if language == "html":
        return _check_html(code)
    if language == "css":
        return _check_css_braces(code)
    if language == "json":
        return _check_json(code)

    return {"checked": False, "passed": True, "output": f"No local syntax checker for '{language}' — skipped."}
````

## REPLACE: `config.py`

````python
"""
config.py
---------
Loads settings from a .env file so we never hard-code secrets in the code.

Beginner note: a ".env" file is just a plain text file with KEY=VALUE lines.
python-dotenv reads it and puts those values into os.environ for us.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # reads the .env file in the project root, if it exists

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Google periodically retires older free-tier models for new API keys.
# gemini-3.5-flash-lite is the current recommended lightweight/free-tier
# model as of mid-2026. If Google ever returns a 404 "model not found" or
# "no longer available" error, check https://ai.google.dev/gemini-api/docs/models
# for the current model name and update this default (or set GEMINI_MODEL
# in your .env file instead of editing this file).
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# How many times the Debugging Agent will try to fix a broken file before
# the Orchestrator gives up on it and moves on with the best attempt.
MAX_DEBUG_RETRIES = int(os.getenv("MAX_DEBUG_RETRIES", "3"))

# How many agents are allowed to work AT THE SAME TIME (e.g. multiple Coder
# Agents each writing a different file simultaneously, like different
# developers on a real team). Higher = faster for multi-file projects, but
# uses more API quota at once. 4 is a safe default for a free-tier key.
MAX_PARALLEL_WORKERS = int(os.getenv("MAX_PARALLEL_WORKERS", "4"))

# Where finished projects get saved. Each run creates its own timestamped
# sub-folder here so nothing ever gets overwritten.
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "generated_projects")
````

## REPLACE: `agents/code_utils.py`

````python
"""
code_utils.py
-------------
Small shared helpers used by multiple agents.
"""

import json
import re


def clean_code_block(text: str) -> str:
    """
    LLMs love wrapping code in ```python ... ``` fences even when you ask
    them not to — this strips that off so we always end up with clean,
    runnable source code.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop the opening ```language line
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]  # drop the closing ```
        text = "\n".join(lines)
    return text.strip()


def parse_json_response(text: str) -> dict:
    """
    The Planner and the QA Reviewer agents are asked to respond with pure
    JSON, but LLMs sometimes wrap it in markdown fences or add a stray
    sentence before/after anyway. This tries a few increasingly forgiving
    strategies to still get a usable dict out of it.
    """
    text = clean_code_block(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: grab the outermost { ... } block and try again.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(
        "Could not parse JSON from the model's response. Raw response was:\n" + text
    )
````

## REPLACE: `agents/planner_agent.py`

````python
"""
planner_agent.py
-----------------
Job: act like a tech lead. Read the user's plain-language request — which
could be "a function that reverses a string" OR "a full portfolio website"
— and turn it into a concrete, structured project plan: what kind of
project this is, which files need to exist, what language each is in, what
each file is responsible for, and which other files it depends on.

Every other agent in the system works off THIS plan.
"""

from agents.llm_client import call_llm
from agents.code_utils import parse_json_response

SYSTEM_PROMPT = """You are the Planner Agent — the tech lead of an AI software
engineering team. You turn a plain-language request into a concrete,
buildable project plan for your team (a Coder Agent, a Testing Agent, a
Debugging Agent, and a Review Agent).

The request could be tiny (one function) or big (a full multi-page website,
a small game, a CLI tool, a REST API, etc). Pick whatever project type and
tech stack genuinely fits the request best. Don't be afraid of multiple
files and real languages (HTML/CSS/JS for websites, Python for scripts and
backends, etc).

Respond with ONLY a single JSON object, no markdown fences, no commentary,
in EXACTLY this shape:

{
  "project_name": "short-kebab-case-name",
  "project_type": "script | cli_tool | web_app | backend_api | library | other",
  "summary": "2-3 sentences describing what will be built and how the pieces fit together",
  "files": [
    {
      "path": "relative/file/path.ext",
      "language": "python | javascript | typescript | html | css | java | cpp | other",
      "description": "what this specific file is responsible for, in detail",
      "depends_on": ["other/file/path.ext", "..."]
    }
  ]
}

Rules:
- "depends_on" lists other files in THIS SAME plan whose contents this file
  needs to stay consistent with (e.g. a script.js that manipulates specific
  HTML element IDs depends_on the html file that defines those IDs).
- Keep the file list as small as it can genuinely be while still fully
  satisfying the request — don't over-engineer a simple request into 15
  files, and don't under-scope a real app into one giant file either.
- Every project must be runnable/openable by a beginner using only a
  standard Python install and a web browser (assume Node.js, Java, etc. may
  NOT be installed — prefer Python and/or plain HTML/CSS/JS unless the
  request specifically demands another language).
"""


def plan(user_request: str) -> dict:
    raw = call_llm(SYSTEM_PROMPT, f"User request: {user_request}")
    project_plan = parse_json_response(raw)

    # Basic sanity defaults so a slightly malformed LLM response doesn't
    # crash the rest of the pipeline.
    project_plan.setdefault("project_name", "codecrew-project")
    project_plan.setdefault("project_type", "other")
    project_plan.setdefault("summary", "")
    project_plan.setdefault("files", [])
    for f in project_plan["files"]:
        f.setdefault("depends_on", [])
        f.setdefault("language", "text")

    return project_plan
````

## REPLACE: `agents/coder_agent.py`

````python
"""
coder_agent.py
--------------
Job: write ONE file of the project, in whatever language the Planner
assigned it, as if you're a senior engineer on a real team — meaning you
pay attention to how your file needs to work together with the other files
your teammates are writing (matching HTML element IDs, function names,
API routes, imports, etc).

Multiple Coder Agents (one per file) can run at the same time — see
orchestrator.py, which dispatches independent files concurrently, the same
way independent tickets get picked up by different developers on a team.
"""

from agents.llm_client import call_llm
from agents.code_utils import clean_code_block

SYSTEM_PROMPT_TEMPLATE = """You are a senior {language} software engineer with
10+ years of professional experience. You write clean, correct, secure,
production-quality code, and you think through edge cases before writing a
single line — the way a top engineer at a great company would.

You are one member of a coordinated engineering team building a project
together. You are personally responsible for exactly ONE file: {path}

Rules:
- Return ONLY the final content of this file. No explanations, no markdown
  fences, no commentary before or after.
- Write complete, real, working code — never leave TODOs, "implement this
  later" comments, or placeholder stubs.
- If other files' contents are shown to you below, your file MUST integrate
  correctly with them: match element IDs, function/class names, imports,
  API routes, and data formats EXACTLY.
- Add brief comments where they genuinely help someone reading the code,
  but don't over-comment obvious lines.
"""


def generate_file(file_spec: dict, project_summary: str, dependency_contents: dict) -> str:
    """
    file_spec: one entry from the plan's "files" list
               ({"path", "language", "description", "depends_on"})
    project_summary: the plan's overall "summary" string, for context
    dependency_contents: {path: code} for files in file_spec["depends_on"]
                          that have ALREADY been generated
    """
    language = file_spec.get("language", "text")
    path = file_spec["path"]
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(language=language, path=path)

    prompt_parts = [
        f"Project summary: {project_summary}",
        f"\nYour file: {path}",
        f"Purpose of this file: {file_spec.get('description', '')}",
    ]

    if dependency_contents:
        prompt_parts.append("\nOther files you must stay compatible with:")
        for dep_path, dep_code in dependency_contents.items():
            prompt_parts.append(f"\n--- {dep_path} ---\n{dep_code}")
    else:
        prompt_parts.append("\n(This file has no dependencies on other files.)")

    user_prompt = "\n".join(prompt_parts)
    code = call_llm(system_prompt, user_prompt)
    return clean_code_block(code)
````

## REPLACE: `agents/testing_agent.py`

````python
"""
testing_agent.py
-----------------
Job: verify the whole project, not just one file. This agent does THREE
layers of checking, combined:

1. Syntax/structure checks per file, using whatever real tool is available
   on this machine for that language (see language_utils.py). Python is
   always checked. JS/TS is checked if Node.js happens to be installed.
   Other languages fall back to "not checked here" rather than lying about
   having verified them.

2. For Python files specifically: real PyTest tests are generated AND
   actually executed in an isolated temp folder (with every Python file in
   the project copied in, so imports between your own files work).

3. An LLM-based senior QA review of the ENTIRE project together — this is
   what catches logic bugs, security issues, and cross-file inconsistencies
   that a syntax checker can never catch, and it works for every language
   equally since it's just reading code, not executing it.
"""

import os
import shutil
import subprocess
import sys
import tempfile

from agents.llm_client import call_llm
from agents.code_utils import clean_code_block, parse_json_response
from agents import language_utils

PYTEST_SYSTEM_PROMPT = """You are the Testing Agent. You will receive a
Python file's purpose and its full code. Write PyTest test cases covering
normal cases and realistic edge cases.

Rules:
- Return ONLY Python test code. No explanations, no markdown fences.
- The module will be importable using its filename without the .py
  extension. Import exactly what you need from it.
- Write at least 3 test functions.
"""

QA_REVIEW_SYSTEM_PROMPT = """You are the Testing Agent, acting as a senior QA
engineer reviewing a teammate's completed project before it ships. You will
be shown every file in the project. Look for real bugs: logic errors,
off-by-one mistakes, broken references between files (e.g. JS code
targeting an HTML element ID that doesn't exist, a Python import for a
function that isn't actually defined anywhere), unhandled edge cases, and
obvious security issues.

Respond with ONLY a single JSON object, no markdown fences, no commentary,
in EXACTLY this shape:

{
  "passed": true or false,
  "issues": [
    {"file": "path/that/has/the/problem.ext", "problem": "clear description", "severity": "high | medium | low"}
  ]
}

"passed" should be false if there are any "high" severity issues. Minor
style nitpicks are not issues — only report things that would actually
break or meaningfully harm the project.
"""


def _run_python_tests(files: dict) -> dict:
    """
    Copies every Python file in the project into one temp folder (so they
    can import each other), generates tests for each one, and runs the
    whole test suite together with a single real pytest subprocess call.
    """
    python_files = {p: f for p, f in files.items() if f["language"] == "python"}
    if not python_files:
        return {"ran": False, "passed": True, "output": "No Python files in this project.", "generated_tests": {}}

    with tempfile.TemporaryDirectory() as tmp_dir:
        for path, f in python_files.items():
            full_path = os.path.join(tmp_dir, os.path.basename(path))
            with open(full_path, "w") as fh:
                fh.write(f["code"])

        generated_tests = {}
        for path, f in python_files.items():
            module_name = os.path.splitext(os.path.basename(path))[0]
            prompt = f"Module name to import from: {module_name}\n\nCode:\n{f['code']}"
            raw = call_llm(PYTEST_SYSTEM_PROMPT, prompt)
            test_code = clean_code_block(raw)
            generated_tests[path] = test_code

            test_file = os.path.join(tmp_dir, f"test_{module_name}.py")
            with open(test_file, "w") as fh:
                fh.write(test_code)

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", ".", "-v"],
                cwd=tmp_dir, capture_output=True, text=True, timeout=45,
            )
            passed = result.returncode == 0
            output = result.stdout + "\n" + result.stderr
        except subprocess.TimeoutExpired:
            passed = False
            output = "Tests timed out after 45 seconds (possible infinite loop)."

        return {"ran": True, "passed": passed, "output": output, "generated_tests": generated_tests}


def _llm_review(plan: dict, files: dict) -> dict:
    parts = [f"Project summary: {plan.get('summary', '')}", ""]
    for path, f in files.items():
        parts.append(f"--- {path} ({f['language']}) ---\n{f['code']}\n")
    raw = call_llm(QA_REVIEW_SYSTEM_PROMPT, "\n".join(parts))
    try:
        review = parse_json_response(raw)
        review.setdefault("passed", True)
        review.setdefault("issues", [])
        return review
    except ValueError:
        # If the reviewer's JSON is unparsable, don't crash the pipeline —
        # just treat it as "no structured issues found."
        return {"passed": True, "issues": [], "raw": raw}


def run_project_checks(plan: dict, files: dict) -> dict:
    """
    files: {path: {"language": str, "code": str}}
    Returns a combined report the Orchestrator uses to decide what (if
    anything) needs to go back to the Debugging Agent.
    """
    syntax_results = {
        path: language_utils.check_syntax(f["language"], f["code"])
        for path, f in files.items()
    }

    pytest_result = _run_python_tests(files)
    review = _llm_review(plan, files)

    syntax_ok = all(r["passed"] for r in syntax_results.values() if r["checked"])
    high_severity_issues = [i for i in review["issues"] if i.get("severity") == "high"]

    overall_passed = syntax_ok and pytest_result["passed"] and not high_severity_issues and review["passed"]

    return {
        "passed": overall_passed,
        "syntax_results": syntax_results,
        "pytest": pytest_result,
        "review": review,
    }


def files_needing_fixes(check_result: dict, all_paths: list) -> dict:
    """
    Turns the combined check_result into {path: "human-readable reason(s)
    this file needs fixing"} so the Debugging Agent has something concrete
    per file. A file with no entry needs no changes.
    """
    reasons = {}

    for path, result in check_result["syntax_results"].items():
        if result["checked"] and not result["passed"]:
            reasons.setdefault(path, []).append(f"Syntax error:\n{result['output']}")

    if not check_result["pytest"]["passed"] and check_result["pytest"]["ran"]:
        # We don't know exactly which python file(s) caused it, so flag all
        # of them — cheap to re-check, and usually it's obvious from output.
        for path in all_paths:
            if path.endswith(".py"):
                reasons.setdefault(path, []).append(
                    f"Project's pytest suite failed:\n{check_result['pytest']['output']}"
                )

    for issue in check_result["review"]["issues"]:
        if issue.get("severity") in ("high", "medium"):
            reasons.setdefault(issue["file"], []).append(
                f"QA review ({issue.get('severity')}): {issue['problem']}"
            )

    return {path: "\n\n".join(msgs) for path, msgs in reasons.items()}
````

## REPLACE: `agents/debugger_agent.py`

````python
"""
debugger_agent.py
------------------
Job: fix ONE broken file. It receives that file's own code, a description
of what's wrong (syntax error output, failing test output, or a QA review
comment — whatever the Testing Agent found), and a short reminder of what
its sibling files look like, then returns a corrected, complete version.

Multiple broken files can be fixed at the same time by the Orchestrator
(each gets its own Debugging Agent call), the same way two different bugs
in two different files could be picked up by two developers at once.
"""

from agents.llm_client import call_llm
from agents.code_utils import clean_code_block

SYSTEM_PROMPT_TEMPLATE = """You are a senior {language} debugging specialist.
You will receive one file's code and a description of what's wrong with it
(a syntax error, a failing test, or a code review finding). Find the real
root cause and return a corrected, COMPLETE version of the file.

Rules:
- Return ONLY the corrected file content. No explanations, no markdown
  fences, no commentary.
- Fix the actual underlying problem — never just silence an error without
  addressing why it happened.
- Keep everything about the file that already works unchanged.
"""


def debug(path: str, language: str, code: str, issue_description: str, sibling_summary: str) -> str:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(language=language)
    user_prompt = (
        f"File: {path}\n\n"
        f"Current code:\n{code}\n\n"
        f"What's wrong:\n{issue_description}\n\n"
        f"Other files in this project (for context, do not rewrite these):\n{sibling_summary}"
    )
    fixed_code = call_llm(system_prompt, user_prompt)
    return clean_code_block(fixed_code)
````

## REPLACE: `agents/reviewer_agent.py`

````python
"""
reviewer_agent.py
------------------
Job: final polish on the whole project. Takes the finished (tested) project
and writes a proper README.md explaining what it is, its file structure,
and exactly how to run/open it — written for whoever receives this project
next, who wasn't part of building it.
"""

from agents.llm_client import call_llm
from agents.code_utils import clean_code_block

SYSTEM_PROMPT = """You are the Review/Documentation Agent, finishing up a
completed and tested project before handoff. Write a clear, well-organized
README.md for it.

Rules:
- Return ONLY the README's Markdown content. No commentary outside it.
- Include: what the project does, its file structure, and step-by-step
  instructions for actually running or opening it (be specific: exact
  commands, or "open index.html in your browser", etc. based on the
  project type and files given).
- Keep it practical and beginner-friendly. No filler.
"""


def write_readme(plan: dict, files: dict) -> str:
    file_list = "\n".join(f"- {path} ({f['language']})" for path, f in files.items())
    prompt = (
        f"Project name: {plan.get('project_name')}\n"
        f"Project type: {plan.get('project_type')}\n"
        f"Summary: {plan.get('summary')}\n\n"
        f"Files:\n{file_list}"
    )
    readme = call_llm(SYSTEM_PROMPT, prompt)
    return clean_code_block(readme)
````

## REPLACE: `orchestrator.py`

````python
"""
orchestrator.py
-----------------
This is the brain of CodeCrew. It turns a Planner's project plan into
actual files by dispatching Coder Agents — running independent files'
agents AT THE SAME TIME, the way independent tickets get picked up by
different developers on a real team — then runs the Testing Agent, and
loops broken files through the Debugging Agent (again, in parallel where
possible) until everything passes or the retry limit is hit.
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from agents import planner_agent, coder_agent, testing_agent, debugger_agent, reviewer_agent
from config import MAX_DEBUG_RETRIES, MAX_PARALLEL_WORKERS, OUTPUT_DIR


def _run_concurrently(jobs: dict, log, label: str) -> dict:
    """
    jobs: {key: zero-arg callable}
    Runs every job in a thread pool (LLM calls are network I/O, so threads
    give real concurrency here even though Python has a GIL) and returns
    {key: result}. Logging happens before/after the whole batch rather than
    from inside worker threads, to keep it simple and safe.
    """
    if not jobs:
        return {}

    log(f"[{label}] Starting {len(jobs)} agent(s) simultaneously: {', '.join(jobs.keys())}")
    results = {}
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        future_to_key = {executor.submit(fn): key for key, fn in jobs.items()}
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            results[key] = future.result()
    log(f"[{label}] All {len(jobs)} finished.")
    return results


def _compute_waves(files_spec: list) -> list:
    """
    Groups files into "waves" based on their depends_on lists, so files
    with no unmet dependencies can be built in parallel, then the next
    wave (whose dependencies are now satisfied) runs, and so on.
    """
    remaining = {f["path"]: f for f in files_spec}
    done = set()
    waves = []

    while remaining:
        wave = [f for f in remaining.values() if all(dep in done for dep in f["depends_on"])]
        if not wave:
            # Circular or missing dependency reference — build everything
            # that's left in one final wave rather than looping forever.
            wave = list(remaining.values())
        waves.append(wave)
        for f in wave:
            done.add(f["path"])
            del remaining[f["path"]]

    return waves


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", name.strip().lower()).strip("-")
    return slug or "codecrew-project"


def run_pipeline(user_request: str, log=print) -> dict:
    """
    Runs the full CodeCrew pipeline for one request, which may produce
    ONE file or an entire multi-file, multi-language project.

    Returns a dict with the plan, the final files, whether checks passed,
    the full activity log, and the on-disk path the project was saved to.
    """
    activity_log = []

    def step(agent_name: str, message: str):
        line = f"[{agent_name}] {message}"
        activity_log.append(line)
        log(line)

    step("Orchestrator", f"Received request: {user_request}")

    # ---------- 1. Planning ----------
    step("Planner", "Analyzing the request and designing the project...")
    plan = planner_agent.plan(user_request)
    file_specs = plan["files"]
    step("Planner", f"Plan ready: '{plan['project_name']}' ({plan['project_type']}), {len(file_specs)} file(s).")

    # ---------- 2. Concurrent code generation, wave by wave ----------
    files = {}  # path -> {"language": str, "code": str}
    waves = _compute_waves(file_specs)
    for i, wave in enumerate(waves, start=1):
        jobs = {}
        for f in wave:
            dep_contents = {dep: files[dep]["code"] for dep in f["depends_on"] if dep in files}
            jobs[f["path"]] = (
                lambda f=f, dep_contents=dep_contents: coder_agent.generate_file(f, plan["summary"], dep_contents)
            )
        step("Code Generation", f"Wave {i}/{len(waves)}: writing {len(wave)} file(s)...")
        results = _run_concurrently(jobs, log, f"Code Generation - Wave {i}")
        for f in wave:
            files[f["path"]] = {"language": f.get("language", "text"), "code": results[f["path"]]}
    step("Code Generation", f"All {len(files)} file(s) written.")

    # ---------- 3. Test / review / debug loop ----------
    passed = False
    check_result = None
    for attempt in range(1, MAX_DEBUG_RETRIES + 1):
        step("Testing", f"Running checks on the whole project (attempt {attempt} of {MAX_DEBUG_RETRIES})...")
        check_result = testing_agent.run_project_checks(plan, files)

        if check_result["passed"]:
            step("Testing", "All checks passed.")
            passed = True
            break

        broken = testing_agent.files_needing_fixes(check_result, list(files.keys()))
        if not broken:
            # Nothing concrete to fix but "passed" was False (e.g. reviewer
            # JSON was odd) — don't loop forever on nothing actionable.
            step("Testing", "No specific file issues identified; stopping here.")
            break

        preview = "; ".join(f"{p}: {msg.splitlines()[0]}" for p, msg in broken.items())
        step("Testing", f"Issues found in {len(broken)} file(s) — {preview}")

        jobs = {}
        for path, issue_text in broken.items():
            sibling_summary = "\n".join(f"- {p} ({f['language']})" for p, f in files.items() if p != path)
            jobs[path] = (
                lambda path=path, issue_text=issue_text, sibling_summary=sibling_summary: debugger_agent.debug(
                    path, files[path]["language"], files[path]["code"], issue_text, sibling_summary
                )
            )
        step("Debugging", f"Fixing {len(jobs)} file(s) simultaneously...")
        fixed = _run_concurrently(jobs, log, f"Debugging - Attempt {attempt}")
        for path, new_code in fixed.items():
            files[path]["code"] = new_code

    if not passed:
        step("Orchestrator", "Hit the retry limit — proceeding with the best attempt made.")

    # ---------- 4. Review / documentation ----------
    step("Review", "Writing project README...")
    readme = reviewer_agent.write_readme(plan, files)

    # ---------- 5. Save to disk ----------
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project_dir = os.path.join(OUTPUT_DIR, f"{_slugify(plan['project_name'])}-{timestamp}")
    for path, f in files.items():
        full_path = os.path.join(project_dir, path)
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
        with open(full_path, "w") as fh:
            fh.write(f["code"])
    with open(os.path.join(project_dir, "README.md"), "w") as fh:
        fh.write(readme)

    step("Orchestrator", f"Saved project to: {project_dir}")
    step("Orchestrator", "Pipeline complete.")

    return {
        "plan": plan,
        "files": files,
        "readme": readme,
        "tests_passed": passed,
        "check_result": check_result,
        "activity_log": activity_log,
        "project_dir": project_dir,
    }
````

## REPLACE: `cli.py`

````python
"""
cli.py
------
The simplest possible way to try CodeCrew — no browser needed.
Run: python cli.py
"""

from orchestrator import run_pipeline


def main():
    print("=== CodeCrew: Multi-Agent Software Engineering Team ===")
    request = input("Describe what you want built: ").strip()

    if not request:
        print("You didn't type anything — try again.")
        return

    print()
    result = run_pipeline(request)

    print("\n" + "=" * 60)
    print(f"PROJECT: {result['plan']['project_name']}  ({result['plan']['project_type']})")
    print("=" * 60)
    print(result["plan"]["summary"])

    print(f"\nFiles ({len(result['files'])}):")
    for path in result["files"]:
        print(f"  - {path}")

    status = "ALL CHECKS PASSED ✅" if result["tests_passed"] else "SOME ISSUES REMAIN ⚠️ (best attempt saved)"
    print(f"\nStatus: {status}")
    print(f"Saved to: {result['project_dir']}")


if __name__ == "__main__":
    main()
````

## REPLACE: `app.py`

````python
"""
app.py
------
A web interface for CodeCrew, built with Streamlit.
Run: streamlit run app.py

Describe anything from a single function to a full website. Watch every
agent's progress live, then browse the generated files, download the whole
project as a zip, and see whether all checks passed.
"""

import io
import zipfile

import streamlit as st
from orchestrator import run_pipeline

st.set_page_config(page_title="CodeCrew", page_icon="🤖", layout="wide")

st.title("🤖 CodeCrew — Multi-Agent Software Engineering Team")
st.caption(
    "Describe what you want built — a single function, or a full website. "
    "A team of AI agents will plan, code, test, debug, and document it."
)

request = st.text_area(
    "What do you want built?",
    placeholder="e.g. A personal portfolio website with a home page, an about section, and a contact form.",
    height=100,
)

if st.button("🚀 Build it", type="primary") and request.strip():
    log_placeholder = st.empty()
    logs = []

    def live_log(message: str):
        logs.append(message)
        log_placeholder.code("\n".join(logs), language=None)

    with st.spinner("The team is working..."):
        result = run_pipeline(request, log=live_log)

    plan = result["plan"]
    files = result["files"]

    if result["tests_passed"]:
        st.success(f"✅ '{plan['project_name']}' is done — all checks passed!")
    else:
        st.warning(f"⚠️ '{plan['project_name']}' finished, but some issues remain after retries.")

    st.subheader(plan["project_name"])
    st.write(plan["summary"])
    st.caption(f"Saved to: `{result['project_dir']}`")

    # Zip everything up for a one-click download
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, f in files.items():
            zf.writestr(path, f["code"])
        zf.writestr("README.md", result["readme"])
    st.download_button(
        "⬇️ Download project as .zip",
        data=zip_buffer.getvalue(),
        file_name=f"{plan['project_name']}.zip",
        mime="application/zip",
    )

    tab_names = list(files.keys()) + ["README.md"]
    tabs = st.tabs(tab_names)
    for tab, path in zip(tabs, files.keys()):
        with tab:
            st.code(files[path]["code"], language=files[path]["language"])
    with tabs[-1]:
        st.markdown(result["readme"])

    with st.expander("🔍 Testing & QA report"):
        cr = result["check_result"]
        if cr:
            st.write("**Syntax checks:**")
            for path, r in cr["syntax_results"].items():
                icon = "✅" if r["passed"] else ("⏭️" if not r["checked"] else "❌")
                st.text(f"{icon} {path}")
            st.write("**Python test suite:**", "✅ passed" if cr["pytest"]["passed"] else "❌ failed")
            if cr["review"]["issues"]:
                st.write("**QA review findings:**")
                for issue in cr["review"]["issues"]:
                    st.text(f"[{issue.get('severity', '?')}] {issue['file']}: {issue['problem']}")
            else:
                st.write("**QA review findings:** none")

    with st.expander("🪵 Full agent activity log"):
        st.text("\n".join(result["activity_log"]))
````

## REPLACE: `demo_offline_test.py`

````python
"""
demo_offline_test.py
----------------------
Run this BEFORE you even have a Gemini API key: `python demo_offline_test.py`

It proves the v2 orchestration logic works — concurrent multi-file
generation, real syntax/pytest checks, an LLM-style QA review layer, and
the debug-retry loop — by faking the LLM responses instead of calling the
real API. This scenario builds a tiny 3-file website:

  - index.html and styles.css have NO dependency on each other, so the
    Orchestrator generates them AT THE SAME TIME (wave 1).
  - script.js depends on index.html, so it's generated after (wave 2).
  - script.js is written with a bug on purpose: it looks for an HTML
    element ID that doesn't actually match index.html. This is NOT a
    syntax error (both files are individually valid) — it's exactly the
    kind of cross-file bug only the QA Review agent can catch, which is
    the point of this demo.
  - The Debugging Agent fixes it, and the second QA review passes.

Fake responses are chosen based on WHICH agent is asking and, for the
Coder agent, WHICH file it's writing — not by call order — so this stays
correct no matter how the retry loop or thread scheduling plays out.
"""

import re
import threading
from unittest.mock import patch

PLAN_JSON = """{
  "project_name": "demo-counter-website",
  "project_type": "web_app",
  "summary": "A tiny website with a button that increments a counter shown on the page.",
  "files": [
    {"path": "index.html", "language": "html", "description": "Page with a button and a counter display.", "depends_on": []},
    {"path": "styles.css", "language": "css", "description": "Basic styling for the page.", "depends_on": []},
    {"path": "script.js", "language": "javascript", "description": "Increments the counter when the button is clicked.", "depends_on": ["index.html"]}
  ]
}"""

HTML_CODE = """<!DOCTYPE html>
<html>
<head>
  <title>Counter</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <h1>Click Counter</h1>
  <span id="countDisplay">0</span>
  <button id="incrementBtn">Click me</button>
  <script src="script.js"></script>
</body>
</html>
"""

CSS_CODE = """body {
  font-family: sans-serif;
  text-align: center;
  margin-top: 4rem;
}

button {
  padding: 0.5rem 1rem;
  font-size: 1rem;
}
"""

BUGGY_JS = """let count = 0;
const button = document.getElementById("increment-btn");
const display = document.getElementById("countDisplay");

button.addEventListener("click", function () {
  count += 1;
  display.textContent = count;
});
"""

FIXED_JS = """let count = 0;
const button = document.getElementById("incrementBtn");
const display = document.getElementById("countDisplay");

button.addEventListener("click", function () {
  count += 1;
  display.textContent = count;
});
"""

REVIEW_FAIL_JSON = """{
  "passed": false,
  "issues": [
    {"file": "script.js", "problem": "getElementById(\\"increment-btn\\") does not match the actual id \\"incrementBtn\\" in index.html, so the button will be null and clicking it will throw an error.", "severity": "high"}
  ]
}"""

REVIEW_PASS_JSON = """{"passed": true, "issues": []}"""

README_CONTENT = """# Demo Counter Website

A tiny website with a button that increments a counter on the page.

## Files
- `index.html` — the page structure
- `styles.css` — styling
- `script.js` — click handling logic

## How to run
Open `index.html` directly in any web browser.
"""

_qa_call_count = {"n": 0}
_lock = threading.Lock()


def fake_call_llm(system_prompt, user_prompt):
    if "Planner Agent" in system_prompt:
        return PLAN_JSON

    if "responsible for exactly ONE file" in system_prompt:
        match = re.search(r"Your file: (\S+)", user_prompt)
        path = match.group(1) if match else None
        if path == "index.html":
            return HTML_CODE
        if path == "styles.css":
            return CSS_CODE
        if path == "script.js":
            return BUGGY_JS
        raise ValueError(f"Demo doesn't know how to fake a Coder response for: {path}")

    if "acting as a senior QA" in system_prompt:
        with _lock:
            _qa_call_count["n"] += 1
            call_number = _qa_call_count["n"]
        return REVIEW_FAIL_JSON if call_number == 1 else REVIEW_PASS_JSON

    if "debugging specialist" in system_prompt:
        return FIXED_JS

    if "Review/Documentation Agent" in system_prompt:
        return README_CONTENT

    if "PyTest test cases" in system_prompt:
        raise AssertionError("This demo has no Python files — pytest generation should not be called.")

    raise ValueError("Unrecognized agent system prompt in demo mock:\n" + system_prompt[:200])


with patch("agents.llm_client.call_llm", side_effect=fake_call_llm):
    from orchestrator import run_pipeline

    result = run_pipeline("A website with a button that counts how many times it's clicked")

    print("\n" + "=" * 60)
    print("SELF-TEST RESULT")
    print("=" * 60)
    print("Tests passed:", result["tests_passed"])
    print("Files generated:", list(result["files"].keys()))
    print("Saved to:", result["project_dir"])
    print("QA review calls made:", _qa_call_count["n"], "(expected 2: one fail, one pass after the fix)")

    assert result["tests_passed"] is True, "Expected the pipeline to pass after the debug retry"
    assert _qa_call_count["n"] == 2, "Expected exactly 2 QA review rounds (fail, then pass)"
    assert "incrementBtn" in result["files"]["script.js"]["code"], "Expected the FIXED script.js to be what got saved"
    print("\n✅ ALL SELF-TEST ASSERTIONS PASSED — concurrent multi-file pipeline works correctly.")
````

## REPLACE: `README.md`

````markdown
# CodeCrew v2 — Multi-Agent AI Software Engineering Team

A team of independent AI agents — **Planner, Coder(s), Tester, Debugger,
Reviewer** — that plan, write, test, debug, and document real software
together, coordinated by an Orchestrator. Unlike v1 (which only wrote a
single Python function), v2 can build **entire multi-file, multi-language
projects** — a website, a CLI tool, a small backend — the same way a real
small dev team would split up the work.

This guide assumes you've never done this before. Follow it top to bottom.

---

## 1. What changed from v1 — and why

You asked for something closer to how a real IT team works: every agent
thinking for itself, coding in whatever language actually fits the request,
and multiple agents working **at the same time** instead of one after
another. Here's what that means concretely:

| | v1 | v2 |
|---|---|---|
| Output | One Python function | A full project: any number of files, any mix of languages |
| Coder Agent | Always Python | Writes HTML, CSS, JavaScript, Python, or anything else the Planner assigns it |
| Concurrency | Fully sequential | Independent files are coded **simultaneously** by separate Coder Agent calls (real thread-based concurrency) |
| Testing | Only ran pytest | Runs pytest (for Python files) **+** real syntax checks per language **+** an LLM "senior QA engineer" review of the whole project together, which catches cross-file logic bugs syntax checkers can't see |
| Debugging | Fixed one file | Fixes only the specific broken file(s), and can fix several different broken files at the same time |
| Output location | Printed to screen | Saved as a real project folder under `generated_projects/`, ready to open |

**Read `orchestrator.py` first** — it's the actual multi-agent coordination
logic (the wave-based scheduling + concurrency + retry loop). Everything
else is a supporting agent it calls.

---

## 2. An important honest limitation

The Coder Agent really can write in *any* language — it's an LLM producing
text, there's no hard restriction. But **automatically testing** that code
by actually running it needs the right tool installed on your machine:

- **Python** — always works (Python is already installed, that's how
  you're running CodeCrew).
- **JavaScript/TypeScript** — real syntax-checked only if you also have
  **Node.js** installed. If not, it's skipped automatically — no error, no
  crash, it just relies on the QA review step instead (see below).
- **HTML/CSS/JSON** — checked using Python's own standard library, so
  these always work with no extra installs.
- **Any other language** (Java, C++, Go, etc.) — no execution-based check
  is attempted, since we can't assume you have every compiler installed.

To make sure NOTHING slips through untested regardless of language, every
project also goes through an **LLM-based QA review** step that reads all
the files together and looks for real bugs, security issues, and
cross-file inconsistencies (like JavaScript referencing an HTML element ID
that doesn't actually exist — a bug no syntax checker would ever catch).
This is what the offline demo (`demo_offline_test.py`) specifically shows
off.

---

## 3. Project structure

```
codecrew/
├── agents/
│   ├── llm_client.py       # the ONLY file that talks to the Gemini API
│   ├── code_utils.py       # cleans code fences, parses JSON responses
│   ├── language_utils.py   # per-language syntax checking (Python/JS/HTML/CSS/JSON)
│   ├── planner_agent.py    # turns your request into a structured, multi-file project plan
│   ├── coder_agent.py      # writes ONE file, in whatever language it was assigned
│   ├── testing_agent.py    # syntax checks + pytest + LLM "QA engineer" review
│   ├── debugger_agent.py   # fixes ONE broken file
│   └── reviewer_agent.py   # writes the final project README
├── orchestrator.py         # coordinates everyone: wave scheduling, concurrency, retries
├── cli.py                  # try it from the terminal
├── app.py                  # try it from a web page (Streamlit) — file browser + zip download
├── demo_offline_test.py    # proves the pipeline works, no API key needed
├── config.py
├── requirements.txt
├── generated_projects/     # every project you build gets its own timestamped folder here
└── .env.example             # copy this to .env and add your key
```

---

## 4. Install Python dependencies

```bash
python -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

(Optional but recommended: also install **Node.js** from nodejs.org if you
want real syntax-checking for any JavaScript/TypeScript files CodeCrew
generates. Not required — it just adds one more layer of checking.)

---

## 5. Try it WITHOUT an API key first

```bash
python demo_offline_test.py
```

This fakes the AI responses with a scripted example: a 3-file website
(`index.html`, `styles.css`, `script.js`) where `index.html` and
`styles.css` are generated **at the same time** (they don't depend on each
other), then `script.js` afterward. `script.js` is deliberately written
with a bug that only the QA review step can catch (a mismatched HTML
element ID) — you'll see it get flagged, fixed by the Debugging Agent, and
pass on the second check. This is worth screenshotting for your synopsis.

---

## 6. Get your free Gemini API key

1. Go to **https://aistudio.google.com/apikey**
2. Sign in with any Google account, click **"Create API key"**. No credit
   card needed for the free tier.
3. Copy `.env.example` to `.env`: `cp .env.example .env`
4. Paste your key into `.env`:
   ```
   GEMINI_API_KEY=paste_your_real_key_here
   GEMINI_MODEL=gemini-3.5-flash-lite
   ```

**Never commit your `.env` file to GitHub** — it's already in `.gitignore`.

---

## 7. Run it for real

### Terminal
```bash
python cli.py
```
Try something ambitious: *"A personal portfolio website with a home page,
an about section, and a contact form."*

### Web interface (best for your presentation)
```bash
streamlit run app.py
```
Type a request, watch every agent work live (including which files are
being built **simultaneously**), then browse each generated file in its
own tab, read the QA report, and download the whole project as a zip.

Every project also gets saved automatically to
`generated_projects/<project-name>-<timestamp>/` — open that folder
directly (e.g. double-click `index.html` for a website) any time.

---

## 8. What's actually happening when you run a request

1. **Orchestrator** receives your plain-English request.
2. **Planner Agent** designs the whole project: picks a project type and
   tech stack, and produces a list of files — each with a language, a
   description, and which other files it depends on.
3. **Orchestrator** groups files into "waves" based on those dependencies.
   Files with no dependencies on each other are sent to **separate Coder
   Agent calls running at the same time** (real thread-based concurrency —
   this is the "simultaneous team" part). Once a wave finishes, the next
   wave runs, now able to see the finished code of files it depends on.
4. **Testing Agent** checks the WHOLE finished project together:
   - runs a real syntax check per file (using whatever tool is available
     for that language),
   - generates and actually executes PyTest tests for any Python files,
   - and does an LLM-based senior QA review of every file together,
     looking for cross-file bugs and real logic errors.
5. If anything's broken: **Orchestrator** sends just the broken file(s) to
   the **Debugging Agent** — again, multiple broken files get fixed at the
   same time if there's more than one. Then step 4 runs again. This
   repeats up to `MAX_DEBUG_RETRIES` (default 3, in `config.py`).
6. **Review Agent** writes a project README explaining what was built and
   how to run it.
7. Everything is saved to `generated_projects/<name>-<timestamp>/`.

---

## 9. Things you can extend for extra marks

- Add a dedicated **Security Review Agent** as a separate pass before the
  general QA review.
- Let the Planner ask a follow-up question when a request is ambiguous,
  instead of always guessing.
- Add a **Deployment Agent** that zips finished web projects and optionally
  pushes them to GitHub Pages.
- Track and display how much wall-clock time was SAVED by running Coder
  Agents concurrently vs. sequentially — a great, easy-to-measure metric
  for your report.

---

## 10. Troubleshooting

- **"GEMINI_API_KEY is not set"** → you haven't created `.env` yet, or it's
  in the wrong folder. It must sit next to `config.py`.
- **`404 NOT_FOUND ... model is no longer available`** → Google retires
  old free-tier model names sometimes. The error tells you the
  replacement — put it in `GEMINI_MODEL` in your `.env` file.
- **JavaScript files never get a real syntax check** → install Node.js
  from nodejs.org. Not required, but nice to have.
- **A generated project still has an issue after 3 retries** → normal for
  ambitious requests with a small/free model. Try a more specific request,
  or raise `MAX_DEBUG_RETRIES` in `config.py`.
- **It feels slow for big projects** → raise `MAX_PARALLEL_WORKERS` in
  `config.py` (default 4) so more files get coded/debugged at once — mind
  your API's rate limits if you go much higher.
````

---

## After applying all the files above: verification steps

Run these, in order, and fix anything that fails before considering this
done:

1. **Compile check** — every file should import/compile with no syntax
   errors:
   ````bash
   python -m py_compile config.py orchestrator.py cli.py app.py demo_offline_test.py agents/*.py
   ````

2. **Offline self-test (no API key needed)** — this proves the concurrent,
   multi-file pipeline actually works, using scripted fake AI responses
   instead of real API calls:
   ````bash
   python demo_offline_test.py
   ````
   Expected: it builds a fake 3-file website (`index.html`, `styles.css`,
   `script.js`), shows `index.html` and `styles.css` being generated
   **simultaneously** (they have no dependency on each other), shows a
   deliberate cross-file bug in `script.js` get caught by the QA review
   step and fixed by the Debugging Agent, and ends with:
   ````
   ✅ ALL SELF-TEST ASSERTIONS PASSED — concurrent multi-file pipeline works correctly.
   ````
   If this fails, debug it before moving on — it means something in the
   rewritten pipeline is broken, independent of any real API issues.

3. **Real run** — with a real `GEMINI_API_KEY` already set up in `.env`
   from before, try:
   ````bash
   python cli.py
   ````
   Test with a REQUEST THAT NEEDS MULTIPLE FILES, e.g.: *"A personal
   portfolio website with a home page, an about section, and a contact
   form."* Confirm it prints multiple files, the pipeline log shows a
   "Starting N agent(s) simultaneously" line for at least one wave, and a
   project folder appears under `generated_projects/`.

4. **Streamlit UI**:
   ````bash
   streamlit run app.py
   ````
   Confirm the file tabs, the QA report expander, and the "Download as
   .zip" button all work.

## Known limitations to leave as-is (don't try to "fix" these)

- JavaScript/TypeScript only get a REAL syntax check if Node.js happens to
  be installed on this machine (checked via `shutil.which("node")`). If
  it's not installed, that's fine — the code already falls back to relying
  on the LLM QA review step instead, and logs it as "skipped", not
  "failed". Do not make Node.js a hard requirement.
- Languages with no local checker at all (Java, C++, Go, etc.) rely
  entirely on the LLM QA review layer for verification. This is an
  intentional design tradeoff, not a bug — installing every possible
  compiler isn't realistic for a student project.
- If a Gemini model name ever gets deprecated (Google does this
  periodically), the fix is updating `GEMINI_MODEL` in `.env`, not editing
  any code.
