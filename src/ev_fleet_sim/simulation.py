"""Compose each vehicle simulation using independent, stable random streams."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .battery import simulate_battery
from .calendar import generate_driving_calendar
from .connections import generate_connection_timeline
from .travel import generate_daily_travel_windows, place_driving_segments
from .validation import validate_agents, validate_time_grid


def simulate_population(
    agents: pd.DataFrame,
    simulation_dates: pd.DatetimeIndex,
    simulation_timestamps: pd.DatetimeIndex,
    driving_assumptions: pd.DataFrame,
    seed: int = 42,
    timestep_minutes: int = 5,
    average_speed_mph: float = 30.0,
    outbound_distance_share: float = 0.5,
    charging_efficiency: float = 0.99,
    reserve_soc: float = 0.1,
) -> pd.DataFrame:
    """
    Run the current single-agent model for a population.

    Uses:
    - Archetype-specific daily driving probabilities and annual mileage.
    - Bounded daily distances with their mean calibrated to annual mileage.
    - Explicit local departure and return anchors.
    - Travel windows constrained by driving duration and home charging time.
    - Two driving segments per active day.
    - Probabilistic connection and immediate charging.
    - Initial SoC equal to each agent's target; initially connected.

    Scheduled charging uses its nominal local-clock charging window.
    Archetype F connects whenever home, with explicit travel anchors. Range-aware connections use the next away demand.

    If an agent cannot complete its planned driving, stop and identify
    the agent rather than silently excluding it from population results.
    """
    validate_agents(agents)
    validate_time_grid(simulation_dates, simulation_timestamps, timestep_minutes)
    if agents.empty:
        raise ValueError("Provide at least one agent.")
    if not agents["agent_id"].is_unique:
        raise ValueError("Each agent_id must be unique.")
    if not np.isfinite(average_speed_mph) or average_speed_mph <= 0:
        raise ValueError("Average speed must be positive.")
    if not 0 < outbound_distance_share < 1:
        raise ValueError("Outbound distance share must be between 0 and 1.")
    results = []
    for position in range(len(agents)):
        agent_table = agents.iloc[[position]]
        agent = agent_table.iloc[0]
        # Python hash() varies by process, so derive stream IDs with BLAKE2.
        identity = int.from_bytes(
            hashlib.blake2b(str(agent["agent_id"]).encode(), digest_size=8).digest(), "little"
        )
        agent_seed = np.random.SeedSequence([seed, identity])
        mileage_seed, timing_seed, connection_seed = agent_seed.generate_state(3)
        try:
            calendar = generate_driving_calendar(
                agents=agent_table,
                simulation_dates=simulation_dates,
                driving_assumptions=driving_assumptions,
                seed=int(mileage_seed),
                reserve_soc=reserve_soc,
            )
            windows = generate_daily_travel_windows(
                driving_calendar=calendar,
                agents=agent_table,
                seed=int(timing_seed),
                timestep_minutes=timestep_minutes,
                average_speed_mph=average_speed_mph,
                outbound_distance_share=outbound_distance_share,
                charging_efficiency=charging_efficiency,
                reserve_soc=reserve_soc,
            )
            timeline = generate_connection_timeline(
                agent=agent,
                travel_windows=windows,
                simulation_timestamps=simulation_timestamps,
                simulation_dates=simulation_dates,
                seed=int(connection_seed),
                initially_plugged_in=True,
            )
            timeline = place_driving_segments(
                timeline,
                windows,
                agent,
                timestep_minutes,
                average_speed_mph,
                outbound_distance_share,
            )
            battery = simulate_battery(
                agent_timeseries=timeline,
                agent=agent,
                timestep_minutes=timestep_minutes,
                initial_soc=float(agent["target_soc"]),
                charging_efficiency=charging_efficiency,
                reserve_soc=reserve_soc,
            )
            battery["archetype"] = agent["archetype"]
            results.append(battery)
        except ValueError as error:
            raise ValueError(
                f"Simulation failed for {agent['agent_id']} ({agent['archetype']}): {error}"
            ) from error
    return pd.concat(results, ignore_index=True)
