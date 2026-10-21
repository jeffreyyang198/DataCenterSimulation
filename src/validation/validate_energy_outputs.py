"""Validate scenario estimates and report extremes without changing the model."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = ROOT / 'data/processed/data_centers_with_energy.csv'
OUTPUT_DIR = ROOT / 'data/validation'
RATED = 'estimated_rated_it_power_mw'
AVERAGE = 'estimated_average_it_power_mw'
ANNUAL = 'estimated_annual_facility_energy_mwh'
AREA = 'estimated_gross_area_sqft'
ESTIMATES = [AREA, RATED, AVERAGE, ANNUAL]
NUMERIC_COLUMNS = ['square_feet', *ESTIMATES, 'power_density_w_sqft',
                   'floor_area_multiplier', 'utilization', 'idle_fraction', 'pue']
STAT_COLUMNS = [RATED, AVERAGE, ANNUAL, 'square_feet']
BUILDING_INPUTS = ['square_feet', 'floor_area_multiplier', 'power_density_w_sqft',
                   'utilization', 'idle_fraction', 'pue']
REPORT_COLUMNS = ['site_id', 'site_name', 'operator', 'state', 'county', 'site_type',
                  'square_feet', RATED, AVERAGE, ANNUAL]


def load_energy_outputs(path: str | Path = INPUT_FILE) -> pd.DataFrame:
    """Preserve identifiers and literal text; interpret only blank cells as null."""
    return pd.read_csv(path, dtype='string', keep_default_na=False, na_values=[''])


def numeric_values(series: pd.Series) -> pd.Series:
    """Return finite numeric values only, for statistics and ranking."""
    values = pd.to_numeric(series, errors='coerce')
    return values.loc[values.notna() & ~values.isin([float('inf'), -float('inf')])].astype(float)


def describe_numeric(series: pd.Series) -> dict[str, float | int]:
    """Describe finite observations with linear quantiles and sample SD (ddof=1).

    No observations yields count=0 and blank statistics. Sample SD is undefined
    for a single observation. Call validate_structure to detect malformed inputs.
    """
    values = numeric_values(series)
    return {
        'count': len(values), 'min': values.min(), 'q05': values.quantile(.05),
        'q25': values.quantile(.25), 'median': values.median(),
        'q75': values.quantile(.75), 'q95': values.quantile(.95),
        'max': values.max(), 'mean': values.mean(), 'standard_deviation': values.std(ddof=1),
    }


def structural_counts(df: pd.DataFrame) -> dict[str, int]:
    """Count statuses separately from types and actual missing building estimates."""
    building = df.site_type.eq('building')
    estimates = df.reindex(columns=ESTIMATES)
    return {
        'total_sites': len(df),
        'building_sites': int(building.sum()),
        'campus_sites': int(df.site_type.eq('campus').sum()),
        'point_sites': int(df.site_type.eq('point').sum()),
        'estimated_buildings': int(df.energy_estimate_status.eq('estimated_building').sum()),
        'missing_footprint_records': int(df.energy_estimate_status.eq('missing_footprint').sum()),
        'unsupported_campus_records': int(df.energy_estimate_status.eq('campus_not_supported').sum()),
        'unsupported_point_records': int(df.energy_estimate_status.eq('point_not_supported').sum()),
        'missing_building_estimates': int((building & estimates.isna().any(axis=1)).sum()),
        # Number of duplicated ID values, not number of extra rows.
        'duplicated_site_id_values': int(df.loc[df.site_id.duplicated(False), 'site_id'].nunique()),
        'rows_missing_coordinates': int(df[['latitude', 'longitude']].isna().any(axis=1).sum()),
    }


def validate_structure(df: pd.DataFrame) -> pd.DataFrame:
    """Raise on structural or numeric errors; return a numeric working copy.

    Present non-null values must be numeric and finite. Missing building inputs
    or outputs are left for review flags. Unsupported records may have blank
    estimates but may not contain footprint-derived estimates.
    """
    required = {'site_id', 'site_type', 'energy_estimate_status', 'latitude', 'longitude'}
    if missing := required - set(df.columns):
        raise ValueError(f'Missing structural columns: {sorted(missing)}')
    errors = []
    result = df.copy()
    if df.site_id.isna().any() or df.site_id.astype('string').str.strip().eq('').any():
        errors.append('missing site_id')
    if df.site_id.duplicated().any():
        errors.append('duplicate site_id')
    if df[['latitude', 'longitude']].isna().any().any():
        errors.append('missing coordinates')
    if not df.site_type.isin(['building', 'campus', 'point']).all():
        errors.append('unknown or missing site_type')
    for column in [*NUMERIC_COLUMNS, 'latitude', 'longitude']:
        if column not in df:
            continue
        values = pd.to_numeric(df[column], errors='coerce')
        if (df[column].notna() & values.isna()).any() or values.isin([float('inf'), -float('inf')]).any():
            errors.append(f'{column}: nonnumeric or nonfinite values')
        result[column] = values
        if column in ['utilization', 'idle_fraction']:
            invalid = values.notna() & ~values.between(0, 1)
        elif column == 'pue':
            invalid = values < 1
        elif column in ['latitude', 'longitude']:
            bound = 90 if column == 'latitude' else 180
            invalid = values.notna() & ~values.between(-bound, bound)
        else:
            invalid = values < 0
        if invalid.any():
            errors.append(f'{column}: values outside allowed range')
    expected_status = df.site_type.map({'building': 'estimated_building',
                                       'campus': 'campus_not_supported', 'point': 'point_not_supported'})
    status_ok = df.energy_estimate_status.eq(expected_status) | (
        df.site_type.eq('building') & df.energy_estimate_status.eq('missing_footprint'))
    if not status_ok.fillna(False).all():
        errors.append('energy_estimate_status inconsistent with site_type')
    unsupported = df.site_type.isin(['campus', 'point'])
    if df.reindex(columns=ESTIMATES).loc[unsupported].notna().any().any():
        errors.append('unsupported site type has footprint-derived estimates')
    if errors:
        raise ValueError('Energy validation failed: ' + '; '.join(errors))
    return result


def add_plausibility_flags(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """Flag values strictly above q99; thresholds identify review candidates only.

    Rated-power threshold uses estimated buildings; footprint uses all buildings.
    Missing inputs (including zero positive-only inputs) or outputs are flagged.
    Empty populations have NaN thresholds and generate no high-value flags.
    """
    building = df.site_type.eq('building')
    estimated = building & df.energy_estimate_status.eq('estimated_building')
    values = df.reindex(columns=NUMERIC_COLUMNS)
    thresholds = {
        'q99_rated_it_power_mw': float(numeric_values(values.loc[estimated, RATED]).quantile(.99)),
        'q99_building_square_feet': float(numeric_values(values.loc[building, 'square_feet']).quantile(.99)),
    }
    missing = values[BUILDING_INPUTS + ESTIMATES].isna().any(axis=1)
    for column in ['square_feet', 'floor_area_multiplier', 'power_density_w_sqft']:
        missing |= values[column].le(0).fillna(False)
    flags = []
    for index in range(len(df)):
        row_flags = []
        if not building.iloc[index]:
            row_flags.append('unsupported_site_type')
        else:
            if missing.iloc[index] or df.energy_estimate_status.iloc[index] == 'missing_footprint':
                row_flags.append('missing_required_input')
            power = values[RATED].iloc[index]
            footprint = values.square_feet.iloc[index]
            if pd.notna(power) and power > thresholds['q99_rated_it_power_mw']:
                row_flags.append('very_large_power_estimate')
            if pd.notna(footprint) and footprint > thresholds['q99_building_square_feet']:
                row_flags.append('very_large_footprint')
        flags.append(';'.join(row_flags) or 'ok')
    result = df.copy()
    result['energy_validation_flag'] = flags
    return result, thresholds


def top_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """Return three ranked top-ten lists; repeated sites retain each ranking context."""
    buildings = df.loc[df.site_type.eq('building')]
    reports = []
    columns = [column for column in REPORT_COLUMNS if column in df]
    for metric in [RATED, ANNUAL, 'square_feet']:
        if metric not in df:
            continue
        eligible = buildings.loc[numeric_values(buildings[metric]).index]
        top = eligible.sort_values([metric, 'site_id'], ascending=[False, True]).head(10)[columns].copy()
        top.insert(0, 'rank', range(1, len(top) + 1))
        top.insert(0, 'ranking_metric', metric)
        reports.append(top)
    return pd.concat(reports, ignore_index=True) if reports else pd.DataFrame(columns=['ranking_metric', 'rank', *columns])


def main() -> None:
    raw = load_energy_outputs()
    # Report structural counts before raising for bad rows.
    structural = {'site_id', 'site_type', 'energy_estimate_status', 'latitude', 'longitude'}
    if structural.issubset(raw.columns):
        print(pd.Series(structural_counts(raw)).to_string())
    df = validate_structure(raw)
    counts = structural_counts(df)
    statistics = pd.DataFrame({column: describe_numeric(df[column])
                               for column in STAT_COLUMNS if column in df}).T
    statistics.index.name = 'variable'
    flagged, thresholds = add_plausibility_flags(df)
    outliers = top_outliers(df)
    summary = dict(counts)
    for column, suffix in [(RATED, 'rated_it_power_mw'), (ANNUAL, 'annual_energy_mwh'),
                           ('square_feet', 'square_feet')]:
        for statistic in ['median', 'q95', 'max']:
            summary[f'{statistic}_{suffix}'] = statistics.loc[column, statistic] if column in statistics.index else float('nan')
    summary.update(thresholds)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Preserve original cell representations in the row-level report.
    results = raw.copy()
    results['energy_validation_flag'] = flagged.energy_validation_flag
    results.to_csv(OUTPUT_DIR / 'energy_validation_results.csv', index=False)
    outliers.to_csv(OUTPUT_DIR / 'top_energy_outliers.csv', index=False)
    statistics.to_csv(OUTPUT_DIR / 'energy_descriptive_statistics.csv')
    pd.DataFrame(summary.items(), columns=['metric', 'value']).to_csv(OUTPUT_DIR / 'energy_summary.csv', index=False)
    print('\nDescriptive statistics (all finite observations; footprint includes campuses):')
    print(statistics.to_string())
    print('\nThresholds:')
    print(pd.Series(thresholds).to_string())
    print('\nFlag combinations:')
    print(flagged.energy_validation_flag.value_counts().to_string())
    print('\nTen largest rated IT estimates:')
    print(outliers.loc[outliers.ranking_metric.eq(RATED)].to_string(index=False))
    print(f'\nValidation passed. Reports saved to {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
