"""Home presence and habitual connection state."""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_connection_timeline(
    agent: pd.Series,
    travel_windows: pd.DataFrame,
    simulation_timestamps: pd.DatetimeIndex,
    simulation_dates: pd.DatetimeIndex,
    seed: int = 44,
    initially_plugged_in: bool = True,
) -> pd.DataFrame:
    """
    Generate home presence and connection status for one agent.

    Assumptions
    -----------
    - The agent starts home; initial connection status is configurable.
    - Departure disconnects the vehicle.
    - On driving days, the connection opportunity is at home arrival.
    - On non-driving days, it is at the nominal plug-in time.
    - Once connected, the vehicle stays connected until departure.
    - plugin_frequency_per_day is provisionally interpreted as a
      daily connection probability, restricted to values from 0 to 1.

    This function does not calculate SoC or charging power.
    """
    rng = np.random.default_rng(seed)
    windows = travel_windows.loc[travel_windows["agent_id"] == agent["agent_id"]].copy()
    probability = float(agent["plugin_frequency_per_day"])
    if not np.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("The daily connection probability must be between 0 and 1.")
    timeline = pd.DataFrame({"timestamp": simulation_timestamps})
    timeline["agent_id"] = agent["agent_id"]
    timeline["is_home"] = True
    for window in windows.itertuples(index=False):
        away = (timeline["timestamp"] >= window.departure_time) & (
            timeline["timestamp"] < window.return_time
        )
        timeline.loc[away, "is_home"] = False
    returns = windows.set_index("drive_date")["return_time"]
    nominal_time = agent["nominal_plugin_time"]
    chosen_connection_steps = set()
    for day in simulation_dates:
        if day in returns.index:
            opportunity = returns.loc[day]
        else:
            opportunity = day + pd.DateOffset(hours=nominal_time.hour, minutes=nominal_time.minute)
        if rng.random() < probability:
            position = simulation_timestamps.searchsorted(opportunity)
            if position < len(simulation_timestamps):
                chosen_connection_steps.add(simulation_timestamps[position])
    connected = initially_plugged_in
    connection_status = []
    for row in timeline.itertuples(index=False):
        if not row.is_home:
            connected = False
        elif row.timestamp in chosen_connection_steps:
            connected = True
        connection_status.append(connected)
    timeline["is_plugged_in"] = connection_status
    return timeline
