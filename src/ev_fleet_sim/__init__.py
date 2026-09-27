"""An agent-based EV travel and home-charging simulator."""

from .config import SimulationConfig
from .population import default_driving_assumptions, generate_population, load_archetypes
from .scenario import ScenarioResult, run_scenario

__version__ = "0.1.0"
__all__ = [
    "SimulationConfig",
    "ScenarioResult",
    "load_archetypes",
    "generate_population",
    "default_driving_assumptions",
    "run_scenario",
]
