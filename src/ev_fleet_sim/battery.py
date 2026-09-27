"""Home charging policy and interval-by-interval battery energy balance."""

from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_battery(
    agent_timeseries: pd.DataFrame,
    agent: pd.Series,
    timestep_minutes: int = 5,
    initial_soc: float | None = None,
    charging_efficiency: float = 0.99,
    reserve_soc: float = 0.1,
) -> pd.DataFrame:
    """
    Simulate battery energy and charging for one agent

    Connection behavior
    -------------------
    Retain the previously generated habitual connection schedule.

    If home and battery energy cannot cover the next away window's
    driving demand plus a reserve, connect early. Remain connected
    until departure.

    Assumptions
    -----------
    - The agent knows the next away window's total driving demand.
    - A home charger is available whenever the agent is home.
    - The archetype target SoC is the normal charging target.
    - If the next away window needs more energy plus the reserve,
      increase the charging target up to 100% SoC.
    - Scheduled charging still restricts power draw to its nominal
      plug-in/plug-out local-clock window.
    - Initial SoC defaults to target SoC.
    - No public charging, V2G, or standby consumption is modeled.

    Additional output
    -----------------
    planned_is_plugged_in:
        Connection status from the original behavioral schedule.
    range_override_active:
        Whether an early connection override is active.
    next_away_drive_kwh:
        Driving energy required for the next/current away window.
    charging_target_soc:
        Charging target for this interval, including any increase for
        the next planned away window. The normal target is shown while away.

    Important Notes
    -----
    The agent knows the next away window's total driving demand.
    Raising the target does not change the sampled driving distance.
    Battery capacity and available charging time still limit feasibility.
    The reserve is a planning goal, not a guaranteed minimum SoC.
    """
    capacity = float(agent["battery_capacity_kwh"])
    charger_kw = float(agent["charger_power_kw"])
    target_soc = float(agent["target_soc"])
    if initial_soc is None:
        initial_soc = target_soc
    if not np.isfinite(capacity) or capacity <= 0:
        raise ValueError("Battery capacity must be positive.")
    if not np.isfinite(charger_kw) or charger_kw < 0:
        raise ValueError("Charger power must be nonnegative.")
    if not 0 <= initial_soc <= 1 or not 0 <= target_soc <= 1:
        raise ValueError("Initial and target SoC must be between 0 and 1.")
    if not 0 <= reserve_soc <= target_soc:
        raise ValueError("Reserve SoC must be between zero and target SoC.")
    if not 0 < charging_efficiency <= 1:
        raise ValueError("Charging efficiency must be in (0, 1].")
    if not np.isfinite(timestep_minutes) or timestep_minutes <= 0:
        raise ValueError("Timestep must be positive.")
    result = agent_timeseries.sort_values("timestamp").reset_index(drop=True).copy()
    if result.empty:
        raise ValueError("The agent timeline is empty.")
    if not result["agent_id"].eq(agent["agent_id"]).all():
        raise ValueError("Pass a timeline containing only this agent.")
    if not result["timestamp"].diff().dropna().eq(pd.Timedelta(minutes=timestep_minutes)).all():
        raise ValueError("The timeline must have regular, unique timesteps.")
    required_columns = ["is_home", "is_plugged_in", "is_driving", "drive_energy_kwh"]
    if result[required_columns].isna().any().any():
        raise ValueError("Timeline states and driving energy cannot be missing.")
    consumption = result["drive_energy_kwh"].to_numpy(dtype=float)
    if not np.isfinite(consumption).all() or (consumption < 0).any():
        raise ValueError("Driving energy must be finite and nonnegative.")
    if (result["is_home"] & result["is_driving"]).any():
        raise ValueError("The agent cannot be home and driving simultaneously.")
    result["planned_is_plugged_in"] = result["is_plugged_in"]
    home_groups = result["is_home"].ne(result["is_home"].shift()).cumsum()
    window_energy = result.groupby(home_groups)["drive_energy_kwh"].transform("sum")
    # Backfill next-trip demand into home intervals. Parking contributes zero.
    result["next_away_drive_kwh"] = window_energy.where(~result["is_home"]).bfill().fillna(0.0)
    step_hours = timestep_minutes / 60
    energy = initial_soc * capacity
    target_energy = target_soc * capacity
    reserve_energy = reserve_soc * capacity
    override_connected = False
    records = []
    for row in result.itertuples(index=False):
        energy_start = energy
        if not row.is_home:
            override_connected = False
            connected = False
        else:
            connected = bool(row.planned_is_plugged_in) or override_connected
            if (
                not connected
                and row.next_away_drive_kwh > 0
                and (energy < row.next_away_drive_kwh + reserve_energy - 1e-09)
            ):
                override_connected = True
                connected = True
        if row.drive_energy_kwh > energy + 1e-09:
            if row.next_away_drive_kwh > capacity + 1e-09:
                raise ValueError(
                    f"Driving window containing {row.timestamp} requires {row.next_away_drive_kwh:.2f} kWh, exceeding full battery capacity ({capacity:.2f} kWh). This plan requires charging away from home or a revised travel model; earlier home charging cannot solve it."
                )
            raise ValueError(
                f"Insufficient battery energy at {row.timestamp}, even with range-aware connection. Check trip demand and available charging time."
            )
        energy = max(0.0, energy - row.drive_energy_kwh)
        charging_target_energy = target_energy
        if row.is_home and row.next_away_drive_kwh > 0:
            charging_target_energy = min(
                capacity, max(target_energy, row.next_away_drive_kwh + reserve_energy)
            )
        grid_kwh = 0.0
        charge_kwh = 0.0
        charge_allowed = True
        if agent["charging_policy"] == "scheduled":
            clock = row.timestamp.time()
            opening = agent["nominal_plugin_time"]
            closing = agent["nominal_plugout_time"]
            charge_allowed = (
                opening <= clock < closing
                if opening < closing
                else clock >= opening or clock < closing
            )
        if connected and (not row.is_driving) and charge_allowed:
            needed_kwh = max(0.0, charging_target_energy - energy)
            grid_kwh = min(charger_kw * step_hours, needed_kwh / charging_efficiency)
            charge_kwh = grid_kwh * charging_efficiency
            energy += charge_kwh
        records.append(
            {
                "is_plugged_in": connected,
                "range_override_active": override_connected,
                "charging_allowed": charge_allowed,
                "charging_target_soc": charging_target_energy / capacity,
                "battery_energy_start_kwh": energy_start,
                "battery_energy_end_kwh": energy,
                "soc_start": energy_start / capacity,
                "soc_end": energy / capacity,
                "battery_charge_kwh": charge_kwh,
                "grid_energy_kwh": grid_kwh,
                "grid_power_kw": grid_kwh / step_hours,
            }
        )
    calculated = pd.DataFrame(records)
    result[calculated.columns] = calculated
    return result
