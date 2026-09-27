"""Validate model inputs and audit independent physical identities."""

from datetime import time

import numpy as np
import pandas as pd


def validate_agents(agents: pd.DataFrame) -> None:
    """Reject missing identities, nonphysical parameters, and unknown policies."""
    required = [
        "agent_id",
        "archetype",
        "miles_per_year",
        "battery_capacity_kwh",
        "driving_efficiency_mi_per_kwh",
        "plugin_frequency_per_day",
        "charger_power_kw",
        "target_soc",
        "nominal_plugin_time",
        "nominal_plugout_time",
        "charging_policy",
        "departure_anchor",
        "return_anchor",
    ]
    missing = set(required) - set(agents.columns)
    if missing:
        raise ValueError(f"Missing agent columns: {sorted(missing)}")
    if agents.empty or agents[required].isna().any().any():
        raise ValueError("Agents must be nonempty with no missing parameters.")
    if not agents.agent_id.is_unique:
        raise ValueError("Each agent_id must be unique.")
    if not agents.agent_id.map(lambda x: isinstance(x, str) and bool(x)).all():
        raise ValueError("agent_id must contain nonempty strings.")
    for name, positive in [
        ("miles_per_year", False),
        ("battery_capacity_kwh", True),
        ("driving_efficiency_mi_per_kwh", True),
        ("charger_power_kw", False),
    ]:
        values = agents[name].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values <= 0 if positive else values < 0).any():
            raise ValueError(
                f"{name} must be finite and {'positive' if positive else 'nonnegative'}."
            )
    for name in ["target_soc", "plugin_frequency_per_day"]:
        if not agents[name].between(0, 1).all():
            raise ValueError(f"{name} must be between 0 and 1.")
    if not agents.charging_policy.isin(["immediate", "scheduled"]).all():
        raise ValueError("charging_policy must be immediate or scheduled.")
    for name in [
        "nominal_plugin_time",
        "nominal_plugout_time",
        "departure_anchor",
        "return_anchor",
    ]:
        if not agents[name].map(lambda x: isinstance(x, time) and x.tzinfo is None).all():
            raise ValueError(f"{name} must contain local datetime.time values.")
    if (agents.departure_anchor >= agents.return_anchor).any():
        raise ValueError("Departure anchors must precede same-day return anchors.")


def validate_time_grid(
    dates: pd.DatetimeIndex, timestamps: pd.DatetimeIndex, timestep_minutes: int
) -> None:
    """Require a complete, regular grid for consecutive local calendar days."""
    if (
        isinstance(timestep_minutes, bool)
        or not isinstance(timestep_minutes, (int, np.integer))
        or timestep_minutes <= 0
        or 60 % timestep_minutes
    ):
        raise ValueError("timestep_minutes must be a positive integer dividing 60.")
    dates, timestamps = pd.DatetimeIndex(dates), pd.DatetimeIndex(timestamps)
    if dates.empty or dates.hasnans or not dates.equals(dates.normalize()):
        raise ValueError("Simulation dates must be nonempty local midnights.")
    expected_dates = pd.date_range(dates[0], periods=len(dates), freq="D")
    if not dates.equals(expected_dates):
        raise ValueError("Simulation dates must be unique, ordered, and consecutive.")
    expected = pd.date_range(
        dates[0], dates[-1] + pd.DateOffset(days=1), freq=f"{timestep_minutes}min", inclusive="left"
    )
    if not timestamps.equals(expected):
        raise ValueError("Timestamps must cover every interval of the simulation dates.")


def check_physical_invariants(
    data: pd.DataFrame,
    agents: pd.DataFrame,
    timestep_minutes: int = 5,
    charging_efficiency: float = 0.99,
) -> pd.DataFrame:
    """Audit energy conservation, continuity, SoC, charging limits, and state consistency."""
    data = data.sort_values(["agent_id", "timestamp"]).copy()
    parameters = data.merge(
        agents[
            [
                "agent_id",
                "battery_capacity_kwh",
                "charger_power_kw",
                "driving_efficiency_mi_per_kwh",
            ]
        ],
        on="agent_id",
        validate="many_to_one",
    )
    energy_error = (
        data.battery_energy_end_kwh
        - data.battery_energy_start_kwh
        - data.battery_charge_kwh
        + data.drive_energy_kwh
    )
    previous_energy = data.groupby("agent_id").battery_energy_end_kwh.shift()
    continuity = data.battery_energy_start_kwh - previous_energy
    times = data.groupby("agent_id").timestamp.diff().dropna()
    checks = {
        "No missing values": not data.isna().any().any(),
        "Unique agent/timestamp rows": not data.duplicated(["agent_id", "timestamp"]).any(),
        "Regular time intervals": times.eq(pd.Timedelta(minutes=timestep_minutes)).all(),
        "SoC within physical bounds": data[["soc_start", "soc_end"]].ge(-1e-09).all().all()
        and data[["soc_start", "soc_end"]].le(1 + 1e-09).all().all(),
        "Energy conserved each interval": np.allclose(energy_error, 0, atol=1e-08),
        "Energy continuous between intervals": np.allclose(continuity.dropna(), 0, atol=1e-08),
        "SoC matches stored energy": np.allclose(
            parameters.soc_start * parameters.battery_capacity_kwh,
            parameters.battery_energy_start_kwh,
        ),
        "Driving energy matches distance": np.allclose(
            parameters.drive_energy_kwh,
            parameters.distance_miles / parameters.driving_efficiency_mi_per_kwh,
        ),
        "Driving occurs away and disconnected": not (
            data.is_driving & (data.is_home | data.is_plugged_in)
        ).any(),
        "Connections occur at home": not (data.is_plugged_in & ~data.is_home).any(),
        "Charging requires connection and allowed hours": not (
            data.grid_power_kw.gt(1e-09) & (~data.is_plugged_in | ~data.charging_allowed)
        ).any(),
        "Grid power within charger rating": (
            parameters.grid_power_kw.ge(-1e-09)
            & parameters.grid_power_kw.le(parameters.charger_power_kw + 1e-09)
        ).all(),
        "Power integrates to grid energy": np.allclose(
            data.grid_energy_kwh, data.grid_power_kw * timestep_minutes / 60
        ),
        "Charging losses accounted for": np.allclose(
            data.battery_charge_kwh, data.grid_energy_kwh * charging_efficiency
        ),
    }
    return pd.Series(checks, name="passed").to_frame()
