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
