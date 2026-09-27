# Validation

The 29 tests cover energy conservation, battery continuity, session boundaries, charging policies, reproducible random streams, invalid inputs, and daylight-saving transitions. A seven-day regression scenario compares mileage, energy, and state totals for all six archetypes against a saved [baseline](../tests/fixtures/baseline_metrics.json).

| Check | Result |
| --- | --- |
| Tests | 29 passed |
| Ruff lint and formatting | Passed |
| Source distribution and wheel | Built successfully; wheel installed and tested |
| Default example | 100 vehicles, seven days, 201,600 rows, all 14 physical checks passed |

Package checks used Python 3.12.14, NumPy 2.3.5, pandas 2.2.3, and Plotly 7.1.0. Tests, exported charts, and live notebook controls were also checked on macOS with Python 3.13. Windows has not been tested locally.

GitHub Actions is configured for Python 3.10 and 3.12. The repository's Actions tab shows the status of hosted runs.

## Example run

The default scenario produced a peak grid demand of **343.0 kW**, total grid energy of **8,475.59 kWh**, and **30,297.35 miles** driven. These are simulation outputs. The configuration and dependency versions are in [example-run.json](example-run.json).

These checks test numerical and state consistency. They do not validate the behavioral assumptions against observed drivers.
