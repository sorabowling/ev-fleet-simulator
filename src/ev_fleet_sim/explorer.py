"""Optional notebook controls. All modeling lives in the reusable package."""

import datetime as dt
import json

from .config import SimulationConfig
from .population import default_driving_assumptions, generate_population, load_archetypes
from .scenario import run_scenario


class FleetExplorer:
    """Notebook UI with a fixed sampled fleet and explicit run action.

    ``result`` holds the last successful ScenarioResult. Beginning another
    run clears it so a failed simulation cannot display stale output.
    """

    def __init__(self, number_of_agents: int = 100, seed: int = 42):
        import ipywidgets as widgets

        self.seed = seed
        self.metadata = load_archetypes()
        self.agents = generate_population(self.metadata, number_of_agents, seed)
        self.result = None
        self.selection = {
            name: widgets.Checkbox(value=True, description=name, indent=False)
            for name in self.metadata.archetype
        }
        self.start = widgets.DatePicker(description="Start:", value=dt.date(2026, 1, 5))
        self.days = widgets.BoundedIntText(value=7, min=1, max=90, description="Days:")
        self.probabilities = {}
        rows = []
        for row in default_driving_assumptions(self.metadata).itertuples(index=False):
            weekday = widgets.FloatSlider(
                value=row.weekday_drive_probability,
                min=0,
                max=1,
                step=0.05,
                description="Weekday",
                continuous_update=False,
            )
            weekend = widgets.FloatSlider(
                value=row.weekend_drive_probability,
                min=0,
                max=1,
                step=0.05,
                description="Weekend",
                continuous_update=False,
            )
            self.probabilities[row.archetype] = (weekday, weekend)
            rows.append(
                widgets.VBox(
                    [widgets.HTML(f"<b>{row.archetype}</b>"), widgets.HBox([weekday, weekend])]
                )
            )
        panel = widgets.Accordion(children=[widgets.VBox(rows)])
        panel.set_title(0, "Driving probabilities")
        panel.selected_index = None
        self.button = widgets.Button(description="Run scenario", button_style="primary")
        self.output = widgets.Output()
        self.individual = widgets.Output()
        self.agent_choice = widgets.Dropdown(options=[], description="Vehicle:", disabled=True)
        self.button.on_click(self.run)
        self.agent_choice.observe(self.show_agent, names="value")
        self.widget = widgets.VBox(
            [
                widgets.HTML("<b>Select archetypes from the fixed sampled fleet</b>"),
                widgets.HBox(list(self.selection.values())[:3]),
                widgets.HBox(list(self.selection.values())[3:]),
                widgets.HBox([self.start, self.days]),
                panel,
                self.button,
                self.output,
                self.agent_choice,
                self.individual,
            ]
        )

    @staticmethod
    def _append_figure(output, figure) -> None:
        output.outputs += (
            {
                "output_type": "display_data",
                "data": {"application/vnd.plotly.v1+json": json.loads(figure.to_json())},
                "metadata": {},
            },
        )

    def show_agent(self, change=None) -> None:
        from .plotting import make_agent_figure

        self.individual.outputs = ()
        if self.result is not None and self.agent_choice.value is not None:
            self._append_figure(
                self.individual,
                make_agent_figure(
                    self.result.data, self.agent_choice.value, self.result.config.timestep_minutes
                ),
            )

    def run(self, button=None) -> None:
        from IPython.display import Markdown

        from .plotting import make_population_figure

        if self.button.disabled:
            return
        self.button.disabled = True
        self.result = None
        self.output.outputs = ()
        self.individual.outputs = ()
        self.agent_choice.disabled = True
        self.agent_choice.options = []
        self.output.append_stdout("Simulating...\n")
        try:
            selected = [name for name, control in self.selection.items() if control.value]
            agents = self.agents.loc[self.agents.archetype.isin(selected)].copy()
            if agents.empty:
                raise ValueError("Choose at least one archetype present in the sampled fleet.")
            if self.start.value is None:
                raise ValueError("Choose a start date.")
            assumptions = default_driving_assumptions(self.metadata)
            for name, (weekday, weekend) in self.probabilities.items():
                assumptions.loc[
                    assumptions.archetype.eq(name),
                    ["weekday_drive_probability", "weekend_drive_probability"],
                ] = [weekday.value, weekend.value]
            config = SimulationConfig(
                start=self.start.value.isoformat(),
                days=self.days.value,
                number_of_agents=len(self.agents),
                seed=self.seed,
            )
            result = run_scenario(config, agents=agents, assumptions=assumptions)
            self.result = result
            self.output.outputs = ()
            self.output.append_display_data(
                Markdown(
                    f"**{len(agents):,} vehicles · {config.days} days · "
                    f"peak demand {result.summary.grid_power_kw.max():.1f} kW**"
                )
            )
            self._append_figure(self.output, make_population_figure(result.summary))
            self.output.append_display_data(result.calibration.round(3))
            self.output.append_display_data(result.checks)
            self.agent_choice.options = agents.agent_id.tolist()
            self.agent_choice.disabled = False
            self.show_agent()
        except ValueError as error:
            self.output.outputs = ()
            self.output.append_stdout(f"Scenario could not be completed: {error}\n")
        finally:
            self.button.disabled = False


def build_explorer(number_of_agents: int = 100, seed: int = 42) -> FleetExplorer:
    """Construct controls without running a simulation."""
    return FleetExplorer(number_of_agents, seed)
