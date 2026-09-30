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


def fake_call_llm(system_prompt, user_prompt, role="coder", **kwargs):
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

    if "Code Auditor" in system_prompt or role == "auditor":
        import json
        match = re.search(r"--- CODE TO AUDIT ---\n(.*?)\n--- END OF CODE ---", user_prompt, re.DOTALL)
        code_str = match.group(1) if match else ""
        return json.dumps({
            "fact_check_passed": True,
            "lines_analyzed": len(code_str.splitlines()),
            "unnecessary_lines_removed": 0,
            "audit_notes": "Audited cleanly with zero bloat.",
            "refined_code": code_str
        })

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
