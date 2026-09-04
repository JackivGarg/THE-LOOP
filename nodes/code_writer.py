"""
Code Writer Node — generates a complete single-file HTML website.
Uses Qwen3 32B via Groq with thinking mode disabled.
Called only on iteration 1.
"""

import os

from groq import Groq
from dotenv import load_dotenv

from utils.html_validator import extract_html
from utils.retry import call_with_retry

load_dotenv()

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
_MODEL = "llama-3.3-70b-versatile"

# Load the code writer system prompt
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "code_writer_prompt.txt")
with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    _SYSTEM_PROMPT = f.read().strip()


def _call_code_writer(instruction: str) -> str:
    """Make the actual Groq API call for code generation."""
    response = _client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ],
        # reasoning_effort and reasoning_format removed as they aren't supported by Llama 3.3
        max_completion_tokens=5000,   # Reduced to stay within 12K TPM headroom
        temperature=0.7,
        top_p=0.8,
    )
    return response.choices[0].message.content


def write_code(state: dict) -> dict:
    """
    Generate a complete HTML website from the planner's instruction.
    
    Reads the planner's instruction from state, calls Qwen3 to generate
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
