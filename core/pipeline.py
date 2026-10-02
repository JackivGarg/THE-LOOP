"""The original planner → writer/updater → evaluator loop, usable by any UI.

Callbacks checkpoint progress after each stage. Nodes remain independent functions
that accept and return state, which makes the pipeline testable without API calls.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

from nodes.planner import plan
from nodes.code_writer import write_code
from nodes.code_updater import update_code
from nodes.rater import rate
from state import compute_overall_reward, is_quality_ready, should_stop


class RunCancelled(Exception):
    """Cancellation is checked between stages and during retry waits."""


@dataclass(frozen=True)
class PipelineNodes:
    planner: Callable = plan
    writer: Callable = write_code
    updater: Callable = update_code
    evaluator: Callable = rate


def run_pipeline(state: dict, *, on_event: Callable, cancelled: Callable = lambda: False,
                 nodes: PipelineNodes | None = None) -> dict:
    """Run bounded improvement rounds and return the best evaluated draft.

    A completed run means the bounded search finished, not that quality passed.
    Each candidate is evaluated independently; regressions remain in history but
    cannot replace the best downloadable result.
    """
    nodes = nodes or PipelineNodes()
    best = None
    best_reward = -1.0
    while not should_stop(state):
        round_number = state["iteration"] + 1
        stages = [("planning", nodes.planner),
                  ("writing" if state["iteration"] == 0 else "improving",
                   nodes.writer if state["iteration"] == 0 else nodes.updater),
                  ("evaluating", nodes.evaluator)]
        for stage, node in stages:
            if cancelled():
                raise RunCancelled("Run cancelled between stages.")
            on_event(stage, state, f"Round {round_number}: {stage}")
            state = node(state)
            on_event("checkpoint", state, f"Round {round_number}: {stage} finished")
        reward = compute_overall_reward(state["last_rating_json"]["scores"],
                                        state["last_deterministic_evaluation"]["score"])
        state["reward_history"].append(reward)
        state["iteration"] += 1
        if reward > best_reward:
            best_reward = reward
            best = deepcopy({key: state[key] for key in (
                "current_code", "last_rating_json", "last_deterministic_evaluation", "last_deductions")})
            state["best_iteration"] = state["iteration"]
        on_event("iteration", state, f"Round {round_number} evaluated: {reward:.3f}")
    state["stop_reason"] = (
        "quality_reached" if state["iteration"] >= state["min_iterations"]
        and state["reward_history"][-1] >= state["quality_threshold"] and is_quality_ready(state)
        else "plateau" if state.get("early_exit") else "iteration_limit"
    )
    if best:
        state.update(best)
    state["best_reward"] = best_reward
    state["quality_passed"] = best_reward >= state["quality_threshold"] and is_quality_ready(state)
    state["generation_complete"] = True
    state["is_running"] = False
    on_event("completed", state, f"Finished after {state['iteration']} rounds; selected round {state.get('best_iteration')}")
    return state
