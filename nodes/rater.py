"""
Rater Node — scores generated HTML across 5 dimensions.
Uses the centrally configured Groq rater model with JSON mode enforced.
Returns structured scores + deductions string.
"""

import os
from profiles.profile_manager import get_composed_rater_prompt
from utils.deterministic_evaluator import evaluate_html
from utils.groq_provider import record_completion_metadata, request_structured_completion
from utils.retry import call_with_retry


def _call_rater(system_prompt: str, html_code: str):
    """Make the actual Groq API call for rating."""
    return request_structured_completion(
        "rater",
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Rate the following HTML website code:\n\n{html_code}"},
        ],
    )


def rate(state: dict) -> dict:
    """
    Rate the current HTML code in state.
    
    Reads the active profile to compose the full rater prompt,
    calls the Groq API with JSON mode, validates the output,
    and updates state with the rating results.
    
    Args:
        state: The session state dict (must have 'current_code' and 'active_profile')
    
    Returns:
        Updated state dict with 'last_rating_json' and 'last_deductions' populated
    """
    html_code = state.get("current_code", "")
    if not html_code:
        raise ValueError("Cannot rate: no current_code in state")

    profile_name = state.get("active_profile", "default")
    system_prompt = get_composed_rater_prompt(profile_name)
    deterministic_evaluation = evaluate_html(
        html_code,
        title=state.get("user_input", {}).get("title", ""),
        description=state.get("user_input", {}).get("description", ""),
    )

    # Call with retry for rate-limit resilience
    raw_rating, completion = call_with_retry(_call_rater, system_prompt, html_code)
    record_completion_metadata(state, completion)
    clean_rating = raw_rating.model_dump()

    # Update state
    state["last_rating_json"] = clean_rating
    state["last_deterministic_evaluation"] = deterministic_evaluation
    deterministic_summary = (
        f"Deterministic checks: {deterministic_evaluation['score']:.1f}/10. "
        + ("; ".join(deterministic_evaluation["issues"][:3]) or "No issues found.")
    )
    state["last_deductions"] = f"{clean_rating['deductions']}\n\n{deterministic_summary}"

    return state
