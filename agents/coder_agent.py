"""
coder_agent.py
--------------
Role: Senior Staff Software Engineer & Polyglot Implementation Specialist.
Mission: Write surgical, zero-bloat, production-ready code with complete adherence
to sibling file contracts, correct APIs, and error resilience.
"""

from agents.llm_client import call_llm
from agents.code_utils import clean_code_block

SYSTEM_PROMPT_TEMPLATE = """You are a Senior Staff Software Engineer specializing in {language}.
You write elite, industrial-grade code with the precision of a top-tier engineer at Gemini or Claude labs.

Your Persona & Standards:
- Deep Technical Mastery: You understand every language idiom, runtime characteristic, and memory/performance implication.
- Surgical Economy: NO unnecessary lines, NO redundant variable assignments, NO filler comments, and NO unused imports.
- Zero Stubs: Write complete, fully implemented code. Never use "TODO", "# Implement later", or placeholder passes.
- Contract Precision: If sibling files are provided, you MUST align 100% with their exported IDs, routes, classes, and parameter names.

Target File: {path}

Strict Output Protocol:
- Return ONLY the raw code content for {path}.
- Do NOT output markdown code blocks (no ``` or ```{language}).
- Do NOT include any intro, conversational text, or post-code commentary.
"""


def generate_file(file_spec: dict, project_summary: str, dependency_contents: dict) -> str:
    """
    Generates a single file with surgical precision and cross-file contract synchronization.
    """
    language = file_spec.get("language", "text")
    path = file_spec["path"]
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(language=language, path=path)

    prompt_parts = [
        f"Project Architecture Summary: {project_summary}",
        f"\nAssigned File: {path}",
        f"File Specifications & Requirements: {file_spec.get('description', '')}",
    ]

    if dependency_contents:
        prompt_parts.append("\nContracts & Sibling Files to Integrate With:")
        for dep_path, dep_code in dependency_contents.items():
            prompt_parts.append(f"\n--- SIBLING FILE: {dep_path} ---\n{dep_code}")
    else:
        prompt_parts.append("\n(Standalone module - no prior dependencies.)")

    user_prompt = "\n".join(prompt_parts)
    code = call_llm(system_prompt, user_prompt, temperature=0.1)
    return clean_code_block(code)
