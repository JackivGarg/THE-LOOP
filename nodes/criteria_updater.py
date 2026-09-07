"""
Criteria Updater Node — updates the [EDITABLE] block of a profile based on user feedback.
Uses the centrally configured Groq criteria-update model.
Called only when user submits preference feedback after generation.
"""

from profiles.profile_manager import criteria_diff, load_profile, save_profile, validate_criteria
from utils.groq_provider import record_completion_metadata, request_structured_completion
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
5. Return only the editable criteria bullet list; never add prompt headings, [FIXED]/[EDITABLE] markers, or template instructions
6. Keep the format as a bulleted list (each line starts with "- ")

Return ONLY a JSON object with:
{
  "updated_criteria": "<the full updated criteria block as a string>",
  "changelog": "<one-line summary of what changed, e.g., 'v3: added whitespace preference, penalized dark backgrounds'>"
}

Do NOT include any text outside the JSON."""


def _call_criteria_updater(current_criteria: str, user_feedback: str):
    """Make the actual Groq API call."""
    user_message = (
        f"## CURRENT CRITERIA\n{current_criteria}\n\n"
        f"## USER FEEDBACK\n{user_feedback}"
    )
    return request_structured_completion(
        "criteria_updater",
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )


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
    result, completion = call_with_retry(_call_criteria_updater, current_criteria, user_feedback)
    record_completion_metadata(state, completion)

    # Extract updated criteria
    updated_criteria = validate_criteria(result.updated_criteria)
    changelog_entry = result.changelog

    # Persist only the validated editable block as an append-only profile version.
    profile = save_profile(profile_name, updated_criteria, changelog=changelog_entry, source="criteria_updater")
    previous_version = profile["current_version"] - 1
    current_version = profile["current_version"]

    # Update state
    state["criteria_version"] = current_version
    state["criteria_changelog"].append(changelog_entry)
    state["last_criteria_diff"] = (
        criteria_diff(profile_name, previous_version, current_version)
        if previous_version >= 1 else ""
    )

    return state
