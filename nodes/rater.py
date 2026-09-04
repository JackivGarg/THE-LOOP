"""
Rater Node — scores generated HTML across 5 dimensions.
Uses Llama 3.3 70B Versatile via Groq with JSON mode enforced.
Returns structured scores + deductions string.
"""

import os
import json

from groq import Groq
from dotenv import load_dotenv

from profiles.profile_manager import get_composed_rater_prompt
from utils.retry import call_with_retry

load_dotenv()

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
_MODEL = "llama-3.3-70b-versatile"

# Expected keys in the rater's JSON output
_REQUIRED_SCORE_KEYS = {"layout", "typography", "responsiveness", "visual_design", "description_match"}


def _validate_rating(data: dict) -> dict:
    """
    Validate and normalize the rater's JSON output.
    Ensures all score keys exist and are integers 0-10.
    Returns a clean dict with 'scores' and 'deductions'.
    """
    scores = data.get("scores", {})

    # Ensure all required keys exist with valid integer values 0-10
    clean_scores = {}
    for key in _REQUIRED_SCORE_KEYS:
        val = scores.get(key, 5)  # Default to 5 if missing
        try:
            val = int(val)
            val = max(0, min(10, val))  # Clamp to 0-10
        except (TypeError, ValueError):
            val = 5
        clean_scores[key] = val

    deductions = data.get("deductions", "No specific deductions provided.")
    if not isinstance(deductions, str):
        deductions = str(deductions)

    return {
        "scores": clean_scores,
        "deductions": deductions,
    }


def _call_rater(system_prompt: str, html_code: str) -> dict:
    """Make the actual Groq API call for rating."""
    response = _client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Rate the following HTML website code:\n\n{html_code}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,       # Low temperature for consistent scoring
        max_completion_tokens=512,  # Rating JSON is small
    )
    raw_text = response.choices[0].message.content
    try:
        return json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        # If JSON parsing fails, return a default mid-range rating
        return {
            "scores": {"layout": 5, "typography": 5, "responsiveness": 5, "visual_design": 5, "description_match": 5},
            "deductions": f"Rater returned malformed JSON. Raw output: {raw_text[:200]}"
        }


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

    # Call with retry for rate-limit resilience
    raw_rating = call_with_retry(_call_rater, system_prompt, html_code)

    # Validate and normalize
    clean_rating = _validate_rating(raw_rating)

    # Update state
    state["last_rating_json"] = clean_rating
    state["last_deductions"] = clean_rating["deductions"]

    return state
