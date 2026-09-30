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
