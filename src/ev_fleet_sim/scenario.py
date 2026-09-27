"""Public scenario API and portable result exports."""

import json
import platform
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import SimulationConfig
from .population import default_driving_assumptions, generate_population, load_archetypes
from .reporting import summarize_simulation
from .sessions import extract_sessions
from .simulation import simulate_population


@dataclass
class ScenarioResult:
    """Tables and configuration belonging to one complete, successful run."""

    config: SimulationConfig
    agents: pd.DataFrame
    assumptions: pd.DataFrame
    data: pd.DataFrame
    summary: pd.DataFrame
    calibration: pd.DataFrame
    checks: pd.DataFrame
    sessions: pd.DataFrame

    def save(self, directory: str | Path, charts: bool = False) -> Path:
        """Export CSVs, a reproducibility manifest, and optional offline HTML."""
        destination = Path(directory)
        # Construct optional charts first so a missing extra cannot leave a
        # result folder that looks like a complete export.
        figure = None
        if charts:
            from .plotting import make_population_figure

            figure = make_population_figure(self.summary)
        destination.mkdir(parents=True, exist_ok=True)
        for name in ["agents", "assumptions", "summary", "sessions"]:
            getattr(self, name).to_csv(destination / f"{name}.csv", index=False)
        self.data.to_csv(destination / "timeseries.csv.gz", index=False, compression="gzip")
        self.calibration.to_csv(destination / "calibration.csv", index_label="archetype")
        self.checks.to_csv(destination / "checks.csv", index_label="check")
        manifest = {
            "model_version": "home_only_bounded_v1",
            "package_version": "0.1.0",
            "config": asdict(self.config),
            "simulated_agents": len(self.agents),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "all_physical_checks_passed": bool(self.checks.passed.all()),
            "peak_grid_power_kw": float(self.summary.grid_power_kw.max()),
            "total_grid_energy_kwh": float(self.data.grid_energy_kwh.sum()),
            "total_distance_miles": float(self.data.distance_miles.sum()),
        }
        (destination / "run.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        if figure is not None:
            figure.write_html(destination / "fleet.html", include_plotlyjs=True)
        return destination


def run_scenario(
    config: SimulationConfig | None = None,
    *,
    archetypes: pd.DataFrame | None = None,
    assumptions: pd.DataFrame | None = None,
    agents: pd.DataFrame | None = None,
) -> ScenarioResult:
    """Run a complete scenario. Explicit agents bypass population sampling.

    All agents must complete their planned mileage. Infeasibility raises a
    ValueError, and no partial cohort is returned.
    """
    config = config or SimulationConfig()
    metadata = load_archetypes() if archetypes is None else archetypes.copy()
    if agents is None:
        agents = generate_population(metadata, config.number_of_agents, config.seed)
    else:
        agents = agents.copy()
    if assumptions is None:
        assumptions = default_driving_assumptions(agents.drop_duplicates("archetype"))
    assumptions = assumptions.copy()
    dates, timestamps = config.time_grid()
    data = simulate_population(
        agents,
        dates,
        timestamps,
        assumptions,
        seed=config.seed,
        timestep_minutes=config.timestep_minutes,
        charging_efficiency=config.charging_efficiency,
        reserve_soc=config.reserve_soc,
        average_speed_mph=config.average_speed_mph,
        outbound_distance_share=config.outbound_distance_share,
    )
    summary, calibration, checks = summarize_simulation(
        data, agents, config.days, config.timestep_minutes, config.charging_efficiency
    )
    if not checks.passed.all():
        failed = checks.index[~checks.passed].tolist()
        raise ValueError(f"Simulation invariant checks failed: {failed}")
    return ScenarioResult(
        config,
        agents,
        assumptions,
        data,
        summary,
        calibration,
        checks,
        extract_sessions(data, config.timestep_minutes),
    )
