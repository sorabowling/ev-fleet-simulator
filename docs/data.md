# Inputs and output fields

## Bundled inputs

Six aggregate EV driver archetypes provide the model's starting inputs. The simulator generates vehicle-level driving and charging time series from these summaries, without individual trip or charging records.

The numerical archetype inputs are reference assumptions rather than new empirical findings. The weekday/weekend driving probabilities, bounded distance distribution, travel anchors, home-only policy, reserve, and charging efficiency are modeling choices. Charging policies and travel anchors are stored separately from display labels.

| Input field | Unit / meaning | Role |
| --- | --- | --- |
| `archetype_id`, `archetype` | Stable row identifier, neutral display label | Cohort identification |
| `population_percent` | Reference percentage | Retained for comparison |
| `population_share` | Nonnegative weight | Active sampling input, normalized on use |
| `miles_per_year` | Miles per 365-day year | Expected driving demand |
| `battery_capacity_kwh` | Usable kWh, as assumed | Energy capacity |
| `driving_efficiency_mi_per_kwh` | Miles per battery kWh | Driving consumption |
| `plugin_frequency_per_day` | Interpreted as probability in [0, 1] | Daily connection opportunity |
| `charger_power_kw` | Grid-side kW | Maximum charging power |
| `target_soc` | Fraction in [0, 1] | Normal charging target |
| `nominal_plugin_time`, `nominal_plugout_time` | Local HH:MM | Connection opportunity / scheduled charging clocks |
| `departure_anchor`, `return_anchor` | Local HH:MM | Mean departure and return draws |
| `charging_policy` | `immediate` or `scheduled` | Allowed charging hours |
| `reference_kwh_per_year` | kWh/year | Retained comparison value |
| `reference_kwh_per_plugin` | kWh/connection | Retained comparison value |
| `reference_plugin_soc`, `reference_soc_requirement` | Fractions | Retained comparison values |
| `reference_charging_duration_hours` | Hours | Retained comparison value |

Reference fields are comparison values and do not constrain simulated sessions. Only annual mileage and connection rate are currently included in the calibration output. The other reference fields are available for further comparisons.

Archetype F has a nominal 00:00 connection opportunity on days at home, probability 1, and connects on every return. Its travel anchors are explicitly 07:00 and 18:00. Archetype E separates 09:00/18:00 travel from its 22:00–09:00 power window.

## Interval table

Every timestamp starts an elapsed-time interval of the configured duration. Events use `[start, end)` boundaries. Positive grid power means charging, while a connected state can persist at zero power.

| Field | Definition |
| --- | --- |
| `agent_id`, `archetype`, `timestamp` | Vehicle, cohort, interval start |
| `is_home` | At the modeled home charger location |
| `is_driving` | In an outbound or return driving leg |
| `planned_is_plugged_in` | Habitual connection schedule before range intervention |
| `is_plugged_in` | Actual modeled connection, including range intervention |
| `range_override_active` | Early-connection override remains active until departure |
| `charging_allowed` | Local charging window permits power draw |
| `next_away_drive_kwh` | Energy demand of the next away window at home, or current window while away |
| `charging_target_soc` | Current charging target, including any range adjustment |
| `distance_miles`, `drive_energy_kwh` | Interval driving demand |
| `soc_start`, `soc_end` | Battery fractions at the two interval boundaries |
| `battery_energy_start_kwh`, `battery_energy_end_kwh` | Stored energy at those boundaries |
| `grid_energy_kwh` | Electricity drawn from the grid in the interval |
| `battery_charge_kwh` | Electricity retained after charging losses |
| `grid_power_kw` | Grid energy divided by interval duration in hours |

## Session table

`session_type` is `connection`, `charging`, or `driving`. Each row is a contiguous span of that state for one agent. Charging is a subset of connection, so energy appears in both views. **Filter by session type before summing** to avoid double-counting charging energy.

`start` and `end` are half-open boundaries. `soc_start` and `soc_end` are fractions. A connection row's starting SoC answers the plug-in SoC question when `left_censored` is false. A left-censored connection was already present at the beginning, so its start is not an observed plug-in event. `right_censored` means the state continues to the final observed boundary, and its actual ending beyond that boundary is unknown.

`duration_hours` measures elapsed time, including across clock changes. Session sums include miles, driving energy, grid energy, and battery charging energy. Back-to-back driving legs with no parking gap form one continuous driving session.

## Fleet summary and calibration

Fleet mean and percentile SoC use the start of each interval and weight each vehicle equally. Stored kWh sum battery energy across vehicles. Power sums interval-average grid power. These measures are not all evaluated at the end of an interval.

Calibration uses every sampled vehicle, including those with zero observed driving. New connections require a false-to-true transition and exclude the initial connected state. Early connections count transitions triggered by the range override. Rates divide by agent count and local calendar days. On clock-change days, that denominator remains one calendar day.

`mileage_difference_percent` is undefined when expected mileage is zero. The timeseries remains valid for a zero-mileage scenario.
