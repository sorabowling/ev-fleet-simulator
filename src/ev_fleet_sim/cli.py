"""Command-line entry point for reproducible CSV and HTML exports."""

import argparse
import sys
from pathlib import Path

from .config import SimulationConfig
from .population import load_archetypes
from .scenario import run_scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate EV travel and home charging.")
    parser.add_argument("--agents", type=int, default=100)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--start", default="2026-01-05")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--step", type=int, default=5, help="Interval minutes, must divide 60.")
    parser.add_argument("--charging-efficiency", type=float, default=0.99)
    parser.add_argument("--archetypes", type=Path, help="Replacement archetype CSV.")
    parser.add_argument("--output", type=Path, default=Path("outputs/demo"))
    parser.add_argument(
        "--charts", action="store_true", help="Also write a standalone interactive HTML chart."
    )
    args = parser.parse_args(argv)
    try:
        config = SimulationConfig(
            start=args.start,
            days=args.days,
            number_of_agents=args.agents,
            seed=args.seed,
            timestep_minutes=args.step,
            charging_efficiency=args.charging_efficiency,
        )
        result = run_scenario(config, archetypes=load_archetypes(args.archetypes))
        result.save(args.output, charts=args.charts)
    except (ValueError, OSError, ImportError) as error:
        print(f"Scenario failed: {error}", file=sys.stderr)
        return 1
    print(
        f"Saved {len(result.agents):,} vehicles and {len(result.data):,} intervals to {args.output}"
    )
    print(f"Peak demand: {result.summary.grid_power_kw.max():.1f} kW")
    print(f"Grid energy: {result.data.grid_energy_kwh.sum():.1f} kWh")
    print(f"Physical checks: {int(result.checks.passed.sum())}/{len(result.checks)} passed")
    return 0
