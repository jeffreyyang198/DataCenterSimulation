"""Geographic screening estimates using EPA eGRID2023 total-output rates."""
import argparse
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    'subregions.zip': 'https://www.epa.gov/system/files/other-files/2025-01/egrid2023_subregions.zip',
    'multiple.zip': 'https://www.epa.gov/system/files/other-files/2025-01/egrid2023_multiple_subregions.zip',
    'egrid2023.xlsx': 'https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx',
}
RATE_FIELDS = {'co2': 'SRCO2RTA', 'co2e': 'SRC2ERTA', 'nox': 'SRNOXRTA', 'so2': 'SRSO2RTA'}


def emissions_tonnes(energy, rate):
    """MWh × lb/MWh × exact international pound kg / kg per tonne."""
    return energy * rate * 0.45359237 / 1000


def assign_subregions(sites, primary, multiple, code_column):
    if sites.site_id.isna().any() or sites.site_id.duplicated().any():
        raise ValueError('Site IDs must be present and unique')
    xy = sites[['longitude', 'latitude']].apply(pd.to_numeric, errors='raise')
    if not np.isfinite(xy).all().all() or not (xy.longitude.between(-180, 180) & xy.latitude.between(-90, 90)).all():
        raise ValueError('Invalid coordinates')
    points = gpd.GeoDataFrame(sites[['site_id']].copy(), geometry=gpd.points_from_xy(xy.longitude, xy.latitude), crs=4326)
    hits = gpd.sjoin(points, primary[[code_column, 'geometry']].to_crs(4326), how='left', predicate='intersects')
    candidates = hits.groupby('site_id')[code_column].agg(lambda s: ';'.join(sorted(set(s.dropna().astype(str)))))
    shared = gpd.sjoin(points, multiple[['geometry']].to_crs(4326), how='inner', predicate='intersects').site_id
    result = sites[['site_id']].copy()
    result['egrid_candidates'] = result.site_id.map(candidates)
    result['egrid_mapping_status'] = 'geographic_screening'
    result.loc[result.egrid_candidates.eq(''), 'egrid_mapping_status'] = 'unmatched'
    ambiguous = result.site_id.isin(shared) | result.egrid_candidates.str.contains(';')
    result.loc[ambiguous, 'egrid_mapping_status'] = 'utility_verification_required'
    result['egrid_subregion'] = result.egrid_candidates.where(result.egrid_mapping_status.eq('geographic_screening'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/processed/data_centers_with_energy.csv')
    parser.add_argument('--raw-dir', type=Path, default=ROOT / 'data/raw/egrid')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/processed/emissions')
    args = parser.parse_args()
    sites = pd.read_csv(args.input, dtype={'site_id': str, 'county_fips': str, 'state_fips': str, 'source_site_id': str})
    raw = pd.read_excel(args.raw_dir / 'egrid2023.xlsx', sheet_name='SRL23', header=1)
    factors = raw[['SUBRGN', *RATE_FIELDS.values()]].rename(columns={'SUBRGN': 'egrid_subregion', **{v: f'{k}_lb_per_mwh' for k, v in RATE_FIELDS.items()}})
    factors = factors.dropna(subset=['egrid_subregion'])
    if factors.egrid_subregion.duplicated().any():
        raise ValueError('Duplicate subregion factors')
    for col in [f'{k}_lb_per_mwh' for k in RATE_FIELDS]:
        factors[col] = pd.to_numeric(factors[col], errors='raise')
        if not np.isfinite(factors[col]).all() or factors[col].lt(0).any():
            raise ValueError('Invalid emission factor')
    primary = gpd.read_file(args.raw_dir / 'subregions.zip')
    multiple = gpd.read_file(args.raw_dir / 'multiple.zip')
    mapping = assign_subregions(sites, primary, multiple, 'Subregion')
    result = sites.merge(mapping, on='site_id', validate='one_to_one').merge(factors, on='egrid_subregion', how='left', validate='many_to_one')
    energy = pd.to_numeric(result.estimated_annual_facility_energy_mwh, errors='raise')
    if (energy.notna() & (~np.isfinite(energy) | energy.lt(0))).any():
        raise ValueError('Invalid facility energy')
    result['emissions_status'] = result.egrid_mapping_status
    result.loc[result.egrid_subregion.notna() & result.co2_lb_per_mwh.isna(), 'emissions_status'] = 'missing_factor'
    result.loc[energy.isna(), 'emissions_status'] = 'missing_energy'
    eligible = energy.notna() & result.egrid_subregion.notna() & result.co2_lb_per_mwh.notna()
    result.loc[eligible, 'emissions_status'] = 'estimated_geographic_screening'
    for pollutant in RATE_FIELDS:
        result[f'estimated_annual_{pollutant}_tonnes'] = emissions_tonnes(energy, result[f'{pollutant}_lb_per_mwh']).where(eligible)
    result['egrid_factor_year'] = 2023
    result['energy_basis'] = 'existing_scenario_8760_hours'
    result['grid_loss_adjustment_pct'] = 0.0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(args.output_dir / 'site_egrid_mapping.csv', index=False)
    factors.to_csv(args.output_dir / 'egrid2023_factors.csv', index=False)
    result.to_csv(args.output_dir / 'data_centers_with_emissions.csv', index=False)
    result.loc[~eligible].to_csv(args.output_dir / 'emissions_review.csv', index=False)
    report = {'factor_year': 2023, 'mapping_status_counts': mapping.egrid_mapping_status.value_counts().to_dict(), 'emissions_status_counts': result.emissions_status.value_counts().to_dict(), 'source_files': {name: {'url': url, 'sha256': hashlib.sha256((args.raw_dir / name).read_bytes()).hexdigest()} for name, url in SOURCES.items()}, 'limitations': ['Geographic screening; electricity supplier not verified.', 'Shared subregion areas require utility verification; no emissions imputed.', '2023 factors applied to hypothetical full-year 8760-hour energy scenarios.', 'Total-output generation factors; no grid-loss uplift or contractual renewable adjustment.', 'No aggregate site totals: overlapping source facilities remain unresolved.']}
    (args.output_dir / 'emissions_report.json').write_text(json.dumps(report, indent=2) + '\n')
    plot_comparison(factors, args.output_dir)
    print(json.dumps(report['emissions_status_counts'], indent=2))


def plot_comparison(factors, output_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    comparison = factors.copy()
    comparison['scenario_annual_energy_mwh'] = 911040.0
    comparison['annual_co2_thousand_tonnes'] = emissions_tonnes(911040.0, comparison.co2_lb_per_mwh) / 1000
    comparison = comparison.sort_values('annual_co2_thousand_tonnes')
    comparison.to_csv(output_dir / 'same_facility_comparison.csv', index=False)
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.barh(comparison.egrid_subregion, comparison.annual_co2_thousand_tonnes)
    ax.invert_yaxis()
    ax.axvline(comparison.annual_co2_thousand_tonnes.median(), color='gray', linestyle='--', label='Median across subregions')
    ax.set_title('Same hypothetical facility (911,040 MWh/year) in each eGRID subregion')
    ax.set_xlabel('Annual CO₂ (thousand metric tonnes)')
    ax.legend()
    fig.text(0.1, 0.01, 'Source: EPA eGRID2023, revision 2; annual total-output CO₂ rates (lb/MWh). No grid-loss adjustment.', fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(output_dir / 'same_facility_co2_by_subregion.png', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    main()
