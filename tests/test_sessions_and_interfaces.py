import json

import pandas as pd
import pytest

from ev_fleet_sim import SimulationConfig, generate_population, load_archetypes
from ev_fleet_sim.cli import main
from ev_fleet_sim.connections import generate_connection_timeline
from ev_fleet_sim.travel import place_driving_segments
from ev_fleet_sim.validation import validate_time_grid


def test_session_boundaries_plugin_soc_and_energy(reference_run):
    s = reference_run.sessions
    assert (s.end > s.start).all()
    assert (s.soc_start.between(0, 1) & s.soc_end.between(0, 1)).all()
    for (agent_id, kind), spans in s.groupby(["agent_id", "session_type"]):
        assert (
            spans.start.iloc[1:].reset_index(drop=True)
            >= spans.end.iloc[:-1].reset_index(drop=True)
        ).all()
        if kind == "connection":
            agent = reference_run.data.query("agent_id == @agent_id").set_index("timestamp")
            for row in spans.itertuples():
                assert row.soc_start == agent.loc[row.start, "soc_start"]
    connections = s.query("session_type == 'connection'")
    assert connections.left_censored.sum() == len(reference_run.agents)
    assert (~connections.left_censored).sum() == reference_run.calibration.connections.sum()
    assert s.query("session_type == 'driving'").distance_miles.sum() == pytest.approx(
        reference_run.data.distance_miles.sum()
    )
    assert s.query("session_type == 'charging'").grid_energy_kwh.sum() == pytest.approx(
        reference_run.data.grid_energy_kwh.sum()
    )


def test_skipped_opportunity_does_not_disconnect(six_agents):
    agent = six_agents.iloc[0].copy()
    agent.plugin_frequency_per_day = 0
    dates, times = SimulationConfig(days=2).time_grid()
    windows = pd.DataFrame(columns=["agent_id", "drive_date", "departure_time", "return_time"])
    connected = generate_connection_timeline(agent, windows, times, dates)
    disconnected = generate_connection_timeline(
        agent, windows, times, dates, initially_plugged_in=False
    )
    assert connected.is_plugged_in.all()
    assert not disconnected.is_plugged_in.any()


def test_overlapping_legs_rejected(six_agents, timeline):
    windows = pd.DataFrame(
        {
            "departure_time": [timeline.timestamp.iloc[0]],
            "return_time": [timeline.timestamp.iloc[1]],
            "drive_date": [timeline.timestamp.iloc[0]],
            "distance_miles": [20.0],
        }
    )
    timeline.is_home = False
    with pytest.raises(ValueError, match="overlap"):
        place_driving_segments(timeline, windows, six_agents.iloc[0])


def test_truncated_grid_rejected():
    dates, times = SimulationConfig(days=1).time_grid()
    with pytest.raises(ValueError, match="every interval"):
        validate_time_grid(dates, times[:-1], 5)


def test_population_sampling_uses_positions_with_custom_index():
    metadata = load_archetypes()
    metadata.index = ["custom"] * len(metadata)
    agents = generate_population(metadata, 10)
    assert len(agents) == 10
    assert agents.agent_id.is_unique


def test_csv_export_and_manifest(tmp_path, reference_run):
    reference_run.save(tmp_path)
    assert (tmp_path / "timeseries.csv.gz").is_file()
    manifest = json.loads((tmp_path / "run.json").read_text())
    assert manifest["all_physical_checks_passed"]
    exported = pd.read_csv(tmp_path / "sessions.csv")
    assert len(exported) == len(reference_run.sessions)


def test_cli_run_and_failure_status(tmp_path, capsys):
    assert main(["--agents", "3", "--days", "1", "--output", str(tmp_path / "ok")]) == 0
    assert (tmp_path / "ok/run.json").is_file()
    assert main(["--days", "0", "--output", str(tmp_path / "bad")]) == 1
    assert not (tmp_path / "bad").exists()
    assert "Scenario failed" in capsys.readouterr().err


def test_optional_figures(reference_run):
    pytest.importorskip("plotly")
    from ev_fleet_sim.plotting import make_agent_figure, make_population_figure

    assert len(make_population_figure(reference_run.summary).data) == 6
    figure = make_agent_figure(reference_run.data, reference_run.agents.agent_id.iloc[0])
    assert len(figure.data[0].x) == len(reference_run.summary) + 1
