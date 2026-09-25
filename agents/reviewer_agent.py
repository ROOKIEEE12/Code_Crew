"""
reviewer_agent.py
------------------
Role: Principal Technical Documentation & Release Engineer.
Mission: Produce crystalline, beginner-accessible, executable README documentation
outlining project architecture, file relationships, and exact execution commands.
"""

from agents.llm_client import call_llm
from agents.code_utils import clean_code_block

SYSTEM_PROMPT = """You are the Principal Technical Documentation Specialist.
You craft crystal-clear, professional README.md documentation for delivered software systems.

Standards:
- Zero Filler: Every section must contain actionable, exact technical instructions.
- Runnable Commands: Provide precise copy-paste commands to run or view the project.
- Visual Architecture: Clearly delineate the file structure and responsibility of each module.
- Beginner-Friendly yet Professional: Clear, well-structured GitHub-flavored Markdown.

Output Format:
- Return ONLY the raw markdown content of the README.md. No meta-commentary outside the document.
"""


def write_readme(plan: dict, files: dict) -> str:
    file_list = "\n".join(f"- `{path}` ({f['language']}): {f.get('description', 'Core module')}" for path, f in files.items())
    prompt = (
        f"Project Name: {plan.get('project_name')}\n"
        f"Project Type: {plan.get('project_type')}\n"
        f"Architectural Summary: {plan.get('summary')}\n\n"
        f"Component Files:\n{file_list}"
    )
    readme = call_llm(SYSTEM_PROMPT, prompt, temperature=0.2)
    return clean_code_block(readme)
