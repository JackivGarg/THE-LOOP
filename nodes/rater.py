"""
Rater Node — scores generated HTML across 5 dimensions.
Uses the centrally configured Groq rater model with JSON mode enforced.
Returns structured scores + deductions string.
"""

import json
import os
from profiles.profile_manager import get_composed_rater_prompt
from utils.deterministic_evaluator import evaluate_html
from utils.groq_provider import record_completion_metadata, request_structured_completion
from utils.retry import call_with_retry


def _build_rating_request(state: dict, html_code: str, deterministic_evaluation: dict) -> str:
    """Give the rater the brief and objective evidence needed for a grounded score."""
    user_input = state.get("user_input", {})
    failed_checks = [
        {"name": check["name"], "score": check["score"], "details": check["details"]}
        for check in deterministic_evaluation["checks"]
        if check["score"] < 1
    ]
    return (
        "## ORIGINAL USER BRIEF\n"
        f"Title: {user_input.get('title', '')}\n"
        f"Description: {user_input.get('description', '')}\n\n"
        "## OBJECTIVE CHECK RESULTS\n"
        f"Deterministic score: {deterministic_evaluation['score']}/10\n"
        f"Failed or partial checks: {json.dumps(failed_checks)}\n"
        f"Known issues: {json.dumps(deterministic_evaluation['issues'])}\n\n"
        "## HTML TO REVIEW\n"
        f"{html_code}"
    )


def _call_rater(system_prompt: str, rating_request: str):
    """Make the actual Groq API call for rating."""
    return request_structured_completion(
        "rater",
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": rating_request},
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
    rating_request = _build_rating_request(state, html_code, deterministic_evaluation)
    raw_rating, completion = call_with_retry(_call_rater, system_prompt, rating_request)
    record_completion_metadata(state, completion)
    clean_rating = raw_rating.model_dump()

    # Update state
    state["last_rating_json"] = clean_rating
    state["last_deterministic_evaluation"] = deterministic_evaluation
    state.setdefault("evaluation_history", []).append(
        {
            "iteration": state.get("iteration", 0) + 1,
            "deterministic": deterministic_evaluation,
            "llm_rating": clean_rating,
        }
    )
    deterministic_summary = (
        f"Deterministic checks: {deterministic_evaluation['score']:.1f}/10. "
        + ("; ".join(deterministic_evaluation["issues"][:3]) or "No issues found.")
    )
    state["last_deductions"] = f"{clean_rating['deductions']}\n\n{deterministic_summary}"

    return state
