"""
Code Writer Node — generates a complete single-file HTML website.
Uses the centrally configured Groq code-generation model.
Called only on iteration 1.
"""

import os

from utils.html_validator import extract_html
from utils.groq_provider import get_groq_client, get_task_config
from utils.retry import call_with_retry

# Load the code writer system prompt
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "code_writer_prompt.txt")
with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    _SYSTEM_PROMPT = f.read().strip()


def _call_code_writer(instruction: str) -> str:
    """Make the actual Groq API call for code generation."""
    model, settings = get_task_config("code_writer")
    response = get_groq_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ],
        max_completion_tokens=settings.max_completion_tokens,
        temperature=settings.temperature,
        top_p=settings.top_p,
        reasoning_effort=settings.reasoning_effort,
    )
    return response.choices[0].message.content


def write_code(state: dict) -> dict:
    """
    Generate a complete HTML website from the planner's instruction.
    
    Reads the planner's instruction from state, calls the configured model to generate
    the full HTML, validates the output, and stores it in state.
    
    Args:
        state: Session state dict (must have 'planner_instruction')
    
    Returns:
        Updated state with 'current_code' populated
    
    Raises:
        ValueError: If the LLM output doesn't contain valid HTML
    """
    instruction = state.get("planner_instruction", "")
    if not instruction:
        raise ValueError("Cannot write code: no planner_instruction in state")

    # Call with retry
    raw_output = call_with_retry(_call_code_writer, instruction)

    # Validate and extract HTML
    html = extract_html(raw_output)
    if html is None:
        # Fallback: if extraction fails, try using the raw output directly
        # (some models output clean HTML without any wrapping)
        if raw_output.strip().startswith("<!") or raw_output.strip().startswith("<html"):
            html = raw_output.strip()
        else:
            raise ValueError(
                "Code Writer produced output that doesn't contain valid HTML. "
                f"First 200 chars: {raw_output[:200]}"
            )

    state["current_code"] = html
    return state
