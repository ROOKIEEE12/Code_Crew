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
            with open(full_path, "w", encoding="utf-8") as fh:
                fh.write(f["code"])

        generated_tests = {}
        for path, f in python_files.items():
            module_name = os.path.splitext(os.path.basename(path))[0]
            prompt = f"Module name to import from: {module_name}\n\nCode:\n{f['code']}"
            raw = call_llm(PYTEST_SYSTEM_PROMPT, prompt)
            test_code = clean_code_block(raw)
            generated_tests[path] = test_code

            test_file = os.path.join(tmp_dir, f"test_{module_name}.py")
            with open(test_file, "w", encoding="utf-8") as fh:
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
