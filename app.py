"""
AI Website Builder — Streamlit App
Main entry point. Two-column layout with live preview, reward graph,
and iterative AI generation loop.
"""

import os
import sys
import base64

import streamlit as st
import streamlit.components.v1 as st_components

# Ensure project root is on Python path for imports
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from state import init_state, should_stop, compute_overall_reward
from nodes.planner import plan
from nodes.code_writer import write_code
from nodes.code_updater import update_code
from nodes.rater import rate
from nodes.criteria_updater import update_criteria
from profiles.profile_manager import (
    list_profiles,
    load_profile,
    save_profile,
    clone_profile,
    delete_profile,
    criteria_diff,
    get_profile_version,
    list_profile_versions,
    rollback_profile,
)
from utils.reward_graph import build_reward_graph
from utils.groq_provider import get_provider_config
from utils.retry import RetryExhaustedError

# ─── Page Config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AI Website Builder",
    page_icon="🔁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

try:
    get_provider_config()
except RuntimeError as error:
    st.error(f"AI generation is unavailable: {error}")
    st.stop()

# ─── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Dark theme overrides */
    .stApp {
        background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%);
    }

    .block-container {
        max-width: 1500px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    [data-testid="stMetric"] {
        background: rgba(30,30,50,0.42);
        border: 1px solid rgba(99,102,241,0.22);
        border-radius: 10px;
        padding: 0.65rem 0.8rem;
    }
    
    /* Reward badge styles */
    .reward-badge {
        font-size: 2rem;
        font-weight: 700;
        padding: 0.5rem 1rem;
        border-radius: 12px;
        text-align: center;
        margin: 0.5rem 0;
    }
    .reward-low { background: rgba(239,68,68,0.2); color: #ef4444; }
    .reward-mid { background: rgba(245,158,11,0.2); color: #f59e0b; }
    .reward-high { background: rgba(34,197,94,0.2); color: #22c55e; }
    
    /* Iteration counter */
    .iter-counter {
        font-size: 1.1rem;
        color: #94a3b8;
        padding: 0.3rem 0;
    }
    
    /* Deductions box */
    .deductions-box {
        background: rgba(30,30,50,0.6);
        border: 1px solid rgba(99,102,241,0.3);
        border-radius: 10px;
        padding: 1rem;
        font-size: 0.85rem;
        color: #cbd5e1;
        max-height: 150px;
        overflow-y: auto;
    }
    
    /* Status indicator */
    .status-running {
        color: #6366f1;
        font-weight: 600;
    }
    .status-complete {
        color: #22c55e;
        font-weight: 600;
    }

    /* Section dividers */
    .section-divider {
        border-top: 1px solid rgba(99,102,241,0.2);
        margin: 1rem 0;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Title styling */
    h1 {
        background: linear-gradient(90deg, #6366f1, #a78bfa, #c084fc);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800 !important;
    }
</style>
""", unsafe_allow_html=True)


# ─── Session State Init ───────────────────────────────────────────────────────

if "gen_state" not in st.session_state:
    st.session_state.gen_state = init_state()
if "show_feedback" not in st.session_state:
    st.session_state.show_feedback = False
if "error_msg" not in st.session_state:
    st.session_state.error_msg = None


# ─── Helper Functions ──────────────────────────────────────────────────────────

def get_reward_color_class(reward: float) -> str:
    """Return CSS class based on reward value."""
    if reward >= 0.75:
        return "reward-high"
    elif reward >= 0.50:
        return "reward-mid"
    return "reward-low"


def get_reward_arrow(history: list[float]) -> str:
    """Return ↑ ↓ or → based on last two rewards."""
    if len(history) < 2:
        return ""
    delta = history[-1] - history[-2]
    if delta > 0.01:
        return " ↑"
    elif delta < -0.01:
        return " ↓"
    return " →"


def save_html_file(state: dict) -> str:
    """Save the generated HTML to outputs/ directory. Returns the file path."""
    output_dir = os.path.join(_PROJECT_ROOT, "outputs")
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{state['session_id']}.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(state["current_code"])
    return filepath


def make_fullscreen_link(html_code: str) -> str:
    """Create a data:text/html base64 link for full-screen preview."""
    encoded = base64.b64encode(html_code.encode("utf-8")).decode("utf-8")
    return f"data:text/html;base64,{encoded}"


def render_html_preview(html_code: str, container):
    """Render HTML preview inside a Streamlit container using an iframe."""
    # Encode the HTML into a base64 data URI and render via an iframe in markdown.
    # This avoids the st.empty() + st.components.v1.html() incompatibility.
    encoded = base64.b64encode(html_code.encode("utf-8")).decode("utf-8")
    iframe_html = (
        f'<iframe src="data:text/html;base64,{encoded}" '
        f'width="100%" height="620" '
        f'style="border:1px solid rgba(99,102,241,0.3); border-radius:12px;" '
        f'sandbox="allow-scripts allow-same-origin">'
        f'</iframe>'
    )
    container.markdown(iframe_html, unsafe_allow_html=True)


# ─── Main Workspace ───────────────────────────────────────────────────────────

state = st.session_state.gen_state
header_col, status_col = st.columns([4, 1])
with header_col:
    st.title("🔁 THE LOOP")
    st.caption("Create a website, inspect the live result, then let the evaluation loop improve it.")
with status_col:
    if state.get("generation_complete"):
        st.success("Ready")
    elif state.get("is_running"):
        st.info("Generating")
    else:
        st.caption("Workspace idle")

control_col, preview_col = st.columns([0.9, 2.1], gap="large")

# ─── Build Controls ───────────────────────────────────────────────────────────

with control_col:
    with st.container(border=True):
        st.subheader("Build brief")
        title = st.text_input(
            "Website title",
            value=state["user_input"]["title"],
            placeholder="My Portfolio",
            disabled=state.get("is_running", False),
        )
        description = st.text_area(
            "What should it include?",
            value=state["user_input"]["description"],
            placeholder="A clean, minimal portfolio for a data scientist from Delhi...",
            height=150,
            disabled=state.get("is_running", False),
        )

        profiles = list_profiles()
        profile_idx = profiles.index(state["active_profile"]) if state["active_profile"] in profiles else 0
        selected_profile = st.selectbox(
            "Evaluation profile",
            profiles,
            index=profile_idx,
            disabled=state.get("is_running", False),
        )
        state["active_profile"] = selected_profile

        generate_clicked = st.button(
            "🚀 Generate website",
            type="primary",
            use_container_width=True,
            disabled=state.get("is_running", False) or not title.strip(),
        )

    with st.expander("Manage evaluation profiles"):
        pcol1, pcol2, pcol3 = st.columns(3)
        with pcol1:
            if st.button("➕ New", disabled=state.get("is_running", False), use_container_width=True):
                st.session_state._show_new_profile = True
        with pcol2:
            if st.button("📋 Clone", disabled=state.get("is_running", False), use_container_width=True):
                st.session_state._show_clone_profile = True
        with pcol3:
            if st.button("🗑️ Delete", disabled=state.get("is_running", False) or selected_profile == "default", use_container_width=True):
                try:
                    delete_profile(selected_profile)
                    state["active_profile"] = "default"
                    st.rerun()
                except (ValueError, FileNotFoundError) as error:
                    st.error(str(error))

        if st.session_state.get("_show_new_profile", False):
            with st.form("new_profile_form"):
                new_name = st.text_input("Profile name")
                new_criteria = st.text_area("Criteria (one per line, start with -)")
                if st.form_submit_button("Create profile") and new_name.strip():
                    try:
                        save_profile(new_name.strip(), new_criteria, changelog="Created from the profile manager.")
                        state["active_profile"] = new_name.strip()
                        st.session_state._show_new_profile = False
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))

        if st.session_state.get("_show_clone_profile", False):
            with st.form("clone_profile_form"):
                clone_name = st.text_input("New profile name")
                if st.form_submit_button("Clone profile") and clone_name.strip():
                    try:
                        clone_profile(selected_profile, clone_name.strip())
                        state["active_profile"] = clone_name.strip()
                        st.session_state._show_clone_profile = False
                        st.rerun()
                    except (FileExistsError, FileNotFoundError) as error:
                        st.error(str(error))

        try:
            versions = list_profile_versions(selected_profile)
            current_version = versions[-1]["version"]
            version_options = [version["version"] for version in reversed(versions)]
            viewed_version = st.selectbox(
                "Saved criteria version",
                version_options,
                format_func=lambda version: f"v{version} — {get_profile_version(selected_profile, version)['changelog']}",
                key=f"profile_version_{selected_profile}",
            )
            viewed = get_profile_version(selected_profile, viewed_version)
            st.caption(f"Saved {viewed['created_at']} · source: {viewed.get('source', 'manual')}")
            st.code(viewed["criteria"], language="text")
            if viewed_version < current_version:
                st.caption("Changes from this version to the current criteria:")
                st.code(criteria_diff(selected_profile, viewed_version, current_version) or "No text changes.", language="diff")
                if st.button(f"Restore v{viewed_version}", key=f"restore_{selected_profile}_{viewed_version}"):
                    restored = rollback_profile(selected_profile, viewed_version)
                    state["criteria_version"] = restored["current_version"]
                    state["criteria_changelog"].append(f"v{restored['current_version']}: restored v{viewed_version}")
                    st.session_state.gen_state = state
                    st.rerun()
        except (FileNotFoundError, ValueError) as error:
            st.error(f"Profile history is unavailable: {error}")

    with st.container(border=True):
        st.subheader("Evaluation progress")
        status_placeholder = st.empty()
        iter_placeholder = st.empty()
        reward_placeholder = st.empty()
        validation_placeholder = st.empty()
        with st.expander("Reward history", expanded=False):
            graph_placeholder = st.empty()
        with st.expander("Latest feedback", expanded=False):
            deductions_placeholder = st.empty()

        if state["reward_history"]:
            current_reward = state["reward_history"][-1]
            arrow = get_reward_arrow(state["reward_history"])
            color_class = get_reward_color_class(current_reward)
            iter_placeholder.markdown(
                f'<div class="iter-counter">Iteration {state["iteration"]} of {state["max_iterations"]}</div>',
                unsafe_allow_html=True,
            )
            reward_placeholder.markdown(
                f'<div class="reward-badge {color_class}">{current_reward:.3f}{arrow}</div>',
                unsafe_allow_html=True,
            )
            evaluation = state.get("last_deterministic_evaluation")
            if evaluation:
                validation_placeholder.caption(f"Deterministic quality · {evaluation['score']:.1f}/10")
            graph_placeholder.plotly_chart(
                build_reward_graph(state["reward_history"], state["quality_threshold"]),
                use_container_width=True,
                config={"displayModeBar": False},
            )
            if state["last_deductions"]:
                deductions_placeholder.markdown(
                    f'<div class="deductions-box"><b>Latest feedback</b><br>{state["last_deductions"]}</div>',
                    unsafe_allow_html=True,
                )

        if state.get("generation_complete"):
            status_placeholder.success("Generation complete")
            if state.get("early_exit"):
                st.caption("Stopped early because the reward plateaued.")
        elif not state.get("is_running"):
            status_placeholder.caption("Describe the site you want, then generate your first draft.")


# ─── Live Preview ─────────────────────────────────────────────────────────────

with preview_col:
    with st.container(border=True):
        preview_header, preview_note = st.columns([3, 1])
        with preview_header:
            st.subheader("Live preview")
        with preview_note:
            st.caption("Rendered safely in a sandbox")

        preview_placeholder = st.empty()
        if state.get("current_code"):
            render_html_preview(state["current_code"], preview_placeholder)
        else:
            preview_placeholder.info("Your generated website will appear here after the first generation.")


# ─── GENERATION LOOP ─────────────────────────────────────────────────────────

if generate_clicked and title.strip():
    # Reset state for new generation
    state = init_state()
    state["user_input"]["title"] = title.strip()
    state["user_input"]["description"] = description.strip()
    state["active_profile"] = selected_profile
    state["is_running"] = True
    st.session_state.gen_state = state

    # Update status
    status_placeholder.markdown(
        '<span class="status-running">⚡ Generating...</span>',
        unsafe_allow_html=True,
    )

    try:
        for i in range(state["max_iterations"]):
            if should_stop(state):
                break

            # ── Step 1: Plan ──
            status_placeholder.markdown(
                f'<span class="status-running">🧠 Planning (iteration {state["iteration"] + 1})...</span>',
                unsafe_allow_html=True,
            )
            state = plan(state)

            # ── Step 2: Generate or Update Code ──
            if state["iteration"] == 0:
                status_placeholder.markdown(
                    '<span class="status-running">💻 Writing code...</span>',
                    unsafe_allow_html=True,
                )
                state = write_code(state)
            else:
                status_placeholder.markdown(
                    f'<span class="status-running">🔧 Updating code (iteration {state["iteration"] + 1})...</span>',
                    unsafe_allow_html=True,
                )
                state = update_code(state)

            # Update preview immediately after code generation
            if state.get("current_code"):
                render_html_preview(state["current_code"], preview_placeholder)

            # ── Step 3: Rate ──
            status_placeholder.markdown(
                '<span class="status-running">⭐ Rating...</span>',
                unsafe_allow_html=True,
            )
            state = rate(state)

            # Compute reward and update history
            reward = compute_overall_reward(
                state["last_rating_json"]["scores"],
                state["last_deterministic_evaluation"]["score"],
            )
            state["reward_history"].append(reward)
            state["iteration"] += 1

            # ── Update Left Panel ──
            arrow = get_reward_arrow(state["reward_history"])
            color_class = get_reward_color_class(reward)

            iter_placeholder.markdown(
                f'<div class="iter-counter">Iteration {state["iteration"]} / {state["max_iterations"]}</div>',
                unsafe_allow_html=True,
            )
            reward_placeholder.markdown(
                f'<div class="reward-badge {color_class}">{reward:.3f}{arrow}</div>',
                unsafe_allow_html=True,
            )
            graph_placeholder.plotly_chart(
                build_reward_graph(state["reward_history"], state["quality_threshold"]),
                use_container_width=True,
            )
            if state["last_deductions"]:
                deductions_placeholder.markdown(
                    f'<div class="deductions-box">💬 <b>Rater says:</b><br>{state["last_deductions"]}</div>',
                    unsafe_allow_html=True,
                )
            evaluation = state.get("last_deterministic_evaluation")
            if evaluation:
                validation_placeholder.caption(f"Deterministic quality: {evaluation['score']:.1f}/10")

        # ── Generation Complete ──
        state["generation_complete"] = True
        state["is_running"] = False

        # Save HTML file
        filepath = save_html_file(state)
        state["output_path"] = filepath

        st.session_state.gen_state = state

        status_placeholder.markdown(
            '<span class="status-complete">✅ Generation complete!</span>',
            unsafe_allow_html=True,
        )

    except RetryExhaustedError as e:
        state["is_running"] = False
        st.session_state.gen_state = state
        retry_hint = (
            f" Groq asked for about {e.retry_after_seconds:.1f} seconds between requests."
            if e.retry_after_seconds is not None
            else ""
        )
        status_placeholder.error("Generation paused by Groq's rate limit")
        st.error(
            "The model's token-per-minute limit was reached before this round could finish. "
            "The app retried automatically, but Groq is still throttling this account." + retry_hint
        )
        with st.expander("Technical error details"):
            st.code(str(e))

    except Exception as e:
        state["is_running"] = False
        metadata = getattr(e, "metadata", None)
        if metadata is not None:
            state.setdefault("llm_request_trace", []).append(metadata.as_dict())
        st.session_state.gen_state = state
        status_placeholder.markdown(
            f'<span style="color:#ef4444;">❌ Error: {str(e)}</span>',
            unsafe_allow_html=True,
        )
        st.error(f"Generation failed: {e}")


# ─── POST-GENERATION SECTION ─────────────────────────────────────────────────

if state.get("generation_complete") and state.get("current_code"):
    with st.container(border=True):
        st.subheader("Results & quality")
        action_col1, action_col2, _ = st.columns([1, 1, 5])
        with action_col1:
            st.download_button(
                label="⬇️ Download HTML",
                data=state["current_code"],
                file_name=f"{state['user_input']['title'].replace(' ', '_').lower()}_website.html",
                mime="text/html",
            )
        with action_col2:
            fullscreen_url = make_fullscreen_link(state["current_code"])
            st.markdown(
                f'<a href="{fullscreen_url}" target="_blank" style="'
                f'display:inline-block; padding:0.45rem 0.75rem; '
                f'background:rgba(99,102,241,0.2); border:1px solid rgba(99,102,241,0.4); '
                f'border-radius:8px; color:#a5b4fc; text-decoration:none; font-weight:600;'
                f'">↗️ Full screen</a>',
                unsafe_allow_html=True,
            )

        if state["reward_history"]:
            summary_cols = st.columns(4)
            summary_cols[0].metric("Iterations", state["iteration"])
            summary_cols[1].metric("Final reward", f"{state['reward_history'][-1]:.3f}")
            summary_cols[2].metric("Best reward", f"{max(state['reward_history']):.3f}")
            improvement = state["reward_history"][-1] - state["reward_history"][0] if len(state["reward_history"]) > 1 else 0
            summary_cols[3].metric("Improvement", f"{improvement:+.3f}")

        evaluation = state.get("last_deterministic_evaluation")
        if evaluation:
            with st.expander("Evaluation report", expanded=False):
                st.metric("Deterministic quality", f"{evaluation['score']:.1f} / 10")
                if evaluation["issues"]:
                    for issue in evaluation["issues"]:
                        st.write(f"- {issue}")
                else:
                    st.success("All deterministic checks passed.")

        with st.expander("Refine this result", expanded=False):
            if state.get("last_criteria_diff"):
                st.caption("Most recent criteria change")
                st.code(state["last_criteria_diff"], language="diff")
            feedback_text = st.text_area(
                "What would you like different?",
                placeholder="e.g., Make it more minimalist, use darker colors, less gradients...",
                height=80,
                label_visibility="collapsed",
            )
            fcol1, fcol2, _ = st.columns([1, 1, 4])
            with fcol1:
                if st.button("📝 Save preference", disabled=not feedback_text.strip()):
                    with st.spinner("Updating your profile preferences..."):
                        state = update_criteria(state, feedback_text.strip())
                        st.session_state.gen_state = state
                        st.success(f"Profile updated! {state['criteria_changelog'][-1]}")
            with fcol2:
                if st.button("🔄 Regenerate"):
                    new_state = init_state()
                    new_state["user_input"]["title"] = state["user_input"]["title"]
                    new_state["user_input"]["description"] = state["user_input"]["description"]
                    new_state["active_profile"] = state["active_profile"]
                    st.session_state.gen_state = new_state
                    st.rerun()
