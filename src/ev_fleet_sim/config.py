"""Scenario configuration and timezone-aware interval construction."""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SimulationConfig:
    """A run begins at local midnight, connected, at each vehicle's target SoC."""

    start: str = "2026-01-05"
    days: int = 7
    number_of_agents: int = 100
    seed: int = 42
    timestep_minutes: int = 5
    timezone: str = "Europe/London"
    charging_efficiency: float = 0.99
    reserve_soc: float = 0.10
    average_speed_mph: float = 30.0
    outbound_distance_share: float = 0.5

    def __post_init__(self) -> None:
        for name in ["days", "number_of_agents", "timestep_minutes", "seed"]:
            value = getattr(self, name)
            minimum = 0 if name == "seed" else 1
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, np.integer))
                or value < minimum
            ):
                raise ValueError(f"{name} must be an integer >= {minimum}.")
        # Dividing an hour also keeps DST clock shifts aligned to the grid.
        if 60 % self.timestep_minutes:
            raise ValueError("timestep_minutes must divide 60.")
        if not 0 < self.charging_efficiency <= 1:
            raise ValueError("charging_efficiency must be in (0, 1].")
        if not 0 <= self.reserve_soc < 1:
            raise ValueError("reserve_soc must be in [0, 1).")
        if not np.isfinite(self.average_speed_mph) or self.average_speed_mph <= 0:
            raise ValueError("average_speed_mph must be finite and positive.")
        if not 0 < self.outbound_distance_share < 1:
            raise ValueError("outbound_distance_share must be in (0, 1).")

    def time_grid(self) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
        """Use local calendar days and real elapsed intervals across DST."""
        start = pd.Timestamp(self.start)
        start = (
            start.tz_localize(self.timezone)
            if start.tzinfo is None
            else start.tz_convert(self.timezone)
        )
        if pd.isna(start) or start != start.normalize():
            raise ValueError("start must be a valid local midnight date.")
        dates = pd.date_range(start, periods=self.days, freq="D")
        end = start + pd.DateOffset(days=self.days)
        timestamps = pd.date_range(start, end, freq=f"{self.timestep_minutes}min", inclusive="left")
        return dates, timestamps
