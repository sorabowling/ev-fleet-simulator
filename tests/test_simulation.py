import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ev_fleet_sim import SimulationConfig, default_driving_assumptions, run_scenario
from ev_fleet_sim.battery import simulate_battery
from ev_fleet_sim.calendar import generate_driving_calendar
from ev_fleet_sim.validation import check_physical_invariants


def test_energy_state_and_power_invariants(reference_run):
    assert reference_run.checks.passed.all(), reference_run.checks
    d = reference_run.data
    assert not (d.is_driving & d.grid_power_kw.gt(0)).any()
    assert not (d.is_driving & d.is_plugged_in).any()


def test_baseline_regression(reference_run):
    expected = json.loads((Path(__file__).parent / "fixtures/baseline_metrics.json").read_text())
    actual = reference_run.data.groupby("agent_id")[list(expected["metrics"])].sum()
    np.testing.assert_allclose(actual.to_numpy(), expected["values"], rtol=1e-10, atol=1e-8)


def test_cohort_and_order_independent_random_streams(six_agents, reference_run):
    chosen = six_agents.iloc[[4, 1]].copy()
    subset = run_scenario(SimulationConfig(number_of_agents=2), agents=chosen)
    expected = reference_run.data.loc[reference_run.data.agent_id.isin(chosen.agent_id)]

    def sort(d):
        return d.sort_values(["agent_id", "timestamp"]).reset_index(drop=True)

    pd.testing.assert_frame_equal(sort(expected), sort(subset.data))


def test_renaming_labels_does_not_change_policy(six_agents, reference_run):
    agents = six_agents.copy()
    agents.archetype = [f"Group {i}" for i in range(6)]
    renamed = run_scenario(SimulationConfig(number_of_agents=6), agents=agents)
    pd.testing.assert_frame_equal(
        reference_run.data.drop(columns="archetype"), renamed.data.drop(columns="archetype")
    )


def test_scheduled_and_always_home_policies(reference_run):
    scheduled = reference_run.data.query("archetype == 'Archetype E'")
    minutes = scheduled.timestamp.dt.hour * 60 + scheduled.timestamp.dt.minute
    outside = (minutes >= 9 * 60) & (minutes < 22 * 60)
    assert scheduled.loc[outside, "grid_power_kw"].eq(0).all()
    assert scheduled.grid_power_kw.gt(0).any()
    always = reference_run.data.query("archetype == 'Archetype F'")
    assert always.is_home.equals(always.is_plugged_in)


def test_range_override_reconnects_and_persists(six_agents, timeline):
    agent = six_agents.iloc[0]
    t = timeline.copy()
    t["is_plugged_in"] = False
    t.loc[2:, "is_home"] = False
    t.loc[2:, "is_driving"] = True
    t.loc[2:, "drive_energy_kwh"] = 1.0
    d = simulate_battery(t, agent, initial_soc=0.10)
    assert d.range_override_active.tolist() == [True, True, False, False]
    assert d.is_plugged_in.tolist() == [True, True, False, False]


def test_charging_stops_exactly_at_target(six_agents, timeline):
    d = simulate_battery(timeline, six_agents.iloc[0], initial_soc=0.799)
    assert d.soc_end.iloc[0] == pytest.approx(0.8)
    assert 0 < d.grid_power_kw.iloc[0] < 7
    assert d.grid_power_kw.iloc[1:].eq(0).all()
    assert d.is_plugged_in.all()


def test_exhausted_battery_raises(six_agents, timeline):
    timeline["is_home"] = False
    timeline["is_driving"] = True
    timeline["drive_energy_kwh"] = 61.0
    with pytest.raises(ValueError, match="exceeding full battery"):
        simulate_battery(timeline, six_agents.iloc[0])


def test_missing_energy_cannot_hide_in_summary(reference_run):
    damaged = reference_run.data.copy()
    damaged.loc[0, "battery_energy_end_kwh"] += 1
    checks = check_physical_invariants(damaged, reference_run.agents)
    assert not checks.loc["Energy conserved each interval", "passed"]
    assert not checks.loc["Energy continuous between intervals", "passed"]


def test_zero_mileage_produces_no_driving(six_agents):
    agents = six_agents.iloc[:1].copy()
    agents.miles_per_year = 0
    result = run_scenario(SimulationConfig(days=1), agents=agents)
    assert not result.data.is_driving.any()
    assert result.data.distance_miles.eq(0).all()
    assert result.data.is_home.all()


def test_impossible_distance_probability_combination_raises(six_agents):
    assumptions = default_driving_assumptions()
    assumptions[["weekday_drive_probability", "weekend_drive_probability"]] = 0.01
    with pytest.raises(ValueError, match="range limit"):
        run_scenario(SimulationConfig(days=7), agents=six_agents, assumptions=assumptions)


def test_positive_mileage_with_zero_drive_chance_raises(six_agents):
    assumptions = default_driving_assumptions()
    assumptions[["weekday_drive_probability", "weekend_drive_probability"]] = 0
    with pytest.raises(ValueError, match="no chance of driving"):
        run_scenario(SimulationConfig(days=1), agents=six_agents, assumptions=assumptions)


def test_bounded_beta_preserves_mileage_in_expectation(six_agents):
    agent = six_agents.iloc[:1]
    dates = pd.date_range("2000-01-01", periods=36500, freq="D")
    calendar = generate_driving_calendar(agent, dates, default_driving_assumptions(), seed=42)
    assert calendar.distance_miles.between(0, calendar.maximum_daily_miles).all()
    # Independent Monte Carlo uncertainty from Bernoulli times scaled Beta.
    p = calendar.drive_probability.to_numpy()
    mu = calendar.mean_miles_per_driving_day.iloc[0]
    bound = calendar.maximum_daily_miles.iloc[0]
    alpha = 5
    beta = alpha * (bound / mu - 1)
    variance = bound**2 * alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1))
    standard_error = np.sqrt(np.sum(p * variance + p * (1 - p) * mu**2))
    expected = float(agent.miles_per_year.iloc[0]) * len(dates) / 365
    assert abs(calendar.distance_miles.sum() - expected) < 5 * standard_error


@pytest.mark.parametrize("start,intervals", [("2026-03-29", 276), ("2026-10-25", 300)])
def test_dst_has_complete_elapsed_time_grid(start, intervals, six_agents):
    result = run_scenario(SimulationConfig(start=start, days=1), agents=six_agents)
    assert len(result.summary) == intervals
    assert result.checks.passed.all()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"days": 0},
        {"number_of_agents": 0},
        {"seed": -1},
        {"timestep_minutes": 7},
        {"charging_efficiency": 0},
        {"average_speed_mph": float("nan")},
    ],
)
def test_invalid_config_raises(kwargs):
    with pytest.raises(ValueError):
        SimulationConfig(**kwargs)
