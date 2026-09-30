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
