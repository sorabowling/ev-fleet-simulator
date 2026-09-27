"""Derive connection, active charging, and driving sessions from intervals."""

import pandas as pd

SESSION_COLUMNS = [
    "agent_id",
    "archetype",
    "session_type",
    "start",
    "end",
    "duration_hours",
    "soc_start",
    "soc_end",
    "distance_miles",
    "grid_energy_kwh",
    "battery_charge_kwh",
    "drive_energy_kwh",
    "left_censored",
    "right_censored",
]


def extract_sessions(data: pd.DataFrame, timestep_minutes: int = 5) -> pd.DataFrame:
    """Return half-open intervals for each contiguous state.

    A connection may contain zero or multiple active charging sessions.
    ``soc_start`` of a connection is its plug-in SoC, except a left-censored
    connection which was already present at the start of the simulation.
    Driving and charging cannot overlap. Charging is nested in connection.
    """
    step = pd.Timedelta(minutes=timestep_minutes)
    records = []
    for agent_id, agent in data.sort_values(["agent_id", "timestamp"]).groupby("agent_id"):
        states = {
            "connection": agent.is_plugged_in,
            "charging": agent.grid_power_kw.gt(0),
            "driving": agent.is_driving,
        }
        for kind, active in states.items():
            groups = active.ne(active.shift()).cumsum()
            for _, span in agent.loc[active].groupby(groups.loc[active]):
                first, last = span.iloc[0], span.iloc[-1]
                records.append(
                    {
                        "agent_id": agent_id,
                        "archetype": first.archetype,
                        "session_type": kind,
                        "start": first.timestamp,
                        "end": last.timestamp + step,
                        "duration_hours": len(span) * timestep_minutes / 60,
                        "soc_start": first.soc_start,
                        "soc_end": last.soc_end,
                        "distance_miles": span.distance_miles.sum(),
                        "grid_energy_kwh": span.grid_energy_kwh.sum(),
                        "battery_charge_kwh": span.battery_charge_kwh.sum(),
                        "drive_energy_kwh": span.drive_energy_kwh.sum(),
                        "left_censored": first.timestamp == agent.timestamp.iloc[0],
                        "right_censored": last.timestamp == agent.timestamp.iloc[-1],
                    }
                )
    return pd.DataFrame(records, columns=SESSION_COLUMNS).sort_values(
        ["agent_id", "start", "session_type"], ignore_index=True
    )
