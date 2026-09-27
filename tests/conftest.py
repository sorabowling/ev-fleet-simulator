import pandas as pd
import pytest

from ev_fleet_sim import SimulationConfig, load_archetypes, run_scenario


@pytest.fixture
def six_agents():
    agents = load_archetypes().copy()
    agents.insert(0, "agent_id", [f"EV_{i:05d}" for i in range(len(agents))])
    return agents


@pytest.fixture(scope="session")
def reference_run():
    agents = load_archetypes().copy()
    agents.insert(0, "agent_id", [f"EV_{i:05d}" for i in range(len(agents))])
    return run_scenario(SimulationConfig(number_of_agents=6), agents=agents)


@pytest.fixture
def timeline():
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05", periods=4, freq="5min", tz="Europe/London"),
            "agent_id": "EV_00000",
            "is_home": True,
            "is_plugged_in": True,
            "is_driving": False,
            "drive_energy_kwh": 0.0,
        }
    )
