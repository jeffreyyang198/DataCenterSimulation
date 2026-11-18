"""Labels, units and missing-value formatting shared by views."""
import math
import pandas as pd

METRICS = {
    'crpi_equal': ('Community-resource pressure · CRPI', 'score / 100'),
    'annual_water_footprint_m3': ('Water footprint', 'm³'),
    'annual_water_scarcity_footprint_m3_eq': ('Scarcity-weighted water footprint', 'm³-eq'),
    'median_aqueduct_water_stress': ('Aqueduct water stress', 'ratio'),
    'projected_energy_mwh': ('Electricity demand', 'MWh'),
    'annual_co2_metric_tonnes': ('Annual CO₂', 'tonnes CO₂'),
    'unique_population_within_5km': ('Nearby population · ACS 2023', 'people'),
    'cluster_id': ('Watershed profile cluster', ''),
    'hotspot_category': ('Hotspot trajectory · 2023–2030', ''),
    'scenario_robust': ('Scenario robustness · WSF', ''),
}
TEMPORAL = {k: v for k, v in METRICS.items() if k not in {
    'crpi_equal', 'unique_population_within_5km', 'cluster_id', 'hotspot_category', 'scenario_robust'}}
TEMPORAL.update({
    'cumulative_co2_metric_tonnes': ('Cumulative CO₂ since 2023', 'tonnes CO₂'),
    'annual_direct_water_m3': ('Modeled direct water demand', 'm³'),
    'cumulative_direct_water_m3': ('Cumulative direct water since 2023', 'm³'),
    'median_temperature_mean_c': ('NASA background mean temperature', '°C'),
})
HOTSPOTS = {
    'persistent_hotspot': 'Persistent hotspot', 'emerging_hotspot': 'Emerging hotspot',
    'existing_constrained': 'Existing high burden / lower change',
    'rising_watchlist': 'Rising watchlist', 'lower_pressure': 'Below high-burden cutoffs',
    'not_assessable': 'Insufficient burden data',
}


def number(value, unit=''):
    if value is None or pd.isna(value):
        return 'Not available'
    value = float(value)
    if not math.isfinite(value):
        return 'Not available'
    if unit == 'ratio':
        if value >= 9999:
            return '≥100 (open-ended)'
        return 'Censored / open-ended context' if value >= 100 else f'{value:.3f}'
    if unit == '°C':
        return f'{value:.1f} °C'
    if unit == 'score / 100':
        return f'{value:.1f} / 100'
    if unit == 'MWh' and abs(value) >= 1e6:
        return f'{value / 1e6:,.2f} TWh'
    if unit == 'MWh' and abs(value) >= 1e3:
        return f'{value / 1e3:,.1f} GWh'
    if unit == 'tonnes CO₂' and abs(value) >= 1e6:
        return f'{value / 1e6:,.2f} Mt CO₂'
    scale, suffix = (1e9, 'billion') if abs(value) >= 1e9 else ((1e6, 'million') if abs(value) >= 1e6 else (1, ''))
    text = f'{value / scale:,.2f} {suffix}' if scale > 1 else f'{value:,.0f}'
    return f'{text.strip()} {unit}'.strip()


def effective_metric(metric, year):
    if metric not in METRICS:
        raise ValueError(f'Unsupported map metric: {metric}')
    # Annual CRPI has not been validated. Use a saved annual burden, never invent scores.
    return 'annual_water_scarcity_footprint_m3_eq' if metric == 'crpi_equal' and int(year) != 2030 else metric
