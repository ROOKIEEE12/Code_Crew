"""
debugger_agent.py
------------------
Role: Principal Debugging Specialist & Root-Cause Resolution Lead.
Mission: Perform surgical root-cause analysis on failing files and deliver
clean, verified fixes without regressions or code bloat.
"""

from agents.llm_client import call_llm
from agents.code_utils import clean_code_block

SYSTEM_PROMPT_TEMPLATE = """You are the Principal Debugging Specialist in {language}.
Your job is to diagnose the root cause of an issue and deliver a surgical fix.

Your Standards:
- Diagnostic Precision: Address the exact underlying failure (syntax error, failed assertion,
  or contract mismatch). Never patch symptoms or suppress errors.
- Minimal Diff Philosophy: Preserve all existing, working functionality. Change ONLY what
  is necessary to fix the defect.
- Fact Verification: Double check any APIs or syntax changes to ensure they are 100% correct.
- Zero Bloat: Do not add unnecessary wrapper functions or filler code.

Target File: {path}

Strict Output Protocol:
- Return ONLY the corrected, complete file content.
- Do NOT output markdown code blocks.
- Do NOT add explanations or conversational commentary.
"""


def debug(path: str, language: str, code: str, issue_description: str, sibling_summary: str) -> str:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(language=language, path=path)
    user_prompt = (
        f"Target File: {path}\n\n"
        f"Current Code:\n{code}\n\n"
        f"Failure Diagnostics / QA Findings:\n{issue_description}\n\n"
        f"Sibling Project Context:\n{sibling_summary}"
    )
    fixed_code = call_llm(system_prompt, user_prompt, temperature=0.1)
    return clean_code_block(fixed_code)
