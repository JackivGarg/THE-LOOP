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
)
from utils.reward_graph import build_reward_graph
from utils.groq_provider import get_provider_config

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
        f'width="100%" height="700" '
        f'style="border:1px solid rgba(99,102,241,0.3); border-radius:12px;" '
        f'sandbox="allow-scripts allow-same-origin">'
        f'</iframe>'
    )
    container.markdown(iframe_html, unsafe_allow_html=True)


# ─── Main Layout ──────────────────────────────────────────────────────────────

st.markdown("# 🔁 AI Website Builder")
st.markdown("*Generate, rate, and iteratively improve websites with AI*")
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

left_col, right_col = st.columns([1, 2], gap="large")

state = st.session_state.gen_state

# ─── LEFT PANEL ───────────────────────────────────────────────────────────────

with left_col:
    # ── Profile Selector ──
    st.markdown("#### 📋 Profile")
    profiles = list_profiles()
    profile_idx = profiles.index(state["active_profile"]) if state["active_profile"] in profiles else 0
    selected_profile = st.selectbox(
        "Select rating profile",
        profiles,
        index=profile_idx,
        disabled=state.get("is_running", False),
        label_visibility="collapsed",
    )
    state["active_profile"] = selected_profile

    # Profile management row
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
            except (ValueError, FileNotFoundError) as e:
                st.error(str(e))

    # New profile dialog
    if st.session_state.get("_show_new_profile", False):
        with st.form("new_profile_form"):
            new_name = st.text_input("Profile name")
            new_criteria = st.text_area("Criteria (one per line, start with -)")
            if st.form_submit_button("Create"):
                if new_name.strip():
                    save_profile(new_name.strip(), new_criteria)
                    state["active_profile"] = new_name.strip()
                    st.session_state._show_new_profile = False
                    st.rerun()

    # Clone profile dialog
    if st.session_state.get("_show_clone_profile", False):
        with st.form("clone_profile_form"):
            clone_name = st.text_input("New profile name")
            if st.form_submit_button("Clone"):
                if clone_name.strip():
                    try:
                        clone_profile(selected_profile, clone_name.strip())
                        state["active_profile"] = clone_name.strip()
                        st.session_state._show_clone_profile = False
                        st.rerun()
                    except (FileExistsError, FileNotFoundError) as e:
                        st.error(str(e))

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # ── Input Form ──
    st.markdown("#### ✏️ Your Website")
    title = st.text_input(
        "Title",
        value=state["user_input"]["title"],
        placeholder="My Portfolio",
        disabled=state.get("is_running", False),
    )
    description = st.text_area(
        "Description",
        value=state["user_input"]["description"],
        placeholder="A clean minimal portfolio for a data scientist from Delhi...",
        height=100,
        disabled=state.get("is_running", False),
    )

    generate_clicked = st.button(
        "🚀 Generate Website",
        type="primary",
        use_container_width=True,
        disabled=state.get("is_running", False) or not title.strip(),
    )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # ── Live Status ──
    st.markdown("#### 📊 Progress")

    # Placeholders for live updates
    status_placeholder = st.empty()
    iter_placeholder = st.empty()
    reward_placeholder = st.empty()
    graph_placeholder = st.empty()
    deductions_placeholder = st.empty()
    validation_placeholder = st.empty()

    # Show current state if we have data
    if state["reward_history"]:
        current_reward = state["reward_history"][-1]
        arrow = get_reward_arrow(state["reward_history"])
        color_class = get_reward_color_class(current_reward)

        iter_placeholder.markdown(
            f'<div class="iter-counter">Iteration {state["iteration"]} / {state["max_iterations"]}</div>',
            unsafe_allow_html=True,
        )
        reward_placeholder.markdown(
            f'<div class="reward-badge {color_class}">{current_reward:.3f}{arrow}</div>',
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

    if state.get("generation_complete"):
        status_placeholder.markdown(
            '<span class="status-complete">✅ Generation complete</span>',
            unsafe_allow_html=True,
        )
        if state.get("early_exit"):
            st.info("Stopped early — reward plateaued.")


# ─── RIGHT PANEL ──────────────────────────────────────────────────────────────

with right_col:
    st.markdown("#### 🌐 Live Preview")
    preview_placeholder = st.empty()

    if state.get("current_code"):
        render_html_preview(state["current_code"], preview_placeholder)
    else:
        preview_placeholder.markdown(
            """
            <div style="
                height: 700px;
                background: rgba(30,30,50,0.4);
                border: 2px dashed rgba(99,102,241,0.3);
                border-radius: 16px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #64748b;
                font-size: 1.2rem;
            ">
                Your generated website will appear here...
            </div>
            """,
            unsafe_allow_html=True,
        )


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
    with left_col:
        status_placeholder.markdown(
            '<span class="status-running">⚡ Generating...</span>',
            unsafe_allow_html=True,
        )

    try:
        for i in range(state["max_iterations"]):
            if should_stop(state):
                break

            # ── Step 1: Plan ──
            with left_col:
                status_placeholder.markdown(
                    f'<span class="status-running">🧠 Planning (iteration {state["iteration"] + 1})...</span>',
                    unsafe_allow_html=True,
                )
            state = plan(state)

            # ── Step 2: Generate or Update Code ──
            if state["iteration"] == 0:
                with left_col:
                    status_placeholder.markdown(
                        '<span class="status-running">💻 Writing code...</span>',
                        unsafe_allow_html=True,
                    )
                state = write_code(state)
            else:
                with left_col:
                    status_placeholder.markdown(
                        f'<span class="status-running">🔧 Updating code (iteration {state["iteration"] + 1})...</span>',
                        unsafe_allow_html=True,
                    )
                state = update_code(state)

            # Update preview immediately after code generation
            if state.get("current_code"):
                render_html_preview(state["current_code"], preview_placeholder)

            # ── Step 3: Rate ──
            with left_col:
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
            with left_col:
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

        with left_col:
            status_placeholder.markdown(
                '<span class="status-complete">✅ Generation complete!</span>',
                unsafe_allow_html=True,
            )

    except Exception as e:
        state["is_running"] = False
        metadata = getattr(e, "metadata", None)
        if metadata is not None:
            state.setdefault("llm_request_trace", []).append(metadata.as_dict())
        st.session_state.gen_state = state
        with left_col:
            status_placeholder.markdown(
                f'<span style="color:#ef4444;">❌ Error: {str(e)}</span>',
                unsafe_allow_html=True,
            )
        st.error(f"Generation failed: {e}")


# ─── POST-GENERATION SECTION ─────────────────────────────────────────────────

if state.get("generation_complete") and state.get("current_code"):
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("### 📦 Your Website is Ready")

    action_col1, action_col2 = st.columns(2)

    with action_col1:
        # Download button
        st.download_button(
            label="⬇️ Download HTML",
            data=state["current_code"],
            file_name=f"{state['user_input']['title'].replace(' ', '_').lower()}_website.html",
            mime="text/html",
            use_container_width=True,
        )

    with action_col2:
        # Full screen link
        fullscreen_url = make_fullscreen_link(state["current_code"])
        st.markdown(
            f'<a href="{fullscreen_url}" target="_blank" style="'
            f'display:block; text-align:center; padding:0.6rem; '
            f'background:rgba(99,102,241,0.2); border:1px solid rgba(99,102,241,0.4); '
            f'border-radius:8px; color:#a5b4fc; text-decoration:none; font-weight:600;'
            f'">↗️ Open Full Screen</a>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # ── Feedback Section ──
    st.markdown("#### 💬 Tell us your preferences for next time")
    feedback_text = st.text_area(
        "What would you like different?",
        placeholder="e.g., Make it more minimalist, use darker colors, less gradients...",
        height=80,
        label_visibility="collapsed",
    )

    fcol1, fcol2 = st.columns([1, 1])
    with fcol1:
        if st.button("📝 Submit Preference", use_container_width=True, disabled=not feedback_text.strip()):
            with st.spinner("Updating your profile preferences..."):
                state = update_criteria(state, feedback_text.strip())
                st.session_state.gen_state = state
                st.success(f"Profile updated! {state['criteria_changelog'][-1]}")

    with fcol2:
        if st.button("🔄 Regenerate", use_container_width=True):
            # Keep title/description and profile, reset everything else
            old_title = state["user_input"]["title"]
            old_desc = state["user_input"]["description"]
            old_profile = state["active_profile"]

            new_state = init_state()
            new_state["user_input"]["title"] = old_title
            new_state["user_input"]["description"] = old_desc
            new_state["active_profile"] = old_profile

            st.session_state.gen_state = new_state
            st.rerun()

    # ── Final Stats ──
    if state["reward_history"]:
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown("#### 📈 Generation Summary")
        stat_cols = st.columns(4)
        with stat_cols[0]:
            st.metric("Iterations", state["iteration"])
        with stat_cols[1]:
            st.metric("Final Reward", f"{state['reward_history'][-1]:.3f}")
        with stat_cols[2]:
            best = max(state["reward_history"])
            st.metric("Best Reward", f"{best:.3f}")
        with stat_cols[3]:
            improvement = state["reward_history"][-1] - state["reward_history"][0] if len(state["reward_history"]) > 1 else 0
            st.metric("Total Improvement", f"{improvement:+.3f}")

        evaluation = state.get("last_deterministic_evaluation")
        if evaluation:
            with st.expander("Deterministic validation report"):
                st.metric("Deterministic quality", f"{evaluation['score']:.1f} / 10")
                if evaluation["issues"]:
                    for issue in evaluation["issues"]:
                        st.write(f"- {issue}")
                else:
                    st.success("All deterministic checks passed.")
