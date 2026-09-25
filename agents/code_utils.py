"""
code_utils.py
-------------
Small shared helpers used by multiple agents.
"""

import json
import re


def clean_code_block(text: str) -> str:
    """
    LLMs love wrapping code in ```python ... ``` fences even when you ask
    them not to — this strips that off so we always end up with clean,
    runnable source code.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop the opening ```language line
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]  # drop the closing ```
        text = "\n".join(lines)
    return text.strip()


def parse_json_response(text: str) -> dict:
    """
    The Planner and the QA Reviewer agents are asked to respond with pure
    JSON, but LLMs sometimes wrap it in markdown fences or add a stray
    sentence before/after anyway. This tries a few increasingly forgiving
    strategies to still get a usable dict out of it.
    """
    text = clean_code_block(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: grab the outermost { ... } block and try again.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(
        "Could not parse JSON from the model's response. Raw response was:\n" + text
    )
