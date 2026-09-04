"""
Reward graph builder — creates a Plotly figure for the reward history.
Used in the Streamlit UI left panel to visualize convergence over iterations.
"""

import plotly.graph_objects as go


def build_reward_graph(reward_history: list[float], quality_threshold: float = 0.82) -> go.Figure:
    """
    Build a Plotly line chart showing reward progression across iterations.
    
    Args:
        reward_history: List of overall_reward values, one per iteration
        quality_threshold: The target threshold line (default 0.82)
    
    Returns:
        A Plotly Figure object ready for st.plotly_chart()
    """
    iterations = list(range(1, len(reward_history) + 1))

    fig = go.Figure()

    # Reward line
    fig.add_trace(go.Scatter(
        x=iterations,
        y=reward_history,
        mode="lines+markers",
        name="Reward",
        line=dict(color="#6366f1", width=3),
        marker=dict(size=10, color="#6366f1", line=dict(width=2, color="#fff")),
        hovertemplate="Iteration %{x}<br>Reward: %{y:.3f}<extra></extra>",
    ))

    # Threshold line
    if iterations:
        fig.add_trace(go.Scatter(
            x=[1, max(len(reward_history), 10)],
            y=[quality_threshold, quality_threshold],
            mode="lines",
            name=f"Threshold ({quality_threshold})",
            line=dict(color="#ef4444", width=2, dash="dash"),
            hoverinfo="skip",
        ))

    fig.update_layout(
        title=None,
        xaxis_title="Iteration",
        yaxis_title="Reward",
        yaxis=dict(range=[0, 1.05], dtick=0.1),
        xaxis=dict(dtick=1),
        template="plotly_dark",
        height=280,
        margin=dict(l=40, r=20, t=10, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    return fig
