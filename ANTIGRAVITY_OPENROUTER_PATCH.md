# Prompt for Antigravity — Switch CodeCrew from Gemini to Free Multi-Model Routing (OpenRouter)

Paste this into Antigravity inside your existing CodeCrew project folder.

## What this does and why

This moves CodeCrew off Gemini entirely and onto **OpenRouter**
(openrouter.ai) — one API key that gives access to 100+ models from many
different labs, several genuinely free. Instead of one model for
everything, **each agent role now gets whichever free model is actually
best suited to its job**:

| Agent | Model it prefers | Why |
|---|---|---|
| Coder, Debugger | `qwen/qwen3-coder:free` (Alibaba) | Purpose-built for writing/fixing code |
| Planner | `nvidia/nemotron-3-ultra-550b-a55b:free` (NVIDIA) | Strong general reasoning for breaking down requests |
| Tester, Reviewer | `openai/gpt-oss-120b:free` (OpenAI open-weight) | Reliable all-rounder for reviewing/summarizing |

Every role still falls back through the rest of the pool (which also
includes `deepseek/deepseek-chat:free`) if its preferred model is
rate-limited or briefly down — so one busy model, or even one lab's whole
free tier being down, doesn't stop the pipeline. This is genuinely how
production agentic systems are built: route each task to the
best-suited model, with pooled fallback for resilience.

## How to apply

1. **REPLACE** the entire content of each file listed below with the
   version given.
2. In your own `.env` file (not `.env.example`), remove any `GEMINI_*`
   lines and add:
   ```
   OPENROUTER_API_KEY=your_key_here
   ```
   Get a free key (no credit card) at **https://openrouter.ai/keys**.
3. Run `pip install -r requirements.txt` again after replacing it below —
   `google-genai` is replaced with `openai` (the standard OpenAI Python
   package, used here purely for its API *shape*, pointed at OpenRouter's
   URL — not talking to OpenAI itself).
4. Run the verification steps at the end of this document before telling
   the user it's done.

---

## REPLACE: `config.py`

````python
"""
config.py
---------
Loads settings from a .env file so we never hard-code secrets in the code.
"""

import os
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Every model below is on OpenRouter's genuinely free tier (its ID ends in
# ":free" — no card, no trial period, resets daily) as of 2026, and each
# comes from a DIFFERENT lab. That matters for reliability: if one lab's
# free model gets rate-limited or temporarily pulled, the others are
# unaffected, since free-tier limits are set per-model, not shared.
#
#   qwen/qwen3-coder:free        — Alibaba. Purpose-built FOR software
#                                   engineering; the strongest free model
#                                   for actually writing/fixing code.
#   nvidia/nemotron-3-ultra...   — NVIDIA. Strong general reasoning —
#                                   better suited to planning and judgment
#                                   calls than to writing code line-by-line.
#   openai/gpt-oss-120b:free     — OpenAI's open-weight model. Solid,
#                                   reliable all-rounder, good fallback.
#   deepseek/deepseek-chat:free  — DeepSeek. Another strong, independent
#                                   fallback from yet another lab.
#
# Override this list any time in .env (comma-separated) — no code changes
# needed. Check https://openrouter.ai/models?q=free for the current list;
# free models occasionally rotate out with little notice.
_default_pool = (
    "qwen/qwen3-coder:free,"
    "nvidia/nemotron-3-ultra-550b-a55b:free,"
    "openai/gpt-oss-120b:free,"
    "deepseek/deepseek-chat:free"
)
MODEL_POOL = [m.strip() for m in os.getenv("GEMINI_MODEL_POOL", os.getenv("MODEL_POOL", _default_pool)).split(",") if m.strip()]

# Which model each agent role tries FIRST — matching each agent's actual
# job to the model best suited for it, the way a real engineering manager
# would assign the right person to the right kind of task. Every role
# still falls back through the rest of MODEL_POOL above if its preferred
# model is busy, so this only decides the starting point, not a hard limit.
ROLE_PRIMARY_MODEL = {
    "planner": "nvidia/nemotron-3-ultra-550b-a55b:free",   # reasoning/judgment task
    "coder": "qwen/qwen3-coder:free",                       # a pure coding task
    "tester": "openai/gpt-oss-120b:free",                   # reviewing/reasoning task
    "debugger": "qwen/qwen3-coder:free",                    # also a pure coding task
    "reviewer": "openai/gpt-oss-120b:free",                 # writing/summarizing task
}

# How many times the Debugging Agent will try to fix a broken file before
# the Orchestrator gives up on it and moves on with the best attempt.
MAX_DEBUG_RETRIES = int(os.getenv("MAX_DEBUG_RETRIES", "3"))

# How many agents are allowed to work AT THE SAME TIME (e.g. multiple Coder
# Agents each writing a different file simultaneously, like different
# developers on a real team).
MAX_PARALLEL_WORKERS = int(os.getenv("MAX_PARALLEL_WORKERS", "4"))

# Where finished projects get saved. Each run creates its own timestamped
# sub-folder here so nothing ever gets overwritten.
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "generated_projects")
````

## REPLACE: `agents/llm_client.py`

````python
"""
llm_client.py
-------------
This is the ONLY file that actually talks to an LLM. Every agent calls
`call_llm(system_prompt, user_prompt, role=...)` instead of talking to a
provider directly.

We use OpenRouter (https://openrouter.ai) — a single OpenAI-compatible API
in front of 100+ models from many different labs, several of which are
genuinely free. This gives us two things real production agentic systems
use:

1. TASK-APPROPRIATE MODEL ROUTING — each agent role gets whichever model
   is actually best suited to its job (see ROLE_PRIMARY_MODEL in
   config.py): the Coder and Debugger prefer a model built specifically
   for software (Qwen3-Coder), while the Planner prefers a strong general
   reasoning model, and so on.

2. POOLED FALLBACK — every role still has the rest of the model pool
   behind it. If its preferred model is rate-limited, temporarily down, or
   retired, the call automatically retries with the next model in line
   instead of crashing the pipeline.

Because OpenRouter speaks the same API shape as OpenAI, this uses the
standard `openai` Python package pointed at OpenRouter's base_url — no
provider-specific SDK needed, and the same pattern works if you ever want
to point this at a different OpenAI-compatible provider later.
"""

from openai import OpenAI, APIStatusError

from config import OPENROUTER_API_KEY, MODEL_POOL, ROLE_PRIMARY_MODEL

_client = None  # created once and reused (lazy singleton)


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENROUTER_API_KEY:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env "
                "and paste your key in there (see README.md for how to get "
                "a free one, no credit card needed)."
            )
        _client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
    return _client


def _model_order_for(role: str) -> list:
    """This role's preferred model first, then the rest of the shared pool
    as fallbacks, with no duplicates."""
    preferred = ROLE_PRIMARY_MODEL.get(role)
    rest = [m for m in MODEL_POOL if m != preferred]
    ordered = ([preferred] if preferred else []) + rest
    return ordered or MODEL_POOL  # unknown role -> just use the whole pool


def _is_retryable(error: APIStatusError) -> bool:
    # 429 = rate-limited, 404 = model retired/unknown, 503 = provider
    # temporarily overloaded. All three mean "try the next model", not
    # "something is broken."
    return error.status_code in (429, 404, 503)


def call_llm(system_prompt: str, user_prompt: str, role: str = "coder") -> str:
    """
    Sends a prompt to whichever model is best suited for `role` — one of
    "planner", "coder", "tester", "debugger", "reviewer" — falling back
    through the rest of the model pool if that model is currently busy,
    rate-limited, or unavailable.
    """
    client = get_client()
    models_to_try = _model_order_for(role)

    last_error = None
    for model in models_to_try:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": user_prompt.strip()},
                ],
            )
            return (response.choices[0].message.content or "").strip()
        except APIStatusError as e:
            if _is_retryable(e):
                last_error = e
                continue  # this model is busy/retired — try the next one
            raise  # a different kind of error is a real problem, don't hide it

    raise RuntimeError(
        f"Every free model available for role '{role}' is currently "
        "rate-limited or unavailable. Wait a bit and try again, or add "
        "more models to MODEL_POOL in your .env file. "
        f"Last error: {last_error}"
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
    raw = call_llm(SYSTEM_PROMPT, f"User request: {user_request}", role="planner")
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
    code = call_llm(system_prompt, user_prompt, role="coder")
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
            raw = call_llm(PYTEST_SYSTEM_PROMPT, prompt, role="tester")
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
    raw = call_llm(QA_REVIEW_SYSTEM_PROMPT, "\n".join(parts), role="tester")
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
    fixed_code = call_llm(system_prompt, user_prompt, role="debugger")
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
    readme = call_llm(SYSTEM_PROMPT, prompt, role="reviewer")
    return clean_code_block(readme)
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


def fake_call_llm(system_prompt, user_prompt, role="coder"):
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

## REPLACE: `requirements.txt`

````text
openai>=1.50.0
python-dotenv>=1.0.0
pytest>=8.0.0
streamlit>=1.38.0
````

## REPLACE: `.env.example`

````bash
# Get a free key (no credit card needed) at https://openrouter.ai/keys
OPENROUTER_API_KEY=your_api_key_here

# Optional: override the free model pool (comma-separated). Leave unset to
# use the defaults in config.py. Check https://openrouter.ai/models?q=free
# for the current list of genuinely free models.
# MODEL_POOL=qwen/qwen3-coder:free,nvidia/nemotron-3-ultra-550b-a55b:free,openai/gpt-oss-120b:free,deepseek/deepseek-chat:free
````

---

## Verification

````bash
pip install -r requirements.txt
python -m py_compile config.py orchestrator.py cli.py app.py demo_offline_test.py agents/*.py
python demo_offline_test.py
````

Expected: the offline demo still passes exactly as before (it mocks
`call_llm` directly, so it doesn't need a real key) — this just confirms
nothing broke in the rewiring. Then with a real `OPENROUTER_API_KEY` set
in `.env`, run `python cli.py` or `streamlit run app.py` with a real
request and confirm it completes successfully. If you want to SEE the
per-role routing happening, that's determined by `config.py`'s
`ROLE_PRIMARY_MODEL` — it's not logged by default, but you can
temporarily add a `print(model)` inside `llm_client.py`'s `call_llm` loop
to watch it live.

## Note for the synopsis / report

This is worth a paragraph in the project write-up: CodeCrew doesn't just
use "an AI model" — it routes each agent role to the model best suited to
that role's actual job (a coding-specialist model for writing/fixing code,
a reasoning-focused model for planning), with automatic fallback across
models from different labs for resilience. That's a real, current
practice in production multi-agent systems, not just a workaround for
free-tier limits.
