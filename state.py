"""
Session state schema and helper functions for the AI Website Builder.
Manages the single state object that flows through all nodes in the generation loop.
"""

import uuid
import copy


# Weights for computing overall_reward from individual dimension scores.
# overall_reward = sum(score * weight) / 10.0  →  produces 0.0–1.0
REWARD_WEIGHTS = {
    "layout": 0.20,
    "typography": 0.20,
    "responsiveness": 0.15,
    "visual_design": 0.25,
    "description_match": 0.20,
}

DEFAULT_STATE = {
    "session_id": None,
    "user_input": {"title": "", "description": ""},
    "active_profile": "default",
    "iteration": 0,
    "max_iterations": 4,
    "min_iterations": 2,           # Must run at least 2 before early-exit logic activates
    "quality_threshold": 0.82,
    "early_exit_delta": 0.02,      # Stop if improvement < this between consecutive iterations
    "current_code": None,          # Raw HTML string, updated every iteration
    "reward_history": [],          # list[float], one entry per completed iteration
    "last_rating_json": None,      # dict with "scores" and "deductions" from rater
    "last_deductions": "",         # String explaining why marks were reduced
    "criteria_version": 1,
    "criteria_changelog": ["v1: default"],
    "early_exit": False,
    "generation_complete": False,
    "is_running": False,           # Guards against double-click on Generate
    "output_path": None,           # Path to saved .html file in outputs/
}


def init_state() -> dict:
    """Return a fresh copy of DEFAULT_STATE with a new session ID."""
    state = copy.deepcopy(DEFAULT_STATE)
    state["session_id"] = str(uuid.uuid4())
    return state


def compute_overall_reward(scores: dict) -> float:
    """
    Compute a single 0.0–1.0 reward from the rater's per-dimension scores (each 0–10).
    Uses fixed weights defined in REWARD_WEIGHTS.
    Returns 0.0 if scores are missing or malformed.
    """
    try:
        total = sum(scores.get(dim, 0) * weight for dim, weight in REWARD_WEIGHTS.items())
        return round(total / 10.0, 4)
    except (TypeError, AttributeError):
        return 0.0


def should_stop(state: dict) -> bool:
    """
    Determine if the generation loop should stop.
    Three exit conditions:
      1. Max iterations reached
      2. Quality threshold crossed
      3. Plateau detected (improvement < delta) — only after min_iterations
    Regressions (negative delta) do NOT trigger early exit — the planner self-corrects.
    """
    # Hard cap
    if state["iteration"] >= state["max_iterations"]:
        return True

    # Quality threshold met
    if state["reward_history"] and state["reward_history"][-1] >= state["quality_threshold"]:
        return True

    # Plateau detection — only after minimum iterations to avoid noisy early exits
    if state["iteration"] >= state["min_iterations"] and len(state["reward_history"]) >= 2:
        delta = state["reward_history"][-1] - state["reward_history"][-2]
        # Regression → don't exit, let planner fix it
        if delta < 0:
            return False
        # Plateau → exit
        if delta < state["early_exit_delta"]:
            state["early_exit"] = True
            return True

    return False
