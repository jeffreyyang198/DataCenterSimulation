"""Apply explicit density, floor-area, and workload scenarios to cleaned IM3 sites."""

import argparse
import math
from pathlib import Path

import pandas as pd

if __package__:
    from .scenarios import SimulationScenario
else:
    from scenarios import SimulationScenario

if __package__:
    from .energy_model import estimate_average_it_power, estimate_annual_facility_energy
    from .power_density import (assign_power_density_scenario, estimate_rated_power_from_im3,
                                load_power_density_calibration, summarize_power_density)
else:
    from energy_model import estimate_average_it_power, estimate_annual_facility_energy
    from power_density import (assign_power_density_scenario, estimate_rated_power_from_im3,
                               load_power_density_calibration, summarize_power_density)

ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = ROOT / 'data/processed/data_centers.csv'
OUTPUT_FILE = ROOT / 'data/processed/data_centers_with_energy.csv'
ENERGY_SCENARIOS_FILE = ROOT / 'data/model_parameters/energy_scenarios.csv'
ESTIMATE_COLUMNS = [
    'estimated_gross_area_sqft', 'estimated_rated_it_power_mw',
    'estimated_average_it_power_mw', 'estimated_annual_facility_energy_mwh',
]


def load_energy_scenario(scenario: str, path: str | Path = ENERGY_SCENARIOS_FILE) -> dict[str, float]:
    """Load utilization, idle fraction, and PUE assumptions for one workload."""
    df = pd.read_csv(path)
    required = {'scenario', 'utilization', 'idle_fraction', 'pue'}
    if missing := required - set(df.columns):
        raise ValueError(f'Missing energy scenario columns: {sorted(missing)}')
    if df.scenario.isna().any() or df.scenario.duplicated().any():
        raise ValueError('Energy scenario names must be present and unique')
    rows = df.loc[df.scenario == scenario]
    if rows.empty:
        raise ValueError(f'Unknown workload scenario {scenario!r}; choose from {df.scenario.tolist()}')
    parameters = {key: rows.iloc[0][key] for key in ['utilization', 'idle_fraction', 'pue']}
    # Validate even when no building records will be estimated.
    estimate_average_it_power(1.0, parameters['utilization'], parameters['idle_fraction'])
    estimate_annual_facility_energy(1.0, parameters['pue'])
    return {key: float(value) for key, value in parameters.items()}


def apply_energy_model(
    sites: pd.DataFrame,
    summary: dict[str, float | int],
    floor_area_multiplier: float,
    workload_parameters: dict[str, float],
    power_density_scenario: str = 'reference',
    workload_scenario: str = 'ai_training',
    climate_pue: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return a copy with scenario metadata, estimates, and exclusion statuses.

    The area multiplier is required by this API. Metadata describes the chosen
    scenario for every row; numeric estimates remain missing on excluded rows.
    Missing footprint status applies only to buildings; campus/point exclusions
    take precedence. Malformed or nonpositive building areas raise ValueError.
    When climate_pue is supplied, pue_k_fitted overrides scenario PUE by site ID.
    Unmatched sites and sites with missing fitted values use the scenario PUE.
    """
    if missing := {'site_type', 'square_feet'} - set(sites.columns):
        raise ValueError(f'Missing site columns: {sorted(missing)}')
    if not sites.site_type.isin(['building', 'campus', 'point']).all():
        raise ValueError('Every site_type must be building, campus, or point')
    density = assign_power_density_scenario(summary, power_density_scenario)
    estimate_rated_power_from_im3(1.0, floor_area_multiplier, density, 'building')
    if missing := {'utilization', 'idle_fraction', 'pue'} - set(workload_parameters):
        raise ValueError(f'Missing workload parameters: {sorted(missing)}')
    utilization = workload_parameters['utilization']
    idle_fraction = workload_parameters['idle_fraction']
    pue = workload_parameters['pue']
    estimate_average_it_power(1.0, utilization, idle_fraction)
    estimate_annual_facility_energy(1.0, pue)

    result = sites.copy()
    result['power_density_scenario'] = power_density_scenario
    result['power_density_w_sqft'] = density
    result['floor_area_multiplier'] = floor_area_multiplier
    result['workload_scenario'] = workload_scenario
    result['utilization'] = utilization
    result['idle_fraction'] = idle_fraction
    result['pue'] = pue
    if climate_pue is not None:
        if 'site_id' not in sites:
            raise ValueError('Climate PUE requires a site_id column in the model sites')
        site_ids = sites.site_id.astype('string')
        if site_ids.isna().any() or site_ids.str.strip().eq('').any() or site_ids.duplicated().any():
            raise ValueError('Climate PUE requires unique, nonmissing model site IDs')
        if missing := {'site_id', 'pue_k_fitted'} - set(climate_pue.columns):
            raise ValueError(f'Missing climate PUE columns: {sorted(missing)}')
        ids = climate_pue.site_id.astype('string')
        if ids.isna().any() or ids.str.strip().eq('').any() or ids.duplicated().any():
            raise ValueError('Climate PUE site IDs must be present and unique')
        fitted = pd.to_numeric(climate_pue.pue_k_fitted, errors='raise').astype(float)
        if not fitted.dropna().map(lambda value: math.isfinite(value) and value >= 1).all():
            raise ValueError('Fitted PUE must be finite and at least 1')
        matched = site_ids.map(pd.Series(fitted.to_numpy(), index=ids))
        if not matched.notna().any():
            raise ValueError('No modeled site IDs matched a usable fitted PUE')
        result['pue'] = matched.fillna(pue).astype(float)
        result['pue_source'] = matched.notna().map({True: 'climate_fitted', False: 'scenario_fallback'})

    estimates = []
    statuses = []
    for row in result.itertuples(index=False):
        if row.site_type in ('campus', 'point'):
            status = f'{row.site_type}_not_supported'
        elif pd.isna(row.square_feet):
            status = 'missing_footprint'
        else:
            status = 'estimated_building'

        if status != 'estimated_building':
            estimates.append([float('nan')] * len(ESTIMATE_COLUMNS))
        else:
            # CSV identifiers stay strings; parse only the area needed for the model.
            footprint = pd.to_numeric(row.square_feet, errors='raise')
            rated = estimate_rated_power_from_im3(footprint, floor_area_multiplier, density, 'building')
            average = estimate_average_it_power(rated, utilization, idle_fraction)
            annual = estimate_annual_facility_energy(average, row.pue)
            estimates.append([footprint * floor_area_multiplier, rated, average, annual])
        statuses.append(status)

    for index, column in enumerate(ESTIMATE_COLUMNS):
        result[column] = pd.Series([row[index] for row in estimates], index=sites.index, dtype='float64')
    result['energy_estimate_status'] = pd.Series(statuses, index=sites.index, dtype='string')
    return result

def apply_simulation_scenario(
    sites: pd.DataFrame,
    summary: dict[str, float | int],
    scenario: SimulationScenario,
    climate_pue: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Run the existing energy model using a SimulationScenario object.

    This wrapper adds an object-oriented interface without replacing the
    existing pure scientific calculation functions.
    """
    if not isinstance(scenario, SimulationScenario):
        raise TypeError(
            "scenario must be a SimulationScenario"
        )

    return apply_energy_model(
        sites=sites,
        summary=summary,
        floor_area_multiplier=scenario.floor_area_multiplier,
        workload_parameters=scenario.workload_parameters,
        power_density_scenario=scenario.power_density_scenario,
        workload_scenario=scenario.workload,
        climate_pue=climate_pue,
    )
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--power-density-scenario', choices=['low', 'reference', 'high'], default='reference')
    parser.add_argument('--floor-area-multiplier', type=float, default=1.0,
                        help='Explicit gross-area / footprint scenario; default 1.0 = single-story scenario')
    parser.add_argument('--workload-scenario', default='ai_training',
                        help='Name in energy_scenarios.csv (default: ai_training)')
    parser.add_argument('--climate-pue', type=Path, help='CSV with site_id and pue_k_fitted')
    parser.add_argument('--output', type=Path, help='Destination for the energy estimates')
    args = parser.parse_args()

    calibration = load_power_density_calibration()
    summary = summarize_power_density(calibration)
    parameters = load_energy_scenario(args.workload_scenario)
    # Prevent leading-zero loss and preserve literal text such as "NA".
    sites = pd.read_csv(INPUT_FILE, dtype='string', keep_default_na=False, na_values=[''])
    climate_pue = pd.read_csv(args.climate_pue, dtype={'site_id': 'string'},
                              keep_default_na=False, na_values=['']) if args.climate_pue else None
    result = apply_energy_model(sites, summary, args.floor_area_multiplier, parameters,
                                args.power_density_scenario, args.workload_scenario, climate_pue)
    output = args.output or (
        OUTPUT_FILE.with_stem(f'{OUTPUT_FILE.stem}_climate') if args.climate_pue else OUTPUT_FILE
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)

    print(f"Calibration count: {summary['count']}")
    for key in ['q25', 'median', 'q75']:
        print(f"{key}: {summary[key]:.6f} W/ft² of gross area")
    print(f'Density scenario: {args.power_density_scenario}; workload: {args.workload_scenario}')
    area_label = ' (explicit single-story scenario)' if args.floor_area_multiplier == 1.0 else ''
    print(f'Floor-area multiplier: {args.floor_area_multiplier}{area_label}')
    print('Annual operating hours: 8760')
    counts = result.energy_estimate_status.value_counts()
    for status in ['estimated_building', 'missing_footprint', 'campus_not_supported', 'point_not_supported']:
        print(f'{status}: {counts.get(status, 0)}')
    if climate_pue is not None:
        print(result.loc[result.energy_estimate_status == 'estimated_building', 'pue_source']
              .value_counts().to_string())
    print(f'Saved {output}')


if __name__ == '__main__':
    main()
