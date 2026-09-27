"""Run from any directory after installing the package."""

from ev_fleet_sim import SimulationConfig, run_scenario


def main() -> None:
    result = run_scenario(SimulationConfig(number_of_agents=100, days=7, seed=42))
    result.save("outputs/demo", charts=True)
    print(result.calibration.round(3))
    print(result.checks)


if __name__ == "__main__":
    main()
