"""Save six building energy scenarios and a comparison of their distributions."""

import argparse
from pathlib import Path

import pandas as pd

if __package__:
    from .apply_im3_energy_model import INPUT_FILE, ROOT, apply_energy_model, load_energy_scenario
    from .power_density import load_power_density_calibration, summarize_power_density
else:
    from apply_im3_energy_model import INPUT_FILE, ROOT, apply_energy_model, load_energy_scenario
    from power_density import load_power_density_calibration, summarize_power_density

OUTPUT_DIR = ROOT / 'data/processed/energy_scenarios'


def compare_energy_scenarios(
    sites: pd.DataFrame,
    density_summary: dict[str, float | int],
    floor_area_multiplier: float,
    output_dir: str | Path,
) -> pd.DataFrame:
    """Write one CSV per density/workload pair plus a six-row summary.

    Estimates reuse the single-scenario model. Distribution statistics include
    estimated buildings only; excluded sites are unknown, never zero loads.
    No regional totals are computed because overlap has not been resolved.
    Validate all six scenarios before writing any files.
    """
    results = []
    records = []
    workloads = {name: load_energy_scenario(name) for name in ('ai_training', 'ai_inference')}
    for density in ('low', 'reference', 'high'):
        for workload, parameters in workloads.items():
            result = apply_energy_model(
                sites, density_summary, floor_area_multiplier, parameters, density, workload,
            )
            filename = f'{density}_{workload}.csv'
            results.append((filename, result))
            counts = result.energy_estimate_status.value_counts()
            record = {
                'power_density_scenario': density,
                'workload_scenario': workload,
                'floor_area_multiplier': floor_area_multiplier,
                'power_density_w_sqft': density_summary[{'low': 'q25', 'reference': 'median', 'high': 'q75'}[density]],
                **parameters,
                'total_sites': len(result),
                'output_file': filename,
            }
            for status in ('estimated_building', 'missing_footprint', 'campus_not_supported', 'point_not_supported'):
                record[f'{status}_count'] = int(counts.get(status, 0))
            buildings = result.loc[result.energy_estimate_status == 'estimated_building']
            for column in ('estimated_rated_it_power_mw', 'estimated_annual_facility_energy_mwh'):
                values = buildings[column]
                record[f'median_{column}'] = values.median()
                record[f'q95_{column}'] = values.quantile(0.95)
                record[f'max_{column}'] = values.max()
            records.append(record)

    comparison = pd.DataFrame(records)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for filename, result in results:
        result.to_csv(destination / filename, index=False)
    comparison.to_csv(destination / 'scenario_comparison.csv', index=False)
    return comparison


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--floor-area-multiplier', type=float, default=1.0,
                        help='Gross-area / footprint assumption; default 1.0 is a single-story scenario')
    parser.add_argument('--output-dir', type=Path,
                        help='Override destination; reruns replace the seven scenario CSVs there')
    args = parser.parse_args()
    destination = args.output_dir or OUTPUT_DIR / f'floor_area_{args.floor_area_multiplier}'
    sites = pd.read_csv(INPUT_FILE, dtype='string', keep_default_na=False, na_values=[''])
    summary = summarize_power_density(load_power_density_calibration())
    comparison = compare_energy_scenarios(sites, summary, args.floor_area_multiplier, destination)
    print(f'Floor-area multiplier: {args.floor_area_multiplier} (scenario assumption)')
    print(comparison[['power_density_scenario', 'workload_scenario',
                      'estimated_building_count',
                      'median_estimated_annual_facility_energy_mwh']].to_string(index=False))
    print(f'Saved six site-level scenario files and scenario_comparison.csv to {destination}')
    print('Scenario estimates, not observed loads; campus and point estimates remain blank.')


if __name__ == '__main__':
    main()
