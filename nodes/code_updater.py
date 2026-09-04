"""
Code Updater Node — makes surgical fixes to existing HTML based on rater feedback.
Uses Qwen3 32B via Groq with thinking mode disabled.
Called on iterations 2–10.
"""

import os

from groq import Groq
from dotenv import load_dotenv

from utils.html_validator import extract_html
from utils.retry import call_with_retry

load_dotenv()

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
_MODEL = "llama-3.3-70b-versatile"

# Load the code updater system prompt
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "code_updater_prompt.txt")
with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    _SYSTEM_PROMPT = f.read().strip()


def _call_code_updater(current_html: str, fix_instruction: str) -> str:
    """Make the actual Groq API call for code updating."""
    user_message = (
        f"## FIX INSTRUCTIONS\n{fix_instruction}\n\n"
        f"## CURRENT HTML CODE\n{current_html}"
    )
    response = _client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        max_completion_tokens=5000,
        temperature=0.7,
        top_p=0.8,
    )
    return response.choices[0].message.content


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
    raw_output = call_with_retry(_call_code_updater, current_html, fix_instruction)

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
