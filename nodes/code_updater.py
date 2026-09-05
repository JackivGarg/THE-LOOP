"""
Code Updater Node — makes surgical fixes to existing HTML based on rater feedback.
Uses the centrally configured Groq code-update model.
Called on iterations 2–10.
"""

import os

from utils.html_validator import extract_html
from utils.groq_provider import record_completion_metadata, request_completion
from utils.retry import call_with_retry

# Load the code updater system prompt
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "code_updater_prompt.txt")
with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    _SYSTEM_PROMPT = f.read().strip()


def _call_code_updater(current_html: str, fix_instruction: str):
    """Make the actual Groq API call for code updating."""
    user_message = (
        f"## FIX INSTRUCTIONS\n{fix_instruction}\n\n"
        f"## CURRENT HTML CODE\n{current_html}"
    )
    return request_completion(
        "code_updater",
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )


def update_code(state: dict) -> dict:
    """
    Apply surgical fixes to the current HTML based on planner's fix instructions.
    
    Args:
        state: Session state dict (must have 'current_code' and 'planner_instruction')
    
    Returns:
        Updated state with 'current_code' replaced with the fixed version
    
    Raises:
        ValueError: If the LLM output doesn't contain valid HTML
    """
    current_html = state.get("current_code", "")
    fix_instruction = state.get("planner_instruction", "")

    if not current_html:
        raise ValueError("Cannot update code: no current_code in state")
    if not fix_instruction:
        raise ValueError("Cannot update code: no planner_instruction in state")

    # Call with retry
    completion = call_with_retry(_call_code_updater, current_html, fix_instruction)
    record_completion_metadata(state, completion)
    raw_output = completion.content

    # Validate and extract HTML
    html = extract_html(raw_output)
    if html is None:
        if raw_output.strip().startswith("<!") or raw_output.strip().startswith("<html"):
            html = raw_output.strip()
        else:
            # If update fails to produce valid HTML, keep the previous version
            # rather than crashing the entire loop
            return state

    state["current_code"] = html
    return state
