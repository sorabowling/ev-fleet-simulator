"""Sample feasible home-to-home travel windows without changing mileage."""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_daily_travel_windows(
    driving_calendar: pd.DataFrame,
    agents: pd.DataFrame,
    seed: int = 43,
    departure_std_minutes: float = 45.0,
    return_std_minutes: float = 60.0,
    timestep_minutes: int = 5,
    average_speed_mph: float = 30.0,
    outbound_distance_share: float = 0.5,
    charging_efficiency: float = 0.99,
    reserve_soc: float = 0.1,
) -> pd.DataFrame:
    """
    Generate one same-day departure/return window per driving day.

    Timing anchors
    --------------
    Each agent has explicit departure_anchor and return_anchor fields.
    A-D use the source connection clocks as travel anchors. E and F use
    separate same-day travel anchors, as documented in the README.
    These are assumptions, not measured departure and return distributions.

    Connection behavior
    -------------------
    The later connection model should use these generated timestamps:
    - If connected before leaving, unplug at departure.
    - If choosing to connect after returning, plug in at return.

    This function does not decide whether the agent plugs in.

    Model boundary
    --------------
    A window represents time away from home, including destination parking.
    It does not mean continuous driving throughout the window.

    Travel is same-day. Explicit departure and return anchors are stored
    separately from connection clocks for every archetype.

    Home-only feasibility
    ---------------------
    Keep the sampled days and miles fixed. Resample departure/return times
    until both driving legs fit and the preceding home interval provides
    enough charging opportunity for this journey. After a previous journey,
    this conservatively assumes the battery could be at the reserve.
    Actual connection and charging are still decided by the later models.
    These constraints change the sampled timing distribution, not mileage.
    """
    spreads = np.array([departure_std_minutes, return_std_minutes], dtype=float)
    if not np.isfinite(spreads).all() or (spreads < 0).any():
        raise ValueError("Timing standard deviations must be finite and nonnegative.")
    if (
        not isinstance(timestep_minutes, (int, np.integer))
        or timestep_minutes <= 0
        or 1440 % timestep_minutes != 0
    ):
        raise ValueError("timestep_minutes must be a positive integer dividing 1440.")
    if not np.isfinite(average_speed_mph) or average_speed_mph <= 0:
        raise ValueError("Average speed must be positive.")
    if not 0 < outbound_distance_share < 1:
        raise ValueError("Outbound distance share must be between zero and one.")
    if not 0 < charging_efficiency <= 1 or not 0 <= reserve_soc < 1:
        raise ValueError("Invalid charging efficiency or reserve SoC.")
    travel_windows = driving_calendar.loc[
        driving_calendar["is_drive_day"], ["agent_id", "archetype", "drive_date", "distance_miles"]
    ].copy()
    travel_windows["drive_date"] = pd.to_datetime(travel_windows["drive_date"]).dt.normalize()
    if travel_windows.duplicated(["agent_id", "drive_date"]).any():
        raise ValueError("Expected at most one driving row per agent per day.")
    travel_windows = (
        travel_windows.merge(
            agents[["agent_id", "nominal_plugout_time", "nominal_plugin_time"]],
            on="agent_id",
            how="left",
            validate="many_to_one",
        )
        .sort_values(["agent_id", "drive_date"])
        .reset_index(drop=True)
    )
    timing_columns = ["nominal_plugout_time", "nominal_plugin_time"]
    if travel_windows[timing_columns].isna().any().any():
        raise ValueError("Every driving agent needs nominal plug-out and plug-in times.")
    rng = np.random.default_rng(seed)
    departure_times = []
    return_times = []
    previous_returns = {}
    simulation_start = pd.DatetimeIndex(driving_calendar["drive_date"]).min()
    agent_lookup = agents.set_index("agent_id", verify_integrity=True)
    step = pd.Timedelta(minutes=timestep_minutes)

    def clock_minutes(value):
        if isinstance(value, str):
            value = pd.to_datetime(value).time()
        return value.hour * 60 + value.minute + value.second / 60

    def at_local_minute(date, minutes):
        local = date.tz_localize(None).normalize() + pd.Timedelta(minutes=minutes)
        if date.tzinfo is None:
            return local
        return local.tz_localize(date.tzinfo, ambiguous=False, nonexistent="shift_forward")

    def available_charge_kwh(home_start, departure, agent):
        if agent["charging_policy"] != "scheduled":
            count = int((departure - home_start) / step)
        else:
            slots = pd.date_range(home_start, departure, freq=step, inclusive="left")
            minutes = slots.hour * 60 + slots.minute
            opening = clock_minutes(agent["nominal_plugin_time"])
            closing = clock_minutes(agent["nominal_plugout_time"])
            allowed = (
                (minutes >= opening) & (minutes < closing)
                if opening < closing
                else (minutes >= opening) | (minutes < closing)
            )
            count = int(allowed.sum())
        return (
            max(0, count) * timestep_minutes / 60 * agent["charger_power_kw"] * charging_efficiency
        )

    for row in travel_windows.itertuples(index=False):
        agent = agent_lookup.loc[row.agent_id]
        driving_kwh = row.distance_miles / agent["driving_efficiency_mi_per_kwh"]
        home_start = previous_returns.get(row.agent_id, simulation_start)
        if row.agent_id not in previous_returns:
            required_charge_kwh = max(
                0.0,
                driving_kwh
                + reserve_soc * agent["battery_capacity_kwh"]
                - agent["target_soc"] * agent["battery_capacity_kwh"],
            )
        else:
            required_charge_kwh = driving_kwh
        if required_charge_kwh > 0 and agent["charger_power_kw"] <= 0:
            raise ValueError(
                f"{row.agent_id}: this home-only travel plan requires a working home charger."
            )
        outbound_steps = max(
            1,
            int(
                np.ceil(
                    row.distance_miles
                    * outbound_distance_share
                    / average_speed_mph
                    * 60
                    / timestep_minutes
                )
            ),
        )
        return_steps = max(
            1,
            int(
                np.ceil(
                    row.distance_miles
                    * (1 - outbound_distance_share)
                    / average_speed_mph
                    * 60
                    / timestep_minutes
                )
            ),
        )
        minimum_driving_duration = (outbound_steps + return_steps) * step
        departure_anchor = clock_minutes(agent["departure_anchor"])
        return_anchor = clock_minutes(agent["return_anchor"])
        if not 0 <= departure_anchor < return_anchor < 1440:
            raise ValueError(
                f"{row.agent_id}: nominal times do not describe a same-day departure followed by return."
            )
        for attempt in range(1000):
            departure_minutes = rng.normal(loc=departure_anchor, scale=departure_std_minutes)
            return_minutes = rng.normal(loc=return_anchor, scale=return_std_minutes)
            departure_minutes = int(
                np.round(departure_minutes / timestep_minutes) * timestep_minutes
            )
            return_minutes = int(np.round(return_minutes / timestep_minutes) * timestep_minutes)
            if not 0 <= departure_minutes < return_minutes < 1440:
                continue
            departure_time = at_local_minute(row.drive_date, departure_minutes)
            return_time = at_local_minute(row.drive_date, return_minutes)
            if return_time - departure_time < minimum_driving_duration:
                continue
            if departure_time < home_start:
                continue
            if (
                available_charge_kwh(home_start, departure_time, agent) + 1e-09
                < required_charge_kwh
            ):
                continue
            break
        else:
            raise ValueError(
                f"{row.agent_id}: could not fit {row.distance_miles:.1f} miles on {row.drive_date.date()} with sufficient home charging time. Review travel-time assumptions, driving probabilities, and charger power."
            )
        departure_times.append(departure_time)
        return_times.append(return_time)
        previous_returns[row.agent_id] = return_time
    date_dtype = travel_windows["drive_date"].dtype
    travel_windows["departure_time"] = pd.Series(departure_times, dtype=date_dtype)
    travel_windows["return_time"] = pd.Series(return_times, dtype=date_dtype)
    travel_windows["away_duration_hours"] = (
        travel_windows["return_time"] - travel_windows["departure_time"]
    ).dt.total_seconds() / 3600
    return travel_windows


def place_driving_segments(
    timeline: pd.DataFrame,
    windows: pd.DataFrame,
    agent: pd.Series,
    timestep_minutes: int = 5,
    average_speed_mph: float = 30.0,
    outbound_distance_share: float = 0.5,
) -> pd.DataFrame:
    """Place two nonoverlapping driving legs inside each away window.

    Intervals are half-open. Durations round up, with distance distributed
    evenly across the covered intervals so mileage is conserved exactly.
    """
    timeline = timeline.copy()
    step = pd.Timedelta(minutes=timestep_minutes)
    timeline["is_driving"] = False
    timeline["distance_miles"] = 0.0
    for window in windows.itertuples(index=False):
        outbound_miles = window.distance_miles * outbound_distance_share
        return_miles = window.distance_miles - outbound_miles
        outbound_steps = max(
            1, int(np.ceil(outbound_miles / average_speed_mph * 60 / timestep_minutes))
        )
        return_steps = max(
            1, int(np.ceil(return_miles / average_speed_mph * 60 / timestep_minutes))
        )
        outbound_end = window.departure_time + outbound_steps * step
        return_start = window.return_time - return_steps * step
        if outbound_end > return_start:
            raise ValueError(f"Driving segments overlap on {window.drive_date}.")
        segments = [
            (window.departure_time, outbound_end, outbound_miles, outbound_steps),
            (return_start, window.return_time, return_miles, return_steps),
        ]
        for start, end, miles, number_of_steps in segments:
            driving = (timeline["timestamp"] >= start) & (timeline["timestamp"] < end)
            if int(driving.sum()) != number_of_steps:
                raise ValueError("A driving segment is truncated or off the time grid.")
            if timeline.loc[driving, "is_driving"].any():
                raise ValueError("Driving segments overlap.")
            if timeline.loc[driving, "is_home"].any():
                raise ValueError("Driving segments must occur away from home.")
            timeline.loc[driving, "is_driving"] = True
            timeline.loc[driving, "distance_miles"] += miles / number_of_steps
    timeline["drive_energy_kwh"] = (
        timeline["distance_miles"] / agent["driving_efficiency_mi_per_kwh"]
    )
    return timeline
