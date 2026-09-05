"""
Planner Node — the brain of the generation loop.
Uses the centrally configured Groq planner model.

Iteration 1: Creates a site plan from user input + profile criteria.
Iteration 2+: Creates targeted fix instructions from rater feedback.
"""

import os
import json

from profiles.profile_manager import load_profile
from utils.groq_provider import get_groq_client, get_task_config
from utils.retry import call_with_retry

# Load planner system prompt
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "planner_prompt.txt")
with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
    _SYSTEM_PROMPT = f.read().strip()


def _build_user_message_iter1(state: dict) -> str:
    """Build the user message for the first iteration (fresh generation)."""
    title = state["user_input"]["title"]
    description = state["user_input"]["description"]
    profile_name = state.get("active_profile", "default")

    try:
        criteria = load_profile(profile_name)
    except FileNotFoundError:
        criteria = load_profile("default")

    return (
        f"## USER REQUEST\n"
        f"Title: {title}\n"
        f"Description: {description}\n\n"
        f"## DESIGN PREFERENCES (from user's selected profile)\n"
        f"{criteria}\n\n"
        f"## YOUR TASK\n"
        f"Create a detailed site plan for a single-page website. "
        f"This is iteration 1 — you are creating the initial plan from scratch. "
        f"Set action to \"write\"."
    )


def _build_user_message_iter2plus(state: dict) -> str:
    """Build the user message for iterations 2+ (improvement rounds)."""
    title = state["user_input"]["title"]
    description = state["user_input"]["description"]
    rating = state.get("last_rating_json", {})
    scores = rating.get("scores", {})
    deductions = rating.get("deductions", state.get("last_deductions", ""))
    reward_history = state.get("reward_history", [])

    return (
        f"## USER REQUEST (reminder)\n"
        f"Title: {title}\n"
        f"Description: {description}\n\n"
        f"## LAST ITERATION SCORES\n"
        f"{json.dumps(scores, indent=2)}\n\n"
        f"## RATER DEDUCTIONS\n"
        f"{deductions}\n\n"
        f"## REWARD HISTORY\n"
        f"{reward_history}\n\n"
        f"## YOUR TASK\n"
        f"Analyze the scores above. Identify the 2-3 weakest dimensions. "
        f"Create targeted fix instructions for the code updater. "
        f"Focus only on what needs improvement — do not change what's already good. "
        f"Set action to \"update\"."
    )


def _call_planner(user_message: str) -> dict:
    """Make the actual Groq API call for planning."""
    model, settings = get_task_config("planner")
    response = get_groq_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=settings.temperature,
        max_completion_tokens=settings.max_completion_tokens,
    )
    raw_text = response.choices[0].message.content
    try:
        return json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        # If LLM returns malformed JSON, wrap the raw text as an instruction
        return {"action": "write", "instruction": raw_text, "focus_dimensions": []}


def plan(state: dict) -> dict:
    """
    Run the planner node.
    
    On iteration 0: Creates a fresh site plan from user input.
    On iteration 1+: Creates targeted fix instructions from rater feedback.
    
    Stores the planner's instruction in state['planner_instruction']
    for the Code Writer or Code Updater to consume.
    
    Args:
        state: Session state dict
    
    Returns:
        Updated state with 'planner_instruction' populated
    """
    if state["iteration"] == 0:
        user_message = _build_user_message_iter1(state)
    else:
        user_message = _build_user_message_iter2plus(state)

    # Call with retry
    planner_output = call_with_retry(_call_planner, user_message)

    # Extract the instruction text
    instruction = planner_output.get("instruction", "")
    if not instruction:
        # Fallback: stringify the entire planner output as instruction
        instruction = json.dumps(planner_output, indent=2)

    state["planner_instruction"] = instruction
    state["planner_focus"] = planner_output.get("focus_dimensions", [])

    return state
