"""Build Plotly figures from the EV simulation outputs."""

import pandas as pd


def make_population_figure(summary):
    """Fleet connection, SoC, demand, and stored energy."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        specs=[[{"secondary_y": True}], [{}], [{}]],
        vertical_spacing=0.08,
        subplot_titles=(
            "Connection availability and battery SoC",
            "Fleet demand from the grid",
            "Energy stored in the fleet",
        ),
    )
    x = summary.timestamp
    fig.add_trace(
        go.Bar(
            x=x, y=summary.plugged_in_percent, name="Vehicles plugged in", marker_color="#B9D5EB"
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x, y=summary.p05_soc, mode="lines", line_width=0, showlegend=False, hoverinfo="skip"
        ),
        row=1,
        col=1,
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=summary.p95_soc,
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(229,137,58,0.20)",
            line_width=0,
            name="5th–95th percentile SoC",
        ),
        row=1,
        col=1,
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=summary.mean_soc,
            mode="lines",
            line=dict(color="#C76A16", width=2),
            name="Mean SoC",
        ),
        row=1,
        col=1,
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=summary.grid_power_kw,
            mode="lines",
            line=dict(color="#D45C49", shape="hv"),
            name="Grid demand",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=summary.stored_energy_kwh,
            mode="lines",
            line_color="#477C69",
            name="Stored energy",
        ),
        row=3,
        col=1,
    )
    fig.update_yaxes(title_text="Plugged in (%)", range=[0, 100], row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="SoC (%)", range=[0, 100], row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="kW", rangemode="tozero", row=2, col=1)
    fig.update_yaxes(title_text="kWh", rangemode="tozero", row=3, col=1)
    fig.update_layout(
        template="plotly_white",
        height=800,
        bargap=0,
        legend=dict(orientation="h", y=1.10),
        margin=dict(t=100),
        hovermode="x unified",
    )
    return fig


def make_agent_figure(data, agent_id, timestep_minutes=5):
    """SoC at interval boundaries, with connected intervals shaded blue."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    d = data.loc[data.agent_id.eq(agent_id)].sort_values("timestamp")
    if d.empty:
        raise ValueError(f"Unknown agent_id: {agent_id}")
    step = pd.Timedelta(minutes=timestep_minutes)
    # Include the final END value at its actual boundary, not at step start.
    x = list(d.timestamp) + [d.timestamp.iloc[-1] + step]
    soc = list(100 * d.soc_start) + [100 * d.soc_end.iloc[-1]]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.15)
    fig.add_trace(
        go.Scatter(x=x, y=soc, name="SoC", mode="lines", line_color="#C76A16"), row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=d.timestamp,
            y=d.grid_power_kw,
            name="Grid demand",
            line=dict(color="#D45C49", shape="hv"),
        ),
        row=2,
        col=1,
    )
    groups = d.is_plugged_in.ne(d.is_plugged_in.shift()).cumsum()
    for _, span in d.groupby(groups):
        if span.is_plugged_in.iloc[0]:
            fig.add_vrect(
                x0=span.timestamp.iloc[0],
                x1=span.timestamp.iloc[-1] + step,
                fillcolor="#B9D5EB",
                opacity=0.4,
                line_width=0,
                layer="below",
                row=1,
                col=1,
            )
    fig.update_yaxes(title_text="SoC (%)", range=[0, 100], row=1, col=1)
    fig.update_yaxes(title_text="kW", rangemode="tozero", row=2, col=1)
    fig.update_layout(
        template="plotly_white",
        height=450,
        title=f"{agent_id} · blue shading = plugged in",
        hovermode="x unified",
    )
    return fig
