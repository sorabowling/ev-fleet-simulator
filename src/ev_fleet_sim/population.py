"""Load neutral archetypes and sample reproducible vehicle populations."""

from datetime import time
from importlib.resources import files
from pathlib import Path

import numpy as np
import pandas as pd

from .validation import validate_agents

AGENT_COLUMNS = [
    "archetype_id",
    "archetype",
    "miles_per_year",
    "battery_capacity_kwh",
    "driving_efficiency_mi_per_kwh",
    "plugin_frequency_per_day",
    "charger_power_kw",
    "nominal_plugin_time",
    "nominal_plugout_time",
    "target_soc",
    "charging_policy",
    "departure_anchor",
    "return_anchor",
]


def load_archetypes(path: str | Path | None = None) -> pd.DataFrame:
    """Read the bundled CSV or a replacement with the same schema.

    Clock fields use HH:MM local time. Population shares are nonnegative
    sampling weights, normalized by ``generate_population``.
    """
    source = path if path is not None else files("ev_fleet_sim").joinpath("data/archetypes.csv")
    with source.open("rb") if path is None else open(source, "rb") as stream:
        metadata = pd.read_csv(stream)
    for column in [
        "nominal_plugin_time",
        "nominal_plugout_time",
        "departure_anchor",
        "return_anchor",
    ]:
        if column not in metadata:
            raise ValueError(f"Missing archetype column: {column}")
        metadata[column] = metadata[column].map(time.fromisoformat)
    validate_agents(metadata.assign(agent_id=[f"row_{i}" for i in range(len(metadata))]))
    if not metadata.archetype.is_unique:
        raise ValueError("Archetype labels must be unique.")
    return metadata


def generate_population(
    population_metadata: pd.DataFrame,
    number_of_agents: int = 1000,
    seed: int = 42,
) -> pd.DataFrame:
    """Sample archetypes with replacement. Realized proportions fluctuate."""
    if (
        isinstance(number_of_agents, bool)
        or not isinstance(number_of_agents, (int, np.integer))
        or number_of_agents < 1
    ):
        raise ValueError("number_of_agents must be a positive integer.")
    if "population_share" not in population_metadata:
        raise ValueError("Missing archetype column: population_share")
    probabilities = population_metadata.population_share.to_numpy(dtype=float)
    if (
        not np.isfinite(probabilities).all()
        or (probabilities < 0).any()
        or probabilities.sum() <= 0
    ):
        raise ValueError("Population weights must be finite, nonnegative, and have a positive sum.")
    rng = np.random.default_rng(seed)
    positions = rng.choice(
        len(population_metadata), number_of_agents, p=probabilities / probabilities.sum()
    )
    agents = population_metadata.iloc[positions][AGENT_COLUMNS].reset_index(drop=True)
    agents.insert(0, "agent_id", [f"EV_{i:05d}" for i in range(number_of_agents)])
    validate_agents(agents)
    return agents


def default_driving_assumptions(metadata: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return a fresh table of editable weekday and weekend probabilities."""
    if metadata is None:
        metadata = load_archetypes()
    return pd.DataFrame(
        {
            "archetype": metadata.archetype,
            "weekday_drive_probability": 0.85,
            "weekend_drive_probability": 0.55,
        }
    ).reset_index(drop=True)
