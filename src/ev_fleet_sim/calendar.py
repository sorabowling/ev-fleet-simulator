"""Bernoulli driving days and bounded Beta mileage calibrated in expectation."""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_driving_calendar(
    agents: pd.DataFrame,
    simulation_dates: pd.DatetimeIndex,
    driving_assumptions: pd.DataFrame,
    seed: int = 42,
    distance_shape: float = 5.0,
    reserve_soc: float = 0.1,
) -> pd.DataFrame:
    """
    Generate one row per agent per simulation date, including non-driving days

    For each agent:
    1. Look up weekday and weekend driving probabilities
    2. Calculate mean mileage per active driving day from annual mileage
    3. Randomly determine whether driving occurs on each date
    4. Sample mileage for driving days; assign zero to non-driving days

    Inputs
    ----------
    agents : pandas.DataFrame
        One row per agent. Must include agent_id, archetype, miles_per_year,
        battery_capacity_kwh, and driving_efficiency_mi_per_kwh.

    simulation_dates : datetime-like sequence
        One entry per simulation calendar day, normally produced using
        pd.date_range(..., freq="D"). Dates should be unique.

    driving_assumptions : pandas.DataFrame
        One row per archetype, containing weekday_drive_probability and
        weekend_drive_probability.

    seed : int
        Controls reproducibility. Identical inputs, including agent order,
        and the same seed produce the same output.

    distance_shape : float
        Positive alpha parameter for the bounded Beta mileage distribution.
        Higher values produce less variation around the same mean.

    reserve_soc : float
        Battery fraction reserved after a planned away window.
        The maximum daily miles use the remaining fraction of a full battery.

    Returns
    -------
    pandas.DataFrame
        Daily driving decisions and mileage for every agent.

    Important Notes
    -----
    This function generates daily mileage, not timed trips or battery SoC.
    Mileage is bounded by full battery range minus a reserve. Its expected
    total still matches annual mileage scaled to the simulation duration.
    Travel timing and home charging availability are checked separately.
    """
    rng = np.random.default_rng(seed)
    agent_parameters = agents.merge(
        driving_assumptions, on="archetype", how="left", validate="many_to_one"
    )
    probability_columns = ["weekday_drive_probability", "weekend_drive_probability"]
    probabilities = agent_parameters[probability_columns].to_numpy(dtype=float)
    if (
        not np.isfinite(probabilities).all()
        or (probabilities < 0).any()
        or (probabilities > 1).any()
    ):
        raise ValueError("Every agent needs weekday/weekend probabilities between 0 and 1.")
    if not np.isfinite(distance_shape) or distance_shape <= 0:
        raise ValueError("distance_shape must be positive.")
    if not np.isfinite(reserve_soc) or not 0 <= reserve_soc < 1:
        raise ValueError("reserve_soc must be between zero and one, excluding one.")
    dates = pd.DatetimeIndex(simulation_dates)
    is_weekend = dates.dayofweek >= 5
    calendars = []
    for agent in agent_parameters.itertuples(index=False):
        drive_probability = np.where(
            is_weekend, agent.weekend_drive_probability, agent.weekday_drive_probability
        )
        # Calibrate against expected driving days, not the realized count.
        expected_driving_days = drive_probability.sum()
        expected_simulation_miles = agent.miles_per_year * len(dates) / 365
        if expected_driving_days == 0 and expected_simulation_miles > 0:
            raise ValueError(
                f"{agent.archetype} has positive mileage but no chance of driving during this period."
            )
        mean_miles_per_driving_day = (
            expected_simulation_miles / expected_driving_days if expected_driving_days > 0 else 0.0
        )
        maximum_daily_miles = (
            agent.battery_capacity_kwh * (1 - reserve_soc) * agent.driving_efficiency_mi_per_kwh
        )
        if not np.isfinite(maximum_daily_miles) or maximum_daily_miles <= 0:
            raise ValueError(
                "Battery capacity and driving efficiency must define a positive range."
            )
        if mean_miles_per_driving_day >= maximum_daily_miles:
            raise ValueError(
                f"{agent.archetype}: these driving probabilities require {mean_miles_per_driving_day:.1f} mean miles per driving day, but the home-only range limit is {maximum_daily_miles:.1f} miles. Increase the driving probabilities or revise the vehicle assumptions."
            )
        is_drive_day = (rng.random(len(dates)) < drive_probability) & (
            mean_miles_per_driving_day > 0
        )
        if mean_miles_per_driving_day == 0:
            potential_daily_miles = np.zeros(len(dates))
        else:
            beta = distance_shape * (maximum_daily_miles / mean_miles_per_driving_day - 1)
            potential_daily_miles = maximum_daily_miles * rng.beta(
                a=distance_shape, b=beta, size=len(dates)
            )
        calendar = pd.DataFrame(
            {
                "agent_id": agent.agent_id,
                "archetype": agent.archetype,
                "drive_date": dates,
                "day_of_week": dates.day_name(),
                "is_weekend": is_weekend,
                "drive_probability": drive_probability,
                "is_drive_day": is_drive_day,
                "mean_miles_per_driving_day": mean_miles_per_driving_day,
                "maximum_daily_miles": maximum_daily_miles,
                "distance_miles": np.where(is_drive_day, potential_daily_miles, 0.0),
            }
        )
        calendars.append(calendar)
    return pd.concat(calendars, ignore_index=True)
