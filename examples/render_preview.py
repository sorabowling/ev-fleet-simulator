"""Render the README figure from a previously exported scenario.

Run ``ev-fleet --output outputs/demo`` first, then execute this script from
the repository root. Matplotlib is available through the development extra.
"""

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


def main() -> None:
    summary = pd.read_csv("outputs/demo/summary.csv", parse_dates=["timestamp"])
    x = summary.timestamp
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.spines.bottom": False,
            "axes.labelcolor": "#324153",
            "xtick.color": "#596778",
            "ytick.color": "#596778",
        }
    )
    fig, axes = plt.subplots(
        3,
        1,
        figsize=(13.5, 9),
        sharex=True,
        gridspec_kw={"height_ratios": [1.45, 1, 1]},
        layout="constrained",
    )
    fig.set_facecolor("#fbfcfe")
    for ax in axes:
        ax.set_facecolor("#fbfcfe")
        ax.grid(axis="y", color="#e2e7ee", linewidth=0.7)
        ax.set_axisbelow(True)
        ax.tick_params(length=0)
        ax.margins(x=0)
    fig.suptitle(
        "EV Fleet Simulator", x=0.08, ha="left", fontsize=24, fontweight="bold", color="#182b42"
    )
    axes[0].set_title(
        "100 vehicles  /  7 days  /  5-minute intervals  /  seed 42",
        loc="left",
        color="#596778",
        pad=20,
        fontsize=11,
    )
    axes[0].fill_between(
        x,
        summary.plugged_in_percent,
        step="post",
        color="#b7d2ed",
        alpha=0.75,
        label="Vehicles plugged in",
    )
    axes[0].fill_between(
        x,
        summary.p05_soc,
        summary.p95_soc,
        color="#f0be87",
        alpha=0.36,
        label="5th–95th percentile SoC",
    )
    axes[0].plot(x, summary.mean_soc, color="#a65417", linewidth=1.8, label="Mean SoC")
    axes[0].set_ylim(0, 105)
    axes[0].set_ylabel("Vehicles plugged in / SoC (%)")
    axes[0].legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=9)
    axes[1].fill_between(x, summary.grid_power_kw, step="post", color="#f1cdc7", alpha=0.8)
    axes[1].step(x, summary.grid_power_kw, where="post", color="#b24c43", linewidth=1.3)
    axes[1].set_ylabel("Grid demand (kW)")
    axes[1].set_ylim(bottom=0)
    axes[2].plot(x, summary.stored_energy_kwh, color="#28766a", linewidth=1.6)
    axes[2].set_ylabel("Stored energy (kWh)")
    axes[2].set_ylim(bottom=0)
    axes[2].xaxis.set_major_locator(mdates.DayLocator())
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%a\n%d %b", tz=x.dt.tz))
    axes[2].set_xlabel("Local time · Europe/London", labelpad=12)
    output = Path("docs/images/fleet-preview.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == "__main__":
    main()
