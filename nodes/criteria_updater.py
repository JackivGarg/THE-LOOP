"""
Criteria Updater Node — updates the [EDITABLE] block of a profile based on user feedback.
Uses the centrally configured Groq criteria-update model.
Called only when user submits preference feedback after generation.
"""

import os
import json

from profiles.profile_manager import load_profile, save_profile
from utils.groq_provider import get_groq_client, get_structured_response_format, get_task_config
from utils.retry import call_with_retry

_SYSTEM_PROMPT = """You are a criteria updater for a website rating system.

You will receive:
1. The CURRENT criteria block (a list of rating preferences)
2. The USER'S FEEDBACK (what they want to change about future ratings)

Your job is to:
1. Merge the user's feedback into the existing criteria
2. Add new preferences from the feedback
3. Modify existing preferences if the feedback contradicts them
4. Remove preferences if the user explicitly says to
5. Keep the format as a bulleted list (each line starts with "- ")

Return ONLY a JSON object with:
{
  "updated_criteria": "<the full updated criteria block as a string>",
  "changelog": "<one-line summary of what changed, e.g., 'v3: added whitespace preference, penalized dark backgrounds'>"
}

Do NOT include any text outside the JSON."""


def _call_criteria_updater(current_criteria: str, user_feedback: str) -> dict:
    """Make the actual Groq API call."""
    user_message = (
        f"## CURRENT CRITERIA\n{current_criteria}\n\n"
        f"## USER FEEDBACK\n{user_feedback}"
    )
    model, settings = get_task_config("criteria_updater")
    response = get_groq_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        response_format=get_structured_response_format("criteria_updater"),
        temperature=settings.temperature,
        max_completion_tokens=settings.max_completion_tokens,
        reasoning_effort=settings.reasoning_effort,
    )
    raw_text = response.choices[0].message.content
    return json.loads(raw_text)


def update_criteria(state: dict, user_feedback: str) -> dict:
    """
    Update the active profile's criteria based on user feedback.
    
    Reads the current editable block, asks the LLM to merge the feedback,
    writes the updated block back to the profile file, and appends
    a changelog entry to state.
    
    Args:
        state: Session state dict (must have 'active_profile')
        user_feedback: Raw user preference text (e.g., "make it more minimalist")
    
    Returns:
        Updated state with incremented criteria_version and appended changelog
    """
    if not user_feedback or not user_feedback.strip():
        return state

    profile_name = state.get("active_profile", "default")

    # Load current criteria
    try:
        current_criteria = load_profile(profile_name)
    except FileNotFoundError:
        current_criteria = load_profile("default")
        profile_name = "default"

    # Call LLM to merge feedback
    result = call_with_retry(_call_criteria_updater, current_criteria, user_feedback)

    # Extract updated criteria
    updated_criteria = result.get("updated_criteria", current_criteria)
    changelog_entry = result.get("changelog", f"v{state['criteria_version'] + 1}: updated from user feedback")

    # Write back to profile file
    save_profile(profile_name, updated_criteria)

    # Update state
    state["criteria_version"] += 1
    state["criteria_changelog"].append(changelog_entry)

    return state
