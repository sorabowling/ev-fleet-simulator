"""Fleet curves and per-archetype calibration diagnostics."""

from .validation import check_physical_invariants


def summarize_simulation(
    data, agents, simulation_days, timestep_minutes=5, charging_efficiency=0.99
):
    """Return population curves, archetype calibration, and physical checks.

    Each timestamp labels the START of a five-minute interval. SoC and
    stored energy use that boundary; grid power is the interval average.
    Connection counts exclude connections already present at time zero.
    """
    ordered = data.sort_values(["agent_id", "timestamp"]).copy()
    previous = ordered.groupby("agent_id")["is_plugged_in"].shift()
    ordered["new_connection"] = ordered.is_plugged_in & previous.eq(False)
    ordered["early_connection"] = ordered.new_connection & ordered.range_override_active
    summary = (
        ordered.groupby("timestamp")
        .agg(
            number_of_agents=("agent_id", "size"),
            plugged_in_percent=("is_plugged_in", lambda s: 100 * s.mean()),
            mean_soc=("soc_start", lambda s: 100 * s.mean()),
            p05_soc=("soc_start", lambda s: 100 * s.quantile(0.05)),
            p95_soc=("soc_start", lambda s: 100 * s.quantile(0.95)),
            grid_power_kw=("grid_power_kw", "sum"),
            stored_energy_kwh=("battery_energy_start_kwh", "sum"),
        )
        .reset_index()
    )
    totals = ordered.groupby("agent_id").agg(
        simulated_miles=("distance_miles", "sum"),
        connections=("new_connection", "sum"),
        early_connections=("early_connection", "sum"),
    )
    comparison = agents.merge(totals, on="agent_id", validate="one_to_one")
    comparison["expected_miles"] = comparison.miles_per_year * simulation_days / 365
    calibration = comparison.groupby("archetype").agg(
        agents=("agent_id", "size"),
        expected_mean_miles=("expected_miles", "mean"),
        simulated_mean_miles=("simulated_miles", "mean"),
        input_connection_probability=("plugin_frequency_per_day", "mean"),
        connections=("connections", "sum"),
        early_connections=("early_connections", "sum"),
    )
    calibration["mileage_difference_percent"] = 100 * (
        calibration.simulated_mean_miles / calibration.expected_mean_miles - 1
    )
    calibration["connections_per_agent_day"] = calibration.connections / (
        calibration.agents * simulation_days
    )
    checks = check_physical_invariants(ordered, agents, timestep_minutes, charging_efficiency)
    return summary, calibration, checks
