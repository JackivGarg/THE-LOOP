"""Quick smoke test — verifies all imports and core logic work."""
import sys
sys.path.insert(0, ".")

from state import init_state, should_stop, compute_overall_reward
from utils.html_validator import extract_html
from utils.retry import call_with_retry
from utils.reward_graph import build_reward_graph
from profiles.profile_manager import list_profiles, load_profile, get_composed_rater_prompt

print("=== All imports OK ===")

# Test init_state
s = init_state()
print(f"Session ID: {s['session_id'][:8]}...")
print(f"Default iteration: {s['iteration']}")

# Test profiles
profiles = list_profiles()
print(f"Profiles: {profiles}")

default_text = load_profile("default")
print(f"Default profile: {len(default_text)} chars")

composed = get_composed_rater_prompt("default")
print(f"Composed rater prompt: {len(composed)} chars")
assert "{{editable_block}}" not in composed, "Template placeholder not replaced!"
print("Template injection: OK")

# Test compute_overall_reward
scores = {"layout": 7, "typography": 6, "responsiveness": 8, "visual_design": 5, "description_match": 9}
reward = compute_overall_reward(scores, deterministic_score=8)
llm_quality = (7*0.25 + 6*0.25 + 8*0.20 + 5*0.30) / 10.0
expected = 0.40 * 0.8 + 0.40 * llm_quality + 0.20 * 0.9
print(f"Reward: {reward} (expected: {round(expected, 4)})")
assert abs(reward - expected) < 0.001, f"Reward mismatch: {reward} != {expected}"
print("Reward computation: OK")

# Test HTML extraction
html_with_fences = '```html\n<!DOCTYPE html>\n<html><body>test</body></html>\n```'
result = extract_html(html_with_fences)
assert result is not None, "Failed to extract HTML from markdown fences"
assert result.startswith("<!DOCTYPE html>"), f"Bad HTML: {result[:50]}"
print(f"HTML extraction from fences: OK ({len(result)} chars)")

html_clean = '<!DOCTYPE html>\n<html><body>clean</body></html>'
result2 = extract_html(html_clean)
assert result2 is not None and "clean" in result2
print("HTML extraction from clean: OK")

html_no_doctype = '<html><body>no doctype</body></html>'
result3 = extract_html(html_no_doctype)
assert result3 is not None and result3.startswith("<!DOCTYPE html>")
print("HTML extraction no doctype: OK (auto-added)")

# Test should_stop
s["reward_history"] = [0.5, 0.6, 0.7]
s["iteration"] = 3
assert not should_stop(s), "Should NOT stop at 0.7"
print("should_stop at 0.7: correctly returns False")

s["reward_history"] = [0.5, 0.6, 0.85]
s["iteration"] = 3
assert should_stop(s), "Should stop at 0.85 (above threshold)"
print("should_stop at 0.85: correctly returns True (threshold)")

s2 = init_state()
s2["reward_history"] = [0.5, 0.6, 0.61]
s2["iteration"] = 3
result = should_stop(s2)
assert result, "Should stop on plateau (delta 0.01 < 0.02)"
print("should_stop plateau: correctly returns True")

s3 = init_state()
s3["reward_history"] = [0.6, 0.55]
s3["iteration"] = 3
assert not should_stop(s3), "Should NOT stop on regression"
print("should_stop regression: correctly returns False (lets planner fix)")

s4 = init_state()
s4["reward_history"] = [0.5, 0.51]
s4["iteration"] = 1  # Below min_iterations=2
assert not should_stop(s4), "Should NOT stop before min_iterations"
print("should_stop before min_iter: correctly returns False")

# Test reward graph (just check it returns a figure)
fig = build_reward_graph([0.5, 0.6, 0.7, 0.75])
assert fig is not None
print("Reward graph: OK (figure created)")

print("\n=== ALL TESTS PASSED ===")
