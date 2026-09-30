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
