"""
code_utils.py
-------------
Small shared helpers used by multiple agents.
"""

import json
import re


def clean_code_block(text: str) -> str:
    """
    Strips thinking tags (<think>...</think>) and markdown fences (```python ... ```)
    so we always obtain clean, runnable code.
    """
    if not text:
        return ""

    # Remove reasoning/thinking blocks if present
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    # If code is enclosed in markdown code fences anywhere in the output
    fence_match = re.search(r"```(?:\w+)?\n([\s\S]*?)\n```", text)
    if fence_match:
        return fence_match.group(1).strip()

    # Standard fallback fence stripping if it starts with ```
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)

    return text.strip()


def parse_json_response(text: str) -> dict:
    """
    Parses JSON from model responses, handling reasoning preambles,
    markdown fences, or explanatory text before/after.
    """
    if not text:
        raise ValueError("Cannot parse JSON from empty response.")

    # Remove reasoning tags first
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    # Strategy 1: Look for explicit ```json ... ``` or ``` ... ``` block
    block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if block_match:
        try:
            return json.loads(block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 2: Direct JSON parsing
    try:
        return json.loads(clean_code_block(cleaned))
    except json.JSONDecodeError:
        pass

    # Strategy 3: Grab the outermost { ... } block
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(
        "Could not parse JSON from the model's response. Raw response was:\n" + text
    )
